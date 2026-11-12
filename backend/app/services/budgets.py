"""Tenant-scoped monthly budgets and transaction-derived spending totals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.financial import MAX_SAFE_PAISE
from app.models import Budget, Category, Transaction

OVERALL_BUDGET_INDEX: Final = "uq_budgets_one_overall_per_month"
CATEGORY_BUDGET_INDEX: Final = "uq_budgets_one_per_category_month"


class BudgetNotFoundError(LookupError):
    """The requested budget is not owned by the authenticated user."""


class DuplicateBudgetError(ValueError):
    """A budget already exists for this user, month, and budget type."""


class InvalidBudgetError(ValueError):
    """A budget request violates a business rule."""


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    budget: Budget
    category_name: str | None
    actual_spending_paise: int

    @property
    def remaining_paise(self) -> int:
        return self.budget.limit_paise - self.actual_spending_paise

    @property
    def percent_used_basis_points(self) -> int:
        """Return percent used in hundredths of a percent, rounded half-up."""

        numerator = self.actual_spending_paise * 10_000
        return (numerator + self.budget.limit_paise // 2) // self.budget.limit_paise


def list_budgets(
    db: Session, *, user_id: UUID, month_start: date | None = None
) -> list[BudgetSnapshot]:
    """List the user's budgets, optionally limited to one calendar month."""

    if month_start is not None:
        _validate_month_start(month_start)
    return _load_snapshots(db, user_id=user_id, month_start=month_start)


def get_budget(
    db: Session, *, user_id: UUID, budget_id: UUID
) -> BudgetSnapshot:
    """Get one budget only when it belongs to the supplied user."""

    snapshots = _load_snapshots(
        db,
        user_id=user_id,
        budget_id=budget_id,
    )
    if not snapshots:
        raise BudgetNotFoundError
    return snapshots[0]


def create_budget(
    db: Session,
    *,
    user_id: UUID,
    month_start: date,
    category_id: UUID | None,
    limit_paise: int,
) -> BudgetSnapshot:
    """Stage one overall or expense-category budget without committing."""

    _validate_month_start(month_start)
    _validate_limit(limit_paise)
    if category_id is not None:
        _require_active_expense_category(db, user_id=user_id, category_id=category_id)

    budget = Budget(
        user_id=user_id,
        month_start=month_start,
        category_id=category_id,
        limit_paise=limit_paise,
    )
    db.add(budget)
    _flush_or_raise_duplicate(db)
    return get_budget(db, user_id=user_id, budget_id=budget.id)


def update_budget(
    db: Session,
    *,
    user_id: UUID,
    budget_id: UUID,
    changes: dict[str, object],
) -> BudgetSnapshot:
    """Stage permitted budget edits for an owned budget."""

    if not changes:
        raise InvalidBudgetError("At least one budget field must be supplied")
    budget = db.scalar(
        select(Budget)
        .where(Budget.id == budget_id, Budget.user_id == user_id)
        .with_for_update()
    )
    if budget is None:
        raise BudgetNotFoundError

    if "month_start" in changes:
        month_start = changes["month_start"]
        budget.month_start = _validate_month_start(month_start)

    if "limit_paise" in changes:
        limit_paise = changes["limit_paise"]
        budget.limit_paise = _validate_limit(limit_paise)

    if "category_id" in changes:
        category_id = changes["category_id"]
        if category_id is not None and category_id != budget.category_id:
            _require_active_expense_category(
                db, user_id=user_id, category_id=category_id
            )
        budget.category_id = category_id

    _flush_or_raise_duplicate(db)
    return get_budget(db, user_id=user_id, budget_id=budget.id)


def delete_budget(db: Session, *, user_id: UUID, budget_id: UUID) -> None:
    """Hard-delete one owned budget, matching the model's deletion convention."""

    budget = db.scalar(
        select(Budget)
        .where(Budget.id == budget_id, Budget.user_id == user_id)
        .with_for_update()
    )
    if budget is None:
        raise BudgetNotFoundError
    db.delete(budget)
    db.flush()


