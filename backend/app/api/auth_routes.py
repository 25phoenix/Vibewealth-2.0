"""Cookie-based HTTP authentication endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    AuthenticatedRequest,
    create_csrf_token,
    get_authenticated_request,
    get_request_settings,
    require_csrf,
    require_trusted_origin,
)
from app.core.config import Settings
from app.core.database import get_db
from app.core.rate_limit import enforce_auth_rate_limit
from app.schemas.auth import CsrfTokenResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.authentication import AuthenticationError, login_user
from app.services.auth_sessions import revoke_session
from app.services.registration import DuplicateEmailError, register_user

router = APIRouter(prefix="/api/auth", tags=["authentication"])
pre_session_router = APIRouter(dependencies=[Depends(require_trusted_origin)])
# Keep CSRF protection at the router boundary so every unsafe endpoint added
# to this group inherits it without repeating a check in each handler.
csrf_protected_router = APIRouter(dependencies=[Depends(require_csrf)])


def _set_auth_cookie(
    response: Response, settings: Settings, session_token: str, expiry: datetime
) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=session_token,
        expires=expiry.astimezone(timezone.utc),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookie(response: Response, settings: Settings) -> None:
    """Expire the cookie with the same name and security attributes as issuance."""

    response.set_cookie(
        key=settings.auth_cookie_name,
        value="",
        max_age=0,
        expires=0,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _commit_or_rollback(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


@pre_session_router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> UserResponse:
    """Register and authenticate a user after the onboarding transaction commits."""

    enforce_auth_rate_limit(request, settings, operation="register", identity=payload.email)
    try:
        result = register_user(
            db,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            account_type=payload.account_type,
        )
        db.commit()
    except DuplicateEmailError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except Exception:
        db.rollback()
        raise

    _set_auth_cookie(response, settings, result.session_token, result.session_expires_at)
    response.headers["Cache-Control"] = "no-store"
    return UserResponse(
        id=result.user_id,
        email=result.email,
        display_name=result.display_name,
    )


@pre_session_router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> UserResponse:
    """Create an independent session and set it only after transaction commit."""

    enforce_auth_rate_limit(request, settings, operation="login", identity=payload.email)
    try:
        result = login_user(db, email=payload.email, password=payload.password)
        db.commit()
    except AuthenticationError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from error
    except Exception:
        db.rollback()
        raise

    _set_auth_cookie(response, settings, result.session_token, result.session_expires_at)
    response.headers["Cache-Control"] = "no-store"
    return UserResponse(
        id=result.user_id,
        email=result.email,
        display_name=result.display_name,
    )


@router.get("/me", response_model=UserResponse)
def current_user(
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Return the safe identity and persist the existing session's activity touch."""

    _commit_or_rollback(db)
    user = authenticated.current_user
    response.headers["Cache-Control"] = "no-store"
    return UserResponse(id=user.user_id, email=user.email, display_name=user.display_name)


@router.get("/csrf", response_model=CsrfTokenResponse)
def csrf_token(
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> CsrfTokenResponse:
    """Return a deterministic session-bound token; persist the session refresh."""

    token = create_csrf_token(authenticated.session_token, settings)
    _commit_or_rollback(db)
    response.headers["Cache-Control"] = "no-store"
    return CsrfTokenResponse(csrf_token=token)


@csrf_protected_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> Response:
    """Revoke only the current valid session after origin and CSRF validation."""

    try:
        revoked = revoke_session(
            db,
            session_id=authenticated.current_user.session_id,
            user_id=authenticated.current_user.user_id,
        )
        if not revoked:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise

    _clear_auth_cookie(response, settings)
    response.headers["Cache-Control"] = "no-store"
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


router.include_router(pre_session_router)
router.include_router(csrf_protected_router)
