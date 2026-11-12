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
from sqlalchemy import create_engine, event, func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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
from app.core.financial import financial_today
from app.core.financial import MAX_SAFE_PAISE
from app.services.accounts import (
    AccountOpeningBalanceLockedError,
    get_account,
    update_account,
)
from app.services.budgets import DuplicateBudgetError, create_budget
from app.services.goals import (
    ExcessiveGoalWithdrawalError,
    GoalAllocationLimitExceededError,
    GoalNotFoundError,
    InsufficientAvailableToSpendError,
    create_goal,
    create_goal_entry,
    delete_goal,
    get_goal,
)
from app.services.transactions import InvalidTransactionError, create_transaction


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


def _authenticated_finance_headers(client, settings, session, user):
    token, _ = create_session(session, user.id)
    session.commit()
    client.cookies.set(settings.auth_cookie_name, token)
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    return {**_origin_headers(), "X-CSRF-Token": response.json()["csrf_token"]}


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


def test_http_account_and_transaction_balances_filters_and_soft_deletes(auth_http_client):
    client, settings, session = auth_http_client
    user, account, expense_category = _make_financial_user(session)
    income_category = Category(
        user_id=user.id, name="Pay", transaction_type="income"
    )
    session.add(income_category)
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user)
    opening_date = account.opening_balance_as_of
    later_date = opening_date + timedelta(days=1)

    income = client.post(
        "/api/transactions",
        headers=headers,
        json={
            "account_id": str(account.id),
            "category_id": str(income_category.id),
            "transaction_type": "income",
            "amount_paise": 10000,
            "description": "Pay",
            "transaction_date": opening_date.isoformat(),
        },
    )
    expense = client.post(
        "/api/transactions",
        headers=headers,
        json={
            "account_id": str(account.id),
            "category_id": str(expense_category.id),
            "transaction_type": "expense",
            "amount_paise": 2500,
            "description": "Groceries",
            "transaction_date": opening_date.isoformat(),
        },
    )
    later_expense = client.post(
        "/api/transactions",
        headers=headers,
        json={
            "account_id": str(account.id),
            "category_id": str(expense_category.id),
            "transaction_type": "expense",
            "amount_paise": 1000,
            "description": "Transit",
            "transaction_date": later_date.isoformat(),
        },
    )

    assert income.status_code == expense.status_code == later_expense.status_code == 201
    assert income.json()["category_name"] == "Pay"
    assert expense.json()["amount_paise"] == 2500
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.user_id == user.id)
    )
    activity_before_account_read = auth_session.last_activity_at
    current = client.get("/api/accounts")
    session.refresh(auth_session)
    assert auth_session.last_activity_at >= activity_before_account_read
    detail = client.get(f"/api/accounts/{account.id}")
    balance_at_open = client.get(
        f"/api/accounts/{account.id}/balance?as_of={opening_date.isoformat()}"
    )
    balance_current = client.get(f"/api/accounts/{account.id}/balance")
    assert current.status_code == detail.status_code == 200
    assert current.json()[0]["balance_paise"] == 6500
    assert current.json()[0]["goal_allocated_paise"] == 0
    assert current.json()[0]["available_to_spend_paise"] == 6500
    assert detail.json()["balance_paise"] == 6500
    assert balance_at_open.json() == {
        "account_id": str(account.id),
        "balance_paise": 7500,
        "goal_allocated_paise": 0,
        "available_to_spend_paise": 7500,
        "as_of": opening_date.isoformat(),
    }
    assert balance_current.json()["balance_paise"] == 6500
    assert current.headers["cache-control"] == "no-store"

    deleted = Transaction(
        user_id=user.id,
        account_id=account.id,
        category_id=expense_category.id,
        transaction_type="expense",
        amount_paise=9900,
        description="Soft deleted",
        transaction_date=later_date,
        deleted_at=datetime.now(timezone.utc),
    )
    session.add(deleted)
    session.commit()
    assert client.get(f"/api/accounts/{account.id}/balance").json()["balance_paise"] == 6500

    transaction_list = client.get(
        "/api/transactions",
        params={
            "account_id": str(account.id),
            "transaction_type": "expense",
            "category_id": str(expense_category.id),
            "date_from": opening_date.isoformat(),
            "date_to": later_date.isoformat(),
            "limit": 1,
            "offset": 1,
        },
    )
    assert transaction_list.status_code == 200
    assert transaction_list.json()["total"] == 2
    assert len(transaction_list.json()["items"]) == 1
    assert transaction_list.json()["items"][0]["id"] == expense.json()["id"]
    assert transaction_list.json()["items"][0]["category_name"] == "Food"
    assert transaction_list.headers["cache-control"] == "no-store"
    income_id = income.json()["id"]
    assert client.get(f"/api/transactions/{income_id}").status_code == 200
    assert client.get(f"/api/transactions/{deleted.id}").status_code == 404


def test_http_financial_routes_reject_cross_user_ids_and_categories(auth_http_client):
    client, settings, session = auth_http_client
    user_a, account_a, expense_a = _make_financial_user(session)
    user_b, account_b, expense_b = _make_financial_user(session)
    session.commit()
    transaction_b = Transaction(
        user_id=user_b.id,
        account_id=account_b.id,
        category_id=expense_b.id,
        transaction_type="expense",
        amount_paise=500,
        description="Private transaction",
        transaction_date=account_b.opening_balance_as_of,
    )
    session.add(transaction_b)
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user_a)

    assert client.get(f"/api/accounts/{account_b.id}").status_code == 404
    assert client.get(f"/api/transactions/{transaction_b.id}").status_code == 404
    assert client.get(
        "/api/transactions", params={"account_id": str(account_b.id)}
    ).json()["total"] == 0

    foreign_account = client.post(
        "/api/transactions",
        headers=headers,
        json={
            "account_id": str(account_b.id),
            "category_id": str(expense_a.id),
            "transaction_type": "expense",
            "amount_paise": 100,
            "description": "Attempt",
            "transaction_date": account_a.opening_balance_as_of.isoformat(),
        },
    )
    foreign_category = client.post(
        "/api/transactions",
        headers=headers,
        json={
            "account_id": str(account_a.id),
            "category_id": str(expense_b.id),
            "transaction_type": "expense",
            "amount_paise": 100,
            "description": "Attempt",
            "transaction_date": account_a.opening_balance_as_of.isoformat(),
        },
    )
    assert foreign_account.status_code == 404
    assert foreign_category.status_code == 422


def test_http_category_list_is_active_and_tenant_scoped(auth_http_client):
    client, settings, session = auth_http_client
    user_a, _, _ = _make_financial_user(session)
    user_b, _, _ = _make_financial_user(session)
    own_active = Category(
        user_id=user_a.id, name="Travel", transaction_type="expense"
    )
    own_archived = Category(
        user_id=user_a.id,
        name="Old category",
        transaction_type="expense",
        archived_at=datetime.now(timezone.utc),
    )
    foreign_active = Category(
        user_id=user_b.id, name="Private", transaction_type="income"
    )
    session.add_all([own_active, own_archived, foreign_active])
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user_a)

    response = client.get("/api/categories", headers=headers)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    returned = response.json()
    returned_ids = {item["id"] for item in returned}
    assert str(own_active.id) in returned_ids
    assert str(own_archived.id) not in returned_ids
    assert str(foreign_active.id) not in returned_ids
    assert all(set(item) == {"id", "name", "transaction_type"} for item in returned)


