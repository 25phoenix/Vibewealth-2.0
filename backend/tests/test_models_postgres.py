"""Opt-in PostgreSQL integration checks for model-specific DDL behavior."""

import os
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.config import Settings
from app.core.security import verify_password
from app.core.database import engine, get_db
from app.main import create_app
from app.models import (
    Account,
    AuthSession,
    AssistantConversation,
    AssistantMessage,
    Base,
    Budget,
    Category,
    GoalEntry,
    SavingsGoal,
    Transaction,
    User,
)
from app.services.auth_sessions import (
    create_session,
    generate_session_token,
    get_valid_session,
    revoke_session,
)
from app.services.authentication import AuthenticationError, get_current_user, login_user
from app.services import registration
from app.services.registration import DuplicateEmailError, register_user


@pytest.fixture
def postgres_model_session():
    """Create models in a disposable schema of a dedicated test database."""

    database_url = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set POSTGRES_TEST_DATABASE_URL to an isolated PostgreSQL test database")

    test_url = make_url(database_url)
    application_url = get_settings().sqlalchemy_url
    if test_url.drivername != "postgresql+psycopg":
        pytest.fail("POSTGRES_TEST_DATABASE_URL must use postgresql+psycopg")
    if test_url.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("POSTGRES_TEST_DATABASE_URL must target the local PostgreSQL service")
    if test_url.port != application_url.port:
        pytest.fail("POSTGRES_TEST_DATABASE_URL must use the configured local PostgreSQL port")
    if not test_url.database or test_url.database == application_url.database:
        pytest.fail(
            "POSTGRES_TEST_DATABASE_URL must name a database different from the application database"
        )

    engine = create_engine(test_url)
    schema = f"model_test_{uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            translated_connection = connection.execution_options(
                schema_translate_map={None: schema}
            )
            Base.metadata.create_all(translated_connection)

        test_engine = engine.execution_options(schema_translate_map={None: schema})
        factory = sessionmaker(bind=test_engine, class_=Session, expire_on_commit=False)
        with factory() as session:
            yield session
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        engine.dispose()


@pytest.fixture
def auth_http_client(postgres_model_session):
    """Exercise the actual HTTP layer using the existing isolated PG schema."""

    settings = Settings(
        _env_file=None,
        database_url=engine.url.render_as_string(hide_password=False),
        app_environment="development",
        allowed_frontend_origins=["http://localhost:5173"],
        allow_insecure_cookies=True,
        csrf_signing_secret="test-http-csrf-signing-secret-0123456789",
    )
    application = create_app(settings)

    def override_db():
        try:
            yield postgres_model_session
        except Exception:
            postgres_model_session.rollback()
            raise
        finally:
            if postgres_model_session.in_transaction():
                postgres_model_session.rollback()

    application.dependency_overrides[get_db] = override_db
    try:
        with TestClient(
            application,
            base_url="http://localhost:8000",
            raise_server_exceptions=False,
        ) as test_client:
            yield test_client, settings, postgres_model_session
    finally:
        application.dependency_overrides.clear()


def _make_financial_user(session: Session) -> tuple[User, Account, Category]:
    user = User(email=f"{uuid4().hex}@example.test", password_hash="test-hash")
    session.add(user)
    session.flush()
    account = Account(
        user_id=user.id,
        name="Primary",
        account_type="bank",
        is_default=True,
        opening_balance_paise=0,
        opening_balance_as_of=date(2026, 1, 1),
    )
    category = Category(user_id=user.id, name="Food", transaction_type="expense")
    session.add_all([account, category])
    session.flush()
    return user, account, category


def test_postgresql_uuid_timestamp_and_account_defaults(postgres_model_session):
    session = postgres_model_session
    user, account, _ = _make_financial_user(session)
    session.commit()

    assert user.id.version == 4
    assert account.id.version == 4
    assert user.created_at is not None and user.created_at.tzinfo is not None
    assert account.created_at is not None and account.created_at.tzinfo is not None
    assert account.is_default is True
    assert account.opening_balance_paise == 0


