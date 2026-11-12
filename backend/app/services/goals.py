"""Tenant-scoped savings goals and append-only allocation ledger operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.financial import MAX_SAFE_PAISE, financial_today
from app.models import Account, GoalEntry, SavingsGoal
from app.services.accounts import get_account_balance

GoalEntryType = Literal["contribution", "withdrawal"]


class GoalNotFoundError(LookupError):
    """The active goal is not owned by the authenticated user."""


class GoalAccountNotFoundError(LookupError):
    """The account is not owned by the authenticated user or is unavailable."""


class InvalidGoalError(ValueError):
    """A goal request violates a metadata or financial rule."""


class GoalTargetBelowAllocationError(ValueError):
    """A target update would put the target below the existing allocation."""


class InsufficientAvailableToSpendError(ValueError):
    """An account does not have enough unallocated money for a contribution."""


class ExcessiveGoalWithdrawalError(ValueError):
    """A withdrawal exceeds this goal's allocation in this account."""


class GoalAllocationLimitExceededError(ValueError):
    """A contribution would exceed the safe-integer goal aggregate limit."""


class GoalAllocationInvariantError(RuntimeError):
    """Persisted allocations exceed the supported safe-integer response range."""


@dataclass(frozen=True, slots=True)
class GoalSnapshot:
    goal: SavingsGoal
    account_allocations: tuple[tuple[UUID, int], ...]

    @property
    def allocated_paise(self) -> int:
        total = sum(amount for _, amount in self.account_allocations)
        if total > MAX_SAFE_PAISE:
            raise GoalAllocationInvariantError(
                "Goal allocation exceeds the supported safe-integer range"
            )
        return total


@dataclass(frozen=True, slots=True)
class GoalPage:
    items: list[GoalSnapshot]
    total: int
    offset: int
    limit: int


@dataclass(frozen=True, slots=True)
class GoalEntryPage:
    items: list[GoalEntry]
    total: int
    offset: int
    limit: int


