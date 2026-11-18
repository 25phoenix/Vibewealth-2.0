"""Phase 9C.2 metadata and isolated PostgreSQL model/migration verification."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, create_engine, inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.schema import CreateTable

from app.models import AssistantConversation, AssistantMessage, AssistantTurn, Base, User
from app.schemas.assistant import PersistedFailureCode
from tests.postgres_safety import postgres_test_url

BACKEND = Path(__file__).resolve().parents[1]
PARENT = "8c2d6f4a1b90"
REVISION = "9d4e7a2c6b10"
STAMP = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
TABLE = AssistantTurn.__table__


def test_turn_registration_types_nullability_defaults_and_relationships():
    assert Base.metadata.tables["assistant_turns"] is TABLE
    assert set(TABLE.columns.keys()) == {
        "id", "user_id", "conversation_id", "idempotency_key", "request_fingerprint",
        "user_sequence_no", "assistant_sequence_no", "status", "attempt_no", "created_at",
        "attempt_started_at", "attempt_finished_at", "lease_expires_at", "context_as_of",
        "financial_date", "provider_kind", "model_name", "contract_version", "error_code",
    }
    nullable = {"assistant_sequence_no", "attempt_finished_at", "lease_expires_at", "context_as_of", "financial_date", "error_code"}
    assert {c.name for c in TABLE.columns if c.nullable} == nullable
    for field in ("id", "user_id", "conversation_id", "idempotency_key"):
        assert TABLE.c[field].type.compile(dialect=postgresql.dialect()) == "UUID"
    assert TABLE.c.request_fingerprint.type.compile(dialect=postgresql.dialect()) == "BYTEA"
    assert TABLE.c.request_fingerprint.type.length == 32
    for field in ("created_at", "attempt_started_at", "attempt_finished_at", "lease_expires_at", "context_as_of"):
        assert TABLE.c[field].type.timezone
    assert TABLE.c.model_name.type.length == 160
    assert TABLE.c.status.type.length == 16
    assert TABLE.c.provider_kind.type.length == 16
    assert TABLE.c.error_code.type.length == 40
    for field in ("attempt_no", "contract_version"):
        assert TABLE.c[field].type.compile(dialect=postgresql.dialect()) == "SMALLINT"
    assert TABLE.c.id.default.arg.__name__ == "uuid4"
    assert TABLE.c.created_at.server_default is not None
    configure_mappers()
    for name, target in (("conversation", AssistantConversation), ("user_message", AssistantMessage), ("assistant_message", AssistantMessage)):
        relationship = getattr(AssistantTurn, name).property
        assert relationship.mapper.class_ is target
        assert relationship.viewonly


def test_turn_named_keys_owner_links_and_only_required_index():
    constraints = {c.name: c for c in TABLE.constraints}
    assert tuple(c.name for c in constraints["pk_assistant_turns"].columns) == ("id",)
    assert {c.name for c in TABLE.constraints if isinstance(c, UniqueConstraint)} == {
        "uq_assistant_turns_user_key", "uq_assistant_turns_user_message",
    }
    assert tuple(c.name for c in constraints["uq_assistant_turns_user_key"].columns) == ("user_id", "idempotency_key")
    assert tuple(c.name for c in constraints["uq_assistant_turns_user_message"].columns) == ("conversation_id", "user_sequence_no")
    foreign = {c.name: c for c in TABLE.constraints if isinstance(c, ForeignKeyConstraint)}
    expected = {
        "fk_assistant_turns_conversation_owner": (("user_id", "conversation_id"), ("assistant_conversations.user_id", "assistant_conversations.id"), "CASCADE"),
        "fk_assistant_turns_user_message": (("conversation_id", "user_sequence_no"), ("assistant_messages.conversation_id", "assistant_messages.sequence_no"), "CASCADE"),
        "fk_assistant_turns_assistant_message": (("conversation_id", "assistant_sequence_no"), ("assistant_messages.conversation_id", "assistant_messages.sequence_no"), "NO ACTION"),
    }
    assert set(foreign) == set(expected)
    for name, (columns, targets, deletion) in expected.items():
        fk = foreign[name]
        assert tuple(c.name for c in fk.columns) == columns
        assert tuple(e.target_fullname for e in fk.elements) == targets
        assert fk.ondelete == deletion
    reply = foreign["fk_assistant_turns_assistant_message"]
    assert reply.deferrable is True and reply.initially == "DEFERRED"
    assert {index.name for index in TABLE.indexes} == {"uq_assistant_turns_unresolved_conversation"}
    index = next(iter(TABLE.indexes))
    assert index.unique and tuple(c.name for c in index.columns) == ("conversation_id",)
    assert str(index.dialect_options["postgresql"]["where"]) == "status IN ('pending', 'failed')"


def test_turn_check_contract_excludes_derived_failures_and_migration_has_verified_parent():
    checks = {c.name: str(c.sqltext) for c in TABLE.constraints if isinstance(c, CheckConstraint)}
    assert set(checks) == {f"ck_assistant_turns_{name}" for name in (
        "fingerprint_length", "user_sequence", "reply_sequence", "status", "attempt", "provider",
        "model_nonblank", "contract_version", "error_code", "context_pair", "started_order",
        "finished_order", "context_order", "lifecycle",
    )}
    errors = checks["ck_assistant_turns_error_code"]
    assert "GENERATION_INTERRUPTED" not in errors
    for code in PersistedFailureCode:
        assert f"'{code.value}'" in errors
    ddl = str(CreateTable(TABLE).compile(dialect=postgresql.dialect()))
    assert "DEFERRABLE INITIALLY DEFERRED" in ddl
    scripts = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert scripts.get_heads() == [REVISION]
    assert scripts.get_revision(REVISION).down_revision == PARENT


@contextmanager
def isolated_schema():
    """Use unchanged repository safeguards before engine creation or any DDL."""
    url = postgres_test_url()
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    schema = f"model_test_{uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        with engine.connect() as connection:
            # No public fallback: all migration reads/writes are schema-local.
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
            connection.commit()
            yield connection
    finally:
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            engine.dispose()


def migration_config(connection):
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture(scope="module", params=["metadata", "migration"])
def schema_connection(request):
    with isolated_schema() as connection:
        if request.param == "metadata":
            Base.metadata.create_all(connection)
            connection.commit()
        else:
            command.upgrade(migration_config(connection), REVISION)
        yield connection


@pytest.fixture
def pg(schema_connection):
    connection = schema_connection
    if connection.in_transaction():
        connection.rollback()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()


def seed_conversation(connection, *, owner=None):
    if owner is None:
        owner = uuid4()
        connection.execute(User.__table__.insert().values(id=owner, email=f"{uuid4().hex}@example.test", password_hash="test-hash"))
    conversation = uuid4()
    connection.execute(AssistantConversation.__table__.insert().values(id=conversation, user_id=owner, title="Legacy-safe test"))
    return owner, conversation


def seed_message(connection, owner, conversation, sequence=1, role="user"):
    identifier = uuid4()
    connection.execute(AssistantMessage.__table__.insert().values(
        id=identifier, user_id=owner, conversation_id=conversation, sequence_no=sequence,
        role=role, content="Legacy message remains intact",
    ))
    return identifier


def turn_values(owner, conversation, *, sequence=1, status="pending", **overrides):
    values = dict(
        id=uuid4(), user_id=owner, conversation_id=conversation, idempotency_key=uuid4(),
        request_fingerprint=b"x" * 32, user_sequence_no=sequence, assistant_sequence_no=None,
        status=status, attempt_no=1, created_at=STAMP, attempt_started_at=STAMP,
        attempt_finished_at=None, lease_expires_at=STAMP + timedelta(seconds=90),
        context_as_of=None, financial_date=None, provider_kind="fake", model_name="test-only-model",
        contract_version=1, error_code=None,
    )
    if status != "pending":
        values.update(lease_expires_at=None, attempt_finished_at=STAMP + timedelta(seconds=1))
    if status == "completed":
        values.update(assistant_sequence_no=sequence + 1, context_as_of=STAMP, financial_date=STAMP.date())
    if status == "failed":
        values["error_code"] = "PROVIDER_TIMEOUT"
    values.update(overrides)
    return values


def reject_insert(connection, values, constraint):
    with pytest.raises(IntegrityError) as caught:
        with connection.begin_nested():
            connection.execute(TABLE.insert().values(**values))
            connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
    assert caught.value.orig.diag.constraint_name == constraint


def test_postgres_reflected_schema_matches_model_contract(pg):
    inspector = inspect(pg)
    columns = {item["name"]: item for item in inspector.get_columns("assistant_turns")}
    assert set(columns) == set(TABLE.columns.keys())
    for column in TABLE.columns:
        assert columns[column.name]["nullable"] == column.nullable
        assert columns[column.name]["type"].compile(dialect=postgresql.dialect()) == column.type.compile(dialect=postgresql.dialect())
    assert {item["name"] for item in inspector.get_check_constraints("assistant_turns")} == {
        c.name for c in TABLE.constraints if isinstance(c, CheckConstraint)
    }
    assert {item["name"] for item in inspector.get_unique_constraints("assistant_turns")} == {
        "uq_assistant_turns_user_key", "uq_assistant_turns_user_message",
    }
    foreign = {item["name"]: item for item in inspector.get_foreign_keys("assistant_turns")}
    assert set(foreign) == {c.name for c in TABLE.constraints if isinstance(c, ForeignKeyConstraint)}
    options = foreign["fk_assistant_turns_assistant_message"]["options"]
    assert options["deferrable"] and options["initially"] == "DEFERRED"
    indexes = {item["name"]: item for item in inspector.get_indexes("assistant_turns") if not item.get("duplicates_constraint")}
    assert set(indexes) == {"uq_assistant_turns_unresolved_conversation"}
    assert indexes["uq_assistant_turns_unresolved_conversation"]["unique"]


@pytest.mark.parametrize("status", ["pending", "completed", "failed", "abandoned"])
def test_postgres_valid_states_and_readonly_relationships(pg, status):
    owner, conversation = seed_conversation(pg)
    user_message = seed_message(pg, owner, conversation)
    reply = seed_message(pg, owner, conversation, 2, "assistant") if status == "completed" else None
    values = turn_values(owner, conversation, status=status)
    pg.execute(TABLE.insert().values(**values))
    pg.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
    with Session(bind=pg) as session:
        turn = session.get(AssistantTurn, values["id"])
        assert turn.conversation.user_id == owner
        assert turn.user_message.id == user_message
        assert (turn.assistant_message.id if turn.assistant_message else None) == reply


INVALID_STATES = [
    ("pending", {"lease_expires_at": None}, "lifecycle"),
    ("pending", {"lease_expires_at": STAMP}, "lifecycle"),
    ("pending", {"attempt_finished_at": STAMP}, "lifecycle"),
    ("pending", {"error_code": "PROVIDER_TIMEOUT"}, "lifecycle"),
    ("pending", {"assistant_sequence_no": 2}, "lifecycle"),
    ("completed", {"assistant_sequence_no": None}, "lifecycle"),
    ("completed", {"lease_expires_at": STAMP}, "lifecycle"),
    ("completed", {"attempt_finished_at": None}, "lifecycle"),
    ("completed", {"error_code": "PROVIDER_TIMEOUT"}, "lifecycle"),
    ("completed", {"context_as_of": None, "financial_date": None}, "lifecycle"),
    ("failed", {"error_code": None}, "lifecycle"),
    ("failed", {"lease_expires_at": STAMP}, "lifecycle"),
    ("failed", {"attempt_finished_at": None}, "lifecycle"),
    ("failed", {"assistant_sequence_no": 2}, "lifecycle"),
    ("abandoned", {"error_code": "PROVIDER_TIMEOUT"}, "lifecycle"),
    ("abandoned", {"lease_expires_at": STAMP}, "lifecycle"),
    ("abandoned", {"attempt_finished_at": None}, "lifecycle"),
    ("abandoned", {"assistant_sequence_no": 2}, "lifecycle"),
    ("pending", {"request_fingerprint": b"x" * 31}, "fingerprint_length"),
    ("pending", {"request_fingerprint": b"x" * 33}, "fingerprint_length"),
    ("pending", {"user_sequence_no": 0}, "user_sequence"),
    ("pending", {"user_sequence_no": 2147483647}, "user_sequence"),
    ("completed", {"assistant_sequence_no": 3}, "reply_sequence"),
    ("pending", {"status": "interrupted"}, "lifecycle"),
    ("pending", {"attempt_no": 0}, "attempt"),
    ("pending", {"attempt_no": 4}, "attempt"),
    ("pending", {"provider_kind": "disabled"}, "provider"),
    ("pending", {"model_name": ""}, "model_nonblank"),
    ("pending", {"model_name": " \t\r\n"}, "model_nonblank"),
    ("pending", {"contract_version": 2}, "contract_version"),
    ("failed", {"error_code": "GENERATION_INTERRUPTED"}, "error_code"),
    ("failed", {"error_code": "UNKNOWN"}, "error_code"),
    ("pending", {"context_as_of": STAMP}, "context_pair"),
    ("pending", {"financial_date": STAMP.date()}, "context_pair"),
    ("pending", {"created_at": STAMP + timedelta(seconds=1)}, "started_order"),
    ("failed", {"attempt_finished_at": STAMP - timedelta(seconds=1)}, "finished_order"),
    ("pending", {"context_as_of": STAMP - timedelta(seconds=1), "financial_date": STAMP.date()}, "context_order"),
]


@pytest.mark.parametrize("status,overrides,constraint", INVALID_STATES)
def test_postgres_rejects_invalid_lifecycle_and_check_values(pg, status, overrides, constraint):
    owner, conversation = seed_conversation(pg)
    seed_message(pg, owner, conversation)
    seed_message(pg, owner, conversation, 2, "assistant")
    values = turn_values(owner, conversation, status=status)
    values.update(overrides)
    reject_insert(pg, values, f"ck_assistant_turns_{constraint}")


@pytest.mark.parametrize("status", ["failed", "abandoned"])
def test_postgres_resolved_turns_may_retain_context(pg, status):
    owner, conversation = seed_conversation(pg)
    seed_message(pg, owner, conversation)
    pg.execute(TABLE.insert().values(**turn_values(owner, conversation, status=status, context_as_of=STAMP, financial_date=STAMP.date())))


@pytest.mark.parametrize("code", [code.value for code in PersistedFailureCode])
def test_postgres_all_persisted_failure_codes_are_accepted(pg, code):
    owner, conversation = seed_conversation(pg)
    seed_message(pg, owner, conversation)
    pg.execute(TABLE.insert().values(**turn_values(owner, conversation, status="failed", error_code=code)))


def test_postgres_owner_and_composite_message_links(pg):
    owner, conversation = seed_conversation(pg)
    foreign_owner, foreign_conversation = seed_conversation(pg)
    seed_message(pg, owner, conversation)
    seed_message(pg, foreign_owner, foreign_conversation, 3)
    reject_insert(pg, turn_values(foreign_owner, conversation), "fk_assistant_turns_conversation_owner")
    reject_insert(pg, turn_values(owner, conversation, sequence=3), "fk_assistant_turns_user_message")
    reject_insert(pg, turn_values(owner, uuid4()), "fk_assistant_turns_conversation_owner")


def test_postgres_user_wide_idempotency_and_unique_user_message(pg):
    owner, first = seed_conversation(pg)
    _, second = seed_conversation(pg, owner=owner)
    other, third = seed_conversation(pg)
    for user, conversation in ((owner, first), (owner, second), (other, third)):
        seed_message(pg, user, conversation)
    initial = turn_values(owner, first, status="abandoned")
    pg.execute(TABLE.insert().values(**initial))
    reject_insert(pg, turn_values(owner, second, idempotency_key=initial["idempotency_key"]), "uq_assistant_turns_user_key")
    reject_insert(pg, turn_values(owner, first, status="abandoned"), "uq_assistant_turns_user_message")
    pg.execute(TABLE.insert().values(**turn_values(other, third, idempotency_key=initial["idempotency_key"])))


@pytest.mark.parametrize("first_state", ["pending", "failed"])
def test_postgres_one_unresolved_turn_and_abandonment_releases_slot(pg, first_state):
    owner, conversation = seed_conversation(pg)
    for sequence in (1, 3):
        seed_message(pg, owner, conversation, sequence)
    initial = turn_values(owner, conversation, status=first_state)
    pg.execute(TABLE.insert().values(**initial))
    following = turn_values(owner, conversation, sequence=3)
    reject_insert(pg, following, "uq_assistant_turns_unresolved_conversation")
    pg.execute(TABLE.update().where(TABLE.c.id == initial["id"]).values(
        status="abandoned", error_code=None, lease_expires_at=None, attempt_finished_at=STAMP,
    ))
    pg.execute(TABLE.insert().values(**following))


def test_postgres_completed_turn_does_not_block_new_pending_turn(pg):
    owner, conversation = seed_conversation(pg)
    for sequence, role in ((1, "user"), (2, "assistant"), (3, "user")):
        seed_message(pg, owner, conversation, sequence, role)
    pg.execute(TABLE.insert().values(**turn_values(owner, conversation, status="completed")))
    pg.execute(TABLE.insert().values(**turn_values(owner, conversation, sequence=3)))


def test_postgres_reply_link_is_deferred_but_required_and_conversation_scoped(pg):
    owner, conversation = seed_conversation(pg)
    _, other_conversation = seed_conversation(pg, owner=owner)
    seed_message(pg, owner, conversation)
    seed_message(pg, owner, other_conversation, 2, "assistant")
    values = turn_values(owner, conversation, status="completed")
    pg.execute(TABLE.insert().values(**values))  # Missing reply is allowed until constraint validation.
    with pytest.raises(IntegrityError) as caught:
        with pg.begin_nested():
            pg.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
    assert caught.value.orig.diag.constraint_name == "fk_assistant_turns_assistant_message"
    seed_message(pg, owner, conversation, 2, "assistant")
    pg.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
    assert pg.scalar(select(TABLE.c.assistant_sequence_no)) == 2


def test_postgres_reply_delete_is_no_action_and_conversation_delete_cascades(pg):
    owner, conversation = seed_conversation(pg)
    seed_message(pg, owner, conversation)
    reply = seed_message(pg, owner, conversation, 2, "assistant")
    pg.execute(TABLE.insert().values(**turn_values(owner, conversation, status="completed")))
    with pytest.raises(IntegrityError) as caught:
        with pg.begin_nested():
            pg.execute(AssistantMessage.__table__.delete().where(AssistantMessage.id == reply))
            pg.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
    assert caught.value.orig.diag.constraint_name == "fk_assistant_turns_assistant_message"
    pg.execute(AssistantConversation.__table__.delete().where(AssistantConversation.id == conversation))
    pg.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
    assert pg.scalar(select(TABLE.c.id)) is None
    assert pg.scalar(select(AssistantMessage.id)) is None
    assert pg.scalar(select(User.id)) == owner


def test_postgres_user_message_delete_cascades_turn_only(pg):
    owner, conversation = seed_conversation(pg)
    message = seed_message(pg, owner, conversation)
    pg.execute(TABLE.insert().values(**turn_values(owner, conversation)))
    pg.execute(AssistantMessage.__table__.delete().where(AssistantMessage.id == message))
    assert pg.scalar(select(TABLE.c.id)) is None
    assert pg.scalar(select(AssistantConversation.id)) == conversation


def test_postgres_sequence_upper_bound_model_length_and_attempt_boundary(pg):
    owner, conversation = seed_conversation(pg)
    seed_message(pg, owner, conversation, 2147483646)
    seed_message(pg, owner, conversation, 2147483647, "assistant")
    pg.execute(TABLE.insert().values(**turn_values(owner, conversation, sequence=2147483646, status="completed", attempt_no=3, model_name="x" * 160)))
    _, another = seed_conversation(pg, owner=owner)
    seed_message(pg, owner, another)
    with pytest.raises(DataError):
        with pg.begin_nested():
            pg.execute(TABLE.insert().values(**turn_values(owner, another, model_name="x" * 161)))


def test_assistant_turn_migration_roundtrip_preserves_legacy_messages():
    with isolated_schema() as connection:
        config = migration_config(connection)
        command.upgrade(config, PARENT)
        assert "assistant_turns" not in inspect(connection).get_table_names()
        owner, conversation = seed_conversation(connection)
        message = seed_message(connection, owner, conversation)
        before = connection.execute(select(AssistantMessage.__table__)).mappings().one()
        connection.commit()
        command.upgrade(config, REVISION)
        assert MigrationContext.configure(connection).get_current_heads() == (REVISION,)
        assert connection.execute(select(AssistantMessage.__table__)).mappings().one() == before
        assert connection.scalar(select(TABLE.c.id)) is None  # No legacy backfill.
        connection.execute(TABLE.insert().values(**turn_values(owner, conversation, status="abandoned")))
        connection.commit()
        command.downgrade(config, PARENT)
        assert "assistant_turns" not in inspect(connection).get_table_names()
        assert connection.execute(select(AssistantMessage.__table__)).mappings().one() == before
        assert connection.scalar(select(AssistantMessage.id)) == message
        assert connection.scalar(select(AssistantConversation.id)) == conversation
        connection.commit()
        command.upgrade(config, REVISION)
        assert connection.execute(select(AssistantMessage.__table__)).mappings().one() == before
        assert connection.scalar(select(TABLE.c.id)) is None
