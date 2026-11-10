"""Atomic user registration and first-account onboarding."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.email import normalize_email
from app.core.financial import FINANCIAL_TIMEZONE
from app.core.security import hash_password, validate_password
from app.models import Account, Category, User
from app.services.auth_sessions import create_session

EMAIL_UNIQUE_INDEX: Final = "uq_users_email_lower"
SUPPORTED_ACCOUNT_TYPES: Final = frozenset({"cash", "bank", "wallet"})
EXPENSE_CATEGORIES: Final = (
    "Housing",
    "Groceries",
    "Food & dining",
    "Transport",
    "Bills & utilities",
    "Shopping",
    "Health",
    "Entertainment",
    "Education",
    "Other",
)
INCOME_CATEGORIES: Final = ("Salary", "Freelance", "Other")

class DuplicateEmailError(ValueError):
    """Registration was rejected because the normalized email is in use."""


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    """Safe profile fields and the initial token for the trusted caller."""

    user_id: UUID
    email: str
    display_name: str | None
    session_expires_at: datetime
    session_token: str = field(repr=False)


def _validate_display_name(display_name: str | None) -> None:
    if display_name is not None and not isinstance(display_name, str):
        raise ValueError("Display name must be a string or None")
    if display_name is not None and len(display_name) > 120:
        raise ValueError("Display name must be at most 120 characters")


def _opening_balance_date() -> date:
    """Return yesterday in the product's Indian financial timezone."""

    return datetime.now(FINANCIAL_TIMEZONE).date() - timedelta(days=1)


def _raise_if_email_exists(db: Session, normalized_email: str) -> None:
    existing_user_id = db.execute(
        select(User.id).where(func.lower(User.email) == normalized_email)
    ).scalar_one_or_none()
    if existing_user_id is not None:
        raise DuplicateEmailError("An account with this email already exists")


def _is_email_unique_violation(error: IntegrityError) -> bool:
    original = error.orig
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    diagnostic = getattr(original, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    return sqlstate == "23505" and constraint_name == EMAIL_UNIQUE_INDEX


def _seed_default_categories(db: Session, user_id: UUID) -> None:
    categories = [
        Category(user_id=user_id, name=name, transaction_type="expense")
        for name in EXPENSE_CATEGORIES
    ]
    categories.extend(
        Category(user_id=user_id, name=name, transaction_type="income")
        for name in INCOME_CATEGORIES
    )
    db.add_all(categories)
    db.flush()


def _create_default_account(
    db: Session, *, user_id: UUID, account_type: str, opening_balance_as_of: date
) -> None:
    account = Account(
        user_id=user_id,
        name="Main Account",
        account_type=account_type,
        is_default=True,
        opening_balance_paise=0,
        opening_balance_as_of=opening_balance_as_of,
    )
    db.add(account)
    db.flush()


def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    account_type: str,
    display_name: str | None = None,
) -> RegistrationResult:
    """Create a user, default account, categories, and initial session atomically.

    This function never commits or rolls back. The caller must commit after a
    successful return. On any exception, the caller must call ``db.rollback()``
    before reusing the session. In particular, a concurrent duplicate-email
    violation leaves the SQLAlchemy transaction failed even though it is
    translated to ``DuplicateEmailError``.
    """

    normalized_email = normalize_email(email)
    if not isinstance(account_type, str) or account_type not in SUPPORTED_ACCOUNT_TYPES:
        raise ValueError("Account type must be cash, bank, or wallet")
    _validate_display_name(display_name)
    validate_password(password)
    password_hash = hash_password(password)
    opening_balance_as_of = _opening_balance_date()

    _raise_if_email_exists(db, normalized_email)

    user = User(
        email=normalized_email,
        password_hash=password_hash,
        display_name=display_name,
    )
    db.add(user)
    try:
        # Keep the integrity-error translation scoped to the user insert.
        db.flush([user])
    except IntegrityError as error:
        if _is_email_unique_violation(error):
            raise DuplicateEmailError(
                "An account with this email already exists"
            ) from error
        raise

    _create_default_account(
        db,
        user_id=user.id,
        account_type=account_type,
        opening_balance_as_of=opening_balance_as_of,
    )
    _seed_default_categories(db, user.id)
    session_token, auth_session = create_session(db, user.id)

    return RegistrationResult(
        user_id=user.id,
        email=normalized_email,
        display_name=display_name,
        session_expires_at=auth_session.absolute_expires_at,
        session_token=session_token,
    )
