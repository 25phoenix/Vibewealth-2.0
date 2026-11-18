"""C4 only: guarded real PostgreSQL lifecycle, fencing and concurrency tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import time
from threading import Barrier, Event
from types import SimpleNamespace
from uuid import UUID, uuid4

import anyio
import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.assistant_admission import AssistantAdmission
from app.models import AssistantConversation, AssistantMessage, AssistantTurn, AuthSession
from app.schemas.assistant import PersistedFailureCode, ProviderSelection
from app.services import assistant_turns as service
from app.services.assistant_contracts import submission_fingerprint
from app.services.auth_sessions import create_session, revoke_session
from app.api.dependencies import AuthenticatedRequest
from app.services.authentication import get_current_user
from tests.test_assistant_conversations import no_application_database  # noqa: F401
from tests.test_assistant_conversations_postgres import Actor, world  # noqa: F401


# Only the backend-owned bounded executor is accepted by C4 composition.
FakeExecutor = service.TestExecutor

@pytest.fixture
def enabled(world):
    # Explicit test composition. Normal settings/startup never select fake.
    world.app.state.settings = world.app.state.settings.model_copy(update={
        "app_environment": "test", "allow_insecure_cookies": False,
    })
    fake = FakeExecutor()
    world.app.dependency_overrides[service.get_test_executor] = lambda: fake
    yield world, fake
    admission = world.app.state.assistant_admission
    if isinstance(admission, RaceAdmission):
        assert all(ticket.closed for ticket in admission.tickets)
    else:
        assert not admission._active


def path(conversation, turn=None, action=None):
    base = f"/api/assistant/conversations/{conversation}"
    return f"{base}/messages" if turn is None else f"{base}/turns/{turn}" + (f"/{action}" if action else "")


def submit(world, conversation, *, key=None, content="Test input", actor=None):
    with world.client(actor) as client:
        return client.post(path(conversation), json={"content": content},
                           headers={"Idempotency-Key": str(key or uuid4())})


def action(world, conversation, turn, name, expected=1, actor=None):
    with world.client(actor) as client:
        return client.post(path(conversation, turn, name), json={"expected_attempt_no": expected})


def second_session(world):
    with world.factory() as db:
        token, _ = create_session(db, world.first.id)
        db.commit()
    return Actor(world.first.id, token)


def expire(world, turn):
    with world.factory() as db:
        item = db.get(AssistantTurn, turn)
        # Move this attempt's entire test clock window, keeping DB constraints.
        item.created_at -= timedelta(seconds=120)
        item.attempt_started_at -= timedelta(seconds=120)
        item.lease_expires_at = service.now(db) - timedelta(seconds=1)
        db.commit()


def assert_clean_quota(world, count=0):
    admission = world.app.state.assistant_admission
    assert not admission._active
    assert sum(len(events) for events in admission._events.values()) == count


def test_completed_submit_replay_lookup_history_and_user_isolation(enabled):
    world, fake = enabled
    conversation = world.seed_conversation()
    key = uuid4()
    created = submit(world, conversation, key=key, content=" \r\nTest input\r\n ")
    assert created.status_code == 201, created.text
    dto = created.json()
    assert dto["status"] == "completed" and dto["attempt_no"] == 1
    assert dto["user_message"]["content"] == "Test input"
    assert dto["assistant_message"]["content"] == "Test execution completed."
    assert created.headers["cache-control"] == "no-store"
    assert submit(world, conversation, key=key).json() == dto
    assert submit(world, conversation, key=key).status_code == 200
    assert submit(world, conversation, key=key, content="different").json()["code"] == "IDEMPOTENCY_CONFLICT"
    with world.client() as client:
        assert client.get("/api/assistant/turns/by-key", headers={"Idempotency-Key": str(key)}).json() == dto
        assert client.get(path(conversation, dto["id"])).json() == dto
        history = client.get(path(conversation)).json()
        assert [message["sequence_no"] for message in history["items"]] == [1, 2]
        assert all(message["turn"] == {"id": dto["id"], "status": "completed", "attempt_no": 1} for message in history["items"])
    with world.client(world.second) as client:
        assert client.get("/api/assistant/turns/by-key", headers={"Idempotency-Key": str(key)}).status_code == 404
        assert client.get(path(conversation, dto["id"])).status_code == 404
    foreign = world.seed_conversation(world.second)
    assert submit(world, foreign, key=key, actor=world.second).status_code == 201
    assert len(fake.calls) == 2
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantMessage)) == 4
        assert db.scalar(select(func.count()).select_from(AssistantTurn)) == 2


@pytest.mark.parametrize("state,expired", [("pending", True), ("pending", False), ("failed", False)])
def test_unresolved_precedes_disabled_and_exhausted_admission(world, state, expired):
    conversation = world.seed_conversation()
    turn = world.seed_turn(conversation, status=state, expired=expired)
    # Full quota and provider disabled must not conceal existing operation.
    admission = world.app.state.assistant_admission
    for _ in range(8):
        ticket, _ = admission.reserve_quota(world.first.id)
        assert ticket.acquire_capacity()
        ticket.start()
        ticket.close()
    result = submit(world, conversation)
    assert result.status_code == 409
    assert result.json()["code"] == "UNRESOLVED_TURN"
    assert result.json()["current_turn"]["id"] == str(turn)
    assert result.json()["current_turn"]["lease_expired"] == expired


def test_disabled_and_fake_rejection_reserve_nothing(world):
    conversation = world.seed_conversation()
    assert submit(world, conversation).json()["code"] == "PROVIDER_DISABLED"
    fake = FakeExecutor()
    world.app.dependency_overrides[service.get_test_executor] = lambda: fake
    # An override alone in a non-test application cannot enable execution.
    assert submit(world, conversation).json()["code"] == "PROVIDER_CONFIGURATION_INVALID"
    assert not fake.calls
    with pytest.raises(ValueError):
        ProviderSelection(mode="fake", identity=fake.identity)
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantTurn)) == 0
        assert db.scalar(select(func.count()).select_from(AssistantMessage)) == 0
    assert_clean_quota(world)


@pytest.mark.parametrize("outcome", [PersistedFailureCode.PROVIDER_UNAVAILABLE,
    RuntimeError("SECRET raw provider text"), TimeoutError(), "SECRET unrestricted output"])
def test_failure_is_sanitized_and_retry_finalizes_with_200(enabled, outcome):
    world, fake = enabled
    fake.outcome = outcome
    conversation = world.seed_conversation()
    result = submit(world, conversation)
    assert result.status_code == 201 and result.json()["status"] == "failed"
    assert "SECRET" not in result.text
    turn = result.json()["id"]
    again = action(world, conversation, turn, "retry")
    assert again.status_code == 200 and again.json()["status"] == "failed"
    fake.outcome = None
    last = action(world, conversation, turn, "retry", 2)
    assert last.status_code == 200 and last.json()["status"] == "completed"
    assert last.json()["attempt_no"] == 3
    assert last.json()["user_message"]["id"] == result.json()["user_message"]["id"]
    assert action(world, conversation, turn, "retry", 3).status_code == 200
    assert len(fake.calls) == 3


@pytest.mark.parametrize("failure,attempt,code", [
    ("PROVIDER_TIMEOUT", 3, "RETRY_LIMIT_REACHED"),
    ("CONTEXT_LIMIT", 1, "TURN_NOT_RETRYABLE"),
])
def test_retry_limits_and_nonretryable_failures_do_not_consume_attempt(world, failure, attempt, code):
    conversation = world.seed_conversation()
    turn = world.seed_turn(conversation, status="failed", attempt=attempt, failure=failure)
    result = action(world, conversation, turn, "retry", attempt)
    assert result.status_code == 409 and result.json()["code"] == code
    with world.factory() as db:
        assert db.get(AssistantTurn, turn).attempt_no == attempt


def test_abandon_clears_error_retains_context_replays_and_releases_slot(enabled):
    world, fake = enabled
    conversation = world.seed_conversation()
    turn = world.seed_turn(conversation, status="failed")
    result = action(world, conversation, turn, "abandon")
    assert result.status_code == 200
    assert result.json()["status"] == "abandoned" and result.json()["error"] is None
    assert result.json()["context_as_of"] is not None
    assert action(world, conversation, turn, "abandon").json() == result.json()
    assert action(world, conversation, turn, "retry").json()["code"] == "TURN_NOT_RETRYABLE"
    assert action(world, conversation, turn, "abandon", 2).json()["code"] == "ATTEMPT_CONFLICT"
    following = submit(world, conversation)
    assert following.status_code == 201 and following.json()["user_message"]["sequence_no"] == 3
    assert len(fake.calls) == 1


def test_live_pending_replay_202_reads_200_no_dispatch_and_abandon_refusal(enabled):
    world, fake = enabled
    fake.paused = True
    conversation, key = world.seed_conversation(), uuid4()
    other = second_session(world)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(submit, world, conversation, key=key)
        try:
            assert fake.entered.wait(timeout=10)
            duplicate = submit(world, conversation, key=key, actor=other)
            assert duplicate.status_code == 202 and duplicate.headers["retry-after"] == "2"
            turn = duplicate.json()["id"]
            assert action(world, conversation, turn, "retry", actor=other).status_code == 202
            assert action(world, conversation, turn, "abandon", actor=other).json()["code"] == "TURN_NOT_ABANDONABLE"
            with world.client(other) as client:
                for response in (client.get(path(conversation, turn)), client.get(
                        "/api/assistant/turns/by-key", headers={"Idempotency-Key": str(key)})):
                    assert response.status_code == 200 and response.json()["status"] == "pending"
                    assert response.headers["cache-control"] == "no-store"
            assert len(fake.calls) == 1
        finally:
            fake.release.set()
        assert pending.result(timeout=10).status_code == 201


@pytest.mark.parametrize("late_action", ["delete", "revoke", "expire", "retry", "abandon"])
@pytest.mark.parametrize("outcome", [None, PersistedFailureCode.PROVIDER_UNAVAILABLE])
def test_late_result_cannot_overwrite_or_resurrect(enabled, late_action, outcome):
    world, fake = enabled
    fake.paused, fake.outcome = True, outcome
    conversation = world.seed_conversation()
    other = second_session(world)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(submit, world, conversation)
        try:
            assert fake.entered.wait(timeout=10)
            captured = fake.calls[0]
            # Probe all three rows NOWAIT while executor is paused. No DB lock
            # or authentication transaction is allowed to span executor I/O.
            with world.factory() as db:
                session_id = db.scalar(select(AuthSession.id).where(AuthSession.user_id == world.first.id,
                    AuthSession.token_digest == hashlib.sha256(world.first.token.encode()).digest()))
                for model, identifier in ((AuthSession, session_id), (AssistantConversation, conversation), (AssistantTurn, captured.turn_id)):
                    assert db.scalar(select(model.id).where(model.id == identifier).with_for_update(nowait=True)) == identifier
                db.commit()
            if late_action == "delete":
                with world.client(other) as client:
                    assert client.delete(f"/api/assistant/conversations/{conversation}").status_code == 204
            elif late_action == "revoke":
                with world.factory() as db:
                    revoke_session(db, user_id=world.first.id, session_id=session_id)
                    db.commit()
            else:
                expire(world, captured.turn_id)
                if late_action == "retry":
                    # Original execution still owns local capacity; an isolated
                    # test admission instance models a different worker/crash.
                    world.app.state.assistant_admission = AssistantAdmission()
                    world.app.dependency_overrides[service.get_test_executor] = lambda: FakeExecutor()
                    result = action(world, conversation, captured.turn_id, "retry", actor=other)
                    assert result.status_code == 200 and result.json()["attempt_no"] == 2
                elif late_action == "abandon":
                    assert action(world, conversation, captured.turn_id, "abandon", actor=other).status_code == 200
        finally:
            fake.release.set()
        result = pending.result(timeout=10)
    assert result.status_code == (404 if late_action == "delete" else 401 if late_action == "revoke" else 409)
    with world.factory() as db:
        turn = db.get(AssistantTurn, captured.turn_id)
        if late_action == "delete":
            assert turn is None and db.scalar(select(func.count()).select_from(AssistantMessage)) == 0
        elif late_action == "revoke":
            assert turn.status == "failed" and turn.error_code == "SESSION_INVALIDATED"
        elif late_action == "retry":
            assert turn.status == "completed" and turn.attempt_no == 2
        elif late_action == "abandon":
            assert turn.status == "abandoned" and turn.error_code is None
        else:
            assert turn.status == "pending" and turn.attempt_no == 1
        assert db.scalar(select(func.count()).select_from(AssistantMessage).where(AssistantMessage.role == "assistant")) <= 1


class RaceAdmission:
    """Tests deliberately bypass local capacity to exercise DB authority."""
    def __init__(self):
        self.tickets = []

    def reserve_quota(self, user):
        ticket, error = AssistantAdmission().reserve_quota(user)
        self.tickets.append(ticket)
        return ticket, error


def test_cross_conversation_same_user_key_real_constraint_recovery(enabled, monkeypatch):
    world, fake = enabled
    conversations = [world.seed_conversation(), world.seed_conversation()]
    other, key, barrier = second_session(world), uuid4(), Barrier(2)
    admission = RaceAdmission()
    world.app.state.assistant_admission = admission
    insert, recover = service._new_turn, service._recover
    observed = []

    def synchronized(*args, **kwargs):
        barrier.wait(timeout=10)
        return insert(*args, **kwargs)

    def recovery(db, *args):
        assert not db.in_transaction()
        observed.append(args[-1])
        return recover(db, *args)

    monkeypatch.setattr(service, "_new_turn", synchronized)
    monkeypatch.setattr(service, "_recover", recovery)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit, world, conversation, key=key, actor=actor)
                   for conversation, actor in zip(conversations, (world.first, other))]
        responses = [future.result(timeout=20) for future in futures]
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert next(response for response in responses if response.status_code == 409).json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert observed == ["uq_assistant_turns_user_key"] and len(fake.calls) == 1
    assert all(ticket.closed for ticket in admission.tickets)
    assert sum(ticket.started for ticket in admission.tickets) == 1
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantTurn)) == 1
        assert db.scalar(select(func.count()).select_from(AssistantMessage).where(AssistantMessage.role == "user")) == 1


@pytest.mark.parametrize("same_key,same_content", [(True, True), (True, False), (False, True)])
def test_same_conversation_concurrent_reservation_has_one_execution(enabled, same_key, same_content):
    world, fake = enabled
    conversation, other, key = world.seed_conversation(), second_session(world), uuid4()
    start = Barrier(2)
    def send(actor, operation_key, content):
        start.wait(timeout=10)
        return submit(world, conversation, actor=actor, key=operation_key, content=content)
    # Keep the accepted turn unresolved regardless of scheduling.
    fake.outcome = PersistedFailureCode.PROVIDER_UNAVAILABLE
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(send, world.first, key, "Test input"), executor.submit(
            send, other, key if same_key else uuid4(), "Test input" if same_content else "Other input")]
        responses = [future.result(timeout=20) for future in futures]
    assert sum(response.status_code == 201 for response in responses) == 1
    loser = next(response for response in responses if response.status_code != 201)
    assert loser.status_code in ({200, 202} if same_key and same_content else {409})
    if loser.status_code == 409:
        assert loser.json()["code"] == ("IDEMPOTENCY_CONFLICT" if same_key else "UNRESOLVED_TURN")
    assert len(fake.calls) == 1


@pytest.mark.parametrize("constraint", ["key", "unresolved", "unrelated", "winner_deleted", "winner_deleted_after_lookup", "blocking_resolved", "blocking_disappeared"])
def test_named_constraint_recovery_and_winner_deleted(enabled, monkeypatch, constraint):
    world, fake = enabled
    winner_conversation = world.seed_conversation()
    winner = world.seed_turn(winner_conversation, status="failed")
    partial = constraint in {"unresolved", "blocking_resolved", "blocking_disappeared"}
    conversation = winner_conversation if partial else world.seed_conversation()
    with world.factory() as db:
        existing = db.get(AssistantTurn, winner)
        key = existing.idempotency_key
        existing.request_fingerprint = submission_fingerprint(conversation, "Test input")
        db.commit()
    lookup = service.unresolved if partial else service.by_key
    calls = []
    def miss_twice(*args):
        calls.append(True)
        if len(calls) <= 2:
            return None
        result = lookup(*args)
        if constraint == "winner_deleted_after_lookup":
            with world.factory() as other:
                other.execute(delete(AssistantConversation).where(AssistantConversation.id == winner_conversation))
                other.commit()
        return result
    monkeypatch.setattr(service, "unresolved" if partial else "by_key", miss_twice)
    if partial:
        key = uuid4()
    original = service._recover
    def recovery(db, *args):
        assert not db.in_transaction()
        if constraint == "winner_deleted":
            with world.factory() as other:
                other.execute(delete(AssistantConversation).where(AssistantConversation.id == winner_conversation))
                other.commit()
        if constraint in {"blocking_resolved", "blocking_disappeared"}:
            with world.factory() as other:
                blocking = other.get(AssistantTurn, winner)
                if constraint == "blocking_disappeared":
                    other.delete(blocking)
                else:
                    blocking.status, blocking.error_code = "abandoned", None
                other.commit()
        return original(db, *args)
    monkeypatch.setattr(service, "_recover", recovery)
    if constraint == "unrelated":
        original_insert = service._new_turn
        def invalid(db, *args):
            turn = original_insert(db, *args)
            turn.attempt_no = 4
            db.flush()
            return turn
        monkeypatch.setattr(service, "_new_turn", invalid)
        key = uuid4()
    result = submit(world, conversation, key=key)
    assert result.status_code == {"key": 200, "unresolved": 409, "unrelated": 500, "winner_deleted": 404, "winner_deleted_after_lookup": 404, "blocking_resolved": 409, "blocking_disappeared": 409}[constraint], result.text
    if constraint != "key":
        assert result.json()["code"] == {"unresolved": "UNRESOLVED_TURN", "unrelated": "INTERNAL_ERROR", "winner_deleted": "TURN_NOT_FOUND", "winner_deleted_after_lookup": "TURN_NOT_FOUND", "blocking_resolved": "ATTEMPT_CONFLICT", "blocking_disappeared": "ATTEMPT_CONFLICT"}[constraint]
    if constraint in {"blocking_resolved", "blocking_disappeared"}:
        assert result.json()["current_turn"] is None
    assert not fake.calls
    assert_clean_quota(world)


def test_retry_concurrency_clears_interruption_and_stale_abandon_conflicts(enabled):
    world, fake = enabled
    fake.paused = True
    conversation = world.seed_conversation()
    turn = world.seed_turn(conversation, expired=True)
    other = second_session(world)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(action, world, conversation, turn, "retry")
        try:
            assert fake.entered.wait(timeout=10)
            duplicate = action(world, conversation, turn, "retry", actor=other)
            assert duplicate.status_code == 202
            assert duplicate.json()["attempt_no"] == 2 and not duplicate.json()["lease_expired"]
            assert duplicate.json()["error"] is None and duplicate.json()["attempt_finished_at"] is None
            assert action(world, conversation, turn, "abandon", actor=other).json()["code"] == "ATTEMPT_CONFLICT"
            assert action(world, conversation, turn, "retry", 3, actor=other).json()["code"] == "ATTEMPT_CONFLICT"
        finally:
            fake.release.set()
        assert first.result(timeout=10).status_code == 200
    assert len(fake.calls) == 1
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantMessage).where(AssistantMessage.role == "user")) == 1


@pytest.mark.parametrize("refusal", ["disabled", "rate", "capacity"])
def test_retry_admission_refusal_does_not_increment_attempt(enabled, refusal):
    world, fake = enabled
    conversation = world.seed_conversation()
    turn = world.seed_turn(conversation, status="failed")
    held = None
    admission = world.app.state.assistant_admission
    if refusal == "disabled":
        world.app.dependency_overrides.pop(service.get_test_executor)
    if refusal == "rate":
        for _ in range(8):
            ticket, _ = admission.reserve_quota(world.first.id)
            assert ticket.acquire_capacity()
            ticket.start()
            ticket.close()
    if refusal == "capacity":
        held, _ = admission.reserve_quota(world.first.id)
        assert held.acquire_capacity()
    try:
        result = action(world, conversation, turn, "retry")
        assert result.status_code == (503 if refusal == "disabled" else 429)
        assert result.json()["code"] == {"disabled": "PROVIDER_DISABLED", "rate": "RATE_LIMITED", "capacity": "GENERATION_BUSY"}[refusal]
        if refusal != "disabled":
            assert int(result.headers["retry-after"]) >= 1
    finally:
        if held:
            held.close()
    assert not fake.calls
    with world.factory() as db:
        assert db.get(AssistantTurn, turn).attempt_no == 1


@pytest.mark.parametrize("bound", ["turns", "sequence"])
def test_turn_and_sequence_limits(enabled, bound):
    world, fake = enabled
    conversation = world.seed_conversation()
    with world.factory() as db:
        stamp = service.now(db)
        if bound == "sequence":
            db.add(AssistantMessage(user_id=world.first.id, conversation_id=conversation,
                                    sequence_no=2**31-1, role="user", content="Legacy input"))
        else:
            for i in range(1000):
                db.add(AssistantMessage(user_id=world.first.id, conversation_id=conversation,
                                        sequence_no=i*2+1, role="user", content="Test input"))
            db.flush()
            for i in range(1000):
                db.add(AssistantTurn(user_id=world.first.id, conversation_id=conversation,
                    idempotency_key=uuid4(), request_fingerprint=b"x"*32, user_sequence_no=i*2+1,
                    status="abandoned", attempt_no=1, created_at=stamp, attempt_started_at=stamp,
                    attempt_finished_at=stamp, provider_kind="fake", model_name="test-only", contract_version=1))
        db.commit()
    result = submit(world, conversation)
    assert result.status_code == 409 and result.json()["code"] == "TURN_LIMIT_REACHED"
    assert not fake.calls
    assert_clean_quota(world)


@pytest.mark.parametrize("headers", [[], [("Idempotency-Key", "bad")],
    [("Idempotency-Key", str(uuid4())), ("idempotency-key", str(uuid4()))],
    [("Idempotency-Key", str(uuid4()) + "," + str(uuid4()))]])
def test_raw_header_validation_identical_for_submit_and_lookup(enabled, headers):
    world, fake = enabled
    conversation = world.seed_conversation()
    with world.client() as client:
        for response in (client.post(path(conversation), json={"content": "Test input"}, headers=headers),
                         client.get("/api/assistant/turns/by-key", headers=headers)):
            assert response.status_code == 422 and response.json()["code"] == "INVALID_REQUEST"
            assert response.headers["cache-control"] == "no-store"
    assert not fake.calls


def test_atomic_admission_refunds_provisional_and_retains_real_starts():
    clock = [0.0]
    admission = AssistantAdmission(clock=lambda: clock[0])
    tickets = [admission.reserve_quota("owner")[0] for _ in range(8)]
    assert admission.reserve_quota("owner") == (None, 60)
    assert tickets[0].acquire_capacity()
    assert not tickets[1].acquire_capacity()
    other, _ = admission.reserve_quota("other")
    assert other.acquire_capacity()
    third, _ = admission.reserve_quota("third")
    assert not third.acquire_capacity()
    for ticket in tickets[1:] + [third]:
        ticket.close()
    tickets[0].start()
    tickets[0].close()
    other.close()
    assert not admission._active and len(admission._events["owner"]) == 1
    with pytest.raises(RuntimeError):
        tickets[0].close()
    clock[0] = 60
    assert admission.reserve_quota("owner")[0] is not None


@pytest.mark.parametrize("fence_order", ["revoke_before_fence", "revoke_after_fence"])
def test_dispatch_logout_order_and_completion_fence(enabled, monkeypatch, fence_order):
    world, fake = enabled
    conversation = world.seed_conversation()
    fence = service.dispatch_fence
    seen = []

    def revoke():
        with world.factory() as db:
            session_id = db.scalar(select(AuthSession.id).where(AuthSession.user_id == world.first.id))
            revoke_session(db, user_id=world.first.id, session_id=session_id)
            db.commit()

    def ordered(db, authenticated, attempt):
        assert not db.in_transaction()
        if fence_order == "revoke_before_fence":
            revoke()
        fence(db, authenticated, attempt)
        assert not db.in_transaction()
        seen.append(True)
        if fence_order == "revoke_after_fence":
            revoke()

    monkeypatch.setattr(service, "dispatch_fence", ordered)
    result = submit(world, conversation)
    assert result.status_code == 401 and result.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert len(fake.calls) == (0 if fence_order == "revoke_before_fence" else 1)
    assert len(seen) == len(fake.calls)
    with world.factory() as db:
        turn = db.scalar(select(AssistantTurn))
        assert turn.status == "failed" and turn.error_code == "SESSION_INVALIDATED"
        assert db.scalar(select(func.count()).select_from(AssistantMessage).where(AssistantMessage.role == "assistant")) == 0
    assert_clean_quota(world, len(fake.calls))


@pytest.mark.parametrize("replacement", ["retry", "abandon", "delete"])
def test_invalid_session_cleanup_cannot_overwrite_newer_or_removed_attempt(enabled, replacement):
    world, fake = enabled
    fake.paused = True
    conversation = world.seed_conversation()
    other = second_session(world)
    original_admission = world.app.state.assistant_admission
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(submit, world, conversation)
        try:
            assert fake.entered.wait(timeout=10)
            attempt = fake.calls[0]
            expire(world, attempt.turn_id)
            if replacement == "retry":
                world.app.state.assistant_admission = AssistantAdmission()
                world.app.dependency_overrides[service.get_test_executor] = lambda: FakeExecutor()
                assert action(world, conversation, attempt.turn_id, "retry", actor=other).status_code == 200
            elif replacement == "abandon":
                assert action(world, conversation, attempt.turn_id, "abandon", actor=other).status_code == 200
            else:
                with world.client(other) as client:
                    assert client.delete(f"/api/assistant/conversations/{conversation}").status_code == 204
            with world.factory() as db:
                session_id = db.scalar(select(AuthSession.id).where(
                    AuthSession.user_id == world.first.id,
                    AuthSession.token_digest == hashlib.sha256(world.first.token.encode()).digest()))
                revoke_session(db, user_id=world.first.id, session_id=session_id)
                db.commit()
        finally:
            fake.release.set()
        assert pending.result(timeout=10).status_code == 401
    assert not original_admission._active
    with world.factory() as db:
        turn = db.get(AssistantTurn, attempt.turn_id)
        if replacement == "delete":
            assert turn is None
        elif replacement == "retry":
            assert turn.attempt_no == 2 and turn.status == "completed" and turn.error_code is None
        else:
            assert turn.status == "abandoned" and turn.error_code is None


def test_generation_capacity_is_atomic_for_simultaneous_contenders():
    admission = AssistantAdmission()
    start, acquired = Barrier(24), Barrier(24)
    def contend(number):
        ticket, error = admission.reserve_quota(number % 3)
        assert error is None
        start.wait(timeout=10)
        success = ticket.acquire_capacity()
        acquired.wait(timeout=10)  # Keep every acquired token until all tried.
        ticket.close()
        return number % 3, success
    with ThreadPoolExecutor(max_workers=24) as executor:
        results = list(executor.map(contend, range(24)))
    accepted = [owner for owner, success in results if success]
    assert len(accepted) == 2 and len(set(accepted)) == 2
    assert not admission._active
    assert not any(admission._events.values())


@pytest.mark.parametrize("endpoint", ["submit", "retry", "abandon"])
def test_c4_writes_keep_csrf_origin_and_owner_isolation(enabled, endpoint):
    world, fake = enabled
    conversation = world.seed_conversation()
    turn = world.seed_turn(conversation, status="failed") if endpoint != "submit" else None
    url = path(conversation) if turn is None else path(conversation, turn, endpoint)
    payload = {"content": "Test input"} if turn is None else {"expected_attempt_no": 1}
    with world.client() as client:
        for headers, code in (({"X-CSRF-Token": "invalid"}, "CSRF_FAILED"),
                              ({"Origin": "http://evil.test"}, "ORIGIN_REJECTED")):
            result = client.post(url, json=payload, headers={"Idempotency-Key": str(uuid4()), **headers})
            assert result.status_code == 403 and result.json()["code"] == code
            assert result.headers["cache-control"] == "no-store"
    with world.client(world.second) as client:
        result = client.post(url, json=payload, headers={"Idempotency-Key": str(uuid4())})
        assert result.status_code == 404
    assert not fake.calls


def test_retry_resets_context_before_dispatch_and_disabled_replay_still_works(enabled, monkeypatch):
    world, fake = enabled
    conversation = world.seed_conversation()
    turn = world.seed_turn(conversation, status="failed")
    fence = service.dispatch_fence
    def inspect(db, authenticated, attempt):
        with world.factory() as other:
            pending = other.get(AssistantTurn, turn)
            assert pending.attempt_no == 2 and pending.status == "pending"
            assert pending.context_as_of is None and pending.financial_date is None
            assert pending.attempt_finished_at is None and pending.error_code is None
            assert pending.lease_expires_at > service.now(other)
        return fence(db, authenticated, attempt)
    monkeypatch.setattr(service, "dispatch_fence", inspect)
    result = action(world, conversation, turn, "retry")
    assert result.status_code == 200
    key = result.json()["idempotency_key"]
    world.app.dependency_overrides.pop(service.get_test_executor)
    # Seed helper content matches this exact normalized replay.
    with world.factory() as db:
        existing = db.get(AssistantTurn, turn)
        existing.request_fingerprint = submission_fingerprint(conversation, "Show my recorded budgets")
        db.commit()
    replay = submit(world, conversation, key=key, content="Show my recorded budgets")
    assert replay.status_code == 200 and replay.json() == result.json()
    assert len(fake.calls) == 1


def test_request_cancellation_releases_capacity_leaves_durable_pending_for_explicit_retry(enabled):
    world, _ = enabled
    conversation = world.seed_conversation()
    fake = FakeExecutor(paused=True)
    async def interrupted():
        with anyio.CancelScope() as scope:
            def authenticate(db):
                current = get_current_user(db, session_token=world.first.token)
                db.commit()
                return AuthenticatedRequest(current, world.first.token)
            database = world.app.state.assistant_database
            authenticated = await database.run(authenticate, deadline=time.monotonic()+60)
            async def request():
                await service.generate(database, authenticated, conversation,
                    admission=world.app.state.assistant_admission, executor=fake,
                    test_environment=True, deadline=time.monotonic()+60, key=uuid4(), content="Test input")
            async with anyio.create_task_group() as group:
                group.start_soon(request)
                await fake.entered.wait_until(time.monotonic()+5)
                scope.cancel()
    anyio.run(interrupted)
    assert fake.cancelled.is_set() and fake.terminated.is_set()
    assert_clean_quota(world, 1)  # Invocation started; quota retained despite cancellation.
    with world.factory() as db:
        turn = db.scalar(select(AssistantTurn))
        assert turn.status == "pending" and turn.attempt_no == 1
        identifier = turn.id
    assert action(world, conversation, identifier, "retry").status_code == 202
    expire(world, identifier)
    retried = action(world, conversation, identifier, "retry")
    assert retried.status_code == 200 and retried.json()["status"] == "completed"


def test_session_cleanup_storage_failure_keeps_401_and_pending_recovery(enabled, monkeypatch):
    world, fake = enabled
    conversation = world.seed_conversation()
    fence = service.dispatch_fence
    def revoke_before_fence(db, authenticated, attempt):
        with world.factory() as other:
            revoke_session(other, user_id=world.first.id, session_id=authenticated.current_user.session_id)
            other.commit()
        return fence(db, authenticated, attempt)
    def storage_failure(*args):
        raise SQLAlchemyError("SECRET SQL diagnostic")
    monkeypatch.setattr(service, "dispatch_fence", revoke_before_fence)
    monkeypatch.setattr(service, "_fail", storage_failure)
    events = []
    # Migration fixture logging configuration can disable preexisting loggers;
    # assert the exact logging call without changing that shared configuration.
    monkeypatch.setattr(service.logger, "warning", events.append)
    result = submit(world, conversation)
    assert result.status_code == 401 and "SECRET" not in result.text
    assert events == ["assistant_session_cleanup_failed"]
    assert not fake.calls
    assert_clean_quota(world)
    with world.factory() as db:
        assert db.scalar(select(AssistantTurn)).status == "pending"


def test_simultaneous_retry_claims_after_both_initial_reads_execute_once(enabled):
    world, fake = enabled
    fake.outcome = PersistedFailureCode.PROVIDER_UNAVAILABLE
    conversation = world.seed_conversation()
    turn = world.seed_turn(conversation, status="failed")
    other = second_session(world)
    barrier = Barrier(2)
    class RetryRaceAdmission(RaceAdmission):
        def reserve_quota(self, user):
            result = super().reserve_quota(user)
            # Both first-stage reads committed before either second claim.
            barrier.wait(timeout=10)
            return result
    admission = RetryRaceAdmission()
    world.app.state.assistant_admission = admission
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(action, world, conversation, turn, "retry", actor=actor)
                   for actor in (world.first, other)]
        results = [future.result(timeout=20) for future in futures]
    assert all(result.status_code in {200, 202} and result.json()["attempt_no"] == 2 for result in results)
    assert len(fake.calls) == 1
    assert sum(ticket.started for ticket in admission.tickets) == 1
    with world.factory() as db:
        assert db.get(AssistantTurn, turn).attempt_no == 2
        assert db.scalar(select(func.count()).select_from(AssistantMessage)) == 1


def test_simultaneous_abandon_and_retry_cannot_abandon_new_attempt(enabled):
    world, fake = enabled
    conversation = world.seed_conversation()
    turn = world.seed_turn(conversation, status="failed")
    other, start = second_session(world), Barrier(2)
    def send(name, actor):
        start.wait(timeout=10)
        return action(world, conversation, turn, name, actor=actor)
    with ThreadPoolExecutor(max_workers=2) as executor:
        retried = executor.submit(send, "retry", world.first)
        abandoned = executor.submit(send, "abandon", other)
        retry_result, abandon_result = retried.result(timeout=20), abandoned.result(timeout=20)
    with world.factory() as db:
        persisted = db.get(AssistantTurn, turn)
        if abandon_result.status_code == 200:
            assert persisted.status == "abandoned" and persisted.attempt_no == 1
            assert retry_result.status_code == 409 and retry_result.json()["code"] == "TURN_NOT_RETRYABLE"
            assert not fake.calls
        else:
            assert abandon_result.status_code == 409 and abandon_result.json()["code"] == "ATTEMPT_CONFLICT"
            assert retry_result.status_code == 200
            assert persisted.status == "completed" and persisted.attempt_no == 2
            assert len(fake.calls) == 1


@pytest.mark.parametrize("phase", ["reservation", "dispatch_fence"])
def test_expired_work_budget_never_starts_execution_and_refunds_quota(enabled, monkeypatch, phase):
    world, fake = enabled
    conversation = world.seed_conversation()
    clock = [time.monotonic()]
    monkeypatch.setattr(service, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    original = service._new_turn if phase == "reservation" else service.dispatch_fence
    def consume_budget(*args, **kwargs):
        result = original(*args, **kwargs)
        clock[0] += 61
        return result
    monkeypatch.setattr(service, "_new_turn" if phase == "reservation" else "dispatch_fence", consume_budget)
    result = submit(world, conversation)
    assert result.status_code == 503 and result.json()["code"] == "WORK_DEADLINE_EXCEEDED"
    assert not fake.calls
    assert_clean_quota(world)
    with world.factory() as db:
        pending = db.scalar(select(AssistantTurn))
        assert pending.status == "pending" and pending.attempt_no == 1
