"""Authenticated monthly budget CRUD and spending endpoints."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import AuthenticatedRequest, get_authenticated_request, require_csrf
from app.core.database import get_db
from app.schemas.budgets import BudgetCreateRequest, BudgetResponse, BudgetUpdateRequest
from app.services.budgets import (
    BudgetNotFoundError,
    BudgetSnapshot,
    DuplicateBudgetError,
    InvalidBudgetError,
    create_budget,
    delete_budget,
    get_budget,
    list_budgets,
    update_budget,
)

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def _budget_response(snapshot: BudgetSnapshot) -> BudgetResponse:
    budget = snapshot.budget
    return BudgetResponse(
        id=budget.id,
        month_start=budget.month_start,
        category_id=budget.category_id,
        category_name=snapshot.category_name,
        limit_paise=budget.limit_paise,
        actual_spending_paise=str(snapshot.actual_spending_paise),
        remaining_paise=str(snapshot.remaining_paise),
        percent_used_basis_points=str(snapshot.percent_used_basis_points),
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


def _rollback_error(db: Session, *, code: int, message: str) -> HTTPException:
    db.rollback()
    return HTTPException(status_code=code, detail=message)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Budget could not be saved",
        ) from None


def _commit_read_activity(db: Session) -> None:
    """Persist the activity refresh performed by authentication."""

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=list[BudgetResponse])
def budgets(
    response: Response,
    month_start: date | None = None,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> list[BudgetResponse]:
    """List the authenticated user's budgets, optionally for one month."""

    try:
        snapshots = list_budgets(
            db,
            user_id=authenticated.current_user.user_id,
            month_start=month_start,
        )
    except InvalidBudgetError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    _commit_read_activity(db)
    response.headers["Cache-Control"] = "no-store"
    return [_budget_response(snapshot) for snapshot in snapshots]


@router.get("/{budget_id}", response_model=BudgetResponse)
def budget(
    budget_id: UUID,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> BudgetResponse:
    """Get one budget scoped to the authenticated user."""

    try:
        snapshot = get_budget(
            db, user_id=authenticated.current_user.user_id, budget_id=budget_id
        )
    except BudgetNotFoundError:
        raise HTTPException(status_code=404, detail="Budget not found") from None
    _commit_read_activity(db)
    response.headers["Cache-Control"] = "no-store"
    return _budget_response(snapshot)


@router.post(
    "",
    response_model=BudgetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def post_budget(
    payload: BudgetCreateRequest,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> BudgetResponse:
    """Create an overall or expense-category budget."""

    try:
        snapshot = create_budget(
            db,
            user_id=authenticated.current_user.user_id,
            month_start=payload.month_start,
            category_id=payload.category_id,
            limit_paise=payload.limit_paise,
        )
        _commit(db)
    except BudgetNotFoundError:
        raise _rollback_error(db, code=404, message="Budget not found") from None
    except DuplicateBudgetError:
        raise _rollback_error(
            db, code=409, message="A budget of this type already exists for this month"
        ) from None
    except InvalidBudgetError as error:
        raise _rollback_error(db, code=422, message=str(error)) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Budget could not be saved"
        ) from None

    response.headers["Cache-Control"] = "no-store"
    return _budget_response(snapshot)


@router.patch(
    "/{budget_id}",
    response_model=BudgetResponse,
    dependencies=[Depends(require_csrf)],
)
def patch_budget(
    budget_id: UUID,
    payload: BudgetUpdateRequest,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> BudgetResponse:
    """Update a user's existing budget without changing historical spending."""

    try:
        snapshot = update_budget(
            db,
            user_id=authenticated.current_user.user_id,
            budget_id=budget_id,
            changes=payload.model_dump(exclude_unset=True),
        )
        _commit(db)
    except BudgetNotFoundError:
        raise _rollback_error(db, code=404, message="Budget not found") from None
    except DuplicateBudgetError:
        raise _rollback_error(
            db, code=409, message="A budget of this type already exists for this month"
        ) from None
    except InvalidBudgetError as error:
        raise _rollback_error(db, code=422, message=str(error)) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Budget could not be saved"
        ) from None

    response.headers["Cache-Control"] = "no-store"
    return _budget_response(snapshot)


@router.delete(
    "/{budget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_csrf)],
)
def remove_budget(
    budget_id: UUID,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a budget owned by the authenticated user."""

    try:
        delete_budget(
            db, user_id=authenticated.current_user.user_id, budget_id=budget_id
        )
        _commit(db)
    except BudgetNotFoundError:
        raise _rollback_error(db, code=404, message="Budget not found") from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Budget could not be deleted"
        ) from None

    response.status_code = status.HTTP_204_NO_CONTENT
    response.headers["Cache-Control"] = "no-store"
    return response
