"""Authenticated transaction creation and history endpoints."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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
    IdempotencyConflictError,
    InvalidTransactionError,
    TransactionNotFoundError,
    TransactionPage,
    TransactionRecord,
    create_transaction,
    get_idempotent_transaction,
    get_transaction,
    list_transactions,
    transaction_request_fingerprint,
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
    except IntegrityError:
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transaction could not be saved",
        ) from None


def _is_idempotency_unique_violation(error: IntegrityError) -> bool:
    original = error.orig
    sqlstate = getattr(original, 'sqlstate', None) or getattr(original, 'pgcode', None)
    diagnostic = getattr(original, 'diag', None)
    constraint_name = getattr(diagnostic, 'constraint_name', None)
    return sqlstate == '23505' and constraint_name == 'uq_transactions_user_idempotency_key'


def _recover_idempotency_integrity_error(
    db: Session,
    *,
    user_id: UUID,
    idempotency_key: str,
    payload: TransactionCreateRequest,
) -> tuple[TransactionRecord | None, bool]:
    # Return the winning row and whether its payload conflicts, if this was the key race.
    replay = get_idempotent_transaction(
        db, user_id=user_id, idempotency_key=idempotency_key
    )
    if replay is None:
        return None, False
    fingerprint = transaction_request_fingerprint(
        account_id=payload.account_id,
        category_id=payload.category_id,
        transaction_type=payload.transaction_type,
        amount_paise=payload.amount_paise,
        description=payload.description,
        transaction_date=payload.transaction_date,
        notes=payload.notes,
    )
    return replay, replay.transaction.request_fingerprint != fingerprint


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


@router.get("/operations/{idempotency_key}", response_model=TransactionResponse)
def resolve_transaction_operation(
    response: Response,
    idempotency_key: str = Path(
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._~-]+$",
    ),
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> TransactionResponse:
    """Resolve a completed transaction-create operation for its owner."""

    response.headers["Cache-Control"] = "no-store"
    record = get_idempotent_transaction(
        db,
        user_id=authenticated.current_user.user_id,
        idempotency_key=idempotency_key,
    )
    _commit_read_activity(db)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Operation not found",
            headers={"Cache-Control": "no-store"},
        )
    return _transaction_response(record)


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
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._~-]+$",
    ),
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
            idempotency_key=idempotency_key,
        )
        _commit(db)
    except IdempotencyConflictError:
        raise _rollback_error(
            db, code=409, message="Idempotency-Key was already used for a different transaction"
        ) from None
    except AccountNotFoundError:
        raise _rollback_error(db, code=404, message="Account not found") from None
    except InvalidTransactionError as error:
        raise _rollback_error(db, code=422, message=str(error)) from None
    except IntegrityError as error:
        # Roll back every integrity failure, but replay only this named unique
        # violation. Other unique/FK/check errors must remain ordinary failures.
        db.rollback()
        if not _is_idempotency_unique_violation(error):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Transaction could not be saved",
            ) from None
        replay, conflicts = _recover_idempotency_integrity_error(
            db,
            user_id=authenticated.current_user.user_id,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        if replay is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Transaction could not be saved",
            ) from None
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency-Key was already used for a different transaction",
            ) from None
        record = replay

    response.headers["Cache-Control"] = "no-store"
    return _transaction_response(record)