def test_historical_daily_balances_stay_within_javascript_safe_integer(auth_http_client):
    client, settings, session = auth_http_client
    user, account, expense_category = _make_financial_user(session)
    today = financial_today()
    day_one = today - timedelta(days=2)
    day_two = today - timedelta(days=1)
    account.opening_balance_paise = 0
    account.opening_balance_as_of = day_one
    income_category = Category(
        user_id=user.id, name="Income", transaction_type="income"
    )
    session.add(income_category)
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user)
    maximum = 2**53 - 1

    def post(category_id, transaction_type, amount_paise, transaction_date):
        return client.post(
            "/api/transactions",
            headers=headers,
            json={
                "account_id": str(account.id),
                "category_id": str(category_id),
                "transaction_type": transaction_type,
                "amount_paise": amount_paise,
                "description": "Boundary entry",
                "transaction_date": transaction_date.isoformat(),
            },
        )

    # Reaching the safe limit on separate historical days remains valid.
    assert post(income_category.id, "income", maximum, day_one).status_code == 201
    assert post(expense_category.id, "expense", maximum, day_two).status_code == 201

    day_one_balance = client.get(
        f"/api/accounts/{account.id}/balance?as_of={day_one.isoformat()}"
    )
    day_two_balance = client.get(
        f"/api/accounts/{account.id}/balance?as_of={day_two.isoformat()}"
    )
    today_balance = client.get(f"/api/accounts/{account.id}/balance")
    assert day_one_balance.json()["balance_paise"] == maximum
    assert day_two_balance.json()["balance_paise"] == 0
    assert today_balance.json()["balance_paise"] == 0

    # This backdated income would make day one 2 * maximum while leaving the
    # current balance at zero. It must be rejected based on the intermediate day.
    intermediate_overflow = post(
        income_category.id, "income", maximum, day_one
    )
    assert intermediate_overflow.status_code == 422
    assert "daily account balance" in intermediate_overflow.json()["detail"]

    # The upper safe-integer boundary is checked independently, including one
    # paise over. The expense floor rejects spending from a zero balance.
    positive_overflow = post(income_category.id, "income", 1, day_one)
    expense_below_zero = post(expense_category.id, "expense", 1, today)
    assert positive_overflow.status_code == expense_below_zero.status_code == 422

    # Rejected writes are rolled back at the HTTP boundary, and the session can
    # still query the database and return the original historical balances.
    assert session.scalar(
        select(func.count()).select_from(Transaction).where(
            Transaction.user_id == user.id
        )
    ) == 2
    final_balances = [
        day_one_balance.json()["balance_paise"],
        day_two_balance.json()["balance_paise"],
        today_balance.json()["balance_paise"],
    ]
    assert all(-maximum <= balance <= maximum for balance in final_balances)
    assert client.get(
        f"/api/accounts/{account.id}/balance?as_of={day_one.isoformat()}"
    ).json()["balance_paise"] == maximum


def test_soft_deleted_transactions_do_not_affect_safe_balance_validation(
    auth_http_client,
):
    client, settings, session = auth_http_client
    user, account, _ = _make_financial_user(session)
    today = financial_today()
    account.opening_balance_as_of = today
    maximum = 2**53 - 1
    income_category = Category(
        user_id=user.id, name="Income", transaction_type="income"
    )
    session.add(income_category)
    session.flush()
    deleted_transaction = Transaction(
        user_id=user.id,
        account_id=account.id,
        category_id=income_category.id,
        transaction_type="income",
        amount_paise=maximum,
        description="Deleted import",
        transaction_date=today,
        deleted_at=datetime.now(timezone.utc),
    )
    session.add(deleted_transaction)
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user)

    active_transaction = client.post(
        "/api/transactions",
        headers=headers,
        json={
            "account_id": str(account.id),
            "category_id": str(income_category.id),
            "transaction_type": "income",
            "amount_paise": maximum,
            "description": "Live income",
            "transaction_date": today.isoformat(),
        },
    )

    assert active_transaction.status_code == 201
    balance = client.get(f"/api/accounts/{account.id}/balance")
    assert balance.status_code == 200
    assert balance.json()["balance_paise"] == maximum
    assert session.scalar(
        select(func.count()).select_from(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.deleted_at.is_(None),
        )
    ) == 1


@pytest.mark.parametrize("invalid_case", ["type", "archived", "future", "before_opening"])
def test_http_transaction_creation_rejects_invalid_category_and_dates(
    auth_http_client, invalid_case
):
    client, settings, session = auth_http_client
    user, account, expense_category = _make_financial_user(session)
    income_category = Category(
        user_id=user.id, name="Salary", transaction_type="income"
    )
    archived_category = Category(
        user_id=user.id,
        name="Archived",
        transaction_type="expense",
        archived_at=datetime.now(timezone.utc),
    )
    session.add_all([income_category, archived_category])
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user)
    category_id = expense_category.id
    transaction_type = "expense"
    transaction_date = account.opening_balance_as_of
    if invalid_case == "type":
        category_id = expense_category.id
        transaction_type = "income"
    elif invalid_case == "archived":
        category_id = archived_category.id
    elif invalid_case == "future":
        transaction_date = financial_today() + timedelta(days=1)
    else:
        transaction_date = account.opening_balance_as_of - timedelta(days=1)

    response = client.post(
        "/api/transactions",
        headers=headers,
        json={
            "account_id": str(account.id),
            "category_id": str(category_id),
            "transaction_type": transaction_type,
            "amount_paise": 100,
            "description": "Rejected entry",
            "transaction_date": transaction_date.isoformat(),
        },
    )
    assert response.status_code == 422
    assert session.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.user_id == user.id)
    ) == 0


def test_account_opening_balance_locks_after_even_a_soft_deleted_transaction(auth_http_client):
    client, settings, session = auth_http_client
    user, account, expense_category = _make_financial_user(session)
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user)

    metadata = client.patch(
        f"/api/accounts/{account.id}",
        headers=headers,
        json={
            "name": "Everyday",
            "account_type": "wallet",
            "opening_balance_paise": 2500,
        },
    )
    assert metadata.status_code == 200
    assert metadata.json()["name"] == "Everyday"
    assert metadata.json()["account_type"] == "wallet"
    assert metadata.json()["balance_paise"] == 2500

    created = client.post(
        "/api/transactions",
        headers=headers,
        json={
            "account_id": str(account.id),
            "category_id": str(expense_category.id),
            "transaction_type": "expense",
            "amount_paise": 100,
            "description": "First transaction",
            "transaction_date": account.opening_balance_as_of.isoformat(),
        },
    )
    assert created.status_code == 201
    changed = client.patch(
        f"/api/accounts/{account.id}",
        headers=headers,
        json={"opening_balance_paise": 3000},
    )
    assert changed.status_code == 409

    session.execute(
        update(Transaction)
        .where(Transaction.id == UUID(created.json()["id"]))
        .values(deleted_at=datetime.now(timezone.utc))
    )
    session.commit()
    still_locked = client.patch(
        f"/api/accounts/{account.id}",
        headers=headers,
        json={"opening_balance_as_of": "2026-01-02"},
    )
    assert still_locked.status_code == 409