def test_postgresql_partial_unique_index_allows_at_most_one_default(postgres_model_session):
    session = postgres_model_session
    user, _, _ = _make_financial_user(session)
    session.add(
        Account(
            user_id=user.id,
            name="Second default",
            account_type="cash",
            is_default=True,
            opening_balance_paise=0,
            opening_balance_as_of=date(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_postgresql_active_category_name_uniqueness_and_archival(postgres_model_session):
    session = postgres_model_session
    user, _, _ = _make_financial_user(session)
    session.commit()

    session.add(Category(user_id=user.id, name="food", transaction_type="expense"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    original = session.scalar(
        select(Category).where(Category.user_id == user.id, Category.name == "Food")
    )
    historical_budget = Budget(
        user_id=user.id,
        category_id=original.id,
        month_start=date(2026, 1, 1),
        limit_paise=500,
    )
    session.add(historical_budget)
    session.commit()

    original = session.get(Category, original.id)
    original.archived_at = datetime.now(timezone.utc)
    session.add_all(
        [
            Category(user_id=user.id, name="Food", transaction_type="expense"),
            Category(user_id=user.id, name="Other", transaction_type="income"),
            Category(user_id=user.id, name="Other", transaction_type="expense"),
        ]
    )
    session.commit()
    assert session.get(Budget, historical_budget.id) is not None


def test_postgresql_budget_uniqueness_for_overall_and_category_budgets(
    postgres_model_session,
):
    session = postgres_model_session
    user, _, category = _make_financial_user(session)
    session.add_all(
        [
            Budget(user_id=user.id, category_id=None, month_start=date(2026, 1, 1), limit_paise=1000),
            Budget(user_id=user.id, category_id=category.id, month_start=date(2026, 1, 1), limit_paise=500),
        ]
    )
    session.commit()

    session.add(Budget(user_id=user.id, category_id=None, month_start=date(2026, 1, 1), limit_paise=2000))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(
        Budget(user_id=user.id, category_id=category.id, month_start=date(2026, 1, 1), limit_paise=800)
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_postgresql_check_constraints_reject_invalid_values(postgres_model_session):
    session = postgres_model_session
    user, account, category = _make_financial_user(session)
    session.commit()

    session.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            category_id=category.id,
            transaction_type="expense",
            amount_paise=0,
            description="Invalid amount",
            transaction_date=date(2026, 1, 2),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    session.add(Category(user_id=user.id, name="Invalid category", transaction_type="both"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    session.add(
        Budget(
            user_id=user.id,
            month_start=date(2026, 1, 2),
            limit_paise=100,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    session.add(
        Account(
            user_id=user.id,
            name="Invalid type",
            account_type="credit_card",
            opening_balance_paise=0,
            opening_balance_as_of=date(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    goal = SavingsGoal(user_id=user.id, name="Check goal", target_paise=1000)
    conversation = AssistantConversation(user_id=user.id)
    session.add_all([goal, conversation])
    session.commit()

    session.add(
        GoalEntry(
            user_id=user.id,
            goal_id=goal.id,
            account_id=account.id,
            entry_type="transfer",
            amount_paise=100,
            effective_date=date(2026, 1, 2),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    for sequence_no, role, content in (
        (0, "user", "Valid content"),
        (1, "system", "Valid content"),
        (1, "user", " "),
    ):
        session.add(
            AssistantMessage(
                user_id=user.id,
                conversation_id=conversation.id,
                sequence_no=sequence_no,
                role=role,
                content=content,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


@pytest.mark.parametrize(
    "reference",
    ["transaction_account", "transaction_category", "budget_category", "goal", "goal_account", "conversation"],
)
def test_postgresql_composite_foreign_keys_reject_cross_user_references(
    postgres_model_session, reference: str
):
    session = postgres_model_session
    user_a, account_a, category_a = _make_financial_user(session)
    user_b, account_b, category_b = _make_financial_user(session)
    goal_a = SavingsGoal(user_id=user_a.id, name="Goal A", target_paise=1000)
    goal_b = SavingsGoal(user_id=user_b.id, name="Goal B", target_paise=1000)
    conversation_b = AssistantConversation(user_id=user_b.id)
    session.add_all([goal_a, goal_b, conversation_b])
    session.commit()

    if reference == "transaction_account":
        invalid = Transaction(
            user_id=user_a.id,
            account_id=account_b.id,
            category_id=category_a.id,
            transaction_type="expense",
            amount_paise=100,
            description="Cross-user account",
            transaction_date=date(2026, 1, 2),
        )
    elif reference == "transaction_category":
        invalid = Transaction(
            user_id=user_a.id,
            account_id=account_a.id,
            category_id=category_b.id,
            transaction_type="expense",
            amount_paise=100,
            description="Cross-user category",
            transaction_date=date(2026, 1, 2),
        )
    elif reference == "budget_category":
        invalid = Budget(
            user_id=user_a.id,
            category_id=category_b.id,
            month_start=date(2026, 1, 1),
            limit_paise=1000,
        )
    elif reference == "goal":
        invalid = GoalEntry(
            user_id=user_a.id,
            goal_id=goal_b.id,
            account_id=account_a.id,
            entry_type="contribution",
            amount_paise=100,
            effective_date=date(2026, 1, 2),
        )
    elif reference == "goal_account":
        invalid = GoalEntry(
            user_id=user_a.id,
            goal_id=goal_a.id,
            account_id=account_b.id,
            entry_type="contribution",
            amount_paise=100,
            effective_date=date(2026, 1, 2),
        )
    else:
        invalid = AssistantMessage(
            user_id=user_a.id,
            conversation_id=conversation_b.id,
            sequence_no=1,
            role="user",
            content="Cross-user conversation",
        )

    session.add(invalid)
    with pytest.raises(IntegrityError):
        session.commit()


def test_postgresql_message_sequence_is_unique_and_conversation_delete_cascades(
    postgres_model_session,
):
    session = postgres_model_session
    user, _, _ = _make_financial_user(session)
    conversation = AssistantConversation(user_id=user.id)
    session.add(conversation)
    session.flush()
    message = AssistantMessage(
        user_id=user.id,
        conversation_id=conversation.id,
        sequence_no=1,
        role="user",
        content="Hello",
    )
    session.add(message)
    session.commit()

    session.add(
        AssistantMessage(
            user_id=user.id,
            conversation_id=conversation.id,
            sequence_no=1,
            role="assistant",
            content="Duplicate sequence",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    conversation = session.get(AssistantConversation, conversation.id)
    session.delete(conversation)
    session.commit()
    assert session.scalar(
        select(func.count()).select_from(AssistantMessage).where(
            AssistantMessage.conversation_id == conversation.id
        )
    ) == 0


def test_postgresql_deferrable_ownership_fks_allow_user_cascade_and_restrict_account_delete(
    postgres_model_session,
):
    session = postgres_model_session
    user, account, category = _make_financial_user(session)
    transaction = Transaction(
        user_id=user.id,
        account_id=account.id,
        category_id=category.id,
        transaction_type="expense",
        amount_paise=100,
        description="Test expense",
        transaction_date=date(2026, 1, 2),
    )
    goal = SavingsGoal(user_id=user.id, name="Test goal", target_paise=1000)
    conversation = AssistantConversation(user_id=user.id)
    session.add_all([transaction, goal, conversation])
    session.flush()
    session.add(
        GoalEntry(
            user_id=user.id,
            goal_id=goal.id,
            account_id=account.id,
            entry_type="contribution",
            amount_paise=100,
            effective_date=date(2026, 1, 2),
        )
    )
    session.add(
        AssistantMessage(
            user_id=user.id,
            conversation_id=conversation.id,
            sequence_no=1,
            role="user",
            content="Hello",
        )
    )
    session.commit()

    session.delete(account)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    category = session.get(Category, category.id)
    session.delete(category)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    goal = session.get(SavingsGoal, goal.id)
    session.delete(goal)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    conversation = session.get(AssistantConversation, conversation.id)
    session.delete(conversation)
    session.commit()
    assert session.scalar(
        select(func.count()).select_from(AssistantMessage).where(
            AssistantMessage.conversation_id == conversation.id
        )
    ) == 0

    user = session.get(User, user.id)
    session.delete(user)
    session.commit()
    assert session.get(User, user.id) is None


def test_postgresql_auth_session_creation_and_multiple_sessions(postgres_model_session):
    session = postgres_model_session
    user, _, _ = _make_financial_user(session)
    session.commit()

    token_a, auth_session_a = create_session(session, user.id)
    token_b, auth_session_b = create_session(session, user.id)

    assert token_a != token_b
    assert auth_session_a.token_digest == hashlib.sha256(
        token_a.encode("ascii")
    ).digest()
    assert auth_session_a.token_digest != token_a.encode("ascii")
    assert len(auth_session_a.token_digest) == 32
    assert auth_session_a.created_at == auth_session_a.last_activity_at
    assert auth_session_a.absolute_expires_at - auth_session_a.created_at == timedelta(days=30)
    assert auth_session_b.user_id == user.id
    assert auth_session_a.id != auth_session_b.id
    assert session.in_transaction()
    session.commit()

    stored_digest = session.scalar(
        select(AuthSession.token_digest).where(AuthSession.id == auth_session_a.id)
    )
    assert stored_digest == auth_session_a.token_digest
    assert token_a.encode("ascii") != stored_digest


def test_postgresql_session_creation_does_not_commit_implicitly(postgres_model_session):
    session = postgres_model_session
    user, _, _ = _make_financial_user(session)
    session.commit()

    token, auth_session = create_session(session, user.id)
    assert session.in_transaction()
    digest = auth_session.token_digest
    session.rollback()

    assert session.scalar(
        select(AuthSession.id).where(AuthSession.token_digest == digest)
    ) is None
    assert token.encode("ascii") != digest


def test_postgresql_session_lookup_refreshes_activity_and_preserves_absolute_expiry(
    postgres_model_session,
):
    session = postgres_model_session
    user, _, _ = _make_financial_user(session)
    session.commit()
    token, auth_session = create_session(session, user.id)
    session.commit()
    absolute_expiry = auth_session.absolute_expires_at

    session.execute(
        update(AuthSession)
        .where(AuthSession.id == auth_session.id)
        .values(last_activity_at=func.clock_timestamp() - text("INTERVAL '1 minute'"))
        .execution_options(synchronize_session=False)
    )
    session.commit()
    previous_activity = session.scalar(
        select(AuthSession.last_activity_at).where(AuthSession.id == auth_session.id)
    )

    validated = get_valid_session(session, token)

    assert validated is not None
    validated_session, validated_user = validated
    assert validated_session.id == auth_session.id
    assert validated_user.id == user.id
    assert validated_session.last_activity_at > previous_activity
    assert validated_session.absolute_expires_at == absolute_expiry
    session.commit()


def test_postgresql_session_rejects_unknown_revoked_and_expired_tokens(
    postgres_model_session,
):
    session = postgres_model_session
    user, _, _ = _make_financial_user(session)
    session.commit()
    unknown_token = generate_session_token()
    revoked_token, revoked_session = create_session(session, user.id)
    absolute_token, absolute_session = create_session(session, user.id)
    idle_token, idle_session = create_session(session, user.id)
    session.commit()

    session.execute(
        update(AuthSession)
        .where(AuthSession.id == revoked_session.id)
        .values(revoked_at=func.clock_timestamp())
    )
    session.execute(
        update(AuthSession)
        .where(AuthSession.id == absolute_session.id)
        .values(absolute_expires_at=func.clock_timestamp())
    )
    session.execute(
        update(AuthSession)
        .where(AuthSession.id == idle_session.id)
        .values(last_activity_at=func.clock_timestamp() - text("INTERVAL '12 hours'"))
    )
    session.commit()

    assert get_valid_session(session, unknown_token) is None
    assert get_valid_session(session, revoked_token) is None
    assert get_valid_session(session, absolute_token) is None
    assert get_valid_session(session, idle_token) is None


def test_postgresql_revocation_is_idempotent_and_user_scoped(postgres_model_session):
    session = postgres_model_session
    user_a, _, _ = _make_financial_user(session)
    user_b = User(email=f"{uuid4().hex}@example.test", password_hash="test-hash")
    session.add(user_b)
    session.commit()
    token_a1, auth_session_a1 = create_session(session, user_a.id)
    token_a2, auth_session_a2 = create_session(session, user_a.id)
    token_b, auth_session_b = create_session(session, user_b.id)
    session.commit()

    assert revoke_session(
        session, session_id=auth_session_a1.id, user_id=user_b.id
    ) is False
    assert revoke_session(
        session, session_id=auth_session_a1.id, user_id=user_a.id
    ) is True
    assert revoke_session(
        session, session_id=auth_session_a1.id, user_id=user_a.id
    ) is False
    assert session.in_transaction()
    session.commit()

    session.expire(auth_session_a1)
    stored = session.get(AuthSession, auth_session_a1.id)
    assert stored is not None and stored.revoked_at is not None
    assert get_valid_session(session, token_a1) is None
    assert get_valid_session(session, token_a2) is not None
    assert get_valid_session(session, token_b) is not None
    assert auth_session_a2.id != auth_session_a1.id
    assert auth_session_b.user_id == user_b.id


def test_postgresql_concurrent_refreshes_never_move_activity_backwards(
    postgres_model_session,
):
    session = postgres_model_session
    user, _, _ = _make_financial_user(session)
    session.commit()
    token, auth_session = create_session(session, user.id)
    session.commit()
    absolute_expiry = auth_session.absolute_expires_at

    future_activity = session.scalar(
        select(func.clock_timestamp() + text("INTERVAL '5 seconds'"))
    )
    session.execute(
        update(AuthSession)
        .where(AuthSession.id == auth_session.id)
        .values(last_activity_at=future_activity)
    )
    session.commit()

    factory = sessionmaker(bind=session.get_bind(), class_=Session, expire_on_commit=False)

    def refresh_once() -> datetime:
        with factory() as concurrent_session:
            validated = get_valid_session(concurrent_session, token)
            assert validated is not None
            activity = validated[0].last_activity_at
            concurrent_session.commit()
            return activity

    with ThreadPoolExecutor(max_workers=6) as pool:
        observed_activities = list(pool.map(lambda _: refresh_once(), range(12)))

    session.expire(auth_session)
    final_session = session.get(AuthSession, auth_session.id)
    assert final_session is not None
    assert min(observed_activities) >= future_activity
    assert final_session.last_activity_at >= future_activity
    assert final_session.absolute_expires_at == absolute_expiry


def test_postgresql_registration_creates_complete_onboarding(postgres_model_session):
    session = postgres_model_session
    password = "correct horse battery staple"
    result = register_user(
        session,
        email="  Person.Example@Example.Test  ",
        password=password,
        display_name="Example Person",
        account_type="wallet",
    )

    assert session.in_transaction()
    assert result.email == "person.example@example.test"
    assert "raw" not in repr(result)
    user = session.get(User, result.user_id)
    assert user is not None
    assert user.email == "person.example@example.test"
    assert user.password_hash != password
    assert verify_password(password, user.password_hash)
    account_rows = session.scalars(
        select(Account).where(Account.user_id == user.id)
    ).all()
    assert len(account_rows) == 1
    account = account_rows[0]
    assert account.name == "Main Account"
    assert account.account_type == "wallet"
    assert account.is_default is True
    assert account.opening_balance_paise == 0
    assert account.opening_balance_as_of == registration._opening_balance_date()

    category_rows = session.scalars(
        select(Category).where(Category.user_id == user.id)
    ).all()
    assert len(category_rows) == 13
    assert {(row.name, row.transaction_type) for row in category_rows} == {
        (name, "expense")
        for name in (
            "Housing", "Groceries", "Food & dining", "Transport", "Bills & utilities",
            "Shopping", "Health", "Entertainment", "Education", "Other",
        )
    } | {(name, "income") for name in ("Salary", "Freelance", "Other")}

    stored_sessions = session.scalars(
        select(AuthSession).where(AuthSession.user_id == user.id)
    ).all()
    assert len(stored_sessions) == 1
    stored = stored_sessions[0]
    assert stored.revoked_at is None
    expected_digest = hashlib.sha256(result.session_token.encode("ascii")).digest()
    assert stored.token_digest == expected_digest
    assert stored.token_digest != result.session_token.encode("ascii")
    validated = get_valid_session(session, result.session_token)
    assert validated is not None
    assert validated[0].id == stored.id
    assert validated[1].id == user.id
    session.commit()


def test_postgresql_registration_rejects_case_insensitive_duplicate_email(
    postgres_model_session,
):
    session = postgres_model_session
    first = register_user(
        session,
        email="person@example.test",
        password="correct horse battery staple",
        account_type="cash",
    )
    session.commit()

    with pytest.raises(DuplicateEmailError, match="already exists"):
        register_user(
            session,
            email="  PERSON@EXAMPLE.TEST  ",
            password="correct horse battery staple",
            account_type="bank",
        )
    session.rollback()
    assert session.scalar(
        select(func.count()).select_from(User).where(
            func.lower(User.email) == first.email
        )
    ) == 1


@pytest.mark.parametrize("failure_stage", ["account", "categories", "session"])
def test_postgresql_registration_failures_rollback_without_partial_records(
    postgres_model_session, monkeypatch, failure_stage
):
    session = postgres_model_session

    if failure_stage == "account":
        monkeypatch.setattr(
            registration,
            "_create_default_account",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("account failure")),
        )
    elif failure_stage == "categories":
        monkeypatch.setattr(
            registration,
            "_seed_default_categories",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("category failure")),
        )
    else:
        monkeypatch.setattr(
            registration,
            "create_session",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("session failure")),
        )

    with pytest.raises(RuntimeError):
        register_user(
            session,
            email=f"rollback-{failure_stage}@example.test",
            password="correct horse battery staple",
            account_type="bank",
        )
    session.rollback()

    assert session.scalar(select(func.count()).select_from(User)) == 0
    assert session.scalar(select(func.count()).select_from(Account)) == 0
    assert session.scalar(select(func.count()).select_from(Category)) == 0
    assert session.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_postgresql_registration_concurrent_duplicate_email_race(
    postgres_model_session, monkeypatch
):
    session = postgres_model_session
    factory = sessionmaker(bind=session.get_bind(), class_=Session, expire_on_commit=False)
    barrier = Barrier(2)
    original_duplicate_check = registration._raise_if_email_exists

    def synchronized_duplicate_check(db, normalized_email):
        original_duplicate_check(db, normalized_email)
        barrier.wait(timeout=15)

    monkeypatch.setattr(registration, "_raise_if_email_exists", synchronized_duplicate_check)
    monkeypatch.setattr(registration, "hash_password", lambda _password: "test-only-hash")

    def attempt(email):
        with factory() as concurrent_session:
            try:
                result = register_user(
                    concurrent_session,
                    email=email,
                    password="correct horse battery staple",
                    account_type="cash",
                )
                concurrent_session.commit()
                return ("created", result.user_id)
            except DuplicateEmailError:
                concurrent_session.rollback()
                return ("duplicate", None)
            except Exception:
                concurrent_session.rollback()
                raise

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(attempt, [" RACE@Example.Test ", "race@example.test"])
        )

    assert sorted(kind for kind, _ in outcomes) == ["created", "duplicate"]
    assert session.scalar(
        select(func.count()).select_from(User).where(
            func.lower(User.email) == "race@example.test"
        )
    ) == 1


def test_postgresql_login_creates_a_new_session_without_revoking_existing(
    postgres_model_session,
):
    session = postgres_model_session
    password = "correct horse battery staple"
    registered = register_user(
        session,
        email="login@example.test",
        password=password,
        display_name="Login User",
        account_type="cash",
    )
    session.commit()

    result = login_user(
        session,
        email="  LOGIN@EXAMPLE.TEST ",
        password=password,
    )

    assert result.user_id == registered.user_id
    assert result.email == registered.email
    assert result.display_name == "Login User"
    assert result.session_token != registered.session_token
    assert session.in_transaction()
    old_session = get_valid_session(session, registered.session_token)
    new_session = get_valid_session(session, result.session_token)
    assert old_session is not None
    assert new_session is not None
    assert old_session[0].id != new_session[0].id
    assert old_session[1].id == new_session[1].id == registered.user_id
    expected_digest = hashlib.sha256(result.session_token.encode("ascii")).digest()
    assert new_session[0].token_digest == expected_digest
    assert new_session[0].token_digest != result.session_token.encode("ascii")
    active_sessions = session.scalars(
        select(AuthSession).where(
            AuthSession.user_id == registered.user_id,
            AuthSession.revoked_at.is_(None),
        )
    ).all()
    assert len(active_sessions) == 2
    session.commit()


def test_postgresql_login_failures_are_generic_and_create_no_sessions(
    postgres_model_session,
):
    session = postgres_model_session
    register_user(
        session,
        email="failure@example.test",
        password="correct horse battery staple",
        account_type="bank",
    )
    session.commit()

    failures = []
    for email, password in (
        ("failure@example.test", "incorrect password phrase"),
        ("unknown@example.test", "incorrect password phrase"),
    ):
        with pytest.raises(AuthenticationError) as raised:
            login_user(session, email=email, password=password)
        failures.append((type(raised.value), str(raised.value)))
        session.rollback()

    assert failures == [
        (AuthenticationError, "Invalid email or password"),
        (AuthenticationError, "Invalid email or password"),
    ]
    assert session.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_postgresql_login_rollback_removes_staged_session(postgres_model_session):
    session = postgres_model_session
    registered = register_user(
        session,
        email="login-rollback@example.test",
        password="correct horse battery staple",
        account_type="wallet",
    )
    session.commit()

    result = login_user(
        session,
        email=registered.email,
        password="correct horse battery staple",
    )
    digest = hashlib.sha256(result.session_token.encode("ascii")).digest()
    session.rollback()

    assert session.scalar(
        select(func.count()).select_from(AuthSession).where(
            AuthSession.token_digest == digest
        )
    ) == 0
    assert session.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_postgresql_current_user_refresh_is_caller_committed(postgres_model_session):
    session = postgres_model_session
    registered = register_user(
        session,
        email="current-user@example.test",
        password="correct horse battery staple",
        account_type="cash",
    )
    session.commit()
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.user_id == registered.user_id)
    )
    session.execute(
        update(AuthSession)
        .where(AuthSession.id == auth_session.id)
        .values(last_activity_at=func.clock_timestamp() - text("INTERVAL '1 minute'"))
    )
    session.commit()
    previous_activity = session.scalar(
        select(AuthSession.last_activity_at).where(AuthSession.id == auth_session.id)
    )

    current_user = get_current_user(
        session, session_token=registered.session_token
    )

    assert current_user is not None
    assert current_user.user_id == registered.user_id
    assert current_user.email == registered.email
    assert current_user.display_name is None
    assert current_user.session_id == auth_session.id
    assert session.in_transaction()
    refreshed_activity = session.scalar(
        select(AuthSession.last_activity_at).where(AuthSession.id == auth_session.id)
    )
    assert refreshed_activity > previous_activity
    session.rollback()

    rolled_back_activity = session.scalar(
        select(AuthSession.last_activity_at).where(AuthSession.id == auth_session.id)
    )
    assert rolled_back_activity == previous_activity


def test_postgresql_current_user_rejects_revoked_and_expired_sessions(
    postgres_model_session,
):
    session = postgres_model_session
    registered = register_user(
        session,
        email="session-expiry@example.test",
        password="correct horse battery staple",
        account_type="bank",
    )
    session.commit()
    token_revoked, revoked = create_session(session, registered.user_id)
    token_absolute, absolute = create_session(session, registered.user_id)
    token_idle, idle = create_session(session, registered.user_id)
    session.commit()

    session.execute(
        update(AuthSession)
        .where(AuthSession.id == revoked.id)
        .values(revoked_at=func.clock_timestamp())
    )
    session.execute(
        update(AuthSession)
        .where(AuthSession.id == absolute.id)
        .values(absolute_expires_at=func.clock_timestamp())
    )
    session.execute(
        update(AuthSession)
        .where(AuthSession.id == idle.id)
        .values(last_activity_at=func.clock_timestamp() - text("INTERVAL '12 hours'"))
    )
    session.commit()

    for token in (token_revoked, token_absolute, token_idle):
        assert get_current_user(session, session_token=token) is None
        session.rollback()


def _auth_cookie(response) -> SimpleCookie:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie


def _origin_headers(origin="http://localhost:5173"):
    return {"Origin": origin}


def test_http_registration_returns_safe_user_and_host_only_session_cookie(
    auth_http_client,
):
    client, settings, session = auth_http_client
    password = "correct horse battery staple"

    response = client.post(
        "/api/auth/register",
        headers=_origin_headers(),
        json={
            "email": "  Web.User@Example.Test ",
            "password": password,
            "display_name": "Web User",
            "account_type": "wallet",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "web.user@example.test"
    assert body["display_name"] == "Web User"
    assert set(body) == {"id", "email", "display_name"}
    cookie = _auth_cookie(response)[settings.auth_cookie_name]
    assert cookie.value
    assert cookie["httponly"] is True
    assert cookie["secure"] == ""
    assert cookie["samesite"].lower() == "lax"
    assert cookie["path"] == "/"
    assert cookie["domain"] == ""
    assert response.headers["cache-control"] == "no-store"
    assert cookie.value not in response.text
    assert password not in response.text

    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.user_id == UUID(body["id"]))
    )
    assert auth_session is not None
    assert auth_session.token_digest != cookie.value.encode("ascii")
    cookie_expiry = parsedate_to_datetime(cookie["expires"])
    assert cookie_expiry <= auth_session.absolute_expires_at


def test_http_production_registration_uses_secure_host_cookie(postgres_model_session):
    session = postgres_model_session
    settings = Settings(
        _env_file=None,
        database_url=engine.url.render_as_string(hide_password=False),
        app_environment="production",
        allowed_frontend_origins=["https://app.example.test"],
        csrf_signing_secret="production-test-key-material-that-is-not-a-real-secret",
    )
    application = create_app(settings)

    def override_db():
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            if session.in_transaction():
                session.rollback()

    application.dependency_overrides[get_db] = override_db
    try:
        with TestClient(
            application,
            base_url="https://api.example.test",
            raise_server_exceptions=False,
        ) as client:
            response = client.post(
                "/api/auth/register",
                headers={"Origin": "https://app.example.test"},
                json={
                    "email": "production-cookie@example.test",
                    "password": "correct horse battery staple",
                    "account_type": "cash",
                },
            )
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 201
    cookie = _auth_cookie(response)[settings.auth_cookie_name]
    assert settings.auth_cookie_name.startswith("__Host-")
    assert cookie["secure"] is True
    assert cookie["httponly"] is True
    assert cookie["samesite"].lower() == "lax"
    assert cookie["path"] == "/"
    assert cookie["domain"] == ""


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "invalid", "password": "correct horse battery staple", "account_type": "cash"},
        {"email": "valid@example.test", "password": "short", "account_type": "cash"},
        {"email": "valid@example.test", "password": "correct horse battery staple", "account_type": "loan"},
    ],
)
def test_http_registration_validation_failures_set_no_cookie(auth_http_client, payload):
    client, _, session = auth_http_client

    response = client.post(
        "/api/auth/register", headers=_origin_headers(), json=payload
    )

    assert response.status_code == 422
    assert response.headers.get("set-cookie") is None
    assert session.scalar(select(func.count()).select_from(User)) == 0


def test_http_duplicate_registration_returns_409_without_replacing_cookie(
    auth_http_client,
):
    client, _, session = auth_http_client
    payload = {
        "email": "duplicate@example.test",
        "password": "correct horse battery staple",
        "account_type": "cash",
    }
    first = client.post("/api/auth/register", headers=_origin_headers(), json=payload)
    assert first.status_code == 201

    duplicate = client.post(
        "/api/auth/register",
        headers=_origin_headers(),
        json={**payload, "email": " DUPLICATE@EXAMPLE.TEST "},
    )

    assert duplicate.status_code == 409
    assert duplicate.headers.get("set-cookie") is None
    assert "token" not in duplicate.text.lower()
    assert session.scalar(select(func.count()).select_from(User)) == 1


def test_http_registration_unexpected_failure_rolls_back_and_sets_no_cookie(
    auth_http_client, monkeypatch
):
    client, _, session = auth_http_client
    monkeypatch.setattr(
        registration,
        "_seed_default_categories",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("injected failure")),
    )

    response = client.post(
        "/api/auth/register",
        headers=_origin_headers(),
        json={
            "email": "rollback-http@example.test",
            "password": "correct horse battery staple",
            "account_type": "bank",
        },
    )

    assert response.status_code == 500
    assert response.headers.get("set-cookie") is None
    assert session.scalar(select(func.count()).select_from(User)) == 0
    assert session.scalar(select(func.count()).select_from(Account)) == 0
    assert session.scalar(select(func.count()).select_from(Category)) == 0
    assert session.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_http_login_creates_another_session_and_returns_safe_response(auth_http_client):
    client, settings, session = auth_http_client
    password = "correct horse battery staple"
    registered = register_user(
        session,
        email="login-http@example.test",
        password=password,
        account_type="cash",
    )
    session.commit()
    original_token = registered.session_token

    response = client.post(
        "/api/auth/login",
        headers=_origin_headers(),
        json={"email": " LOGIN-HTTP@EXAMPLE.TEST ", "password": password},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": str(registered.user_id),
        "email": registered.email,
        "display_name": None,
    }
    cookie = _auth_cookie(response)[settings.auth_cookie_name]
    assert cookie.value != original_token
    assert cookie["httponly"] is True
    assert cookie["samesite"].lower() == "lax"
    assert cookie["path"] == "/"
    assert cookie["domain"] == ""
    assert cookie.value not in response.text

    assert get_valid_session(session, original_token) is not None
    new_session = get_valid_session(session, cookie.value)
    assert new_session is not None
    assert parsedate_to_datetime(cookie["expires"]) <= new_session[0].absolute_expires_at
    active = session.scalars(
        select(AuthSession).where(
            AuthSession.user_id == registered.user_id,
            AuthSession.revoked_at.is_(None),
        )
    ).all()
    assert len(active) == 2
    session.commit()


def test_http_login_failure_is_generic_and_sets_no_cookie(auth_http_client):
    client, _, session = auth_http_client
    register_user(
        session,
        email="login-failure-http@example.test",
        password="correct horse battery staple",
        account_type="bank",
    )
    session.commit()

    wrong_password = client.post(
        "/api/auth/login",
        headers=_origin_headers(),
        json={"email": "login-failure-http@example.test", "password": "wrong password"},
    )
    unknown_email = client.post(
        "/api/auth/login",
        headers=_origin_headers(),
        json={"email": "unknown-http@example.test", "password": "wrong password"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {
        "detail": "Invalid email or password"
    }
    assert wrong_password.headers.get("set-cookie") is None
    assert unknown_email.headers.get("set-cookie") is None
    assert "login-failure-http@example.test" not in wrong_password.text
    assert "unknown-http@example.test" not in unknown_email.text
    assert session.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_http_current_user_requires_cookie_and_returns_safe_identity(auth_http_client):
    client, settings, _ = auth_http_client
    missing = client.get("/api/auth/me")
    assert missing.status_code == 401

    token = generate_session_token()
    client.cookies.set(settings.auth_cookie_name, token)
    unknown = client.get("/api/auth/me")
    assert unknown.status_code == 401

    # Replace the syntactically valid but unknown token with a real test session.
    client.cookies.clear()
    session = auth_http_client[2]
    registered = register_user(
        session,
        email="me-http@example.test",
        password="correct horse battery staple",
        account_type="wallet",
    )
    session.commit()
    client.cookies.set(settings.auth_cookie_name, registered.session_token)
    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(registered.user_id),
        "email": registered.email,
        "display_name": None,
    }
    assert response.headers["cache-control"] == "no-store"
    assert registered.session_token not in response.text


def test_http_current_user_commits_activity_refresh(auth_http_client):
    client, settings, session = auth_http_client
    registered = register_user(
        session,
        email="me-refresh-http@example.test",
        password="correct horse battery staple",
        account_type="bank",
    )
    session.commit()
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.user_id == registered.user_id)
    )
    session.execute(
        update(AuthSession)
        .where(AuthSession.id == auth_session.id)
        .values(last_activity_at=func.clock_timestamp() - text("INTERVAL '1 minute'"))
    )
    session.commit()
    previous_activity = session.scalar(
        select(AuthSession.last_activity_at).where(AuthSession.id == auth_session.id)
    )
    client.cookies.set(settings.auth_cookie_name, registered.session_token)

    response = client.get("/api/auth/me")

    refreshed = session.scalar(
        select(AuthSession.last_activity_at).where(AuthSession.id == auth_session.id)
    )
    assert response.status_code == 200
    assert refreshed > previous_activity


@pytest.mark.parametrize("state", ["revoked", "idle_expired", "absolute_expired"])
def test_http_current_user_rejects_revoked_or_expired_cookie(auth_http_client, state):
    client, settings, session = auth_http_client
    registered = register_user(
        session,
        email=f"me-{state}-http@example.test",
        password="correct horse battery staple",
        account_type="cash",
    )
    session.commit()
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.user_id == registered.user_id)
    )
    if state == "revoked":
        session.execute(
            update(AuthSession)
            .where(AuthSession.id == auth_session.id)
            .values(revoked_at=func.clock_timestamp())
        )
    elif state == "idle_expired":
        session.execute(
            update(AuthSession)
            .where(AuthSession.id == auth_session.id)
            .values(last_activity_at=func.clock_timestamp() - text("INTERVAL '12 hours'"))
        )
    else:
        session.execute(
            update(AuthSession)
            .where(AuthSession.id == auth_session.id)
            .values(absolute_expires_at=func.clock_timestamp())
        )
    session.commit()
    client.cookies.set(settings.auth_cookie_name, registered.session_token)

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    assert client.get("/api/auth/csrf").status_code == 401
    assert client.post(
        "/api/auth/logout",
        headers={**_origin_headers(), "X-CSRF-Token": "irrelevant"},
    ).status_code == 401


def test_http_csrf_token_is_session_bound_and_not_cached_or_cookied(auth_http_client):
    client, settings, session = auth_http_client
    registered = register_user(
        session,
        email="csrf-http@example.test",
        password="correct horse battery staple",
        account_type="bank",
    )
    session.commit()
    client.cookies.set(settings.auth_cookie_name, registered.session_token)

    first = client.get("/api/auth/csrf")
    second = client.get("/api/auth/csrf")

    assert first.status_code == second.status_code == 200
    token = first.json()["csrf_token"]
    assert token == second.json()["csrf_token"]
    assert registered.session_token not in token
    assert "set-cookie" not in first.headers
    assert first.headers["cache-control"] == "no-store"
    assert token not in str(first.request.url)
    assert session.scalar(select(func.count()).select_from(AuthSession)) == 1


@pytest.mark.parametrize("csrf_header", [None, "modified-token"])
def test_http_logout_rejects_missing_or_modified_csrf_without_revoking(
    auth_http_client, csrf_header
):
    client, settings, session = auth_http_client
    registered = register_user(
        session,
        email=f"logout-reject-{csrf_header is None}@example.test",
        password="correct horse battery staple",
        account_type="cash",
    )
    session.commit()
    client.cookies.set(settings.auth_cookie_name, registered.session_token)
    headers = _origin_headers()
    if csrf_header is not None:
        headers["X-CSRF-Token"] = csrf_header

    response = client.post("/api/auth/logout", headers=headers)

    assert response.status_code == 403
    assert response.headers.get("set-cookie") is None
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.user_id == registered.user_id)
    )
    assert auth_session.revoked_at is None


def test_http_logout_rejects_csrf_token_from_another_session(auth_http_client):
    client, settings, session = auth_http_client
    registered = register_user(
        session,
        email="csrf-cross-session@example.test",
        password="correct horse battery staple",
        account_type="cash",
    )
    session.commit()
    other_token, other_session = create_session(session, registered.user_id)
    session.commit()

    client.cookies.set(settings.auth_cookie_name, other_token)
    other_csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    client.cookies.set(settings.auth_cookie_name, registered.session_token)
    response = client.post(
        "/api/auth/logout",
        headers={**_origin_headers(), "X-CSRF-Token": other_csrf},
    )

    assert response.status_code == 403
    assert session.get(AuthSession, other_session.id).revoked_at is None
    assert get_valid_session(session, registered.session_token) is not None
    session.rollback()


def test_http_logout_revokes_only_current_session_and_clears_matching_cookie(
    auth_http_client,
):
    client, settings, session = auth_http_client
    registered = register_user(
        session,
        email="logout-success@example.test",
        password="correct horse battery staple",
        account_type="wallet",
    )
    session.commit()
    other_token, other_session = create_session(session, registered.user_id)
    session.commit()
    client.cookies.set(settings.auth_cookie_name, registered.session_token)
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]

    response = client.post(
        "/api/auth/logout",
        headers={**_origin_headers(), "X-CSRF-Token": csrf},
    )

    assert response.status_code == 204
    assert response.content == b""
    cleared = _auth_cookie(response)[settings.auth_cookie_name]
    assert cleared.value == ""
    assert cleared["max-age"] == "0"
    assert cleared["httponly"] is True
    assert cleared["secure"] == ""
    assert cleared["samesite"].lower() == "lax"
    assert cleared["path"] == "/"
    assert cleared["domain"] == ""
    current_session = session.scalar(
        select(AuthSession).where(AuthSession.user_id == registered.user_id,
                                  AuthSession.token_digest == hashlib.sha256(registered.session_token.encode("ascii")).digest())
    )
    assert current_session is not None and current_session.revoked_at is not None
    assert get_valid_session(session, other_token) is not None
    session.commit()


@pytest.mark.parametrize("headers", [{}, {"Referer": "http://localhost:5173/login"}])
def test_http_logout_requires_valid_session_before_csrf(auth_http_client, headers):
    client, settings, _ = auth_http_client
    response = client.post("/api/auth/logout", headers=headers)
    assert response.status_code == 401
