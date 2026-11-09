"""Focused unit tests for registration orchestration and safe return values."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Account, Category, User
from app.services import registration
from app.services.registration import (
    DuplicateEmailError,
    RegistrationResult,
    register_user,
)


class FakeSession:
    """A small staging-only session double; persistence is covered by PG tests."""

    def __init__(self, *, existing_user_id=None, flush_error=None):
        self.rows = []
        self.execute_result = Mock()
        self.execute_result.scalar_one_or_none.return_value = existing_user_id
        self.flush_error = flush_error
        self.flush_calls = 0
        self.commit_calls = 0

    def execute(self, _statement):
        return self.execute_result

    def add(self, row):
        self.rows.append(row)

    def add_all(self, rows):
        self.rows.extend(rows)

    def flush(self, objects=None):
        self.flush_calls += 1
        rows = list(objects) if objects is not None else self.rows
        for row in rows:
            if isinstance(row, User) and row.id is None:
                row.id = uuid4()
        if self.flush_error is not None:
            raise self.flush_error

    def commit(self):
        self.commit_calls += 1


@pytest.fixture
def registration_mocks(monkeypatch):
    password_validation = Mock()
    password_hashing = Mock(return_value="argon2id$test-hash")
    session_creation = Mock(
        return_value=(
            "raw-session-token",
            SimpleNamespace(absolute_expires_at=datetime(2026, 12, 6, tzinfo=timezone.utc)),
        )
    )
    monkeypatch.setattr(registration, "validate_password", password_validation)
    monkeypatch.setattr(registration, "hash_password", password_hashing)
    monkeypatch.setattr(registration, "create_session", session_creation)
    monkeypatch.setattr(registration, "_opening_balance_date", lambda: date(2026, 11, 6))
    return password_validation, password_hashing, session_creation


@pytest.mark.parametrize("account_type", ["cash", "bank", "wallet"])
def test_registration_normalizes_email_and_stages_expected_onboarding(
    account_type, registration_mocks, caplog
):
    password_validation, password_hashing, session_creation = registration_mocks
    db = FakeSession()
    password = "a private password that must not leak"
    caplog.set_level(logging.DEBUG)

    result = register_user(
        db,
        email="  Person.Example@Example.Test  ",
        password=password,
        account_type=account_type,
        display_name="Example Person",
    )

    user = next(row for row in db.rows if isinstance(row, User))
    account = next(row for row in db.rows if isinstance(row, Account))
    categories = [row for row in db.rows if isinstance(row, Category)]
    assert user.email == "person.example@example.test"
    assert user.password_hash == "argon2id$test-hash"
    assert password not in user.password_hash
    assert account.user_id == user.id
    assert account.name == "Main Account"
    assert account.account_type == account_type
    assert account.is_default is True
    assert account.opening_balance_paise == 0
    assert account.opening_balance_as_of == date(2026, 11, 6)
    assert len(categories) == 13
    assert {(row.name, row.transaction_type) for row in categories} == {
        (name, "expense")
        for name in (
            "Housing", "Groceries", "Food & dining", "Transport", "Bills & utilities",
            "Shopping", "Health", "Entertainment", "Education", "Other",
        )
    } | {(name, "income") for name in ("Salary", "Freelance", "Other")}
    other_rows = [row for row in categories if row.name == "Other"]
    assert len(other_rows) == 2
    assert other_rows[0] is not other_rows[1]
    assert {row.transaction_type for row in other_rows} == {"expense", "income"}

    assert result == RegistrationResult(
        user.id,
        user.email,
        "Example Person",
        datetime(2026, 12, 6, tzinfo=timezone.utc),
        "raw-session-token",
    )
    assert result.session_token == "raw-session-token"
    assert "raw-session-token" not in repr(result)
    assert password not in repr(result)
    assert "argon2id$test-hash" not in repr(result)
    assert password not in caplog.text
    assert "raw-session-token" not in caplog.text
    password_validation.assert_called_once_with(password)
    password_hashing.assert_called_once_with(password)
    session_creation.assert_called_once_with(db, user.id)
    assert db.commit_calls == 0


def test_registration_accepts_optional_display_name_without_normalizing_it(registration_mocks):
    db = FakeSession()

    result = register_user(
        db,
        email="user@example.test",
        password="a sufficiently long password",
        account_type="bank",
        display_name="  Sam  ",
    )

    user = next(row for row in db.rows if isinstance(row, User))
    assert result.display_name == "  Sam  "
    assert user.display_name == "  Sam  "

    db = FakeSession()
    result = register_user(
        db,
        email="user@example.test",
        password="a sufficiently long password",
        account_type="bank",
    )
    assert result.display_name is None


@pytest.mark.parametrize("email", ["", "  \t", "not-an-email", "missing@domain", "@example.test"])
def test_registration_rejects_invalid_email_before_database_access(email, registration_mocks):
    db = FakeSession()

    with pytest.raises(ValueError, match="Email"):
        register_user(db, email=email, password="a sufficiently long password", account_type="cash")

    assert db.flush_calls == 0
    assert db.rows == []


@pytest.mark.parametrize("account_type", ["credit_card", "", None, [], "Cash"])
def test_registration_rejects_unsupported_account_type(account_type, registration_mocks):
    db = FakeSession()

    with pytest.raises(ValueError, match="Account type"):
        register_user(
            db,
            email="user@example.test",
            password="a sufficiently long password",
            account_type=account_type,
        )

    assert db.flush_calls == 0
    assert db.rows == []


@pytest.mark.parametrize("display_name", [123, "x" * 121])
def test_registration_rejects_invalid_display_name(display_name, registration_mocks):
    db = FakeSession()

    with pytest.raises(ValueError, match="Display name"):
        register_user(
            db,
            email="user@example.test",
            password="a sufficiently long password",
            account_type="cash",
            display_name=display_name,
        )

    assert db.flush_calls == 0


def test_registration_delegates_password_policy_and_stops_when_rejected(monkeypatch):
    db = FakeSession()
    validator = Mock(side_effect=ValueError("weak password"))
    hasher = Mock()
    monkeypatch.setattr(registration, "validate_password", validator)
    monkeypatch.setattr(registration, "hash_password", hasher)

    with pytest.raises(ValueError, match="weak password"):
        register_user(
            db,
            email="user@example.test",
            password="short",
            account_type="cash",
        )

    validator.assert_called_once_with("short")
    hasher.assert_not_called()
    assert db.flush_calls == 0


def test_registration_rejects_existing_normalized_email(registration_mocks):
    db = FakeSession(existing_user_id=uuid4())

    with pytest.raises(DuplicateEmailError, match="already exists"):
        register_user(
            db,
            email=" Person@Example.Test ",
            password="a sufficiently long password",
            account_type="cash",
        )

    assert db.flush_calls == 0
    assert db.rows == []


@pytest.mark.parametrize(
    ("sqlstate", "constraint_name", "expected"),
    [
        ("23505", "uq_users_email_lower", DuplicateEmailError),
        ("23505", "uq_other_constraint", IntegrityError),
        ("23503", "uq_users_email_lower", IntegrityError),
    ],
)
def test_only_email_unique_index_violation_is_translated(
    sqlstate, constraint_name, expected, registration_mocks
):
    original = SimpleNamespace(
        sqlstate=sqlstate,
        diag=SimpleNamespace(constraint_name=constraint_name),
    )
    error = IntegrityError("INSERT", {}, original)
    db = FakeSession(flush_error=error)

    with pytest.raises(expected) as raised:
        register_user(
            db,
            email="user@example.test",
            password="a sufficiently long password",
            account_type="cash",
        )

    if expected is IntegrityError:
        assert raised.value is error


def test_registration_exception_does_not_return_success(registration_mocks, monkeypatch):
    db = FakeSession()
    monkeypatch.setattr(
        registration,
        "_create_default_account",
        Mock(side_effect=RuntimeError("account staging failed")),
    )

    with pytest.raises(RuntimeError, match="account staging failed"):
        register_user(
            db,
            email="user@example.test",
            password="a sufficiently long password",
            account_type="cash",
        )

    assert len([row for row in db.rows if isinstance(row, User)]) == 1
    assert not any(isinstance(row, Account) for row in db.rows)
    assert db.commit_calls == 0
