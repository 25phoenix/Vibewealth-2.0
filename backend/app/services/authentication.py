"""Login and safe current-user lookup using the existing session lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.email import normalize_email
from app.core.security import verify_password
from app.models import User
from app.services.auth_sessions import create_session, get_valid_session

# Generated once with hash_password() under the application's configured
# Argon2id parameters (m=65536,t=3,p=4). It is only a timing equalizer, is never
# stored in the database, and must be regenerated if those parameters change.
# Keeping a precomputed encoded hash avoids an expensive hash generation for
# every unknown-user login. This narrows, but does not eliminate, timing gaps.
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$2n1Ak4vknmaKrkmAeNEbEg$"
    "ElczvwjAXourahCGCSCOTOD62/XuvJOvpAu/wUifSTo"
)
_AUTHENTICATION_FAILURE_MESSAGE = "Invalid email or password"


class AuthenticationError(ValueError):
    """Generic login failure that does not disclose account existence."""


@dataclass(frozen=True, slots=True)
class LoginResult:
    """Safe user identity plus a new raw session token for the trusted caller."""

    user_id: UUID
    email: str
    display_name: str | None
    session_expires_at: datetime
    session_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """Safe identity projection for an authenticated request."""

    user_id: UUID
    email: str
    display_name: str | None
    session_id: UUID


def _verify_dummy_password(password: str) -> None:
    """Perform one normal verifier call for input that cannot resolve a user."""

    verify_password(password, _DUMMY_PASSWORD_HASH)


def login_user(db: Session, *, email: str, password: str) -> LoginResult:
    """Verify credentials and stage a new independent session.

    The service does not commit or roll back. The caller must commit after a
    successful return. A failed login stages no session; the caller may roll
    back the read transaction before reusing its session if desired.
    """

    try:
        normalized_email = normalize_email(email)
    except ValueError:
        _verify_dummy_password(password)
        raise AuthenticationError(_AUTHENTICATION_FAILURE_MESSAGE) from None

    user = db.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    ).scalar_one_or_none()

    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_is_valid = verify_password(password, password_hash)
    if user is None or not password_is_valid:
        raise AuthenticationError(_AUTHENTICATION_FAILURE_MESSAGE)

    session_token, auth_session = create_session(db, user.id)
    return LoginResult(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        session_expires_at=auth_session.absolute_expires_at,
        session_token=session_token,
    )


def get_current_user(db: Session, *, session_token: str) -> CurrentUser | None:
    """Resolve a safe identity while delegating validity and refresh to sessions.

    Activity refresh performed by ``get_valid_session`` remains uncommitted;
    the caller owns the transaction and decides whether to commit it.
    """

    validated = get_valid_session(db, session_token)
    if validated is None:
        return None

    auth_session, user = validated
    return CurrentUser(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        session_id=auth_session.id,
    )
