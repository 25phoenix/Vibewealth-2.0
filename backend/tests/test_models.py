"""Structural tests for SQLAlchemy model registration and constraints."""

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.orm import configure_mappers

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


EXPECTED_TABLES = {
    "auth_sessions",
    "users",
    "accounts",
    "categories",
    "transactions",
    "budgets",
    "savings_goals",
    "goal_entries",
    "assistant_conversations",
    "assistant_messages",
}


def _constraints(model, constraint_type):
    return {
        constraint.name: constraint
        for constraint in model.__table__.constraints
        if isinstance(constraint, constraint_type)
    }


def _indexes(model):
    return {index.name: index for index in model.__table__.indexes}


def test_all_approved_tables_are_registered_on_shared_metadata() -> None:
    assert Base.metadata is User.metadata
    assert {table.name for table in Base.metadata.tables.values()} == EXPECTED_TABLES
    assert all(
        model.metadata is Base.metadata
        for model in (
            AuthSession,
            Account,
            Category,
            Transaction,
            Budget,
            SavingsGoal,
            GoalEntry,
            AssistantConversation,
            AssistantMessage,
        )
    )


def test_models_have_python_uuid_and_server_timestamp_defaults() -> None:
    for model in (
        User,
        AuthSession,
        Account,
        Category,
        Transaction,
        Budget,
        SavingsGoal,
        GoalEntry,
        AssistantConversation,
        AssistantMessage,
    ):
        assert callable(model.__table__.c.id.default.arg)
        assert model.__table__.c.id.default.arg.__name__ == "uuid4"
        assert model.__table__.c.created_at.server_default is not None


def test_relationship_mappers_configure_without_circular_imports() -> None:
    configure_mappers()
    assert User.accounts.property.mapper.class_ is Account
    assert User.auth_sessions.property.mapper.class_ is AuthSession
    assert User.auth_sessions.property.passive_deletes == "all"
    assert AuthSession.user.property.mapper.class_ is User
    assert Transaction.account.property.mapper.class_ is Account
    assert GoalEntry.goal.property.mapper.class_ is SavingsGoal
    assert GoalEntry.account.property.mapper.class_ is Account
    assert AssistantMessage.conversation.property.mapper.class_ is AssistantConversation


def test_owner_scoped_foreign_keys_are_composite_and_deferred() -> None:
    expected = {
        (Transaction, "fk_transactions_account_owner", ("user_id", "account_id")),
        (Transaction, "fk_transactions_category_owner_type", ("user_id", "category_id", "transaction_type")),
        (Budget, "fk_budgets_category_owner", ("user_id", "category_id")),
        (GoalEntry, "fk_goal_entries_goal_owner", ("user_id", "goal_id")),
        (GoalEntry, "fk_goal_entries_account_owner", ("user_id", "account_id")),
    }
    for model, name, columns in expected:
        fk = _constraints(model, ForeignKeyConstraint)[name]
        assert tuple(column.name for column in fk.columns) == columns
        assert fk.ondelete == "NO ACTION"
        assert fk.deferrable is True
        assert fk.initially == "DEFERRED"

    account_unique = _constraints(Account, UniqueConstraint)
    category_unique = _constraints(Category, UniqueConstraint)
    goal_unique = _constraints(SavingsGoal, UniqueConstraint)
    assert tuple(c.name for c in account_unique["uq_accounts_user_id_id"].columns) == ("user_id", "id")
    assert tuple(c.name for c in category_unique["uq_categories_user_id_id"].columns) == ("user_id", "id")
    assert tuple(c.name for c in category_unique["uq_categories_user_id_id_type"].columns) == (
        "user_id", "id", "transaction_type"
    )
    assert tuple(c.name for c in goal_unique["uq_savings_goals_user_id_id"].columns) == ("user_id", "id")


def test_direct_user_foreign_keys_have_stable_names_and_preserve_targets() -> None:
    expected = {
        Account: ("fk_accounts_user_id_users", "accounts"),
        Category: ("fk_categories_user_id_users", "categories"),
        Transaction: ("fk_transactions_user_id_users", "transactions"),
        Budget: ("fk_budgets_user_id_users", "budgets"),
        SavingsGoal: ("fk_savings_goals_user_id_users", "savings_goals"),
        GoalEntry: ("fk_goal_entries_user_id_users", "goal_entries"),
        AssistantConversation: (
            "fk_assistant_conversations_user_id_users",
            "assistant_conversations",
        ),
        AssistantMessage: ("fk_assistant_messages_user_id_users", "assistant_messages"),
    }

    for model, (expected_name, table_name) in expected.items():
        direct_user_fks = [
            fk
            for fk in model.__table__.foreign_key_constraints
            if len(fk.elements) == 1 and fk.elements[0].target_fullname == "users.id"
        ]
        assert len(direct_user_fks) == 1
        fk = direct_user_fks[0]
        assert fk.name == expected_name
        assert tuple(column.name for column in fk.columns) == ("user_id",)
        assert tuple(element.column.name for element in fk.elements) == ("id",)
        assert fk.elements[0].column.table.name == "users"
        assert fk.ondelete == "CASCADE"
        assert table_name == model.__tablename__

    expected_composite_names = {
        Transaction: {
            "fk_transactions_account_owner",
            "fk_transactions_category_owner_type",
        },
        Budget: {"fk_budgets_category_owner"},
        GoalEntry: {"fk_goal_entries_goal_owner", "fk_goal_entries_account_owner"},
        AssistantMessage: {"fk_assistant_messages_conversation_owner"},
    }
    for model, expected_names in expected_composite_names.items():
        actual_names = {
            fk.name for fk in model.__table__.foreign_key_constraints if len(fk.elements) > 1
        }
        assert actual_names == expected_names


