"""Unit tests for credential verification and current-user projection."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.security import verify_password
from app.services import authentication
from app.services.authentication import (
    AuthenticationError,
    CurrentUser,
    LoginResult,
    get_current_user,
    login_user,
)


def _user(*, email="person@example.test", password_hash="stored-argon-hash"):
    return SimpleNamespace(
        id=uuid4(), email=email, display_name="Example Person", password_hash=password_hash
    )


def _db_with_user(user):
    db = Mock()
    db.execute.return_value.scalar_one_or_none.return_value = user
    return db


def test_successful_login_normalizes_email_verifies_hash_and_stages_new_session(
    monkeypatch, caplog
):
    user = _user()
    db = _db_with_user(user)
    verifier = Mock(return_value=True)
    session_creator = Mock(
        return_value=(
            "raw-login-token",
            SimpleNamespace(
                absolute_expires_at=datetime(2026, 12, 6, tzinfo=timezone.utc)
            ),
        )
    )
    monkeypatch.setattr(authentication, "verify_password", verifier)
    monkeypatch.setattr(authentication, "create_session", session_creator)
    caplog.set_level(logging.DEBUG)

    result = login_user(
        db, email="  PERSON@EXAMPLE.TEST  ", password="correct horse battery staple"
    )

    assert isinstance(result, LoginResult)
    assert (result.user_id, result.email, result.display_name) == (
        user.id,
        user.email,
        user.display_name,
    )
    assert result.session_token == "raw-login-token"
    assert "raw-login-token" not in repr(result)
    assert user.password_hash not in repr(result)
    assert "raw-login-token" not in caplog.text
    assert "correct horse battery staple" not in caplog.text
    verifier.assert_called_once_with("correct horse battery staple", user.password_hash)
    session_creator.assert_called_once_with(db, user.id)
    db.commit.assert_not_called()


@pytest.mark.parametrize("existing_user", [None, _user()])
def test_unknown_email_and_wrong_password_have_same_generic_failure(
    monkeypatch, existing_user
):
    db = _db_with_user(existing_user)
    verifier = Mock(return_value=False)
    session_creator = Mock()
    monkeypatch.setattr(authentication, "verify_password", verifier)
    monkeypatch.setattr(authentication, "create_session", session_creator)

    with pytest.raises(AuthenticationError) as raised:
        login_user(db, email="person@example.test", password="wrong password")

    assert str(raised.value) == "Invalid email or password"
    assert "person@example.test" not in str(raised.value)
    assert "wrong password" not in str(raised.value)
    expected_hash = (
        authentication._DUMMY_PASSWORD_HASH
        if existing_user is None
        else existing_user.password_hash
    )
    verifier.assert_called_once_with("wrong password", expected_hash)
    session_creator.assert_not_called()
    db.commit.assert_not_called()


def test_unknown_user_uses_the_same_precomputed_dummy_hash_each_time(monkeypatch):
    verifier = Mock(return_value=False)
    monkeypatch.setattr(authentication, "verify_password", verifier)
    dummy_hash = authentication._DUMMY_PASSWORD_HASH

    for email in ("first@example.test", "second@example.test"):
        with pytest.raises(AuthenticationError, match="^Invalid email or password$"):
            login_user(_db_with_user(None), email=email, password="a candidate password")

    assert [call.args[1] for call in verifier.call_args_list] == [dummy_hash, dummy_hash]
    assert dummy_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")


def test_dummy_hash_is_valid_for_the_configured_argon2id_verifier():
    assert verify_password(
        "VibeWealth fixed timing-only dummy phrase 7f30e4a7",
        authentication._DUMMY_PASSWORD_HASH,
    ) is True


@pytest.mark.parametrize("email", ["", "not-an-email", None, "invalid@domain"])
def test_invalid_email_has_generic_failure_and_performs_dummy_verification(
    monkeypatch, email
):
    db = Mock()
    verifier = Mock(return_value=False)
    monkeypatch.setattr(authentication, "verify_password", verifier)

    with pytest.raises(AuthenticationError, match="^Invalid email or password$") as raised:
        login_user(db, email=email, password="candidate password")

    assert "Email" not in str(raised.value)
    db.execute.assert_not_called()
    verifier.assert_called_once_with("candidate password", authentication._DUMMY_PASSWORD_HASH)


@pytest.mark.parametrize("password", [None, 123, b"password"])
def test_malformed_password_fails_safely_without_session_creation(monkeypatch, password):
    user = _user()
    db = _db_with_user(user)
    verifier = Mock(return_value=False)
    session_creator = Mock()
    monkeypatch.setattr(authentication, "verify_password", verifier)
    monkeypatch.setattr(authentication, "create_session", session_creator)

    with pytest.raises(AuthenticationError, match="^Invalid email or password$"):
        login_user(db, email="person@example.test", password=password)

    verifier.assert_called_once_with(password, user.password_hash)
    session_creator.assert_not_called()


def test_current_user_uses_session_service_and_returns_safe_projection(monkeypatch):
    raw_token = "raw-session-token"
    user = _user()
    session_id = uuid4()
    auth_session = SimpleNamespace(id=session_id, token_digest=b"internal-digest")
    validation = Mock(return_value=(auth_session, user))
    monkeypatch.setattr(authentication, "get_valid_session", validation)
    db = Mock()

    result = get_current_user(db, session_token=raw_token)

    assert result == CurrentUser(user.id, user.email, user.display_name, session_id)
    assert raw_token not in repr(result)
    assert "internal-digest" not in repr(result)
    assert user.password_hash not in repr(result)
    validation.assert_called_once_with(db, raw_token)
    db.commit.assert_not_called()


@pytest.mark.parametrize("token", ["bad-token", "unknown-token", "expired-token", "revoked-token"])
def test_current_user_returns_none_when_session_service_rejects_token(monkeypatch, token):
    validation = Mock(return_value=None)
    monkeypatch.setattr(authentication, "get_valid_session", validation)

    assert get_current_user(Mock(), session_token=token) is None

    validation.assert_called_once()