def _load_snapshots(
    db: Session,
    *,
    user_id: UUID,
    budget_id: UUID | None = None,
    month_start: date | None = None,
) -> list[BudgetSnapshot]:
    statement = (
        select(Budget, Category.name)
        .outerjoin(
            Category,
            (Category.id == Budget.category_id)
            & (Category.user_id == Budget.user_id),
        )
        .where(Budget.user_id == user_id)
        .order_by(
            Budget.month_start.desc(),
            Budget.category_id.is_not(None),
            Budget.category_id,
            Budget.id,
        )
    )
    if budget_id is not None:
        statement = statement.where(Budget.id == budget_id)
    if month_start is not None:
        statement = statement.where(Budget.month_start == month_start)
    budget_rows = db.execute(statement).all()
    if not budget_rows:
        return []

    months = [budget.month_start for budget, _ in budget_rows]
    first_month = min(months)
    spending_statement = (
        select(
            Transaction.transaction_date,
            Transaction.category_id,
            func.sum(Transaction.amount_paise),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == "expense",
            Transaction.deleted_at.is_(None),
            Transaction.transaction_date >= first_month,
        )
        .group_by(Transaction.transaction_date, Transaction.category_id)
    )
    end_month = _next_month(max(months))
    if end_month is not None:
        spending_statement = spending_statement.where(
            Transaction.transaction_date < end_month
        )
    spending_rows = db.execute(spending_statement).all()

    overall_by_month: dict[date, int] = {}
    category_by_month: dict[tuple[date, UUID], int] = {}
    for transaction_date, category_id, total in spending_rows:
        month = transaction_date.replace(day=1)
        amount = int(total)
        overall_by_month[month] = overall_by_month.get(month, 0) + amount
        if category_id is not None:
            key = (month, category_id)
            category_by_month[key] = category_by_month.get(key, 0) + amount

    snapshots: list[BudgetSnapshot] = []
    for budget, category_name in budget_rows:
        if budget.category_id is None:
            actual = overall_by_month.get(budget.month_start, 0)
        else:
            actual = category_by_month.get(
                (budget.month_start, budget.category_id), 0
            )
        snapshots.append(
            BudgetSnapshot(
                budget=budget,
                category_name=category_name,
                actual_spending_paise=actual,
            )
        )
    return snapshots


def _require_active_expense_category(
    db: Session, *, user_id: UUID, category_id: UUID
) -> None:
    category = db.scalar(
        select(Category.id).where(
            Category.id == category_id,
            Category.user_id == user_id,
            Category.transaction_type == "expense",
            Category.archived_at.is_(None),
        )
    )
    if category is None:
        raise InvalidBudgetError(
            "Choose an active expense category owned by you"
        )


def _validate_month_start(value: object) -> date:
    if not isinstance(value, date) or isinstance(value, datetime) or value.day != 1:
        raise InvalidBudgetError("month_start must be the first day of a month")
    return value


def _validate_limit(value: object) -> int:
    if type(value) is not int or not 0 < value <= MAX_SAFE_PAISE:
        raise InvalidBudgetError(
            "limit_paise must be a positive safe integer number of paise"
        )
    return value


def _flush_or_raise_duplicate(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as error:
        if _is_budget_unique_violation(error):
            raise DuplicateBudgetError(
                "A budget of this type already exists for this month"
            ) from error
        raise


def _is_budget_unique_violation(error: IntegrityError) -> bool:
    original = error.orig
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    diagnostic = getattr(original, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    return sqlstate == "23505" and constraint_name in {
        OVERALL_BUDGET_INDEX,
        CATEGORY_BUDGET_INDEX,
    }


def _next_month(month_start: date) -> date | None:
    if month_start.month == 12:
        if month_start.year == date.max.year:
            return None
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)
