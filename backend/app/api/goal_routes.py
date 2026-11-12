"""Authenticated savings-goal and allocation-ledger endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    AuthenticatedRequest,
    get_authenticated_request,
    require_csrf,
)
from app.core.database import get_db
from app.models import GoalEntry
from app.schemas.goals import (
    GoalAccountAllocationResponse,
    GoalAccountSummaryResponse,
    GoalCreateRequest,
    GoalEntryCreateRequest,
    GoalEntryMutationResponse,
    GoalEntryPageResponse,
    GoalEntryResponse,
    GoalPageResponse,
    GoalResponse,
    GoalUpdateRequest,
)
from app.services.accounts import get_account_balance
from app.services.goals import (
    ExcessiveGoalWithdrawalError,
    GoalAllocationLimitExceededError,
    GoalAllocationInvariantError,
    GoalAccountNotFoundError,
    GoalEntryPage,
    GoalNotFoundError,
    GoalPage,
    GoalSnapshot,
    GoalTargetBelowAllocationError,
    InsufficientAvailableToSpendError,
    InvalidGoalError,
    create_goal,
    create_goal_entry,
    delete_goal,
    get_goal,
    list_goal_entries,
    list_goals,
    update_goal,
)

router = APIRouter(prefix="/api/goals", tags=["savings goals"])


def _goal_response(snapshot: GoalSnapshot) -> GoalResponse:
    goal = snapshot.goal
    try:
        allocated_paise = snapshot.allocated_paise
    except GoalAllocationInvariantError:
        raise HTTPException(
            status_code=500,
            detail="Stored goal allocation exceeds the supported monetary range",
        ) from None
    return GoalResponse(
        id=goal.id,
        name=goal.name,
        description=goal.description,
        target_paise=goal.target_paise,
        target_date=goal.target_date,
        allocated_paise=allocated_paise,
        remaining_target_paise=goal.target_paise - allocated_paise,
        account_allocations=[
            GoalAccountAllocationResponse(account_id=account_id, allocated_paise=amount)
            for account_id, amount in snapshot.account_allocations
        ],
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


def _entry_response(entry: GoalEntry) -> GoalEntryResponse:
    return GoalEntryResponse(
        id=entry.id,
        goal_id=entry.goal_id,
        account_id=entry.account_id,
        entry_type=entry.entry_type,
        amount_paise=entry.amount_paise,
        effective_date=entry.effective_date,
        created_at=entry.created_at,
    )


def _entry_mutation_response(
    db: Session, *, user_id: UUID, entry: GoalEntry
) -> GoalEntryMutationResponse:
    goal = get_goal(db, user_id=user_id, goal_id=entry.goal_id)
    account = get_account_balance(
        db,
        user_id=user_id,
        account_id=entry.account_id,
        include_archived=True,
    )
    return GoalEntryMutationResponse(
        entry=_entry_response(entry),
        goal=_goal_response(goal),
        account=GoalAccountSummaryResponse(
            account_id=entry.account_id,
            balance_paise=account.balance_paise,
            goal_allocated_paise=account.goal_allocated_paise,
            available_to_spend_paise=account.available_to_spend_paise,
        ),
    )


def _rollback_error(db: Session, *, code: int, message: str) -> HTTPException:
    db.rollback()
    return HTTPException(status_code=code, detail=message)


def _commit(db: Session, *, message: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail=message) from None


def _commit_read_activity(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=GoalPageResponse)
def goals(
    response: Response,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalPageResponse:
    try:
        page: GoalPage = list_goals(
            db,
            user_id=authenticated.current_user.user_id,
            offset=offset,
            limit=limit,
        )
    except InvalidGoalError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    _commit_read_activity(db)
    response.headers["Cache-Control"] = "no-store"
    return GoalPageResponse(
        items=[_goal_response(item) for item in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.get("/{goal_id}", response_model=GoalResponse)
def goal(
    goal_id: UUID,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalResponse:
    try:
        snapshot = get_goal(
            db, user_id=authenticated.current_user.user_id, goal_id=goal_id
        )
    except GoalNotFoundError:
        raise HTTPException(status_code=404, detail="Goal not found") from None
    _commit_read_activity(db)
    response.headers["Cache-Control"] = "no-store"
    return _goal_response(snapshot)


@router.post(
    "",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def post_goal(
    payload: GoalCreateRequest,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalResponse:
    try:
        snapshot = create_goal(
            db,
            user_id=authenticated.current_user.user_id,
            name=payload.name,
            description=payload.description,
            target_paise=payload.target_paise,
            target_date=payload.target_date,
        )
        _commit(db, message="Goal could not be saved")
    except InvalidGoalError as error:
        raise _rollback_error(db, code=422, message=str(error)) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Goal could not be saved") from None
    response.headers["Cache-Control"] = "no-store"
    return _goal_response(snapshot)


@router.patch(
    "/{goal_id}",
    response_model=GoalResponse,
    dependencies=[Depends(require_csrf)],
)
def patch_goal(
    goal_id: UUID,
    payload: GoalUpdateRequest,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalResponse:
    try:
        snapshot = update_goal(
            db,
            user_id=authenticated.current_user.user_id,
            goal_id=goal_id,
            changes=payload.model_dump(exclude_unset=True),
        )
        _commit(db, message="Goal could not be saved")
    except GoalNotFoundError:
        raise _rollback_error(db, code=404, message="Goal not found") from None
    except GoalTargetBelowAllocationError as error:
        raise _rollback_error(db, code=409, message=str(error)) from None
    except InvalidGoalError as error:
        raise _rollback_error(db, code=422, message=str(error)) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Goal could not be saved") from None
    response.headers["Cache-Control"] = "no-store"
    return _goal_response(snapshot)


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_csrf)],
)
def remove_goal(
    goal_id: UUID,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> Response:
    try:
        delete_goal(db, user_id=authenticated.current_user.user_id, goal_id=goal_id)
        _commit(db, message="Goal could not be deleted")
    except GoalNotFoundError:
        raise _rollback_error(db, code=404, message="Goal not found") from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Goal could not be deleted") from None
    response.status_code = status.HTTP_204_NO_CONTENT
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/{goal_id}/entries", response_model=GoalEntryPageResponse)
def goal_entries(
    goal_id: UUID,
    response: Response,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalEntryPageResponse:
    try:
        page: GoalEntryPage = list_goal_entries(
            db,
            user_id=authenticated.current_user.user_id,
            goal_id=goal_id,
            offset=offset,
            limit=limit,
        )
    except GoalNotFoundError:
        raise HTTPException(status_code=404, detail="Goal not found") from None
    except InvalidGoalError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    _commit_read_activity(db)
    response.headers["Cache-Control"] = "no-store"
    return GoalEntryPageResponse(
        items=[_entry_response(item) for item in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


def _post_goal_entry(
    *,
    goal_id: UUID,
    payload: GoalEntryCreateRequest,
    response: Response,
    authenticated: AuthenticatedRequest,
    db: Session,
    entry_type: str,
) -> GoalEntryMutationResponse:
    user_id = authenticated.current_user.user_id
    try:
        entry = create_goal_entry(
            db,
            user_id=user_id,
            goal_id=goal_id,
            account_id=payload.account_id,
            amount_paise=payload.amount_paise,
            entry_type=entry_type,
        )
        result = _entry_mutation_response(db, user_id=user_id, entry=entry)
        _commit(db, message="Goal allocation could not be saved")
    except GoalNotFoundError:
        raise _rollback_error(db, code=404, message="Goal not found") from None
    except GoalAccountNotFoundError:
        raise _rollback_error(db, code=404, message="Account not found") from None
    except InsufficientAvailableToSpendError:
        raise _rollback_error(
            db, code=409, message="Insufficient available-to-spend balance"
        ) from None
    except GoalAllocationLimitExceededError as error:
        raise _rollback_error(db, code=409, message=str(error)) from None
    except ExcessiveGoalWithdrawalError:
        raise _rollback_error(
            db, code=409, message="Withdrawal exceeds this goal's allocation in this account"
        ) from None
    except InvalidGoalError as error:
        raise _rollback_error(db, code=422, message=str(error)) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Goal allocation could not be saved"
        ) from None
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/{goal_id}/contributions",
    response_model=GoalEntryMutationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def post_goal_contribution(
    goal_id: UUID,
    payload: GoalEntryCreateRequest,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalEntryMutationResponse:
    return _post_goal_entry(
        goal_id=goal_id,
        payload=payload,
        response=response,
        authenticated=authenticated,
        db=db,
        entry_type="contribution",
    )


@router.post(
    "/{goal_id}/withdrawals",
    response_model=GoalEntryMutationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def post_goal_withdrawal(
    goal_id: UUID,
    payload: GoalEntryCreateRequest,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalEntryMutationResponse:
    return _post_goal_entry(
        goal_id=goal_id,
        payload=payload,
        response=response,
        authenticated=authenticated,
        db=db,
        entry_type="withdrawal",
    )
