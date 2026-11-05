"""Opt-in PostgreSQL integration checks for model-specific DDL behavior."""

import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import (
    Account,
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
