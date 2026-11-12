"""Top-level API routes."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.auth_routes import router as auth_router
from app.api.account_routes import router as account_router
from app.api.budget_routes import router as budget_router
from app.api.category_routes import router as category_router
from app.api.goal_routes import router as goal_router
from app.api.transaction_routes import router as transaction_router
from app.core.database import get_db

router = APIRouter()
router.include_router(auth_router)
router.include_router(account_router)
router.include_router(budget_router)
router.include_router(goal_router)
router.include_router(category_router)
router.include_router(transaction_router)


@router.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Report that the API process is responding."""

    return {"status": "ok"}


@router.get("/health/db", tags=["health"])
def database_health_check(db: Session = Depends(get_db)) -> JSONResponse:
    """Report database readiness without returning internal error details."""

    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unavailable"},
        )

    return JSONResponse(
        status_code=200,
        content={"status": "ok", "database": "available"},
    )
