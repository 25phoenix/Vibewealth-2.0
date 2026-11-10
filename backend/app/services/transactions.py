"""Tenant-scoped transaction creation and history queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from sqlalchemy import case, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.core.financial import MAX_SAFE_PAISE, financial_today
from app.models import Account, Category, Transaction


class AccountNotFoundError(LookupError):
    """The requested active account is not owned by the authenticated user."""


class TransactionNotFoundError(LookupError):
    """The requested live transaction is not owned by the authenticated user."""


class InvalidTransactionError(ValueError):
    """A transaction violates a product or financial invariant."""


@dataclass(frozen=True, slots=True)
class TransactionRecord:
    transaction: Transaction
    category_name: str | None


@dataclass(frozen=True, slots=True)
class TransactionPage:
    items: list[TransactionRecord]
    total: int
    offset: int
    limit: int


def create_transaction(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID,
    category_id: UUID,
    transaction_type: str,
    amount_paise: int,
    description: str,
    transaction_date: date,
    notes: str | None = None,
) -> TransactionRecord:
    """Validate and stage one transaction, leaving commit ownership to caller."""

    _validate_transaction_values(
        transaction_type=transaction_type,
        amount_paise=amount_paise,
        description=description,
        transaction_date=transaction_date,
    )

    # Account is always the first locked row. Account-opening edits take the
    # same lock first, making their first-transaction check race-safe.
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

    today = financial_today()
    if transaction_date < account.opening_balance_as_of:
        raise InvalidTransactionError(
            "Transaction date cannot be before the account opening date"
        )

    category = db.scalar(
        select(Category)
        .where(
            Category.id == category_id,
            Category.user_id == user_id,
            Category.transaction_type == transaction_type,
            Category.archived_at.is_(None),
        )
        .with_for_update(read=True)
    )
    if category is None:
        raise InvalidTransactionError(
            "Choose an active category owned by you for this transaction type"
        )

    balance_delta = amount_paise if transaction_type == "income" else -amount_paise
    _validate_daily_balance_range(
        db,
        account=account,
        transaction_date=transaction_date,
        balance_delta=balance_delta,
        as_of=today,
    )

    transaction = Transaction(
        user_id=user_id,
        account_id=account.id,
        category_id=category.id,
        transaction_type=transaction_type,
        amount_paise=amount_paise,
        description=description.strip(),
        transaction_date=transaction_date,
        notes=notes,
    )
    db.add(transaction)
    db.flush()
    db.refresh(transaction)
    return TransactionRecord(transaction=transaction, category_name=category.name)


def get_transaction(
    db: Session, *, user_id: UUID, transaction_id: UUID
) -> TransactionRecord:
    """Return a live transaction scoped to its authenticated owner."""

    row = _transaction_select().where(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
        Transaction.deleted_at.is_(None),
    )
    result = db.execute(row).one_or_none()
    if result is None:
        raise TransactionNotFoundError
    transaction, category_name = result
    return TransactionRecord(transaction=transaction, category_name=category_name)


def list_transactions(
    db: Session,
    *,
    user_id: UUID,
    account_id: UUID | None = None,
    transaction_type: Literal["income", "expense"] | None = None,
    category_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    offset: int = 0,
    limit: int = 50,
) -> TransactionPage:
    """Return paginated live history with stable newest-first ordering."""

    if offset < 0 or limit < 1 or limit > 100:
        raise InvalidTransactionError("Pagination must use offset >= 0 and limit from 1 to 100")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise InvalidTransactionError("date_from must be on or before date_to")

    conditions = [Transaction.user_id == user_id, Transaction.deleted_at.is_(None)]
    if account_id is not None:
        conditions.append(Transaction.account_id == account_id)
    if transaction_type is not None:
        conditions.append(Transaction.transaction_type == transaction_type)
    if category_id is not None:
        conditions.append(Transaction.category_id == category_id)
    if date_from is not None:
        conditions.append(Transaction.transaction_date >= date_from)
    if date_to is not None:
        conditions.append(Transaction.transaction_date <= date_to)

    total = db.scalar(select(func.count()).select_from(Transaction).where(*conditions)) or 0
    statement = (
        _transaction_select()
        .where(*conditions)
        .order_by(
            Transaction.transaction_date.desc(),
            Transaction.created_at.desc(),
            Transaction.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    rows = db.execute(statement).all()
    return TransactionPage(
        items=[
            TransactionRecord(transaction=transaction, category_name=category_name)
            for transaction, category_name in rows
        ],
        total=int(total),
        offset=offset,
        limit=limit,
    )


def _transaction_select():
    return select(Transaction, Category.name).outerjoin(
        Category,
        (Category.id == Transaction.category_id)
        & (Category.user_id == Transaction.user_id)
        & (Category.transaction_type == Transaction.transaction_type),
    )


def _validate_transaction_values(
    *, transaction_type: str, amount_paise: int, description: str, transaction_date: date
) -> None:
    if transaction_type not in {"income", "expense"}:
        raise InvalidTransactionError("Transaction type must be income or expense")
    if (
        type(amount_paise) is not int
        or amount_paise <= 0
        or amount_paise > MAX_SAFE_PAISE
    ):
        raise InvalidTransactionError(
            "Amount must be a positive safe integer number of paise"
        )
    if not isinstance(description, str) or not description.strip() or len(description.strip()) > 120:
        raise InvalidTransactionError("Description must contain 1 to 120 characters")
    if not isinstance(transaction_date, date):
        raise InvalidTransactionError("Transaction date is required")
    if transaction_date > financial_today():
        raise InvalidTransactionError("Transaction date cannot be in the future")


def _validate_daily_balance_range(
    db: Session,
    *,
    account: Account,
    transaction_date: date,
    balance_delta: int,
    as_of: date,
) -> None:
    """Reject a write if any affected daily closing balance would be unsafe.

    Transactions are daily records, so all live entries on a date contribute
    to the same closing balance. The daily aggregates and proposed delta are
    combined before a running-sum window is applied. The outer date filter is
    intentionally after that window so earlier days establish the balance at
    the transaction date. This checks each affected daily closing without
    loading individual transactions into application memory.
    """

    existing_daily = (
        select(
            Transaction.transaction_date.label("day"),
            func.sum(
                case(
                    (Transaction.transaction_type == "income", Transaction.amount_paise),
                    else_=-Transaction.amount_paise,
                )
            ).label("daily_net"),
        )
        .where(
            Transaction.user_id == account.user_id,
            Transaction.account_id == account.id,
            Transaction.deleted_at.is_(None),
            Transaction.transaction_date >= account.opening_balance_as_of,
            Transaction.transaction_date <= as_of,
        )
        .group_by(Transaction.transaction_date)
        .cte("existing_daily")
    )

    # The union makes a date row even when no existing transaction occurred
    # that day. Grouping afterward combines the proposed entry with all other
    # same-day entries before evaluating that day's closing balance.
    daily_entries = union_all(
        select(existing_daily.c.day, existing_daily.c.daily_net),
        select(literal(transaction_date), literal(balance_delta)),
    ).cte("daily_entries")
    daily_net = (
        select(
            daily_entries.c.day,
            func.sum(daily_entries.c.daily_net).label("daily_net"),
        )
        .group_by(daily_entries.c.day)
        .cte("daily_net")
    )
    daily_closings = (
        select(
            daily_net.c.day,
            (
                account.opening_balance_paise
                + func.sum(daily_net.c.daily_net).over(
                    order_by=daily_net.c.day,
                    rows=(None, 0),
                )
            ).label("balance_paise"),
        )
        .cte("daily_closings")
    )
    unsafe_closing = db.execute(
        select(daily_closings.c.day, daily_closings.c.balance_paise)
        .where(
            daily_closings.c.day >= transaction_date,
            or_(
                daily_closings.c.balance_paise < -MAX_SAFE_PAISE,
                daily_closings.c.balance_paise > MAX_SAFE_PAISE,
            ),
        )
        .limit(1)
    ).first()
    if unsafe_closing is not None:
        raise InvalidTransactionError(
            "Transaction would place a daily account balance outside the safe integer range"
        )
