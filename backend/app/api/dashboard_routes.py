"""Authenticated financial dashboard summary endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import AuthenticatedRequest, get_authenticated_request
from app.core.database import get_db
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard import DashboardSummaryInvariantError, get_dashboard_summary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> DashboardSummaryResponse:
    """Return current-month finances for the authenticated user only."""

    try:
        summary = get_dashboard_summary(
            db, user_id=authenticated.current_user.user_id
        )
        # Authentication updates session activity in this request transaction.
        db.commit()
    except DashboardSummaryInvariantError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Stored financial summary exceeds a supported monetary range",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Dashboard summary could not be loaded"
        ) from None

    response.headers["Cache-Control"] = "no-store"
    return DashboardSummaryResponse.model_validate(summary)