def list_goals(
    db: Session, *, user_id: UUID, offset: int = 0, limit: int = 50
) -> GoalPage:
    _validate_pagination(offset=offset, limit=limit)
    count = int(
        db.scalar(
            select(func.count())
            .select_from(SavingsGoal)
            .where(SavingsGoal.user_id == user_id, SavingsGoal.deleted_at.is_(None))
        )
        or 0
    )
    goals = list(
        db.scalars(
            select(SavingsGoal)
            .where(SavingsGoal.user_id == user_id, SavingsGoal.deleted_at.is_(None))
            .order_by(SavingsGoal.created_at.desc(), SavingsGoal.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    allocations = _allocations_by_goal_and_account(
        db, user_id=user_id, goal_ids=[goal.id for goal in goals]
    )
    return GoalPage(
        items=[
            GoalSnapshot(
                goal,
                tuple(
                    sorted(
                        allocations.get(goal.id, {}).items(),
                        key=lambda item: item[0].int,
                    )
                ),
            )
            for goal in goals
        ],
        total=count,
        offset=offset,
        limit=limit,
    )


def get_goal(db: Session, *, user_id: UUID, goal_id: UUID) -> GoalSnapshot:
    goal = db.scalar(
        select(SavingsGoal).where(
            SavingsGoal.id == goal_id,
            SavingsGoal.user_id == user_id,
            SavingsGoal.deleted_at.is_(None),
        )
    )
    if goal is None:
        raise GoalNotFoundError
    allocations = _allocations_by_goal_and_account(
        db, user_id=user_id, goal_ids=[goal.id]
    )
    return GoalSnapshot(
        goal,
        tuple(
            sorted(allocations.get(goal.id, {}).items(), key=lambda item: item[0].int)
        ),
    )


def create_goal(
    db: Session,
    *,
    user_id: UUID,
    name: str,
    description: str | None,
    target_paise: int,
    target_date: date | None,
) -> GoalSnapshot:
    _validate_goal_values(
        name=name,
        description=description,
        target_paise=target_paise,
        target_date=target_date,
    )
    goal = SavingsGoal(
        user_id=user_id,
        name=name.strip(),
        description=_normalize_description(description),
        target_paise=target_paise,
        target_date=target_date,
    )
    db.add(goal)
    db.flush()
    return get_goal(db, user_id=user_id, goal_id=goal.id)


def update_goal(
    db: Session,
    *,
    user_id: UUID,
    goal_id: UUID,
    changes: dict[str, object],
) -> GoalSnapshot:
    if not changes:
        raise InvalidGoalError("At least one goal field must be supplied")
    goal = _lock_active_goal(db, user_id=user_id, goal_id=goal_id)

    if "name" in changes:
        name = changes["name"]
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise InvalidGoalError("Goal name must contain 1 to 100 characters")
        goal.name = name.strip()

    if "description" in changes:
        description = changes["description"]
        if description is not None and (
            not isinstance(description, str) or len(description) > 2000
        ):
            raise InvalidGoalError("Goal description must be at most 2000 characters")
        goal.description = _normalize_description(description)

    if "target_date" in changes:
        target_date = changes["target_date"]
        _validate_target_date(target_date)
        goal.target_date = target_date

    if "target_paise" in changes:
        target_paise = _validate_target_paise(changes["target_paise"])
        allocated_paise = _allocated_for_goal(db, user_id=user_id, goal_id=goal.id)
        if target_paise < allocated_paise:
            raise GoalTargetBelowAllocationError(
                "Target amount cannot be lower than the currently allocated amount"
            )
        goal.target_paise = target_paise

    db.flush()
    return get_goal(db, user_id=user_id, goal_id=goal.id)


def delete_goal(db: Session, *, user_id: UUID, goal_id: UUID) -> None:
    """Release every outstanding account allocation and soft-delete atomically.

    Lock order is goal first, followed by all affected account rows in ascending
    UUID order. Every contribution and withdrawal uses the same goal-then-account
    order, while transaction writes lock only the account row.
    """

    goal = _lock_active_goal(db, user_id=user_id, goal_id=goal_id)
    allocations = _allocations_by_goal_and_account(
        db, user_id=user_id, goal_ids=[goal.id]
    ).get(goal.id, {})
    outstanding = sorted(
        ((account_id, amount) for account_id, amount in allocations.items() if amount > 0),
        key=lambda item: item[0].int,
    )
    if outstanding:
        account_ids = [account_id for account_id, _ in outstanding]
        accounts = list(
            db.scalars(
                select(Account)
                .where(
                    Account.user_id == user_id,
                    Account.id.in_(account_ids),
                )
                .order_by(Account.id)
                .with_for_update()
            ).all()
        )
        if {account.id for account in accounts} != set(account_ids):
            raise GoalAccountNotFoundError
        today = financial_today()
        db.add_all(
            [
                GoalEntry(
                    user_id=user_id,
                    goal_id=goal.id,
                    account_id=account_id,
                    entry_type="withdrawal",
                    amount_paise=amount,
                    effective_date=today,
                )
                for account_id, amount in outstanding
            ]
        )
    goal.deleted_at = datetime.now(timezone.utc)
    db.flush()


def list_goal_entries(
    db: Session,
    *,
    user_id: UUID,
    goal_id: UUID,
    offset: int = 0,
    limit: int = 50,
) -> GoalEntryPage:
    _validate_pagination(offset=offset, limit=limit)
    _require_active_goal(db, user_id=user_id, goal_id=goal_id)
    conditions = [GoalEntry.user_id == user_id, GoalEntry.goal_id == goal_id]
    total = int(
        db.scalar(select(func.count()).select_from(GoalEntry).where(*conditions)) or 0
    )
    entries = list(
        db.scalars(
            select(GoalEntry)
            .where(*conditions)
            .order_by(GoalEntry.created_at.desc(), GoalEntry.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return GoalEntryPage(items=entries, total=total, offset=offset, limit=limit)


def create_goal_entry(
    db: Session,
    *,
    user_id: UUID,
    goal_id: UUID,
    account_id: UUID,
    amount_paise: int,
    entry_type: GoalEntryType,
) -> GoalEntry:
    if entry_type not in {"contribution", "withdrawal"}:
        raise InvalidGoalError("Entry type must be contribution or withdrawal")
    _validate_target_paise(amount_paise)

    # Goal first serializes all allocation changes for this goal, including
    # deletion. The account lock then serializes against all other goals and
    # account transactions that can change available-to-spend.
    goal = _lock_active_goal(db, user_id=user_id, goal_id=goal_id)
    account_statement = select(Account).where(
        Account.id == account_id,
        Account.user_id == user_id,
    )
    if entry_type == "contribution":
        account_statement = account_statement.where(Account.archived_at.is_(None))
    account = db.scalar(account_statement.with_for_update())
    if account is None:
        raise GoalAccountNotFoundError

    today = financial_today()
    account_snapshot = get_account_balance(
        db,
        user_id=user_id,
        account_id=account.id,
        as_of=today,
        include_archived=entry_type == "withdrawal",
    )
    goal_account_allocations = _allocations_by_goal_and_account(
        db, user_id=user_id, goal_ids=[goal.id]
    ).get(goal.id, {})
    goal_allocated = goal_account_allocations.get(account.id, 0)
    if entry_type == "contribution":
        if amount_paise > account_snapshot.available_to_spend_paise:
            raise InsufficientAvailableToSpendError
        goal_allocated_total = sum(goal_account_allocations.values())
        if amount_paise > MAX_SAFE_PAISE - goal_allocated_total:
            raise GoalAllocationLimitExceededError(
                "Goal allocation cannot exceed the safe-integer paise limit"
            )
    elif amount_paise > goal_allocated:
        raise ExcessiveGoalWithdrawalError

    entry = GoalEntry(
        user_id=user_id,
        goal_id=goal.id,
        account_id=account.id,
        entry_type=entry_type,
        amount_paise=amount_paise,
        effective_date=today,
    )
    db.add(entry)
    db.flush()
    db.refresh(entry)
    return entry


def _lock_active_goal(db: Session, *, user_id: UUID, goal_id: UUID) -> SavingsGoal:
    goal = db.scalar(
        select(SavingsGoal)
        .where(
            SavingsGoal.id == goal_id,
            SavingsGoal.user_id == user_id,
            SavingsGoal.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if goal is None:
        raise GoalNotFoundError
    return goal


def _require_active_goal(db: Session, *, user_id: UUID, goal_id: UUID) -> SavingsGoal:
    goal = db.scalar(
        select(SavingsGoal).where(
            SavingsGoal.id == goal_id,
            SavingsGoal.user_id == user_id,
            SavingsGoal.deleted_at.is_(None),
        )
    )
    if goal is None:
        raise GoalNotFoundError
    return goal


def _allocations_by_goal_and_account(
    db: Session, *, user_id: UUID, goal_ids: list[UUID]
) -> dict[UUID, dict[UUID, int]]:
    if not goal_ids:
        return {}
    net_amount = func.sum(
        case(
            (GoalEntry.entry_type == "contribution", GoalEntry.amount_paise),
            else_=-GoalEntry.amount_paise,
        )
    )
    rows = db.execute(
        select(GoalEntry.goal_id, GoalEntry.account_id, net_amount)
        .where(
            GoalEntry.user_id == user_id,
            GoalEntry.goal_id.in_(goal_ids),
            GoalEntry.effective_date <= financial_today(),
        )
        .group_by(GoalEntry.goal_id, GoalEntry.account_id)
        .order_by(GoalEntry.goal_id, GoalEntry.account_id)
    ).all()
    result: dict[UUID, dict[UUID, int]] = {}
    for goal_id, account_id, amount in rows:
        value = int(amount)
        if value < 0:
            raise RuntimeError("Goal allocation ledger invariant was violated")
        if value:
            result.setdefault(goal_id, {})[account_id] = value
    return result


def _allocated_for_goal(db: Session, *, user_id: UUID, goal_id: UUID) -> int:
    allocations = _allocations_by_goal_and_account(
        db, user_id=user_id, goal_ids=[goal_id]
    ).get(goal_id, {})
    return sum(allocations.values())


def _validate_goal_values(
    *,
    name: object,
    description: object,
    target_paise: object,
    target_date: object,
) -> None:
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise InvalidGoalError("Goal name must contain 1 to 100 characters")
    if description is not None and (
        not isinstance(description, str) or len(description) > 2000
    ):
        raise InvalidGoalError("Goal description must be at most 2000 characters")
    _validate_target_paise(target_paise)
    _validate_target_date(target_date)


def _validate_target_paise(value: object) -> int:
    if type(value) is not int or not 0 < value <= MAX_SAFE_PAISE:
        raise InvalidGoalError(
            "Amount must be a positive safe integer number of paise"
        )
    return value


def _validate_target_date(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, date) or isinstance(value, datetime):
        raise InvalidGoalError("Target date must be a valid date")
    if value < financial_today():
        raise InvalidGoalError("Target date cannot be in the past")


def _normalize_description(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidGoalError("Goal description must be text")
    cleaned = value.strip()
    return cleaned or None


def _validate_pagination(*, offset: int, limit: int) -> None:
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise InvalidGoalError("Pagination must use offset >= 0 and limit from 1 to 100")