def test_concurrent_opening_balance_edit_and_transaction_creation_are_serialized(
    postgres_model_session,
):
    session = postgres_model_session
    user, account, category = _make_financial_user(session)
    session.commit()
    barrier = Barrier(2)
    factory = sessionmaker(
        bind=session.get_bind(), class_=Session, expire_on_commit=False
    )
    today = financial_today()

    def create_entry():
        with factory() as worker:
            barrier.wait()
            record = create_transaction(
                worker,
                user_id=user.id,
                account_id=account.id,
                category_id=category.id,
                transaction_type="expense",
                amount_paise=100,
                description="Concurrent transaction",
                transaction_date=today,
            )
            worker.commit()
            return record.transaction.id

    def edit_opening_balance():
        with factory() as worker:
            barrier.wait()
            try:
                update_account(
                    worker,
                    user_id=user.id,
                    account_id=account.id,
                    changes={"opening_balance_paise": 250},
                )
                worker.commit()
                return "updated"
            except AccountOpeningBalanceLockedError:
                worker.rollback()
                return "locked"

    with ThreadPoolExecutor(max_workers=2) as executor:
        transaction_future = executor.submit(create_entry)
        opening_future = executor.submit(edit_opening_balance)
        transaction_id = transaction_future.result(timeout=30)
        opening_result = opening_future.result(timeout=30)

    assert transaction_id is not None
    assert opening_result in {"updated", "locked"}
    session.expire_all()
    persisted = session.get(Account, account.id)
    assert persisted.opening_balance_paise in {0, 250}
    assert session.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.account_id == account.id)
    ) == 1


def _previous_month_start(value: date) -> date:
    this_month = value.replace(day=1)
    previous_month_day = this_month - timedelta(days=1)
    return previous_month_day.replace(day=1)


def test_http_budgets_calculate_spending_and_enforce_tenant_rules(auth_http_client):
    client, settings, session = auth_http_client
    user_a, account_a, food = _make_financial_user(session)
    user_b, account_b, foreign_category = _make_financial_user(session)
    transport = Category(
        user_id=user_a.id, name="Transport", transaction_type="expense"
    )
    salary = Category(user_id=user_a.id, name="Salary", transaction_type="income")
    archived = Category(
        user_id=user_a.id,
        name="Archived",
        transaction_type="expense",
        archived_at=datetime.now(timezone.utc),
    )
    session.add_all([transport, salary, archived])
    session.flush()

    current_month = financial_today().replace(day=1)
    month_start = _previous_month_start(financial_today())
    next_month = current_month
    previous_day = month_start - timedelta(days=1)
    last_day = next_month - timedelta(days=1)
    mid_month = month_start.replace(day=15)
    transaction_rows = [
        Transaction(
            user_id=user_a.id,
            account_id=account_a.id,
            category_id=food.id,
            transaction_type="expense",
            amount_paise=1000,
            description="First day expense",
            transaction_date=month_start,
        ),
        Transaction(
            user_id=user_a.id,
            account_id=account_a.id,
            category_id=food.id,
            transaction_type="expense",
            amount_paise=2000,
            description="Last day expense",
            transaction_date=last_day,
        ),
        Transaction(
            user_id=user_a.id,
            account_id=account_a.id,
            category_id=transport.id,
            transaction_type="expense",
            amount_paise=3000,
            description="Transport expense",
            transaction_date=mid_month,
        ),
        Transaction(
            user_id=user_a.id,
            account_id=account_a.id,
            category_id=salary.id,
            transaction_type="income",
            amount_paise=9000,
            description="Income excluded",
            transaction_date=mid_month,
        ),
        Transaction(
            user_id=user_a.id,
            account_id=account_a.id,
            category_id=food.id,
            transaction_type="expense",
            amount_paise=6000,
            description="Before month",
            transaction_date=previous_day,
        ),
        Transaction(
            user_id=user_a.id,
            account_id=account_a.id,
            category_id=food.id,
            transaction_type="expense",
            amount_paise=7000,
            description="First day after month",
            transaction_date=next_month,
        ),
        Transaction(
            user_id=user_a.id,
            account_id=account_a.id,
            category_id=food.id,
            transaction_type="expense",
            amount_paise=5000,
            description="Deleted expense excluded",
            transaction_date=mid_month,
            deleted_at=datetime.now(timezone.utc),
        ),
        Transaction(
            user_id=user_a.id,
            account_id=account_a.id,
            category_id=None,
            transaction_type="expense",
            amount_paise=500,
            description="Uncategorized import included overall",
            transaction_date=mid_month,
        ),
        Transaction(
            user_id=user_b.id,
            account_id=account_b.id,
            category_id=foreign_category.id,
            transaction_type="expense",
            amount_paise=8000,
            description="Other tenant excluded",
            transaction_date=mid_month,
        ),
    ]
    session.add_all(transaction_rows)
    session.commit()
    headers_a = _authenticated_finance_headers(client, settings, session, user_a)

    def create(month, amount, category_id=None):
        return client.post(
            "/api/budgets",
            headers=headers_a,
            json={
                "month_start": month.isoformat(),
                "category_id": str(category_id) if category_id else None,
                "limit_paise": amount,
            },
        )

    overall = create(month_start, 5000)
    food_budget = create(month_start, 3000, food.id)
    transport_budget = create(month_start, 1000, transport.id)
    empty_month = _previous_month_start(_previous_month_start(month_start))
    empty_budget = create(empty_month, 800)
    assert overall.status_code == food_budget.status_code == transport_budget.status_code == 201
    assert empty_budget.status_code == 201

    assert create(month_start, 4000).status_code == 409
    assert create(month_start, 4000, food.id).status_code == 409
    assert create(month_start, 1000, salary.id).status_code == 422
    assert create(month_start, 1000, foreign_category.id).status_code == 422
    assert create(month_start, 1000, archived.id).status_code == 422

    filtered = client.get(
        "/api/budgets",
        headers=headers_a,
        params={"month_start": month_start.isoformat()},
    )
    assert filtered.status_code == 200
    assert filtered.headers["cache-control"] == "no-store"
    entries = {entry["id"]: entry for entry in filtered.json()}
    assert entries[overall.json()["id"]]["actual_spending_paise"] == "6500"
    assert entries[overall.json()["id"]]["remaining_paise"] == "-1500"
    assert entries[overall.json()["id"]]["percent_used_basis_points"] == "13000"
    assert entries[overall.json()["id"]]["limit_paise"] == 5000
    assert entries[food_budget.json()["id"]]["actual_spending_paise"] == "3000"
    assert entries[food_budget.json()["id"]]["remaining_paise"] == "0"
    assert entries[food_budget.json()["id"]]["percent_used_basis_points"] == "10000"
    assert entries[transport_budget.json()["id"]]["actual_spending_paise"] == "3000"
    assert entries[transport_budget.json()["id"]]["remaining_paise"] == "-2000"
    assert entries[transport_budget.json()["id"]]["percent_used_basis_points"] == "30000"

    category_update = client.patch(
        f"/api/budgets/{empty_budget.json()['id']}",
        headers=headers_a,
        json={"category_id": str(transport.id)},
    )
    assert category_update.status_code == 200
    duplicate_update = client.patch(
        f"/api/budgets/{empty_budget.json()['id']}",
        headers=headers_a,
        json={"month_start": month_start.isoformat()},
    )
    assert duplicate_update.status_code == 409

    empty = client.get(f"/api/budgets/{empty_budget.json()['id']}", headers=headers_a)
    assert empty.status_code == 200
    assert empty.json()["actual_spending_paise"] == "0"
    assert empty.json()["remaining_paise"] == "800"
    assert empty.json()["percent_used_basis_points"] == "0"

    # Archived categories remain valid on historical budgets and their spending.
    food.archived_at = datetime.now(timezone.utc)
    session.commit()
    historical_food_budget = client.get(
        f"/api/budgets/{food_budget.json()['id']}", headers=headers_a
    )
    assert historical_food_budget.status_code == 200
    assert historical_food_budget.json()["category_name"] == "Food"
    assert historical_food_budget.json()["actual_spending_paise"] == "3000"
    changed = client.patch(
        f"/api/budgets/{food_budget.json()['id']}",
        headers=headers_a,
        json={"limit_paise": 3500},
    )
    assert changed.status_code == 200
    assert changed.json()["remaining_paise"] == "500"

    cannot_select_archived = client.patch(
        f"/api/budgets/{overall.json()['id']}",
        headers=headers_a,
        json={"category_id": str(food.id)},
    )
    assert cannot_select_archived.status_code == 422

    headers_b = _authenticated_finance_headers(client, settings, session, user_b)
    foreign_read = client.get(f"/api/budgets/{overall.json()['id']}", headers=headers_b)
    foreign_update = client.patch(
        f"/api/budgets/{overall.json()['id']}",
        headers=headers_b,
        json={"limit_paise": 9000},
    )
    foreign_delete = client.delete(
        f"/api/budgets/{overall.json()['id']}", headers=headers_b
    )
    assert foreign_read.status_code == foreign_update.status_code == 404
    assert foreign_delete.status_code == 404

    headers_a = _authenticated_finance_headers(client, settings, session, user_a)
    deleted = client.delete(
        f"/api/budgets/{transport_budget.json()['id']}", headers=headers_a
    )
    assert deleted.status_code == 204
    assert client.get(
        f"/api/budgets/{transport_budget.json()['id']}", headers=headers_a
    ).status_code == 404


