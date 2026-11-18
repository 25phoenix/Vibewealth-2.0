"""Real PostgreSQL deadline, thread ownership and single-loop ASGI tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import asyncio
import hashlib
import json
from threading import Event, get_ident
import time
from types import SimpleNamespace
from uuid import uuid4

import anyio
import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import Engine

from app.api import assistant_http
from app.api.dependencies import create_csrf_token
from app.models import AssistantConversation, AssistantMessage, AssistantTurn, AuthSession
from app.services import assistant_turns as service
from app.services.auth_sessions import revoke_session

from tests.test_assistant_turn_lifecycle import enabled, world, no_application_database  # noqa: F401


def test_database_phase_owns_worker_and_protocol_waits(enabled, monkeypatch):
    world, _ = enabled
    from app.core import assistant_database
    original = assistant_database.DeadlineSession
    closed = []
    class OwnedSession(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.owner_thread = get_ident()
        def close(self):
            assert get_ident() == self.owner_thread
            closed.append(get_ident())
            super().close()
    monkeypatch.setattr(assistant_database, "DeadlineSession", OwnedSession)
    async def run():
        loop_thread = get_ident()
        def query(db):
            owner = get_ident()
            assert owner != loop_thread
            assert db.scalar(select(1)) == 1
            db.commit()
            assert get_ident() == owner
            return owner
        return await world.app.state.assistant_database.run(query, deadline=time.monotonic() + 10)
    worker = anyio.run(run)
    assert worker != get_ident() and closed == [worker]


async def asgi_request(world, path, *, body=None, method="POST", disconnect=None, done=None, key=None):
    settings = world.app.state.settings
    wire = json.dumps(body).encode() if body is not None else b""
    supplied = False
    messages = []
    async def receive():
        nonlocal supplied
        if not supplied:
            supplied = True
            return {"type": "http.request", "body": wire, "more_body": False}
        if disconnect is not None:
            # Match the server receive path: an already queued disconnect is
            # available immediately, rather than adding an artificial yield.
            if not disconnect.is_set():
                await disconnect.wait()
            return {"type": "http.disconnect"}
        await anyio.sleep_forever()
    async def send(message):
        messages.append(message)
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "server": ("localhost", 8000),
        "client": ("127.0.0.1", 12345), "headers": [
            (b"host", b"localhost:8000"), (b"origin", b"http://localhost:5173"),
            (b"content-type", b"application/json"), (b"idempotency-key", str(key or uuid4()).encode()),
            (b"x-csrf-token", create_csrf_token(world.first.token, settings).encode()),
            (b"cookie", (settings.auth_cookie_name + "=" + world.first.token).encode()),
        ],
    }
    await world.app(scope, receive, send)
    if done is not None:
        done.set()
    return messages


def response(messages):
    start = next(item for item in messages if item["type"] == "http.response.start")
    body = b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body")
    assert dict(start["headers"])[b"cache-control"] == b"no-store"
    return start["status"], json.loads(body) if body else None


@contextmanager
def blocker(world, sql, parameters=None, *, deferred=False):
    """Only its dedicated worker owns this independent blocking transaction."""
    begin, ready, release = Event(), Event(), Event()
    schema = world.factory.kw["bind"].get_execution_options()["schema_translate_map"][None]
    for table in ("auth_sessions", "assistant_conversations"):
        sql = sql.replace(f"FROM {table}", f'FROM "{schema}".{table}')
    if not deferred:
        begin.set()
    def hold():
        assert begin.wait(timeout=10)
        with world.factory() as db:
            db.execute(text(sql), parameters or {})
            ready.set()
            assert release.wait(timeout=10)
            db.rollback()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold)
        try:
            if not deferred:
                assert ready.wait(timeout=10)
            yield begin, ready, release
        finally:
            begin.set()
            release.set()
            future.result(timeout=10)


def session_id(world):
    with world.factory() as db:
        return db.scalar(select(AuthSession.id).where(
            AuthSession.token_digest == hashlib.sha256(world.first.token.encode()).digest()))


def test_one_asgi_loop_progresses_while_authentication_waits_on_session_lock(enabled, monkeypatch):
    world, _ = enabled
    conversation = world.seed_conversation()
    entered = Event()
    armed = Event()
    def before(conn, cursor, statement, parameters, context, executemany):
        if armed.is_set() and statement.lstrip().lower().startswith("update") and "auth_sessions" in statement:
            entered.set()
    event.listen(Engine, "before_cursor_execute", before)
    try:
        with blocker(world, "SELECT id FROM auth_sessions WHERE id=:id FOR UPDATE",
                     {"id": session_id(world)}, deferred=True) as (begin, ready, release):
            fence = service.dispatch_fence
            def blocked_fence(db, *args):
                # Block revalidation AFTER reservation, not merely the initial
                # FastAPI auth dependency (which was already thread-offloaded).
                begin.set()
                assert ready.wait(timeout=5)
                armed.set()
                return fence(db, *args)
            monkeypatch.setattr(service, "dispatch_fence", blocked_fence)
            async def run():
                done, results = anyio.Event(), []
                async def request():
                    results.append(await asgi_request(world,
                        f"/api/assistant/conversations/{conversation}/messages",
                        body={"content": "Test input"}, done=done))
                async with anyio.create_task_group() as group:
                    group.start_soon(request)
                    assert await anyio.to_thread.run_sync(lambda: entered.wait(timeout=5))
                    # The holder still owns the exact session row, so its UPDATE
                    # cannot complete until this event-loop continuation runs.
                    assert not done.is_set()
                    health = await asgi_request(world, "/health", method="GET")
                    assert next(item for item in health if item["type"] == "http.response.start")["status"] == 200
                    assert not done.is_set()  # concurrent HTTP request progressed on THIS loop
                    release.set()
                return response(results[0])
            assert anyio.run(run)[0] == 201
    finally:
        event.remove(Engine, "before_cursor_execute", before)


def PausedExecutor():
    return service.TestExecutor(paused=True)


@pytest.mark.parametrize("phase", ["reservation", "completion", "cleanup"])
def test_blocked_database_phases_obey_absolute_budget_and_remain_recoverable(enabled, monkeypatch, phase):
    world, _ = enabled
    monkeypatch.setattr(assistant_http, "WORK_DEADLINE_SECONDS", 1.0)  # reduce, never raise the contract cap
    conversation = world.seed_conversation()
    database = world.app.state.assistant_database
    if phase == "cleanup":
        sql, parameters = "SELECT id FROM assistant_conversations WHERE id=:id FOR UPDATE", {"id": conversation}
    else:
        # SHARE blocks INSERT, while reads and initial admission remain possible.
        schema = world.factory.kw["bind"].get_execution_options()["schema_translate_map"][None]
        sql, parameters = f'LOCK TABLE "{schema}".assistant_messages IN SHARE MODE', {}
    with blocker(world, sql, parameters, deferred=phase != "reservation") as (begin, ready, release):
        async def run():
            fake, messages = PausedExecutor(), []
            world.app.dependency_overrides[service.get_test_executor] = lambda: fake
            async def request():
                messages.extend(await asgi_request(world,
                    f"/api/assistant/conversations/{conversation}/messages", body={"content": "Test input"}))
            started = time.monotonic()
            async with anyio.create_task_group() as group:
                group.start_soon(request)
                if phase != "reservation":
                    await fake.entered.wait_until(time.monotonic()+5)
                    if phase == "cleanup":
                        def revoke():
                            with world.factory() as db:
                                revoke_session(db, user_id=world.first.id, session_id=session_id(world))
                                db.commit()
                        await anyio.to_thread.run_sync(revoke)
                    begin.set()
                    assert await anyio.to_thread.run_sync(lambda: ready.wait(timeout=5))
                    fake.release.set()
            assert time.monotonic() - started < 1.8
            assert not world.app.state.assistant_admission._active
            return response(messages), fake
        (status, payload), fake = anyio.run(run)
    assert status == (401 if phase == "cleanup" else 503), payload
    assert payload["code"] == ("AUTHENTICATION_REQUIRED" if phase == "cleanup" else "WORK_DEADLINE_EXCEEDED")
    with world.factory() as db:
        turns = db.scalars(select(AssistantTurn)).all()
        assert len(turns) == (0 if phase == "reservation" else 1)
        assert all(turn.status == "pending" for turn in turns)
        assert db.scalar(select(func.count()).select_from(AssistantMessage).where(AssistantMessage.role == "assistant")) == 0
    events = world.app.state.assistant_admission._events
    assert sum(len(value) for value in events.values()) == (0 if phase == "reservation" else 1)


def test_actual_http_disconnect_joins_executor_before_releasing_capacity(enabled):
    world, _ = enabled
    conversation = world.seed_conversation()
    async def run():
        disconnect, messages = anyio.Event(), []
        fake = service.TestExecutor(paused=True, shutdown_blocked=True)
        world.app.dependency_overrides[service.get_test_executor] = lambda: fake
        async def request():
            messages.extend(await asgi_request(world,
                f"/api/assistant/conversations/{conversation}/messages", body={"content": "Test input"},
                disconnect=disconnect))
        async with anyio.create_task_group() as group:
            group.start_soon(request)
            await fake.entered.wait_until(time.monotonic()+5)
            disconnect.set()
            await fake.cancelled.wait_until(time.monotonic()+5)
            assert world.app.state.assistant_admission._active
            assert not messages
            fake.shutdown.set()
        assert fake.terminated.is_set()
        assert not world.app.state.assistant_admission._active
        return messages
    messages = anyio.run(run)
    assert response(messages)[0] == 503
    with world.factory() as db:
        assert db.scalar(select(AssistantTurn)).status == "pending"
        assert db.scalar(select(func.count()).select_from(AssistantMessage)) == 1
    assert sum(len(value) for value in world.app.state.assistant_admission._events.values()) == 1


def test_queued_disconnect_before_invocation_refunds_provisional_quota(enabled):
    world, fake = enabled
    conversation = world.seed_conversation()
    async def run():
        disconnect = anyio.Event()
        disconnect.set()
        return await asgi_request(world,
            f"/api/assistant/conversations/{conversation}/messages", body={"content": "Test input"},
            disconnect=disconnect)
    assert response(anyio.run(run))[0] == 503
    assert not fake.calls and not world.app.state.assistant_admission._active
    assert not any(world.app.state.assistant_admission._events.values())
    with world.factory() as db:
        # The operation-wide monitor now observes an already queued disconnect
        # before reservation, rather than waiting until provider invocation.
        assert db.scalar(select(func.count()).select_from(AssistantTurn)) == 0


def test_completion_fence_commit_first_is_not_retracted_by_logout(enabled, monkeypatch):
    world, _ = enabled
    conversation = world.seed_conversation()
    committed, release = Event(), Event()
    complete = service.complete
    def commit_first(db, *args):
        dto = complete(db, *args)
        assert not db.in_transaction()
        committed.set()
        assert release.wait(timeout=10)
        return dto
    monkeypatch.setattr(service, "complete", commit_first)
    async def run():
        messages = []
        async def request():
            messages.extend(await asgi_request(world,
                f"/api/assistant/conversations/{conversation}/messages", body={"content": "Test input"}))
        async with anyio.create_task_group() as group:
            group.start_soon(request)
            try:
                assert await anyio.to_thread.run_sync(lambda: committed.wait(timeout=5))
                # Same ASGI loop and exact original session; logout can acquire
                # its row after completion's commit, with no retraction claim.
                logout = await asgi_request(world, "/api/auth/logout")
                assert response(logout)[0] == 204
            finally:
                release.set()
        return response(messages)
    status, dto = anyio.run(run)
    assert status == 201 and dto["status"] == "completed"
    with world.factory() as db:
        assert db.scalar(select(AssistantTurn)).status == "completed"


def test_two_second_lock_limit_is_independent_of_longer_work_budget(enabled):
    world, _ = enabled
    from app.services.assistant_contracts import ContractViolation
    from app.schemas.assistant import HttpErrorCode
    identifier = session_id(world)
    with blocker(world, "SELECT id FROM auth_sessions WHERE id=:id FOR UPDATE", {"id": identifier}):
        async def run():
            started = time.monotonic()
            with pytest.raises(ContractViolation) as caught:
                await world.app.state.assistant_database.run(lambda db: db.scalar(
                    select(AuthSession.id).where(AuthSession.id == identifier).with_for_update()),
                    deadline=started + 10)
            assert caught.value.code == HttpErrorCode.WORK_DEADLINE_EXCEEDED
            assert time.monotonic() - started < 3.0
        anyio.run(run)


def test_assistant_csrf_adapter_delegates_to_existing_dependency(monkeypatch):
    from app.api import assistant_dependencies
    calls = []
    request, authenticated, settings = object(), object(), object()
    def existing(*args):
        calls.append(args)
        return authenticated
    monkeypatch.setattr(assistant_dependencies, "require_csrf", existing)
    assert assistant_dependencies.assistant_csrf(request, "supplied", authenticated, settings) is authenticated
    assert calls == [(request, "supplied", authenticated, settings)]


@pytest.mark.parametrize("disconnect_during_run", [True, False])
def test_shutdown_stays_blocked_until_original_deadline_and_terminates_before_capacity_release(
    enabled, monkeypatch, disconnect_during_run,
):
    world, _ = enabled
    monkeypatch.setattr(assistant_http, "WORK_DEADLINE_SECONDS", 0.8)
    conversation, key = world.seed_conversation(), uuid4()
    async def run():
        fake = service.TestExecutor(paused=disconnect_during_run, shutdown_blocked=True)
        world.app.dependency_overrides[service.get_test_executor] = lambda: fake
        disconnect, messages = anyio.Event(), []
        async def request():
            messages.extend(await asgi_request(world,
                f"/api/assistant/conversations/{conversation}/messages", body={"content": "Test input"},
                disconnect=disconnect, key=key))
        started = time.monotonic()
        async with anyio.create_task_group() as group:
            group.start_soon(request)
            await fake.entered.wait_until(started+5)
            if disconnect_during_run:
                disconnect.set()
                await fake.cancelled.wait_until(started+5)
            assert world.app.state.assistant_admission._active
            assert not fake.terminated.is_set()
            assert not messages
            # Intentionally NEVER signal shutdown. Its own absolute deadline
            # must remove the waiter and terminate execution before release.
        assert time.monotonic()-started < 1.6
        assert fake.terminated.is_set() and not fake.shutdown.is_set()
        assert not world.app.state.assistant_admission._active
        assert not fake.shutdown._waiters and not fake.release._waiters
        return messages
    assert response(anyio.run(run))[0] == 503
    with world.client() as client:
        recovered = client.get("/api/assistant/turns/by-key", headers={"Idempotency-Key": str(key)})
        assert recovered.status_code == 200 and recovered.json()["status"] == "pending"
        assert recovered.json()["assistant_message"] is None
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantMessage)) == 1
    assert sum(len(value) for value in world.app.state.assistant_admission._events.values()) == 1


def test_unknown_executor_cannot_claim_deadline_safe_support(enabled):
    world, _ = enabled
    class UnboundedExecutor:
        identity = service.TestExecutor.identity
        async def execute(self, *args, **kwargs):
            raise AssertionError("Unsupported executor must never be invoked")
    world.app.dependency_overrides[service.get_test_executor] = lambda: UnboundedExecutor()
    conversation = world.seed_conversation()
    messages = anyio.run(lambda: asgi_request(world,
        f"/api/assistant/conversations/{conversation}/messages", body={"content": "Test input"}))
    assert response(messages)[0] == 503
    assert response(messages)[1]["code"] == "PROVIDER_CONFIGURATION_INVALID"
    with pytest.raises(TypeError):
        type("UnsafeSubclass", (service.TestExecutor,), {})
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantTurn)) == 0
        assert db.scalar(select(func.count()).select_from(AssistantMessage)) == 0
    assert not world.app.state.assistant_admission._active
    assert not any(world.app.state.assistant_admission._events.values())


@pytest.mark.parametrize("phase", ["reserved", "completed"])
def test_result_expiring_during_worker_disposal_is_not_published_but_commits_are_discoverable(
    enabled, monkeypatch, phase,
):
    world, fake = enabled
    from app.core import assistant_database
    conversation, key = world.seed_conversation(), uuid4()
    database = world.app.state.assistant_database
    make_engine = database._make_engine
    clock = [time.monotonic()]
    cleaned = []
    def engines():
        engine = make_engine()
        dispose = engine.dispose
        def cleanup():
            dispose()
            if getattr(engine, "expire_test_result", False):
                cleaned.append(True)
                # Advance only the DB boundary's clock AFTER real disposal.
                clock[0] = assistant_database._budget.get().deadline + 1
        engine.dispose = cleanup
        return engine
    operation = service._new_turn if phase == "reserved" else service.complete
    def prepare(db, *args, **kwargs):
        result = operation(db, *args, **kwargs)
        db.get_bind().expire_test_result = True
        return result
    with monkeypatch.context() as changes:
        changes.setattr(database, "_make_engine", engines)
        changes.setattr(assistant_database, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        changes.setattr(service, "_new_turn" if phase == "reserved" else "complete", prepare)
        messages = anyio.run(lambda: asgi_request(world,
            f"/api/assistant/conversations/{conversation}/messages", body={"content": "Test input"}, key=key))
    status, payload = response(messages)
    assert status == 503 and payload["code"] == "WORK_DEADLINE_EXCEEDED"
    assert cleaned == [True] and not world.app.state.assistant_admission._active
    with world.client() as client:
        recovered = client.get("/api/assistant/turns/by-key", headers={"Idempotency-Key": str(key)})
    assert recovered.status_code == 200
    assert recovered.json()["status"] == ("completed" if phase == "completed" else "pending")
    assert len(fake.calls) == (1 if phase == "completed" else 0)
    assert sum(len(value) for value in world.app.state.assistant_admission._events.values()) == len(fake.calls)


@pytest.mark.parametrize("kind", ["new", "retry"])
def test_uncommitted_attempt_rolls_back_before_cleanup_expiry_and_remains_recoverable(enabled, monkeypatch, kind):
    world, _ = enabled
    from app.core import assistant_database
    from app.api.dependencies import AuthenticatedRequest
    from app.services.authentication import get_current_user
    from app.services.assistant_contracts import ContractViolation
    from app.schemas.assistant import HttpErrorCode
    conversation = world.seed_conversation()
    turn = world.seed_turn(conversation, expired=True) if kind == "retry" else None
    key = uuid4()
    database, clock, cleaned = world.app.state.assistant_database, [time.monotonic()], []
    make_engine = database._make_engine
    def engines():
        engine = make_engine()
        dispose = engine.dispose
        def cleanup():
            dispose()
            cleaned.append(True)
            clock[0] = assistant_database._budget.get().deadline + 1
        engine.dispose = cleanup
        return engine
    def prepare(db):
        authenticated = AuthenticatedRequest(get_current_user(db, session_token=world.first.token), world.first.token)
        if kind == "retry":
            _, existing = service._admission_state(db, authenticated, conversation, turn_id=turn, expected=1)
            service._retry_turn(db, existing, service.TestExecutor.identity)
            assert service.turn_dto(db, existing).attempt_no == 2
        else:
            fingerprint = service.submission_fingerprint(conversation, "Test input")
            service._admission_state(db, authenticated, conversation, key=key, fingerprint=fingerprint)
            existing = service._new_turn(db, authenticated, conversation, key, fingerprint,
                                         "Test input", service.TestExecutor.identity)
            assert service.turn_dto(db, existing).attempt_no == 1
        return "prepared but NOT committed"
    async def run():
        with pytest.raises(ContractViolation) as caught:
            await database.run(prepare, deadline=time.monotonic()+10)
        assert caught.value.code == HttpErrorCode.WORK_DEADLINE_EXCEEDED
    with monkeypatch.context() as changes:
        changes.setattr(database, "_make_engine", engines)
        changes.setattr(assistant_database, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        anyio.run(run)
    assert cleaned == [True]
    with world.client() as client:
        if kind == "retry":
            recovered = client.get(f"/api/assistant/conversations/{conversation}/turns/{turn}")
            assert recovered.json()["status"] == "pending" and recovered.json()["attempt_no"] == 1
            assert recovered.json()["lease_expired"] and recovered.json()["can_retry"]
            retried = client.post(f"/api/assistant/conversations/{conversation}/turns/{turn}/retry",
                                 json={"expected_attempt_no": 1})
            assert retried.status_code == 200 and retried.json()["status"] == "completed"
            assert retried.json()["attempt_no"] == 2
        else:
            recovered = client.get("/api/assistant/turns/by-key", headers={"Idempotency-Key": str(key)})
            assert recovered.status_code == 404
            resubmitted = client.post(f"/api/assistant/conversations/{conversation}/messages",
                                     json={"content": "Test input"}, headers={"Idempotency-Key": str(key)})
            assert resubmitted.status_code == 201 and resubmitted.json()["attempt_no"] == 1
            assert resubmitted.json()["status"] == "completed"
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantMessage).where(AssistantMessage.role == "user")) == 1


def test_pending_cancellation_after_worker_cleanup_prevents_result_publication(enabled, monkeypatch):
    world, _ = enabled
    from app.core import assistant_database
    original = assistant_database.DeadlineSession
    published, cleaned = [], []
    async def run():
        loop = asyncio.get_running_loop()
        with anyio.CancelScope() as scope:
            class CancellingClose(original):
                def close(self):
                    super().close()
                    cleaned.append(True)
                    # Queued before the worker reports its result to this loop.
                    loop.call_soon_threadsafe(scope.cancel)
            monkeypatch.setattr(assistant_database, "DeadlineSession", CancellingClose)
            value = await world.app.state.assistant_database.run(
                lambda db: db.scalar(select(1)), deadline=time.monotonic()+10)
            published.append(value)
    anyio.run(run)
    assert cleaned == [True] and published == []


def test_actual_handler_disconnect_during_preparation_joins_before_capacity_release(enabled, monkeypatch):
    """Real handler, auth/CSRF/reservation and lookup in guarded PostgreSQL only."""
    from app.core.assistant_admission import GenerationTicket
    world, _ = enabled
    fake = service.TestExecutor(preparation_paused=True)
    world.app.dependency_overrides[service.get_test_executor] = lambda: fake
    conversation, key = world.seed_conversation(), uuid4()
    close = GenerationTicket.close
    def checked_close(ticket):
        assert fake.preparation_terminated.is_set()
        assert not fake.preparation_release._waiters
        close(ticket)
    monkeypatch.setattr(GenerationTicket, "close", checked_close)
    async def run():
        disconnect, messages = anyio.Event(), []
        async def request():
            messages.extend(await asgi_request(world,
                f"/api/assistant/conversations/{conversation}/messages",
                body={"content": "Test input"}, key=key, disconnect=disconnect))
        async with anyio.create_task_group() as group:
            group.start_soon(request)
            await fake.preparation_entered.wait_until(time.monotonic()+5)
            assert world.app.state.assistant_admission._active
            assert not fake.calls and not messages
            disconnect.set()  # Actual ASGI receive message, not scope.cancel().
        assert fake.preparation_terminated.is_set()
        assert not world.app.state.assistant_admission._active
        assert not any(world.app.state.assistant_admission._events.values())
        assert response(messages)[0] == 503
    anyio.run(run)
    with world.client() as client:
        lookup = client.get("/api/assistant/turns/by-key", headers={"Idempotency-Key": str(key)})
    assert lookup.status_code == 200
    assert lookup.json()["status"] == "pending" and lookup.json()["assistant_message"] is None
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantMessage)) == 1
    # The original committed user message/key can recover normally through an
    # explicit retry after lease expiry; cancellation did not roll it back.
    from tests.test_assistant_turn_lifecycle import expire
    from uuid import UUID
    turn_id = UUID(lookup.json()["id"])
    expire(world, turn_id)
    fake.preparation_release.set()
    with world.client() as client:
        retried = client.post(
            f"/api/assistant/conversations/{conversation}/turns/{turn_id}/retry",
            json={"expected_attempt_no": 1})
    assert retried.status_code == 200 and retried.json()["status"] == "completed"
    assert retried.json()["attempt_no"] == 2 and retried.json()["idempotency_key"] == str(key)
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantMessage).where(AssistantMessage.role == "user")) == 1
