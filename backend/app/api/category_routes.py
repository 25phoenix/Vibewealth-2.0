"""Authenticated category selection endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import AuthenticatedRequest, get_authenticated_request
from app.core.database import get_db
from app.schemas.categories import CategoryResponse
from app.services.categories import list_active_categories

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def categories(
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> list[CategoryResponse]:
    """List active categories for the authenticated user."""

    records = list_active_categories(db, user_id=authenticated.current_user.user_id)
    # Authentication updates the session's last-activity timestamp.
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Categories could not be loaded",
        ) from None
    response.headers["Cache-Control"] = "no-store"
    return [
        CategoryResponse(
            id=category.id,
            name=category.name,
            transaction_type=category.transaction_type,
        )
        for category in records
    ]