def test_budget_aggregate_precision_contract_for_list_retrieve_and_openapi(
    auth_http_client,
):
    client, settings, session = auth_http_client
    user, account_a, expense_category = _make_financial_user(session)
    account_a.opening_balance_paise = MAX_SAFE_PAISE
    account_b = _add_account(
        session,
        user,
        name="Large aggregate account",
        opening_paise=MAX_SAFE_PAISE,
    )
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user)
    month_start = financial_today().replace(day=1)

    for account in (account_a, account_b):
        transaction = client.post(
            "/api/transactions",
            headers=headers,
            json={
                "account_id": str(account.id),
                "category_id": str(expense_category.id),
                "transaction_type": "expense",
                "amount_paise": MAX_SAFE_PAISE,
                "description": "Safe per-account maximum",
                "transaction_date": financial_today().isoformat(),
            },
        )
        assert transaction.status_code == 201

    created = client.post(
        "/api/budgets",
        headers=headers,
        json={
            "month_start": month_start.isoformat(),
            "category_id": None,
            "limit_paise": 1,
        },
    )
    assert created.status_code == 201
    budget_id = created.json()["id"]

    listed = client.get("/api/budgets", headers=headers)
    retrieved = client.get(f"/api/budgets/{budget_id}", headers=headers)
    assert listed.status_code == retrieved.status_code == 200
    list_item = next(item for item in listed.json() if item["id"] == budget_id)
    detail = retrieved.json()

    expected_fields = {
        "limit_paise": 1,
        "actual_spending_paise": "18014398509481982",
        "remaining_paise": "-18014398509481981",
        "percent_used_basis_points": "180143985094819820000",
    }
    for response in (created.json(), list_item, detail):
        assert {key: response[key] for key in expected_fields} == expected_fields
        assert type(response["limit_paise"]) is int
        assert all(
            type(response[field]) is str
            for field in (
                "actual_spending_paise",
                "remaining_paise",
                "percent_used_basis_points",
            )
        )

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    properties = openapi.json()["components"]["schemas"]["BudgetResponse"]["properties"]
    assert properties["limit_paise"]["type"] == "integer"
    for field in (
        "actual_spending_paise",
        "remaining_paise",
        "percent_used_basis_points",
    ):
        assert properties[field]["type"] == "string"


def test_budget_service_does_not_commit_and_rollback_removes_record(
    postgres_model_session,
):
    session = postgres_model_session
    user, _, _ = _make_financial_user(session)
    session.commit()

    created = create_budget(
        session,
        user_id=user.id,
        month_start=date(2026, 2, 1),
        category_id=None,
        limit_paise=1000,
    )

    assert session.in_transaction()
    assert created.budget.user_id == user.id
    session.rollback()
    assert session.scalar(
        select(Budget.id).where(Budget.user_id == user.id)
    ) is None


def test_concurrent_duplicate_budget_creation_uses_database_uniqueness(
    postgres_model_session,
):
    session = postgres_model_session
    user, _, _ = _make_financial_user(session)
    session.commit()
    barrier = Barrier(2)
    factory = sessionmaker(
        bind=session.get_bind(), class_=Session, expire_on_commit=False
    )

    def create_concurrently():
        with factory() as worker:
            barrier.wait()
            try:
                created = create_budget(
                    worker,
                    user_id=user.id,
                    month_start=date(2026, 3, 1),
                    category_id=None,
                    limit_paise=1000,
                )
                worker.commit()
                return created.budget.id
            except DuplicateBudgetError:
                worker.rollback()
                return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: create_concurrently(), range(2)))

    assert outcomes.count("duplicate") == 1
    assert len([value for value in outcomes if value != "duplicate"]) == 1
    assert session.scalar(
        select(func.count()).select_from(Budget).where(
            Budget.user_id == user.id,
            Budget.month_start == date(2026, 3, 1),
            Budget.category_id.is_(None),
        )
    ) == 1


def _make_goal(session: Session, user: User, *, name: str, target_paise: int = 50_000):
    return create_goal(
        session,
        user_id=user.id,
        name=name,
        description=None,
        target_paise=target_paise,
        target_date=None,
    ).goal


def _add_account(session: Session, user: User, *, name: str, opening_paise: int) -> Account:
    account = Account(
        user_id=user.id,
        name=name,
        account_type="bank",
        is_default=False,
        opening_balance_paise=opening_paise,
        opening_balance_as_of=date(2026, 1, 1),
    )
    session.add(account)
    session.flush()
    return account


def test_expenses_never_reduce_available_to_spend_below_zero(auth_http_client):
    client, settings, session = auth_http_client
    user, account, expense_category = _make_financial_user(session)
    account.opening_balance_paise = 1_000
    other_account = _add_account(
        session, user, name="Separate funds", opening_paise=5_000
    )
    income_category = Category(
        user_id=user.id, name="Pay", transaction_type="income"
    )
    session.add(income_category)
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user)

    def post_transaction(account_id, category_id, transaction_type, amount):
        return client.post(
            "/api/transactions",
            headers=headers,
            json={
                "account_id": str(account_id),
                "category_id": str(category_id),
                "transaction_type": transaction_type,
                "amount_paise": amount,
                "description": f"{transaction_type} boundary",
                "transaction_date": financial_today().isoformat(),
            },
        )

    # Ordinary overspending is rejected even with no allocation. Funds in a
    # second account do not authorize spending from this account.
    assert post_transaction(
        account.id, expense_category.id, "expense", 1_001
    ).status_code == 422

    goal_response = client.post(
        "/api/goals",
        headers=headers,
        json={"name": "Reserve", "target_paise": 1_000},
    )
    assert goal_response.status_code == 201
    goal_id = UUID(goal_response.json()["id"])
    contribution = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers,
        json={"account_id": str(account.id), "amount_paise": 400},
    )
    assert contribution.status_code == 201

    # Available is 600: 601 is rejected and an exact 600-paise expense is
    # accepted, leaving every paise reserved by the goal.
    assert post_transaction(
        account.id, expense_category.id, "expense", 601
    ).status_code == 422
    exact_available = post_transaction(
        account.id, expense_category.id, "expense", 600
    )
    assert exact_available.status_code == 201
    assert post_transaction(
        account.id, expense_category.id, "expense", 1
    ).status_code == 422

    # Income is permitted with allocations and increases available-to-spend.
    income = post_transaction(
        account.id, income_category.id, "income", 100
    )
    assert income.status_code == 201
    assert post_transaction(
        account.id, expense_category.id, "expense", 101
    ).status_code == 422
    assert post_transaction(
        account.id, expense_category.id, "expense", 100
    ).status_code == 201

    account_snapshot = get_account(session, user_id=user.id, account_id=account.id)
    assert account_snapshot.balance_paise == 400
    assert account_snapshot.goal_allocated_paise == 400
    assert account_snapshot.available_to_spend_paise == 0
    assert get_account(
        session, user_id=user.id, account_id=other_account.id
    ).available_to_spend_paise == 5_000


