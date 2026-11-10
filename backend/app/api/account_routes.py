"""Authenticated account read and metadata endpoints."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import AuthenticatedRequest, get_authenticated_request, require_csrf
from app.core.database import get_db
from app.schemas.accounts import (
    AccountBalanceResponse,
    AccountResponse,
    AccountUpdateRequest,
)
from app.services.accounts import (
    AccountNotFoundError,
    AccountOpeningBalanceLockedError,
    AccountSnapshot,
    InvalidAccountUpdateError,
    get_account,
    get_account_balance,
    list_accounts,
    update_account,
)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _account_response(snapshot: AccountSnapshot) -> AccountResponse:
    account = snapshot.account
    return AccountResponse(
        id=account.id,
        name=account.name,
        account_type=account.account_type,
        is_default=account.is_default,
        opening_balance_paise=account.opening_balance_paise,
        opening_balance_as_of=account.opening_balance_as_of,
        balance_paise=snapshot.balance_paise,
        created_at=account.created_at,
        updated_at=account.updated_at,
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
            detail="Account update could not be saved",
        ) from None


def _commit_read_activity(db: Session) -> None:
    """Persist the session activity touch performed by authentication."""

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=list[AccountResponse])
def accounts(
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> list[AccountResponse]:
    """List active accounts and current balances for the authenticated user."""

    snapshots = list_accounts(db, user_id=authenticated.current_user.user_id)
    _commit_read_activity(db)
    response.headers["Cache-Control"] = "no-store"
    return [
        _account_response(snapshot)
        for snapshot in snapshots
    ]


@router.get("/{account_id}", response_model=AccountResponse)
def account(
    account_id: UUID,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> AccountResponse:
    """Retrieve one active account belonging to the authenticated user."""

    try:
        snapshot = get_account(
            db, user_id=authenticated.current_user.user_id, account_id=account_id
        )
    except AccountNotFoundError:
        raise HTTPException(status_code=404, detail="Account not found") from None
    _commit_read_activity(db)
    response.headers["Cache-Control"] = "no-store"
    return _account_response(snapshot)


@router.get("/{account_id}/balance", response_model=AccountBalanceResponse)
def account_balance(
    account_id: UUID,
    response: Response,
    as_of: date | None = Query(default=None),
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> AccountBalanceResponse:
    """Return a current or historical exact paise balance."""

    try:
        snapshot = get_account_balance(
            db,
            user_id=authenticated.current_user.user_id,
            account_id=account_id,
            as_of=as_of,
        )
    except AccountNotFoundError:
        raise HTTPException(status_code=404, detail="Account not found") from None
    except InvalidAccountUpdateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    _commit_read_activity(db)
    response.headers["Cache-Control"] = "no-store"
    return AccountBalanceResponse(
        account_id=snapshot.account.id,
        balance_paise=snapshot.balance_paise,
        as_of=snapshot.as_of,
    )


@router.patch(
    "/{account_id}",
    response_model=AccountResponse,
    dependencies=[Depends(require_csrf)],
)
def patch_account(
    account_id: UUID,
    payload: AccountUpdateRequest,
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> AccountResponse:
    """Update permitted account metadata, honoring the opening-balance lock."""

    try:
        snapshot = update_account(
            db,
            user_id=authenticated.current_user.user_id,
            account_id=account_id,
            changes=payload.model_dump(exclude_unset=True),
        )
        _commit(db)
    except AccountNotFoundError:
        raise _rollback_error(db, code=404, message="Account not found") from None
    except AccountOpeningBalanceLockedError:
        raise _rollback_error(
            db,
            code=409,
            message="Opening balance cannot change after a transaction has been created",
        ) from None
    except InvalidAccountUpdateError as error:
        raise _rollback_error(db, code=422, message=str(error)) from None

    response.headers["Cache-Control"] = "no-store"
    return _account_response(snapshot)


