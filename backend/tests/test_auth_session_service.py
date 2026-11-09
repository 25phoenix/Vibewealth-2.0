"""Unit tests for opaque session token and transaction behavior."""

import base64
import hashlib
import logging
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.models import AuthSession
from app.services import auth_sessions
from app.services.auth_sessions import (
    SESSION_ABSOLUTE_LIFETIME,
    SESSION_IDLE_TIMEOUT,
    _digest_token,
    create_session,
    generate_session_token,
    get_valid_session,
)


def test_generated_token_encodes_256_random_bits() -> None:
    token = generate_session_token()

    assert len(token) == 43
    decoded = base64.urlsafe_b64decode(token + "=")
    assert len(decoded) == 32
    assert base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") == token


def test_token_digest_is_sha256_of_ascii_representation() -> None:
    token = generate_session_token()

    assert _digest_token(token) == hashlib.sha256(token.encode("ascii")).digest()
    assert len(_digest_token(token)) == 32


@pytest.mark.parametrize("token", [None, "", "short", "a" * 43, "é" * 43, "A" * 42 + "="])
def test_malformed_tokens_are_rejected_before_database_access(token: str | None) -> None:
    db = Mock()

    assert get_valid_session(db, token) is None
    db.scalars.assert_not_called()


def test_session_creation_stores_only_digest_and_does_not_commit(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    token = generate_session_token()
    token_urlsafe = Mock(return_value=token)
    monkeypatch.setattr(auth_sessions.secrets, "token_urlsafe", token_urlsafe)
    db = Mock()
    user_id = uuid4()

    with caplog.at_level(logging.DEBUG):
        returned_token, created = create_session(db, user_id)

    assert returned_token == token
    token_urlsafe.assert_called_once_with(32)
    assert isinstance(created, AuthSession)
    assert created.user_id == user_id
    assert created.token_digest == hashlib.sha256(token.encode("ascii")).digest()
    assert token.encode("ascii") not in created.token_digest
    assert created.absolute_expires_at is not None
    absolute_expression = str(
        created.absolute_expires_at.compile(dialect=postgresql.dialect())
    )
    assert "now() + INTERVAL '2592000 seconds'" in absolute_expression
    db.add.assert_called_once_with(created)
    db.flush.assert_called_once_with()
    db.refresh.assert_called_once_with(created)
    db.commit.assert_not_called()
    assert token not in caplog.text


def test_session_policy_constants_match_approved_timeouts() -> None:
    assert SESSION_IDLE_TIMEOUT == timedelta(hours=12)
    assert SESSION_ABSOLUTE_LIFETIME == timedelta(days=30)
