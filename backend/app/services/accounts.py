"""Tenant-scoped account reads, balance calculations, and metadata updates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.financial import MAX_SAFE_PAISE, financial_today
from app.models import Account, Transaction


class AccountNotFoundError(LookupError):
    """The requested active account is not owned by the authenticated user."""


class AccountOpeningBalanceLockedError(ValueError):
    """An account's opening balance can no longer be changed."""


class InvalidAccountUpdateError(ValueError):
    """An account metadata update violates a domain rule."""


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    account: Account
    balance_paise: int
    as_of: date


def list_accounts(db: Session, *, user_id: UUID) -> list[AccountSnapshot]:
    """Return active accounts and balances with one aggregate query."""

    as_of = financial_today()
    rows = _account_balance_query(db, user_id=user_id, as_of=as_of)
    return [
        AccountSnapshot(account=account, balance_paise=balance, as_of=as_of)
        for account, balance in rows
    ]


def get_account(
    db: Session, *, user_id: UUID, account_id: UUID
) -> AccountSnapshot:
    """Return an active account only when it belongs to the supplied user."""

    as_of = financial_today()
    rows = _account_balance_query(
        db, user_id=user_id, account_id=account_id, as_of=as_of
    )
    if not rows:
        raise AccountNotFoundError
    account, balance = rows[0]
    return AccountSnapshot(account=account, balance_paise=balance, as_of=as_of)


def get_account_balance(
    db: Session, *, user_id: UUID, account_id: UUID, as_of: date | None = None
) -> AccountSnapshot:
    """Calculate the exact balance through the requested India-calendar date."""

    effective_date = as_of or financial_today()
    if effective_date > financial_today():
        raise InvalidAccountUpdateError("Balance date cannot be in the future")
    rows = _account_balance_query(
        db, user_id=user_id, account_id=account_id, as_of=effective_date
    )
    if not rows:
        raise AccountNotFoundError
    account, balance = rows[0]
    if effective_date < account.opening_balance_as_of:
        raise InvalidAccountUpdateError(
            "Balance cannot be calculated before the account opening date"
        )
    return AccountSnapshot(
        account=account, balance_paise=balance, as_of=effective_date
    )


def update_account(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
    changes: dict[str, object],
) -> AccountSnapshot:
    """Update permitted metadata, locking against concurrent transaction creation.

    Opening-balance fields are editable only until the first transaction has
    ever been inserted for the account. Deleted transactions still count. Both
    this operation and transaction creation lock the account row first.
    """

    if not changes:
        raise InvalidAccountUpdateError("At least one account field must be supplied")

    account = db.scalar(
        select(Account)
        .where(
            Account.id == account_id,
            Account.user_id == user_id,
            Account.archived_at.is_(None),
        )
        .with_for_update()
    )
    if account is None:
        raise AccountNotFoundError

    if "name" in changes:
        name = changes["name"]
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise InvalidAccountUpdateError("Account name must contain 1 to 100 characters")
        account.name = name.strip()

    if "account_type" in changes:
        account_type = changes["account_type"]
        if account_type not in {"cash", "bank", "wallet"}:
            raise InvalidAccountUpdateError("Account type must be cash, bank, or wallet")
        account.account_type = account_type

    opening_fields = {"opening_balance_paise", "opening_balance_as_of"}
    if opening_fields.intersection(changes):
        has_transaction = db.scalar(
            select(Transaction.id)
            .where(
                Transaction.user_id == user_id,
                Transaction.account_id == account.id,
            )
            .limit(1)
        )
        if has_transaction is not None:
            raise AccountOpeningBalanceLockedError

        if "opening_balance_paise" in changes:
            opening_balance = changes["opening_balance_paise"]
            if (
                type(opening_balance) is not int
                or opening_balance < 0
                or opening_balance > MAX_SAFE_PAISE
            ):
                raise InvalidAccountUpdateError(
                    "Opening balance must be a non-negative safe integer number of paise"
                )
            account.opening_balance_paise = opening_balance

        if "opening_balance_as_of" in changes:
            opening_date = changes["opening_balance_as_of"]
            if not isinstance(opening_date, date):
                raise InvalidAccountUpdateError("Opening-balance date is required")
            if opening_date > financial_today():
                raise InvalidAccountUpdateError(
                    "Opening-balance date cannot be in the future"
                )
            account.opening_balance_as_of = opening_date

    db.flush()
    return get_account(db, user_id=user_id, account_id=account_id)


def _account_balance_query(
    db: Session, *, user_id: UUID, as_of: date, account_id: UUID | None = None
) -> list[tuple[Account, int]]:
    net_amount = func.coalesce(
        func.sum(
            case(
                (Transaction.transaction_type == "income", Transaction.amount_paise),
                else_=-Transaction.amount_paise,
            )
        ),
        0,
    )
    stmt = (
        select(Account, net_amount)
        .outerjoin(
            Transaction,
            (Transaction.user_id == Account.user_id)
            & (Transaction.account_id == Account.id)
            & (Transaction.deleted_at.is_(None))
            & (Transaction.transaction_date >= Account.opening_balance_as_of)
            & (Transaction.transaction_date <= as_of),
        )
        .where(Account.user_id == user_id, Account.archived_at.is_(None))
        .group_by(Account.id)
        .order_by(Account.is_default.desc(), Account.created_at, Account.id)
    )
    if account_id is not None:
        stmt = stmt.where(Account.id == account_id)

    rows = db.execute(stmt).all()
    result: list[tuple[Account, int]] = []
    for account, net in rows:
        result.append((account, account.opening_balance_paise + int(net)))
    return result