def test_account_financial_snapshot_is_one_statement(postgres_model_session):
    session = postgres_model_session
    user, account, _ = _make_financial_user(session)
    account.opening_balance_paise = 1_000
    goal = _make_goal(session, user, name="Snapshot goal")
    create_goal_entry(
        session,
        user_id=user.id,
        goal_id=goal.id,
        account_id=account.id,
        amount_paise=300,
        entry_type="contribution",
    )
    session.commit()

    connection = session.connection()
    statements = []

    def capture_select(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)

    event.listen(connection, "before_cursor_execute", capture_select)
    try:
        snapshot = get_account(session, user_id=user.id, account_id=account.id)
    finally:
        event.remove(connection, "before_cursor_execute", capture_select)

    assert len(statements) == 1
    assert snapshot.balance_paise == 1_000
    assert snapshot.goal_allocated_paise == 300
    assert snapshot.available_to_spend_paise == 700


def test_http_goal_overfunding_remains_allowed_and_reports_negative_remaining(
    auth_http_client,
):
    client, settings, session = auth_http_client
    user, account, _ = _make_financial_user(session)
    account.opening_balance_paise = 1_000
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user)

    created = client.post(
        "/api/goals",
        headers=headers,
        json={"name": "Target decision", "target_paise": 500},
    )
    assert created.status_code == 201
    contribution = client.post(
        f"/api/goals/{created.json()['id']}/contributions",
        headers=headers,
        json={"account_id": str(account.id), "amount_paise": 501},
    )
    assert contribution.status_code == 201
    assert contribution.json()["goal"]["allocated_paise"] == 501
    assert contribution.json()["goal"]["remaining_target_paise"] == -1


def test_http_goal_crud_contributions_withdrawals_and_account_availability(auth_http_client):
    client, settings, session = auth_http_client
    user_a, account_a, food = _make_financial_user(session)
    account_b = _add_account(session, user_a, name="Secondary", opening_paise=4_000)
    account_c = _add_account(session, user_a, name="Opening lock", opening_paise=1_000)
    account_d = _add_account(session, user_a, name="Unused", opening_paise=1_000)
    income_category = Category(
        user_id=user_a.id, name="Pay", transaction_type="income"
    )
    session.add(income_category)
    user_b, account_foreign, _ = _make_financial_user(session)
    account_foreign.opening_balance_paise = 5_000
    session.commit()
    headers_a = _authenticated_finance_headers(client, settings, session, user_a)

    income = client.post(
        "/api/transactions",
        headers=headers_a,
        json={
            "account_id": str(account_a.id),
            "category_id": str(income_category.id),
            "transaction_type": "income",
            "amount_paise": 10_000,
            "description": "Initial funding",
            "transaction_date": account_a.opening_balance_as_of.isoformat(),
        },
    )
    assert income.status_code == 201

    created = client.post(
        "/api/goals",
        headers=headers_a,
        json={
            "name": "Emergency fund",
            "description": "Unexpected costs",
            "target_paise": 12_000,
            "target_date": (financial_today() + timedelta(days=60)).isoformat(),
        },
    )
    assert created.status_code == 201
    goal_id = created.json()["id"]
    assert created.json()["allocated_paise"] == 0
    assert created.json()["description"] == "Unexpected costs"

    listed = client.get("/api/goals", headers=headers_a)
    retrieved = client.get(f"/api/goals/{goal_id}", headers=headers_a)
    assert listed.status_code == retrieved.status_code == 200
    assert listed.json()["total"] == 1
    assert retrieved.json()["id"] == goal_id

    contribution_a = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers_a,
        json={"account_id": str(account_a.id), "amount_paise": 6_000},
    )
    contribution_b = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers_a,
        json={"account_id": str(account_b.id), "amount_paise": 2_000},
    )
    contribution_c = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers_a,
        json={"account_id": str(account_c.id), "amount_paise": 100},
    )
    assert contribution_a.status_code == contribution_b.status_code == contribution_c.status_code == 201
    assert contribution_a.json()["goal"]["allocated_paise"] == 6_000
    assert contribution_a.json()["account"] == {
        "account_id": str(account_a.id),
        "balance_paise": 10_000,
        "goal_allocated_paise": 6_000,
        "available_to_spend_paise": 4_000,
    }
    assert contribution_b.json()["account"]["balance_paise"] == 4_000
    assert contribution_b.json()["account"]["available_to_spend_paise"] == 2_000

    too_much = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers_a,
        json={"account_id": str(account_a.id), "amount_paise": 5_000},
    )
    foreign_account = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers_a,
        json={"account_id": str(account_foreign.id), "amount_paise": 1},
    )
    unused_account_withdrawal = client.post(
        f"/api/goals/{goal_id}/withdrawals",
        headers=headers_a,
        json={"account_id": str(account_d.id), "amount_paise": 1},
    )
    assert too_much.status_code == 409
    assert foreign_account.status_code == 404
    assert unused_account_withdrawal.status_code == 409

    headers_b = _authenticated_finance_headers(client, settings, session, user_b)
    foreign_history = client.get(
        f"/api/goals/{goal_id}/entries", headers=headers_b
    )
    assert foreign_history.status_code == 404
    foreign_account_summaries = client.get("/api/accounts", headers=headers_b)
    assert foreign_account_summaries.status_code == 200
    assert all(
        item["goal_allocated_paise"] == 0
        for item in foreign_account_summaries.json()
    )
    foreign_goal = client.post(
        "/api/goals",
        headers=headers_b,
        json={"name": "Private goal", "target_paise": 1000},
    )
    assert foreign_goal.status_code == 201
    headers_a = _authenticated_finance_headers(client, settings, session, user_a)
    cross_goal = client.post(
        f"/api/goals/{foreign_goal.json()['id']}/contributions",
        headers=headers_a,
        json={"account_id": str(account_a.id), "amount_paise": 1},
    )
    assert cross_goal.status_code == 404
    assert client.get(f"/api/goals/{foreign_goal.json()['id']}", headers=headers_a).status_code == 404
    foreign_update = client.patch(
        f"/api/goals/{foreign_goal.json()['id']}",
        headers=headers_a,
        json={"name": "Intrusion"},
    )
    foreign_delete = client.delete(
        f"/api/goals/{foreign_goal.json()['id']}", headers=headers_a
    )
    assert foreign_update.status_code == foreign_delete.status_code == 404

    excessive_withdrawal = client.post(
        f"/api/goals/{goal_id}/withdrawals",
        headers=headers_a,
        json={"account_id": str(account_b.id), "amount_paise": 2_001},
    )
    withdrawal = client.post(
        f"/api/goals/{goal_id}/withdrawals",
        headers=headers_a,
        json={"account_id": str(account_a.id), "amount_paise": 1_500},
    )
    assert excessive_withdrawal.status_code == 409
    assert withdrawal.status_code == 201
    assert withdrawal.json()["goal"]["allocated_paise"] == 6_600
    assert withdrawal.json()["account"]["balance_paise"] == 10_000
    assert withdrawal.json()["account"]["available_to_spend_paise"] == 5_500

    lower_target = client.patch(
        f"/api/goals/{goal_id}",
        headers=headers_a,
        json={"target_paise": 6_000},
    )
    update = client.patch(
        f"/api/goals/{goal_id}",
        headers=headers_a,
        json={"name": "Rainy day fund", "target_paise": 7_000},
    )
    assert lower_target.status_code == 409
    assert update.status_code == 200
    assert update.json()["name"] == "Rainy day fund"

    history = client.get(f"/api/goals/{goal_id}/entries", headers=headers_a)
    assert history.status_code == 200
    assert history.json()["total"] == 4
    assert {entry["entry_type"] for entry in history.json()["items"]} == {
        "contribution",
        "withdrawal",
    }
    assert session.scalar(
        select(func.count()).select_from(Transaction).where(
            Transaction.user_id == user_a.id
        )
    ) == 1
    actual_account = client.get(f"/api/accounts/{account_a.id}", headers=headers_a)
    assert actual_account.status_code == 200
    assert actual_account.json()["balance_paise"] == 10_000
    assert actual_account.json()["goal_allocated_paise"] == 4_500
    assert actual_account.json()["available_to_spend_paise"] == 5_500

    opening_edit = client.patch(
        f"/api/accounts/{account_a.id}",
        headers=headers_a,
        json={"opening_balance_paise": 11_000},
    )
    assert opening_edit.status_code == 409
    opening_edit_after_goal_entry = client.patch(
        f"/api/accounts/{account_c.id}",
        headers=headers_a,
        json={"opening_balance_paise": 1_500},
    )
    assert opening_edit_after_goal_entry.status_code == 409

    expense = client.post(
        "/api/transactions",
        headers=headers_a,
        json={
            "account_id": str(account_a.id),
            "category_id": str(food.id),
            "transaction_type": "expense",
            "amount_paise": 6_000,
            "description": "Would spend reserved funds",
            "transaction_date": financial_today().isoformat(),
        },
    )
    assert expense.status_code == 422