def test_conversation_message_cascade_and_sequence_uniqueness() -> None:
    fk = _constraints(AssistantMessage, ForeignKeyConstraint)[
        "fk_assistant_messages_conversation_owner"
    ]
    assert fk.ondelete == "CASCADE"
    assert fk.deferrable is None
    unique = _constraints(AssistantMessage, UniqueConstraint)[
        "uq_assistant_messages_conversation_sequence"
    ]
    assert tuple(column.name for column in unique.columns) == ("conversation_id", "sequence_no")
    assert "ix_assistant_messages_conversation_sequence" not in _indexes(AssistantMessage)


def test_check_constraints_and_partial_unique_indexes_are_named() -> None:
    assert "ck_accounts_type" in _constraints(Account, CheckConstraint)
    assert "ck_accounts_opening_balance_nonnegative" in _constraints(Account, CheckConstraint)
    assert "ck_transactions_amount_positive" in _constraints(Transaction, CheckConstraint)
    assert "ck_budgets_month_start_first_day" in _constraints(Budget, CheckConstraint)
    assert "ck_goal_entries_amount_positive" in _constraints(GoalEntry, CheckConstraint)
    assert SavingsGoal.__table__.c.description.nullable is True
    goal_entry_index = _indexes(GoalEntry)["ix_goal_entries_user_goal_created"]
    assert tuple(column.name for column in goal_entry_index.columns) == (
        "user_id",
        "goal_id",
        "created_at",
        "id",
    )
    assert "ck_assistant_messages_sequence_positive" in _constraints(AssistantMessage, CheckConstraint)
    assert "ck_assistant_messages_content_nonempty" in _constraints(AssistantMessage, CheckConstraint)

    for model, name in (
        (Account, "uq_accounts_one_default_per_user"),
        (Category, "uq_categories_active_name_per_type"),
        (Budget, "uq_budgets_one_overall_per_month"),
        (Budget, "uq_budgets_one_per_category_month"),
    ):
        assert _indexes(model)[name].unique is True
        assert _indexes(model)[name].dialect_options["postgresql"].get("where") is not None


def test_transaction_category_remains_nullable_for_imports() -> None:
    assert Transaction.__table__.c.category_id.nullable is True


def test_user_email_has_case_insensitive_unique_index() -> None:
    index = _indexes(User)["uq_users_email_lower"]
    assert index.unique is True
    assert "lower(email)" in str(index.expressions[0]).lower()


def test_auth_session_schema_and_postgresql_types() -> None:
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.types import LargeBinary, Uuid

    from app.models.auth_session import AuthSession

    table = AuthSession.__table__
    assert table.name == "auth_sessions"
    assert tuple(table.columns.keys()) == (
        "id",
        "user_id",
        "token_digest",
        "created_at",
        "last_activity_at",
        "absolute_expires_at",
        "revoked_at",
    )

    assert isinstance(table.c.id.type, Uuid)
    assert table.c.id.primary_key is True
    assert table.c.id.default.arg.__name__ == "uuid4"
    assert table.c.user_id.nullable is False
    assert isinstance(table.c.token_digest.type, LargeBinary)
    assert table.c.token_digest.type.compile(dialect=postgresql.dialect()) == "BYTEA"
    assert table.c.token_digest.type.length == 32
    assert table.c.token_digest.nullable is False

    for name in ("created_at", "last_activity_at", "absolute_expires_at", "revoked_at"):
        assert table.c[name].type.timezone is True
    assert table.c.created_at.nullable is False
    assert table.c.created_at.server_default is not None
    assert table.c.last_activity_at.nullable is False
    assert table.c.last_activity_at.server_default is not None
    assert table.c.absolute_expires_at.nullable is False
    assert table.c.absolute_expires_at.server_default is None
    assert table.c.revoked_at.nullable is True

    constraints = {constraint.name: constraint for constraint in table.constraints}
    primary_key = constraints["pk_auth_sessions"]
    assert isinstance(primary_key, PrimaryKeyConstraint)
    assert tuple(column.name for column in primary_key.columns) == ("id",)
    digest_unique = constraints["uq_auth_sessions_token_digest"]
    assert isinstance(digest_unique, UniqueConstraint)
    assert tuple(column.name for column in digest_unique.columns) == ("token_digest",)

    user_fk = constraints["fk_auth_sessions_user_id_users"]
    assert isinstance(user_fk, ForeignKeyConstraint)
    assert tuple(column.name for column in user_fk.columns) == ("user_id",)
    assert tuple(element.target_fullname for element in user_fk.elements) == ("users.id",)
    assert user_fk.ondelete == "CASCADE"
    assert user_fk.deferrable is None

    checks = {constraint.name: str(constraint.sqltext) for constraint in table.constraints
              if isinstance(constraint, CheckConstraint)}
    assert checks["ck_auth_sessions_token_digest_length"] == "octet_length(token_digest) = 32"
    assert checks["ck_auth_sessions_absolute_expiry_after_creation"] == (
        "absolute_expires_at > created_at"
    )

    index = {item.name: item for item in table.indexes}["ix_auth_sessions_user_active_expiry"]
    assert tuple(column.name for column in index.columns) == ("user_id", "absolute_expires_at")
    assert index.unique is False
    assert str(index.dialect_options["postgresql"]["where"]) == "revoked_at IS NULL"
    assert str(index.dialect_options["sqlite"]["where"]) == "revoked_at IS NULL"
