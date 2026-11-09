"""Database-backed opaque authentication session operations."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, text, update
from sqlalchemy.orm import Session

from app.models import AuthSession, User

SESSION_TOKEN_BYTES = 32
SESSION_IDLE_TIMEOUT = timedelta(hours=12)
SESSION_ABSOLUTE_LIFETIME = timedelta(days=30)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


def _interval_literal(duration: timedelta):
    """Build a fixed internal PostgreSQL interval from the approved policy."""

    seconds = int(duration.total_seconds())
    return text(f"INTERVAL '{seconds} seconds'")


def generate_session_token() -> str:
    """Generate a 256-bit opaque token suitable for an HttpOnly cookie."""

    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def _digest_token(token: str | None) -> bytes | None:
    """Return a canonical token's SHA-256 digest, or None for malformed input."""

    if not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token + "=")
    except (ValueError, binascii.Error):
        return None
    if len(decoded) != SESSION_TOKEN_BYTES:
        return None
    if base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != token:
        return None
    return hashlib.sha256(token.encode("ascii")).digest()


def create_session(db: Session, user_id: UUID) -> tuple[str, AuthSession]:
    """Stage a new session and return its raw token plus persisted ORM row.

    The caller owns the transaction and must commit or roll it back. The raw
    token is returned only to the trusted caller; only its SHA-256 digest is
    stored in the database.
    """

    token = generate_session_token()
    digest = hashlib.sha256(token.encode("ascii")).digest()
    auth_session = AuthSession(
        user_id=user_id,
        token_digest=digest,
        absolute_expires_at=func.now() + _interval_literal(SESSION_ABSOLUTE_LIFETIME),
    )
    db.add(auth_session)
    db.flush()
    db.refresh(auth_session)
    return token, auth_session


def get_valid_session(db: Session, token: str | None) -> tuple[AuthSession, User] | None:
    """Atomically validate and refresh a session, then resolve its owner.

    Both idle and absolute expiry are checked against PostgreSQL time. At the
    exact expiry boundary the session is invalid. Returning None covers
    malformed, unknown, revoked, expired, and ownerless sessions.
    """

    digest = _digest_token(token)
    if digest is None:
        return None

    statement = (
        update(AuthSession)
        .where(
            AuthSession.token_digest == digest,
            AuthSession.revoked_at.is_(None),
            AuthSession.absolute_expires_at > func.clock_timestamp(),
            AuthSession.last_activity_at
            > func.clock_timestamp() - _interval_literal(SESSION_IDLE_TIMEOUT),
        )
        .values(
            last_activity_at=func.greatest(
                AuthSession.last_activity_at, func.clock_timestamp()
            )
        )
        .returning(AuthSession)
    )
    auth_session = db.scalars(
        statement,
        execution_options={"populate_existing": True, "synchronize_session": False},
    ).one_or_none()
    if auth_session is None or not hmac.compare_digest(auth_session.token_digest, digest):
        return None

    user = db.get(User, auth_session.user_id)
    if user is None:
        return None
    return auth_session, user


def revoke_session(db: Session, *, session_id: UUID, user_id: UUID) -> bool:
    """Revoke only the active session owned by ``user_id``.

    The operation is idempotent: the first call changes revoked_at and returns
    True; repeats or ownership mismatches return False. The caller owns the
    transaction, and no session row is physically deleted.
    """

    statement = (
        update(AuthSession)
        .where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=func.clock_timestamp())
        .returning(AuthSession.id)
        .execution_options(synchronize_session=False)
    )
    return db.execute(statement).scalar_one_or_none() is not None