def test_goal_delete_releases_each_account_and_preserves_append_only_history(auth_http_client):
    client, settings, session = auth_http_client
    user, account_a, _ = _make_financial_user(session)
    account_a.opening_balance_paise = 5_000
    account_b = _add_account(session, user, name="Secondary", opening_paise=3_000)
    account_empty = _add_account(session, user, name="No allocation", opening_paise=500)
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user)
    created = client.post(
        "/api/goals",
        headers=headers,
        json={"name": "Trip", "target_paise": 7_000},
    )
    goal_id = created.json()["id"]
    first = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers,
        json={"account_id": str(account_a.id), "amount_paise": 2_000},
    )
    second = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers,
        json={"account_id": str(account_b.id), "amount_paise": 1_000},
    )
    empty_contribution = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers,
        json={"account_id": str(account_empty.id), "amount_paise": 200},
    )
    assert first.status_code == second.status_code == empty_contribution.status_code == 201
    first_entry_id = first.json()["entry"]["id"]
    second_entry_id = second.json()["entry"]["id"]
    empty_contribution_id = empty_contribution.json()["entry"]["id"]
    partial_withdrawal = client.post(
        f"/api/goals/{goal_id}/withdrawals",
        headers=headers,
        json={"account_id": str(account_a.id), "amount_paise": 500},
    )
    zeroing_withdrawal = client.post(
        f"/api/goals/{goal_id}/withdrawals",
        headers=headers,
        json={"account_id": str(account_empty.id), "amount_paise": 200},
    )
    assert partial_withdrawal.status_code == zeroing_withdrawal.status_code == 201
    partial_withdrawal_id = partial_withdrawal.json()["entry"]["id"]
    zeroing_withdrawal_id = zeroing_withdrawal.json()["entry"]["id"]

    deleted = client.delete(f"/api/goals/{goal_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get("/api/goals", headers=headers).json()["total"] == 0
    assert client.get(f"/api/goals/{goal_id}", headers=headers).status_code == 404
    assert client.get(f"/api/goals/{goal_id}/entries", headers=headers).status_code == 404
    assert client.delete(f"/api/goals/{goal_id}", headers=headers).status_code == 404
    rejected_after_delete = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers,
        json={"account_id": str(account_a.id), "amount_paise": 1},
    )
    assert rejected_after_delete.status_code == 404

    session.expire_all()
    ledger = list(
        session.scalars(
            select(GoalEntry).where(
                GoalEntry.user_id == user.id,
                GoalEntry.goal_id == UUID(goal_id),
            )
        ).all()
    )
    assert len(ledger) == 7
    original_entries = {str(entry.id): entry for entry in ledger}
    assert original_entries[first_entry_id].entry_type == "contribution"
    assert original_entries[first_entry_id].amount_paise == 2_000
    assert original_entries[second_entry_id].entry_type == "contribution"
    assert original_entries[second_entry_id].amount_paise == 1_000
    assert original_entries[empty_contribution_id].amount_paise == 200
    assert original_entries[partial_withdrawal_id].amount_paise == 500
    assert original_entries[zeroing_withdrawal_id].amount_paise == 200
    original_ids = {
        first_entry_id,
        second_entry_id,
        empty_contribution_id,
        partial_withdrawal_id,
        zeroing_withdrawal_id,
    }
    compensations = [entry for entry in ledger if str(entry.id) not in original_ids]
    assert len(compensations) == 2
    assert {(entry.account_id, entry.amount_paise) for entry in compensations} == {
        (account_a.id, 1_500),
        (account_b.id, 1_000),
    }
    assert {
        entry_id: (original_entries[entry_id].entry_type,
                   original_entries[entry_id].amount_paise,
                   original_entries[entry_id].account_id)
        for entry_id in original_ids
    } == {
        first_entry_id: ("contribution", 2_000, account_a.id),
        second_entry_id: ("contribution", 1_000, account_b.id),
        empty_contribution_id: ("contribution", 200, account_empty.id),
        partial_withdrawal_id: ("withdrawal", 500, account_a.id),
        zeroing_withdrawal_id: ("withdrawal", 200, account_empty.id),
    }
    for account, expected_balance in ((account_a, 5_000), (account_b, 3_000)):
        response = client.get(f"/api/accounts/{account.id}", headers=headers)
        assert response.json()["balance_paise"] == expected_balance
        assert response.json()["goal_allocated_paise"] == 0
        assert response.json()["available_to_spend_paise"] == expected_balance
    empty_summary = client.get(f"/api/accounts/{account_empty.id}", headers=headers)
    assert empty_summary.json()["balance_paise"] == 500
    assert empty_summary.json()["goal_allocated_paise"] == 0
    assert empty_summary.json()["available_to_spend_paise"] == 500

    empty_goal = client.post(
        "/api/goals",
        headers=headers,
        json={"name": "Unfunded", "target_paise": 500},
    )
    empty_goal_id = UUID(empty_goal.json()["id"])
    assert client.delete(f"/api/goals/{empty_goal_id}", headers=headers).status_code == 204
    assert session.scalar(
        select(func.count()).select_from(GoalEntry).where(GoalEntry.goal_id == empty_goal_id)
    ) == 0


