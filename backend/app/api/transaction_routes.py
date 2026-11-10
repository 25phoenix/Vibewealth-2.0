"""Authenticated transaction creation and history endpoints."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import AuthenticatedRequest, get_authenticated_request, require_csrf
from app.core.database import get_db
from app.schemas.transactions import (
    TransactionCreateRequest,
    TransactionListResponse,
    TransactionResponse,
)
from app.services.transactions import (
    AccountNotFoundError,
    InvalidTransactionError,
    TransactionNotFoundError,
    TransactionPage,
    TransactionRecord,
    create_transaction,
    get_transaction,
    list_transactions,
)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _transaction_response(record: TransactionRecord) -> TransactionResponse:
    transaction = record.transaction
    return TransactionResponse(
        id=transaction.id,
        account_id=transaction.account_id,
        category_id=transaction.category_id,
        category_name=record.category_name,
        transaction_type=transaction.transaction_type,
        amount_paise=transaction.amount_paise,
        description=transaction.description,
        transaction_date=transaction.transaction_date,
        notes=transaction.notes,
        created_at=transaction.created_at,
        updated_at=transaction.updated_at,
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
            detail="Transaction could not be saved",
        ) from None


def _commit_read_activity(db: Session) -> None:
    """Persist the session activity touch performed by authentication."""

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=TransactionListResponse)
def transactions(
    response: Response,
    account_id: UUID | None = None,
    transaction_type: Literal["income", "expense"] | None = None,
    category_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> TransactionListResponse:
    """List the user's live transactions with filters and stable pagination."""

    try:
        page: TransactionPage = list_transactions(
            db,
            user_id=authenticated.current_user.user_id,
            account_id=account_id,
            transaction_type=transaction_type,
            category_id=category_id,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=limit,
        )
    except InvalidTransactionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    _commit_read_activity(db)
    response.headers["Cache-Control"] = "no-store"
    return TransactionListResponse(
        items=[_transaction_response(record) for record in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
def transaction(
    transaction_id: UUID,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> TransactionResponse:
    """Retrieve a live transaction only for its authenticated owner."""

    try:
        record = get_transaction(
            db,
            user_id=authenticated.current_user.user_id,
            transaction_id=transaction_id,
        )
    except TransactionNotFoundError:
        raise HTTPException(status_code=404, detail="Transaction not found") from None
    _commit_read_activity(db)
    response.headers["Cache-Control"] = "no-store"
    return _transaction_response(record)


@router.post(
    "",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def post_transaction(
    payload: TransactionCreateRequest,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> TransactionResponse:
    """Create one income or expense and commit at the HTTP boundary."""

    try:
        record = create_transaction(
            db,
            user_id=authenticated.current_user.user_id,
            account_id=payload.account_id,
            category_id=payload.category_id,
            transaction_type=payload.transaction_type,
            amount_paise=payload.amount_paise,
            description=payload.description,
            transaction_date=payload.transaction_date,
            notes=payload.notes,
        )
        _commit(db)
    except AccountNotFoundError:
        raise _rollback_error(db, code=404, message="Account not found") from None
    except InvalidTransactionError as error:
        raise _rollback_error(db, code=422, message=str(error)) from None

    response.headers["Cache-Control"] = "no-store"
    return _transaction_response(record)


