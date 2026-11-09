"""Reusable request dependencies for database-backed authentication."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import get_db
from app.core.origins import is_trusted_request_origin
from app.services.authentication import CurrentUser, get_current_user

CSRF_HEADER_NAME = "X-CSRF-Token"
_CSRF_DOMAIN = b"vibewealth:http-csrf-token:v1\x00"


@dataclass(frozen=True, slots=True)
class AuthenticatedRequest:
    """Validated identity and internal cookie token for request processing."""

    current_user: CurrentUser
    session_token: str = field(repr=False)


def get_request_settings(request: Request) -> Settings:
    """Resolve the validated settings used to assemble this application."""

    return request.app.state.settings


def require_trusted_origin(
    request: Request,
    settings: Settings = Depends(get_request_settings),
) -> None:
    """Require an explicitly allowed Origin, or Referer when Origin is absent."""

    if not is_trusted_request_origin(request, settings.allowed_frontend_origins):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed",
        )


def get_authenticated_request(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_request_settings),
) -> AuthenticatedRequest:
    """Validate the host-only session cookie through the existing service."""

    session_token = request.cookies.get(settings.auth_cookie_name)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    current_user = get_current_user(db, session_token=session_token)
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return AuthenticatedRequest(current_user=current_user, session_token=session_token)


def create_csrf_token(session_token: str, settings: Settings) -> str:
    """Derive a deterministic session-bound synchronizer token with HMAC-SHA256."""

    message = _CSRF_DOMAIN + session_token.encode("ascii")
    return hmac.new(settings.csrf_key, message, hashlib.sha256).hexdigest()


def require_csrf(
    request: Request,
    csrf_token: str | None = Header(default=None, alias=CSRF_HEADER_NAME),
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    settings: Settings = Depends(get_request_settings),
) -> AuthenticatedRequest:
    """Require a valid session, trusted origin, and matching custom CSRF header."""

    if not is_trusted_request_origin(request, settings.allowed_frontend_origins):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed",
        )

    expected_token = create_csrf_token(authenticated.session_token, settings)
    supplied_bytes = (csrf_token or "").encode("utf-8")
    expected_bytes = expected_token.encode("ascii")
    if not hmac.compare_digest(expected_bytes, supplied_bytes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )
    return authenticated