def test_goal_delete_post_flush_failure_rolls_back_all_compensations(postgres_model_session):
    session = postgres_model_session
    user, account, _ = _make_financial_user(session)
    account.opening_balance_paise = 1_000
    goal = _make_goal(session, user, name="Rollback goal")
    create_goal_entry(
        session,
        user_id=user.id,
        goal_id=goal.id,
        account_id=account.id,
        amount_paise=400,
        entry_type="contribution",
    )
    other_account = _add_account(
        session, user, name="Second rollback account", opening_paise=1_000
    )
    create_goal_entry(
        session,
        user_id=user.id,
        goal_id=goal.id,
        account_id=other_account.id,
        amount_paise=300,
        entry_type="contribution",
    )
    session.commit()

    observed_flushed_compensation = False

    def fail_after_compensation_flush(db, _flush_context):
        nonlocal observed_flushed_compensation
        flushed_count = db.connection().execute(
            select(func.count()).select_from(GoalEntry).where(
                GoalEntry.user_id == user.id,
                GoalEntry.goal_id == goal.id,
                GoalEntry.entry_type == "withdrawal",
            )
        ).scalar_one()
        if flushed_count > 0:
            observed_flushed_compensation = True
            raise SQLAlchemyError("simulated failure after PostgreSQL flush")

    event.listen(session, "after_flush_postexec", fail_after_compensation_flush)
    try:
        with pytest.raises(SQLAlchemyError, match="after PostgreSQL flush"):
            delete_goal(session, user_id=user.id, goal_id=goal.id)
    finally:
        event.remove(session, "after_flush_postexec", fail_after_compensation_flush)
        session.rollback()
    assert observed_flushed_compensation
    session.expire_all()

    assert session.get(SavingsGoal, goal.id).deleted_at is None
    assert session.scalar(
        select(func.count()).select_from(GoalEntry).where(
            GoalEntry.goal_id == goal.id,
            GoalEntry.entry_type == "withdrawal",
        )
    ) == 0
    assert session.scalar(
        select(func.count()).select_from(GoalEntry).where(
            GoalEntry.goal_id == goal.id,
            GoalEntry.entry_type == "contribution",
        )
    ) == 2


def test_concurrent_goal_withdrawals_cannot_overdraw_one_allocation(postgres_model_session):
    session = postgres_model_session
    user, account, _ = _make_financial_user(session)
    account.opening_balance_paise = 100
    goal = _make_goal(session, user, name="Concurrent withdrawal")
    create_goal_entry(
        session,
        user_id=user.id,
        goal_id=goal.id,
        account_id=account.id,
        amount_paise=100,
        entry_type="contribution",
    )
    session.commit()
    factory = sessionmaker(
        bind=session.get_bind(), class_=Session, expire_on_commit=False
    )
    barrier = Barrier(2)

    def withdraw():
        with factory() as worker:
            barrier.wait()
            try:
                entry = create_goal_entry(
                    worker,
                    user_id=user.id,
                    goal_id=goal.id,
                    account_id=account.id,
                    amount_paise=60,
                    entry_type="withdrawal",
                )
                worker.commit()
                return entry.id
            except ExcessiveGoalWithdrawalError:
                worker.rollback()
                return "insufficient-allocation"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: withdraw(), range(2)))

    assert outcomes.count("insufficient-allocation") == 1
    assert len([value for value in outcomes if value != "insufficient-allocation"]) == 1
    session.expire_all()
    snapshot = get_goal(session, user_id=user.id, goal_id=goal.id)
    account_snapshot = get_account(session, user_id=user.id, account_id=account.id)
    assert snapshot.allocated_paise == 40
    assert account_snapshot.balance_paise == 100
    assert account_snapshot.available_to_spend_paise == 60


def test_goal_contribution_racing_deletion_leaves_no_stranded_allocation(postgres_model_session):
    session = postgres_model_session
    user, account, _ = _make_financial_user(session)
    account.opening_balance_paise = 100
    goal = _make_goal(session, user, name="Delete race")
    create_goal_entry(
        session,
        user_id=user.id,
        goal_id=goal.id,
        account_id=account.id,
        amount_paise=50,
        entry_type="contribution",
    )
    session.commit()
    factory = sessionmaker(
        bind=session.get_bind(), class_=Session, expire_on_commit=False
    )
    barrier = Barrier(2)

    def contribute():
        with factory() as worker:
            barrier.wait()
            try:
                create_goal_entry(
                    worker,
                    user_id=user.id,
                    goal_id=goal.id,
                    account_id=account.id,
                    amount_paise=50,
                    entry_type="contribution",
                )
                worker.commit()
                return "contributed"
            except GoalNotFoundError:
                worker.rollback()
                return "goal-already-deleted"

    def delete():
        with factory() as worker:
            barrier.wait()
            delete_goal(worker, user_id=user.id, goal_id=goal.id)
            worker.commit()
            return "deleted"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(contribute), executor.submit(delete)]
        outcomes = [future.result() for future in futures]

    assert "deleted" in outcomes
    assert set(outcomes) <= {"deleted", "contributed", "goal-already-deleted"}
    session.expire_all()
    persisted_goal = session.get(SavingsGoal, goal.id)
    assert persisted_goal.deleted_at is not None
    entries = list(
        session.scalars(select(GoalEntry).where(GoalEntry.goal_id == goal.id)).all()
    )
    contributions = sum(
        entry.amount_paise for entry in entries if entry.entry_type == "contribution"
    )
    withdrawals = sum(
        entry.amount_paise for entry in entries if entry.entry_type == "withdrawal"
    )
    assert contributions in {50, 100}
    assert withdrawals == contributions
    account_snapshot = get_account(session, user_id=user.id, account_id=account.id)
    assert account_snapshot.balance_paise == 100
    assert account_snapshot.goal_allocated_paise == 0
    assert account_snapshot.available_to_spend_paise == 100


def test_concurrent_contributions_share_account_available_balance(postgres_model_session):
    session = postgres_model_session
    user, account, _ = _make_financial_user(session)
    account.opening_balance_paise = 100
    goals = [
        _make_goal(session, user, name="First concurrent goal"),
        _make_goal(session, user, name="Second concurrent goal"),
    ]
    session.commit()
    factory = sessionmaker(
        bind=session.get_bind(), class_=Session, expire_on_commit=False
    )
    barrier = Barrier(2)

    def contribute(goal_id):
        with factory() as worker:
            barrier.wait()
            try:
                entry = create_goal_entry(
                    worker,
                    user_id=user.id,
                    goal_id=goal_id,
                    account_id=account.id,
                    amount_paise=80,
                    entry_type="contribution",
                )
                worker.commit()
                return entry.id
            except InsufficientAvailableToSpendError:
                worker.rollback()
                return "insufficient-available"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(contribute, [item.id for item in goals]))

    assert outcomes.count("insufficient-available") == 1
    assert len([value for value in outcomes if value != "insufficient-available"]) == 1
    session.expire_all()
    account_snapshot = get_account(session, user_id=user.id, account_id=account.id)
    assert account_snapshot.balance_paise == 100
    assert account_snapshot.goal_allocated_paise == 80
    assert account_snapshot.available_to_spend_paise == 20


def test_goal_aggregate_safe_integer_limit_across_accounts(auth_http_client):
    client, settings, session = auth_http_client
    user, account_a, _ = _make_financial_user(session)
    account_a.opening_balance_paise = MAX_SAFE_PAISE
    account_b = _add_account(
        session, user, name="Boundary account", opening_paise=MAX_SAFE_PAISE
    )
    session.commit()
    headers = _authenticated_finance_headers(client, settings, session, user)
    created = client.post(
        "/api/goals",
        headers=headers,
        json={"name": "Safe aggregate", "target_paise": MAX_SAFE_PAISE},
    )
    assert created.status_code == 201
    goal_id = UUID(created.json()["id"])

    first = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers,
        json={"account_id": str(account_a.id), "amount_paise": MAX_SAFE_PAISE},
    )
    assert first.status_code == 201

    overflow = client.post(
        f"/api/goals/{goal_id}/contributions",
        headers=headers,
        json={"account_id": str(account_b.id), "amount_paise": 1},
    )
    assert overflow.status_code == 409
    session.expire_all()
    snapshot = get_goal(session, user_id=user.id, goal_id=goal_id)
    assert snapshot.allocated_paise == MAX_SAFE_PAISE
    assert created.json()["target_paise"] - snapshot.allocated_paise == 0
    assert get_account(session, user_id=user.id, account_id=account_b.id).goal_allocated_paise == 0


