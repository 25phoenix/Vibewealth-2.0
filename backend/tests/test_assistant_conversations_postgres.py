"""Migration-backed conversation HTTP tests in guarded disposable schemas only."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from threading import Barrier, Event, local
from unittest.mock import Mock
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
import anyio
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import sessionmaker

from app.api import assistant_routes
from app.api.dependencies import create_csrf_token
from app.core.database import get_db
from app.core.assistant_database import AssistantDatabase
from app.models import AssistantConversation, AssistantMessage, AssistantTurn, AuthSession, User
from app.services.auth_sessions import create_session, revoke_session
from tests.test_assistant_conversations import application, no_application_database  # noqa: F401
from tests.test_assistant_turns import isolated_schema, migration_config

BASE = "/api/assistant/conversations"
ORIGIN = "http://localhost:5173"


@dataclass(frozen=True)
class Actor:
    id: UUID
    token: str = field(repr=False)


@dataclass
class World:
    app: object
    factory: object
    first: Actor
    second: Actor

    def client(self, actor=None):
        actor = actor or self.first
        client = TestClient(self.app)
        settings = self.app.state.settings
        client.cookies.set(settings.auth_cookie_name, actor.token)
        client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": create_csrf_token(actor.token, settings)})
        return client

    def seed_conversation(self, actor=None, *, identifier=None, title="Recorded title", timestamp=None):
        actor = actor or self.first
        identifier = identifier or uuid4()
        with self.factory() as db:
            values = dict(id=identifier, user_id=actor.id, title=title)
            if timestamp:
                values.update(created_at=timestamp, updated_at=timestamp)
            db.add(AssistantConversation(**values))
            db.commit()
        return identifier

    def seed_turn(self, conversation, *, status="pending", expired=False, attempt=1, failure="PROVIDER_TIMEOUT"):
        with self.factory() as db:
            now = db.scalar(select(func.clock_timestamp())).astimezone(timezone.utc)
            start = now - timedelta(seconds=120 if expired else 10)
            turn_id = uuid4()
            db.add(AssistantMessage(user_id=self.first.id, conversation_id=conversation,
                                    sequence_no=1, role="user", content="Show my recorded budgets"))
            db.flush()
            values = dict(
                id=turn_id, user_id=self.first.id, conversation_id=conversation,
                idempotency_key=uuid4(), request_fingerprint=b"x" * 32,
                user_sequence_no=1, assistant_sequence_no=None, status=status, attempt_no=attempt,
                created_at=start, attempt_started_at=start, attempt_finished_at=None,
                lease_expires_at=start + timedelta(seconds=90), context_as_of=None, financial_date=None,
                provider_kind="fake", model_name="test-only", contract_version=1, error_code=None,
            )
            if status != "pending":
                values.update(lease_expires_at=None, attempt_finished_at=now)
            if status == "failed":
                values.update(error_code=failure, context_as_of=start, financial_date=start.astimezone(
                    ZoneInfo("Asia/Kolkata")).date())
            if status == "completed":
                values.update(assistant_sequence_no=2, context_as_of=start,
                              financial_date=start.astimezone(ZoneInfo("Asia/Kolkata")).date())
                db.add(AssistantMessage(user_id=self.first.id, conversation_id=conversation,
                                       sequence_no=2, role="assistant", content="Backend-rendered recorded answer"))
                db.flush()
            db.add(AssistantTurn(**values))
            db.commit()
        return turn_id


@pytest.fixture
def world():
    # Calls the unchanged PostgreSQL safety helper before engine creation.
    with isolated_schema() as connection:
        command.upgrade(migration_config(connection), "9d4e7a2c6b10")
        schema = connection.scalar(select(func.current_schema()))
        connection.commit()
        factory = sessionmaker(bind=connection.engine.execution_options(schema_translate_map={None: schema}),
                               expire_on_commit=False)
        actors = []
        with factory() as db:
            for _ in range(2):
                user = User(email=f"{uuid4().hex}@example.test", password_hash="test-hash")
                db.add(user)
                db.flush()
                token, _ = create_session(db, user.id)
                actors.append(Actor(user.id, token))
            db.commit()
        app = application()
        app.state.assistant_database = AssistantDatabase(factory.kw["bind"])

        def override_db():
            with factory() as db:
                try:
                    yield db
                except Exception:
                    db.rollback()
                    raise
                finally:
                    if db.in_transaction():
                        db.rollback()

        app.dependency_overrides[get_db] = override_db
        yield World(app, factory, *actors)
        app.dependency_overrides.clear()


def test_create_normalization_replay_conflict_and_foreign_collision(world):
    identifier = str(uuid4())
    with world.client() as first, world.client(world.second) as second:
        created = first.post(BASE, json={"id": identifier, "title": " \u2003 My budgets\r\n "})
        assert created.status_code == 201
        assert created.json() == {**created.json(), "id": identifier, "title": "My budgets",
                                  "last_sequence_no": 0, "unresolved_turn": None}
        replay = first.post(BASE, json={"id": identifier, "title": "My budgets"})
        assert replay.status_code == 200 and replay.json() == created.json()
        conflict = first.post(BASE, json={"id": identifier, "title": "Different"})
        assert conflict.status_code == 409 and conflict.json()["code"] == "CONVERSATION_CREATE_CONFLICT"
        collision = second.post(BASE, json={"id": identifier, "title": "My budgets"})
        assert collision.status_code == 404 and collision.json()["code"] == "CONVERSATION_NOT_FOUND"
        assert "My budgets" not in collision.text
        assert all(response.headers["cache-control"] == "no-store" for response in (created, replay, conflict, collision))
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantConversation)) == 1


def test_omitted_and_null_title_replay_and_server_ownership(world):
    identifier = str(uuid4())
    with world.client() as client:
        assert client.post(BASE, json={"id": identifier}).status_code == 201
        replay = client.post(BASE, json={"id": identifier, "title": None})
        assert replay.status_code == 200 and replay.json()["title"] is None
        invalid = client.post(BASE, json={"id": str(uuid4()), "user_id": str(world.second.id)})
        assert invalid.status_code == 422
        assert str(world.second.id) not in invalid.text


@pytest.mark.parametrize("payload", [
    {"title": "Missing id"}, {"id": "not-a-uuid"}, {"id": "123e4567-e89b-12d3-a456-426614174000"},
    {"id": str(uuid4()), "title": " "}, {"id": str(uuid4()), "title": "x" * 161},
    {"id": str(uuid4()), "title": False},
])
def test_create_strict_payload_errors_are_sanitized(world, payload):
    with world.client() as client:
        response = client.post(BASE, json=payload)
    assert response.status_code == 422 and response.json()["code"] == "INVALID_REQUEST"
    assert response.headers["cache-control"] == "no-store"


def test_create_body_bound_duplicates_and_encoding(world):
    identifier = str(uuid4())
    with world.client() as client:
        duplicate = client.post(BASE, content='{"id":"' + identifier + '","title":"a","title":"b"}')
        large = client.post(BASE, content=b" " * 65537)
        encoding = client.post(BASE, json={"id": identifier}, headers={"Content-Encoding": "gzip"})
    assert duplicate.status_code == 422 and encoding.status_code == 422
    assert large.status_code == 413 and large.json()["code"] == "REQUEST_TOO_LARGE"
    assert all(response.headers["cache-control"] == "no-store" for response in (duplicate, large, encoding))


def test_list_get_pagination_count_order_and_tenant_isolation(world):
    stamp = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    ids = [world.seed_conversation(timestamp=stamp) for _ in range(3)]
    newest = world.seed_conversation(timestamp=stamp + timedelta(seconds=1))
    foreign = world.seed_conversation(world.second)
    expected = [str(newest), *[str(value) for value in sorted(ids, reverse=True)]]
    with world.client() as client:
        page = client.get(BASE + "?offset=1&limit=2")
        assert page.status_code == 200
        assert page.json()["total"] == 4
        assert [item["id"] for item in page.json()["items"]] == expected[1:3]
        default = client.get(BASE).json()
        assert default["offset"] == 0 and default["limit"] == 50
        assert [item["id"] for item in default["items"]] == expected
        empty = client.get(BASE + "?offset=99&limit=1").json()
        assert empty == {"items": [], "total": 4, "offset": 99, "limit": 1}
        assert client.get(f"{BASE}/{newest}").status_code == 200
        for identifier in (foreign, uuid4()):
            response = client.get(f"{BASE}/{identifier}")
            assert response.status_code == 404 and response.json()["code"] == "CONVERSATION_NOT_FOUND"
    with world.client(world.second) as client:
        assert [item["id"] for item in client.get(BASE).json()["items"]] == [str(foreign)]


def test_history_orders_actual_sequences_and_keeps_legacy_metadata_null(world):
    conversation = world.seed_conversation()
    foreign = world.seed_conversation(world.second)
    with world.factory() as db:
        for sequence, role in ((5, "user"), (2, "assistant"), (1, "user")):
            db.add(AssistantMessage(user_id=world.first.id, conversation_id=conversation,
                                    sequence_no=sequence, role=role, content=f"Legacy record {sequence}"))
        db.commit()
    with world.client() as client:
        history = client.get(f"{BASE}/{conversation}/messages?offset=1&limit=1").json()
        assert history["total"] == 3 and history["items"][0]["sequence_no"] == 2
        assert history["items"][0]["turn"] is None
        assert [item["sequence_no"] for item in client.get(f"{BASE}/{conversation}/messages").json()["items"]] == [1, 2, 5]
        assert client.get(f"{BASE}/{conversation}").json()["last_sequence_no"] == 5
        for identifier in (foreign, uuid4()):
            assert client.get(f"{BASE}/{identifier}/messages").status_code == 404


@pytest.mark.parametrize("status,expired,attempt,failure", [
    ("pending", False, 1, "PROVIDER_TIMEOUT"), ("pending", True, 1, "PROVIDER_TIMEOUT"),
    ("pending", True, 3, "PROVIDER_TIMEOUT"), ("failed", False, 1, "CONTEXT_LIMIT"),
    ("failed", False, 2, "SESSION_INVALIDATED"),
])
def test_unresolved_projection_is_read_only_and_uses_persisted_sequence(world, status, expired, attempt, failure):
    conversation = world.seed_conversation()
    turn_id = world.seed_turn(conversation, status=status, expired=expired, attempt=attempt, failure=failure)
    with world.factory() as db:
        before = dict(db.execute(select(AssistantTurn.__table__)).mappings().one())
    with world.client() as client:
        detail = client.get(f"{BASE}/{conversation}")
        listing = client.get(BASE)
        assert detail.status_code == listing.status_code == 200
        dto = detail.json()
        assert dto["last_sequence_no"] == 1  # Reserved sequence 2 is not a persisted message.
        assert dto == listing.json()["items"][0]
        turn = dto["unresolved_turn"]
        assert turn["id"] == str(turn_id) and turn["status"] == status
        assert turn["lease_expired"] == expired
        if expired:
            assert turn["error"]["code"] == "GENERATION_INTERRUPTED"
            assert turn["can_retry"] == (attempt < 3)
        elif status == "failed":
            assert turn["error"]["code"] == failure
        else:
            assert turn["error"] is None
        assert turn["user_message"]["turn"] == {"id": str(turn_id), "status": status, "attempt_no": attempt}
        assert not {"provider_kind", "model_name", "request_fingerprint", "session_id"} & turn.keys()
    with world.factory() as db:
        assert dict(db.execute(select(AssistantTurn.__table__)).mappings().one()) == before


def test_completed_and_abandoned_history_is_shallow_and_not_unresolved(world):
    for status in ("completed", "abandoned"):
        conversation = world.seed_conversation()
        turn_id = world.seed_turn(conversation, status=status)
        with world.client() as client:
            detail = client.get(f"{BASE}/{conversation}").json()
            assert detail["unresolved_turn"] is None
            assert detail["last_sequence_no"] == (2 if status == "completed" else 1)
            messages = client.get(f"{BASE}/{conversation}/messages").json()["items"]
            assert all(message["turn"] == {"id": str(turn_id), "status": status, "attempt_no": 1} for message in messages)


def test_creation_limit_replays_before_capacity_and_does_not_rename(world):
    with world.factory() as db:
        ids = [uuid4() for _ in range(100)]
        db.add_all([AssistantConversation(id=identifier, user_id=world.first.id, title="Original") for identifier in ids])
        db.commit()
    with world.client() as client:
        assert client.post(BASE, json={"id": str(ids[0]), "title": "Original"}).status_code == 200
        assert client.post(BASE, json={"id": str(ids[0]), "title": "Other"}).json()["code"] == "CONVERSATION_CREATE_CONFLICT"
        refused = client.post(BASE, json={"id": str(uuid4())})
        assert refused.status_code == 409 and refused.json()["code"] == "CONVERSATION_LIMIT_REACHED"


@pytest.mark.parametrize("status", ["pending", "completed", "failed", "abandoned"])
def test_delete_cascades_messages_turns_only_and_is_non_disclosing(world, status):
    conversation = world.seed_conversation()
    world.seed_turn(conversation, status=status)
    foreign = world.seed_conversation(world.second)
    with world.client() as client:
        assert client.delete(f"{BASE}/{foreign}").status_code == 404
        invalid = client.request("DELETE", f"{BASE}/{conversation}", json={})
        assert invalid.status_code == 422
        response = client.delete(f"{BASE}/{conversation}")
        assert response.status_code == 204 and response.content == b""
        assert response.headers["cache-control"] == "no-store"
        assert client.get(f"{BASE}/{conversation}").status_code == 404
        assert client.delete(f"{BASE}/{conversation}").status_code == 404
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantMessage)) == 0
        assert db.scalar(select(func.count()).select_from(AssistantTurn)) == 0
        assert db.scalar(select(func.count()).select_from(User)) == 2
        assert db.get(AssistantConversation, foreign) is not None


def test_csrf_and_origin_on_both_writes_and_no_store(world):
    conversation = world.seed_conversation()
    with world.client() as client:
        for method, path, payload in (("POST", BASE, {"id": str(uuid4())}),
                                      ("DELETE", f"{BASE}/{conversation}", None)):
            for headers, expected in (({"X-CSRF-Token": "invalid"}, "CSRF_FAILED"),
                                      ({"Origin": "http://evil.test"}, "ORIGIN_REJECTED")):
                response = client.request(method, path, json=payload, headers=headers)
                assert response.status_code == 403 and response.json()["code"] == expected
                assert response.headers["cache-control"] == "no-store"


def test_write_rate_limit_retry_after_and_no_create(world):
    for _ in range(30):
        world.app.state.assistant_rate_limiter.check(world.first.id, write=True)
    with world.client() as client:
        response = client.post(BASE, json={"id": str(uuid4())})
        assert response.status_code == 429 and int(response.headers["retry-after"]) >= 1
        assert response.json()["code"] == "RATE_LIMITED"
        assert response.headers["cache-control"] == "no-store"
        assert client.get(BASE).json()["total"] == 0


@pytest.mark.parametrize("matching", [True, False])
def test_simultaneous_same_owner_create_serializes_matching_and_conflicting_titles(world, monkeypatch, matching):
    with world.factory() as db:
        token, _ = create_session(db, world.first.id)
        db.commit()
    second_session = Actor(world.first.id, token)
    barrier = Barrier(2)
    thread = local()
    original = assistant_routes.service._creation_lookup

    def synchronize_initial_lookup(db, identifier):
        result = original(db, identifier)
        if not getattr(thread, "seen", False):
            thread.seen = True
            barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(assistant_routes.service, "_creation_lookup", synchronize_initial_lookup)
    identifier = str(uuid4())

    def submit(actor, title):
        with world.client(actor) as client:
            return client.post(BASE, json={"id": identifier, "title": title})

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(submit, world.first, "Original")
        second = executor.submit(submit, second_session, "Original" if matching else "Different")
        responses = [first.result(timeout=20), second.result(timeout=20)]
    assert sorted(response.status_code for response in responses) == ([200, 201] if matching else [201, 409])
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantConversation)) == 1


def test_cross_owner_primary_key_race_rolls_back_reauthenticates_and_returns_foreign_404(world, monkeypatch):
    barrier = Barrier(2)
    insert = assistant_routes.service._insert_conversation
    classifier = assistant_routes.service.is_creation_primary_key_conflict
    reauth = assistant_routes._reauthenticate
    observed = []
    revalidated = []

    def synchronized_insert(*args, **kwargs):
        barrier.wait(timeout=10)
        return insert(*args, **kwargs)

    def observe_error(error):
        observed.append((error.orig.sqlstate, error.orig.diag.constraint_name))
        return classifier(error)

    def observe_reauth(db, authenticated):
        assert not db.in_transaction()
        revalidated.append(True)
        return reauth(db, authenticated)

    monkeypatch.setattr(assistant_routes.service, "_insert_conversation", synchronized_insert)
    monkeypatch.setattr(assistant_routes.service, "is_creation_primary_key_conflict", observe_error)
    monkeypatch.setattr(assistant_routes, "_reauthenticate", observe_reauth)
    identifier = str(uuid4())

    def submit(actor):
        with world.client(actor) as client:
            return client.post(BASE, json={"id": identifier, "title": "Private title"})

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit, actor) for actor in (world.first, world.second)]
        responses = [future.result(timeout=20) for future in futures]
    assert sorted(response.status_code for response in responses) == [201, 404]
    assert observed == [("23505", "pk_assistant_conversations")]
    assert revalidated == [True]
    assert "Private title" not in next(response for response in responses if response.status_code == 404).text


@pytest.mark.parametrize("matching", [True, False])
def test_primary_key_recovery_same_owner_replays_or_conflicts_without_second_insert(world, monkeypatch, matching):
    identifier = world.seed_conversation(title="Original")
    lookup = assistant_routes.service._creation_lookup
    calls = []
    reauth = Mock(wraps=assistant_routes._reauthenticate)

    def miss_two_admission_reads(db, conversation_id):
        calls.append(True)
        return None if len(calls) <= 2 else lookup(db, conversation_id)

    # Force the real PostgreSQL unique-constraint branch after stale lookups.
    monkeypatch.setattr(assistant_routes.service, "_creation_lookup", miss_two_admission_reads)
    monkeypatch.setattr(assistant_routes, "_reauthenticate", reauth)
    with world.client() as client:
        response = client.post(BASE, json={"id": str(identifier), "title": "Original" if matching else "Different"})
    assert response.status_code == (200 if matching else 409)
    reauth.assert_called_once()
    assert len(calls) == 3  # Recovery never retries insertion.
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantConversation)) == 1


def test_primary_key_recovery_revalidates_revocation_before_resolving_winner(world, monkeypatch):
    identifier = world.seed_conversation()
    lookup = assistant_routes.service._creation_lookup
    calls = []
    real_reauth = assistant_routes._reauthenticate

    def miss(db, value):
        calls.append(True)
        return None if len(calls) <= 2 else lookup(db, value)

    def revoke_then_revalidate(db, authenticated):
        with world.factory() as other:
            revoke_session(other, user_id=world.first.id, session_id=authenticated.current_user.session_id)
            other.commit()
        return real_reauth(db, authenticated)

    monkeypatch.setattr(assistant_routes.service, "_creation_lookup", miss)
    monkeypatch.setattr(assistant_routes, "_reauthenticate", revoke_then_revalidate)
    with world.client() as client:
        response = client.post(BASE, json={"id": str(identifier)})
    assert response.status_code == 401 and response.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert len(calls) == 2  # Winner was not exposed after session invalidation.


def test_unrelated_integrity_failure_is_not_replayed_or_exposed(world, monkeypatch):
    reauth = Mock()

    def bad_insert(db, *, user_id, payload):
        db.add(AssistantConversation(id=payload.id, user_id=uuid4(), title="Private SQL title"))
        db.flush()  # Actual unrelated foreign-key violation.

    monkeypatch.setattr(assistant_routes.service, "_insert_conversation", bad_insert)
    monkeypatch.setattr(assistant_routes, "_reauthenticate", reauth)
    with world.client() as client:
        response = client.post(BASE, json={"id": str(uuid4())})
    assert response.status_code == 500 and response.json()["code"] == "INTERNAL_ERROR"
    assert "Private SQL title" not in response.text and "INSERT" not in response.text
    reauth.assert_not_called()


def test_reads_use_consistent_readonly_snapshot_after_auth_commit(world, monkeypatch):
    original = assistant_routes.service.list_conversations
    settings = []

    def inspect_snapshot(db, **kwargs):
        settings.append(db.execute(text(
            "SELECT current_setting('transaction_isolation'), current_setting('transaction_read_only')"
        )).one())
        return original(db, **kwargs)

    monkeypatch.setattr(assistant_routes.service, "list_conversations", inspect_snapshot)
    with world.client() as client:
        assert client.get(BASE).status_code == 200
    assert settings == [("repeatable read", "on")]


def test_create_and_delete_follow_session_user_conversation_lock_order(world):
    captured = []
    target = world.factory.kw["bind"]

    def record_sql(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement.lower())  # Never capture parameter values.

    event.listen(target, "before_cursor_execute", record_sql)
    try:
        identifier = str(uuid4())
        with world.client() as client:
            assert client.post(BASE, json={"id": identifier}).status_code == 201
            auth = next(i for i, sql in enumerate(captured) if sql.lstrip().startswith("update") and "auth_sessions" in sql)
            owner = next(i for i, sql in enumerate(captured) if "for update" in sql and ".users" in sql)
            insert = next(i for i, sql in enumerate(captured) if sql.lstrip().startswith("insert") and "assistant_conversations" in sql)
            assert auth < owner < insert
            captured.clear()
            assert client.delete(f"{BASE}/{identifier}").status_code == 204
            auth = next(i for i, sql in enumerate(captured) if sql.lstrip().startswith("update") and "auth_sessions" in sql)
            conversation = next(i for i, sql in enumerate(captured) if "for update" in sql and "assistant_conversations" in sql)
            deletion = next(i for i, sql in enumerate(captured) if sql.lstrip().startswith("delete") and "assistant_conversations" in sql)
            assert auth < conversation < deletion
            assert not any("for update" in sql and ".users" in sql for sql in captured)
    finally:
        event.remove(target, "before_cursor_execute", record_sql)


def test_concurrent_creation_cannot_exceed_owner_limit(world, monkeypatch):
    with world.factory() as db:
        db.add_all([AssistantConversation(user_id=world.first.id) for _ in range(99)])
        token, _ = create_session(db, world.first.id)
        db.commit()
    barrier = Barrier(2)
    thread = local()
    original = assistant_routes.service._creation_lookup

    def synchronize(db, identifier):
        result = original(db, identifier)
        if not getattr(thread, "seen", False):
            thread.seen = True
            barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(assistant_routes.service, "_creation_lookup", synchronize)

    def submit(actor):
        with world.client(actor) as client:
            return client.post(BASE, json={"id": str(uuid4())})

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit, actor) for actor in (world.first, Actor(world.first.id, token))]
        responses = [future.result(timeout=20) for future in futures]
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert next(response for response in responses if response.status_code == 409).json()["code"] == "CONVERSATION_LIMIT_REACHED"
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantConversation).where(AssistantConversation.user_id == world.first.id)) == 100


@pytest.mark.parametrize("method,credential_state,expected", [
    ("POST", "valid", 201), ("POST", "invalid_csrf", 403),
    ("POST", "revoked", 401), ("DELETE", "valid", 204),
])
def test_delayed_body_does_not_checkout_connection_or_lock_session(world, method, credential_state, expected):
    identifier = world.seed_conversation() if method == "DELETE" else uuid4()
    with world.factory() as db:
        session_id = db.scalar(select(AuthSession.id).where(AuthSession.user_id == world.first.id))
    settings = world.app.state.settings
    body = json.dumps({"id": str(identifier)}).encode() if method == "POST" else b""
    waiting = Event()
    release = Event()
    checkouts = []
    pool = world.factory.kw["bind"].pool

    def checkout(*args):
        checkouts.append(True)

    async def request():
        part = 0
        messages = []

        async def receive():
            nonlocal part
            part += 1
            if part == 1:
                return {"type": "http.request", "body": body[:1], "more_body": True}
            if part == 2:
                waiting.set()
                assert await anyio.to_thread.run_sync(lambda: release.wait(timeout=15))
                return {"type": "http.request", "body": body[1:], "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        csrf = "invalid" if credential_state == "invalid_csrf" else create_csrf_token(world.first.token, settings)
        path = BASE if method == "POST" else f"{BASE}/{identifier}"
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
            "query_string": b"", "root_path": "", "server": ("localhost", 8000),
            "client": ("127.0.0.1", 12345), "headers": [
                (b"host", b"localhost:8000"), (b"origin", ORIGIN.encode()),
                (b"content-type", b"application/json"), (b"x-csrf-token", csrf.encode()),
                (b"cookie", (settings.auth_cookie_name + "=" + world.first.token).encode()),
            ],
        }
        await world.app(scope, receive, send)
        return messages

    event.listen(pool, "checkout", checkout)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: anyio.run(request))
            try:
                assert waiting.wait(timeout=10), "Request never paused during body reception"
                assert checkouts == [], "Body reception acquired a database connection"
                # This independent connection would fail NOWAIT if the request
                # already held get_valid_session's UPDATE lock on the same row.
                with world.factory() as other:
                    locked = other.scalar(select(AuthSession.id).where(
                        AuthSession.id == session_id,
                    ).with_for_update(nowait=True))
                    assert locked == session_id
                    if credential_state == "revoked":
                        revoke_session(other, user_id=world.first.id, session_id=session_id)
                    other.commit()
            finally:
                release.set()
            messages = future.result(timeout=20)
    finally:
        release.set()
        event.remove(pool, "checkout", checkout)
    start = next(message for message in messages if message["type"] == "http.response.start")
    assert start["status"] == expected
    assert dict(start["headers"])[b"cache-control"] == b"no-store"
    with world.factory() as db:
        conversation = db.get(AssistantConversation, identifier)
        if expected == 201:
            assert conversation is not None and conversation.user_id == world.first.id
        else:
            assert conversation is None
    if expected in {401, 403}:
        payload = json.loads(b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body"))
        assert payload["code"] == ("AUTHENTICATION_REQUIRED" if expected == 401 else "CSRF_FAILED")
