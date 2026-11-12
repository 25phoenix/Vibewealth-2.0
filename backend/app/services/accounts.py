"""Tenant-scoped account reads, balance calculations, and metadata updates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.financial import MAX_SAFE_PAISE, financial_today
from app.models import Account, GoalEntry, Transaction


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
    goal_allocated_paise: int = 0
    available_to_spend_paise: int = 0


def list_accounts(db: Session, *, user_id: UUID) -> list[AccountSnapshot]:
    """Return active accounts and balances with one aggregate query."""

    as_of = financial_today()
    rows = _account_balance_query(db, user_id=user_id, as_of=as_of)
    return [
        AccountSnapshot(
            account=account,
            balance_paise=balance,
            as_of=as_of,
            goal_allocated_paise=allocated,
            available_to_spend_paise=available,
        )
        for account, balance, allocated, available in rows
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
    account, balance, allocated, available = rows[0]
    return AccountSnapshot(
        account=account,
        balance_paise=balance,
        as_of=as_of,
        goal_allocated_paise=allocated,
        available_to_spend_paise=available,
    )


def get_account_balance(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
    as_of: date | None = None,
    include_archived: bool = False,
) -> AccountSnapshot:
    """Calculate the exact balance through the requested India-calendar date."""

    effective_date = as_of or financial_today()
    if effective_date > financial_today():
        raise InvalidAccountUpdateError("Balance date cannot be in the future")
    rows = _account_balance_query(
        db,
        user_id=user_id,
        account_id=account_id,
        as_of=effective_date,
        include_archived=include_archived,
    )
    if not rows:
        raise AccountNotFoundError
    account, balance, allocated, available = rows[0]
    if effective_date < account.opening_balance_as_of:
        raise InvalidAccountUpdateError(
            "Balance cannot be calculated before the account opening date"
        )
    return AccountSnapshot(
        account=account,
        balance_paise=balance,
        as_of=effective_date,
        goal_allocated_paise=allocated,
        available_to_spend_paise=available,
    )


def update_account(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
    changes: dict[str, object],
) -> AccountSnapshot:
    """Update permitted metadata, locking against concurrent transaction creation.

    Opening-balance fields are editable only until the first transaction or
    goal-ledger entry has been inserted for the account. Deleted transactions
    and compensated entries still count. This operation, transaction creation,
    and goal allocation mutations lock the account row before relying on its
    balance.
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
        has_goal_entry = db.scalar(
            select(GoalEntry.id)
            .where(
                GoalEntry.user_id == user_id,
                GoalEntry.account_id == account.id,
            )
            .limit(1)
        )
        if has_transaction is not None or has_goal_entry is not None:
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
    db: Session,
    *,
    user_id: UUID,
    as_of: date,
    account_id: UUID | None = None,
    include_archived: bool = False,
) -> list[tuple[Account, int, int, int]]:
    """Read account metadata and its complete financial snapshot in one statement.

    Grouped subqueries are joined to the account rows so PostgreSQL evaluates
    balance, allocations, and available-to-spend from one READ COMMITTED
    statement snapshot. This avoids mixing commits between separate aggregates.
    """

    transaction_net = (
        select(
            Transaction.user_id.label("user_id"),
            Transaction.account_id.label("account_id"),
            func.sum(
                case(
                    (Transaction.transaction_type == "income", Transaction.amount_paise),
                    else_=-Transaction.amount_paise,
                )
            ).label("net_paise"),
        )
        .join(
            Account,
            (Account.user_id == Transaction.user_id)
            & (Account.id == Transaction.account_id),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
            Transaction.transaction_date >= Account.opening_balance_as_of,
            Transaction.transaction_date <= as_of,
        )
    )
    allocation_net = select(
        GoalEntry.user_id.label("user_id"),
        GoalEntry.account_id.label("account_id"),
        func.sum(
            case(
                (GoalEntry.entry_type == "contribution", GoalEntry.amount_paise),
                else_=-GoalEntry.amount_paise,
            )
        ).label("net_paise"),
    ).where(
        GoalEntry.user_id == user_id,
        GoalEntry.effective_date <= as_of,
    )
    if account_id is not None:
        transaction_net = transaction_net.where(Transaction.account_id == account_id)
        allocation_net = allocation_net.where(GoalEntry.account_id == account_id)
    transaction_net = transaction_net.group_by(
        Transaction.user_id, Transaction.account_id
    ).subquery("transaction_net")
    allocation_net = allocation_net.group_by(
        GoalEntry.user_id, GoalEntry.account_id
    ).subquery("allocation_net")

    actual_balance = (
        Account.opening_balance_paise
        + func.coalesce(transaction_net.c.net_paise, 0)
    )
    allocated = func.coalesce(allocation_net.c.net_paise, 0)
    available = actual_balance - allocated
    stmt = (
        select(Account, actual_balance, allocated, available)
        .outerjoin(
            transaction_net,
            (transaction_net.c.user_id == Account.user_id)
            & (transaction_net.c.account_id == Account.id),
        )
        .outerjoin(
            allocation_net,
            (allocation_net.c.user_id == Account.user_id)
            & (allocation_net.c.account_id == Account.id),
        )
        .where(Account.user_id == user_id)
        .order_by(Account.is_default.desc(), Account.created_at, Account.id)
    )
    if account_id is not None:
        stmt = stmt.where(Account.id == account_id)
    if not include_archived:
        stmt = stmt.where(Account.archived_at.is_(None))

    rows = db.execute(stmt).all()
    return [
        (account, int(balance), int(goal_allocated), int(available_to_spend))
        for account, balance, goal_allocated, available_to_spend in rows
    ]