def test_concurrent_cross_account_contributions_cannot_overflow_goal_aggregate(
    postgres_model_session,
):
    session = postgres_model_session
    user, account_a, _ = _make_financial_user(session)
    account_a.opening_balance_paise = MAX_SAFE_PAISE
    account_b = _add_account(session, user, name="Concurrent B", opening_paise=1)
    account_c = _add_account(session, user, name="Concurrent C", opening_paise=1)
    goal = _make_goal(
        session, user, name="Concurrent safe aggregate", target_paise=MAX_SAFE_PAISE
    )
    create_goal_entry(
        session,
        user_id=user.id,
        goal_id=goal.id,
        account_id=account_a.id,
        amount_paise=MAX_SAFE_PAISE - 1,
        entry_type="contribution",
    )
    session.commit()
    factory = sessionmaker(
        bind=session.get_bind(), class_=Session, expire_on_commit=False
    )
    barrier = Barrier(2)

    def contribute(account_id):
        with factory() as worker:
            barrier.wait()
            try:
                entry = create_goal_entry(
                    worker,
                    user_id=user.id,
                    goal_id=goal.id,
                    account_id=account_id,
                    amount_paise=1,
                    entry_type="contribution",
                )
                worker.commit()
                return entry.id
            except GoalAllocationLimitExceededError:
                worker.rollback()
                return "aggregate-limit"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(contribute, [account_b.id, account_c.id]))

    assert outcomes.count("aggregate-limit") == 1
    assert len([value for value in outcomes if value != "aggregate-limit"]) == 1
    session.expire_all()
    snapshot = get_goal(session, user_id=user.id, goal_id=goal.id)
    assert snapshot.allocated_paise == MAX_SAFE_PAISE
    assert 0 <= snapshot.allocated_paise <= MAX_SAFE_PAISE


def test_goal_contributions_may_exceed_target_without_exceeding_safe_integer(
    postgres_model_session,
):
    session = postgres_model_session
    user, account, _ = _make_financial_user(session)
    account.opening_balance_paise = 1_000
    goal = _make_goal(session, user, name="Overfunding decision", target_paise=500)
    session.commit()

    create_goal_entry(
        session,
        user_id=user.id,
        goal_id=goal.id,
        account_id=account.id,
        amount_paise=501,
        entry_type="contribution",
    )
    session.commit()
    snapshot = get_goal(session, user_id=user.id, goal_id=goal.id)
    assert snapshot.allocated_paise == 501
    assert goal.target_paise - snapshot.allocated_paise == -1


def test_concurrent_expense_and_contribution_preserve_available_to_spend(
    postgres_model_session,
):
    session = postgres_model_session
    user, account, expense_category = _make_financial_user(session)
    account.opening_balance_paise = 100
    goal = _make_goal(session, user, name="Expense contribution race")
    session.commit()
    factory = sessionmaker(
        bind=session.get_bind(), class_=Session, expire_on_commit=False
    )
    barrier = Barrier(2)

    def contribute():
        with factory() as worker:
            barrier.wait()
            try:
                create_goal_entry(
                    worker,
                    user_id=user.id,
                    goal_id=goal.id,
                    account_id=account.id,
                    amount_paise=80,
                    entry_type="contribution",
                )
                worker.commit()
                return "contributed"
            except InsufficientAvailableToSpendError:
                worker.rollback()
                return "contribution-rejected"

    def spend():
        with factory() as worker:
            barrier.wait()
            try:
                create_transaction(
                    worker,
                    user_id=user.id,
                    account_id=account.id,
                    category_id=expense_category.id,
                    transaction_type="expense",
                    amount_paise=50,
                    description="Concurrent expense",
                    transaction_date=financial_today(),
                )
                worker.commit()
                return "spent"
            except InvalidTransactionError:
                worker.rollback()
                return "expense-rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [executor.submit(contribute), executor.submit(spend)]
        results = [future.result() for future in outcomes]

    assert sum(result in {"contributed", "spent"} for result in results) == 1
    session.expire_all()
    snapshot = get_account(session, user_id=user.id, account_id=account.id)
    assert snapshot.available_to_spend_paise >= 0
    assert snapshot.balance_paise >= snapshot.goal_allocated_paise


def test_concurrent_expense_and_withdrawal_preserve_available_to_spend(
    postgres_model_session,
):
    session = postgres_model_session
    user, account, expense_category = _make_financial_user(session)
    account.opening_balance_paise = 100
    goal = _make_goal(session, user, name="Expense withdrawal race")
    create_goal_entry(
        session,
        user_id=user.id,
        goal_id=goal.id,
        account_id=account.id,
        amount_paise=80,
        entry_type="contribution",
    )
    session.commit()
    factory = sessionmaker(
        bind=session.get_bind(), class_=Session, expire_on_commit=False
    )
    barrier = Barrier(2)

    def withdraw():
        with factory() as worker:
            barrier.wait()
            try:
                create_goal_entry(
                    worker,
                    user_id=user.id,
                    goal_id=goal.id,
                    account_id=account.id,
                    amount_paise=30,
                    entry_type="withdrawal",
                )
                worker.commit()
                return "withdrew"
            except ExcessiveGoalWithdrawalError:
                worker.rollback()
                return "withdrawal-rejected"

    def spend():
        with factory() as worker:
            barrier.wait()
            try:
                create_transaction(
                    worker,
                    user_id=user.id,
                    account_id=account.id,
                    category_id=expense_category.id,
                    transaction_type="expense",
                    amount_paise=50,
                    description="Concurrent expense",
                    transaction_date=financial_today(),
                )
                worker.commit()
                return "spent"
            except InvalidTransactionError:
                worker.rollback()
                return "expense-rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [executor.submit(withdraw), executor.submit(spend)]
        results = [future.result() for future in outcomes]

    assert "withdrew" in results
    session.expire_all()
    snapshot = get_account(session, user_id=user.id, account_id=account.id)
    assert snapshot.available_to_spend_paise >= 0
    assert snapshot.balance_paise >= snapshot.goal_allocated_paise


def test_concurrent_opening_balance_update_and_contribution_serialize(
    postgres_model_session,
):
    session = postgres_model_session
    user, account, _ = _make_financial_user(session)
    account.opening_balance_paise = 100
    goal = _make_goal(session, user, name="Opening balance race")
    session.commit()
    factory = sessionmaker(
        bind=session.get_bind(), class_=Session, expire_on_commit=False
    )
    barrier = Barrier(2)

    def update_opening_balance():
        with factory() as worker:
            barrier.wait()
            try:
                update_account(
                    worker,
                    user_id=user.id,
                    account_id=account.id,
                    changes={"opening_balance_paise": 200},
                )
                worker.commit()
                return "updated"
            except AccountOpeningBalanceLockedError:
                worker.rollback()
                return "locked-by-ledger"

    def contribute():
        with factory() as worker:
            barrier.wait()
            create_goal_entry(
                worker,
                user_id=user.id,
                goal_id=goal.id,
                account_id=account.id,
                amount_paise=50,
                entry_type="contribution",
            )
            worker.commit()
            return "contributed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(update_opening_balance), executor.submit(contribute)]
        results = [future.result() for future in futures]

    assert "contributed" in results
    assert results.count("updated") + results.count("locked-by-ledger") == 1
    session.expire_all()
    snapshot = get_account(session, user_id=user.id, account_id=account.id)
    assert snapshot.balance_paise in {100, 200}
    assert snapshot.goal_allocated_paise == 50
    assert snapshot.available_to_spend_paise >= 0
