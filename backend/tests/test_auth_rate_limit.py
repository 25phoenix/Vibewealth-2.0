"""Deterministic rate-limit and HTTP authentication regression tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api import auth_routes
from app.api.dependencies import AuthenticatedRequest, get_authenticated_request, require_csrf
from app.core.config import Settings
from app.core.database import engine, get_db
from app.core.rate_limit import InMemoryAuthRateLimiter, _client_ip
from app.main import create_app
from app.services.authentication import LoginResult
from app.services.registration import RegistrationResult

ORIGIN = "http://localhost:5173"
CSRF_SECRET = "local-test-csrf-signing-secret-0123456789"


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "database_url": engine.url.render_as_string(hide_password=False),
        "app_environment": "development",
        "allowed_frontend_origins": [ORIGIN],
        "allow_insecure_cookies": True,
        "csrf_signing_secret": CSRF_SECRET,
        "auth_login_ip_limit": 10,
        "auth_login_identity_limit": 1,
        "auth_login_window_seconds": 60,
        "auth_registration_ip_limit": 10,
        "auth_registration_identity_limit": 1,
        "auth_registration_window_seconds": 60,
    }
    values.update(overrides)
    return Settings(**values)


def _request(client_host: str | None, headers=()) -> Request:
    raw_headers = [(key.encode(), value.encode()) for key, value in headers]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": raw_headers,
        "client": (client_host, 1234) if client_host is not None else None,
    }
    return Request(scope)


def test_token_bucket_limits_identity_and_refills_deterministically():
    clock = FakeClock()
    limiter = InMemoryAuthRateLimiter(clock=clock)
    common = {
        "operation": "login",
        "ip_limit": 10,
        "identity_limit": 1,
        "window_seconds": 60,
    }

    assert limiter.check(client_ip="203.0.113.1", identity="a@example.test", **common) is None
    assert limiter.check(client_ip="203.0.113.1", identity="a@example.test", **common) == 60
    assert limiter.check(client_ip="203.0.113.2", identity="a@example.test", **common) is None
    assert limiter.check(client_ip="203.0.113.1", identity="b@example.test", **common) is None

    clock.advance(60)
    assert limiter.check(client_ip="203.0.113.1", identity="a@example.test", **common) is None


def test_bucket_storage_stays_within_configured_memory_bounds():
    limiter = InMemoryAuthRateLimiter(
        clock=FakeClock(), max_ip_buckets=2, max_identity_buckets=3
    )
    for index in range(20):
        assert limiter.check(
            operation="login",
            client_ip=f"203.0.113.{index + 1}",
            identity=f"user-{index}@example.test",
            ip_limit=10,
            identity_limit=5,
            window_seconds=60,
        ) is None

    assert len(limiter._ip_buckets) == 2
    assert len(limiter._identity_buckets) == 3


@pytest.mark.parametrize("client_host", [None, "not-an-ip"])
def test_missing_or_invalid_client_address_uses_conservative_shared_bucket(client_host):
    clock = FakeClock()
    limiter = InMemoryAuthRateLimiter(clock=clock)
    request = _request(client_host)

    assert _client_ip(request) == "unknown"
    assert limiter.check(
        operation="login",
        client_ip=_client_ip(request),
        identity="person@example.test",
        ip_limit=1,
        identity_limit=10,
        window_seconds=60,
    ) is None
    assert limiter.check(
        operation="login",
        client_ip="unknown",
        identity="another@example.test",
        ip_limit=1,
        identity_limit=10,
        window_seconds=60,
    ) == 60


def _client(app, ip: str = "203.0.113.10") -> TestClient:
    return TestClient(app, client=(ip, 50000))


def test_login_rate_limit_returns_retry_after_without_echoing_credentials(monkeypatch):
    app = create_app(
        _settings(auth_login_ip_limit=10, auth_login_identity_limit=1)
    )
    app.state.auth_rate_limiter = InMemoryAuthRateLimiter(clock=FakeClock())
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(
        auth_routes,
        "login_user",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            auth_routes.AuthenticationError("Invalid email or password")
        ),
    )
    with _client(app) as client:
        first = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "private@example.test", "password": "secret-password"},
        )
        limited = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "private@example.test", "password": "another-secret"},
        )

    assert first.status_code == 401
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert "private@example.test" not in limited.text
    assert "another-secret" not in limited.text


def test_registration_limits_are_isolated_by_ip_and_do_not_trust_forwarded_headers(monkeypatch):
    app = create_app(
        _settings(auth_registration_ip_limit=10, auth_registration_identity_limit=1)
    )
    app.state.auth_rate_limiter = InMemoryAuthRateLimiter(clock=FakeClock())
    app.dependency_overrides[get_db] = lambda: MagicMock()
    monkeypatch_result = RegistrationResult(
        user_id=uuid4(),
        email="private@example.test",
        display_name=None,
        session_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        session_token="registration-token",
    )
    monkeypatch.setattr(auth_routes, "register_user", lambda *args, **kwargs: monkeypatch_result)
    with _client(app, "203.0.113.11") as first_client:
        first = first_client.post(
            "/api/auth/register",
            headers={"Origin": ORIGIN, "X-Forwarded-For": "198.51.100.1"},
            json={"email": "private@example.test", "password": "ignored", "account_type": "cash"},
        )
        limited = first_client.post(
            "/api/auth/register",
            headers={"Origin": ORIGIN, "X-Forwarded-For": "198.51.100.2"},
            json={"email": "private@example.test", "password": "ignored", "account_type": "cash"},
        )
    with _client(app, "203.0.113.12") as other_client:
        other = other_client.post(
            "/api/auth/register",
            headers={"Origin": ORIGIN},
            json={"email": "private@example.test", "password": "ignored", "account_type": "cash"},
        )

    assert first.status_code == 201
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert other.status_code == 201


def test_register_login_and_logout_success_flows_remain_usable(monkeypatch):
    app = create_app(_settings())
    app.dependency_overrides[get_db] = lambda: MagicMock()
    user_id = uuid4()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    monkeypatch.setattr(
        auth_routes,
        "register_user",
        lambda *args, **kwargs: RegistrationResult(
            user_id=user_id,
            email="new@example.test",
            display_name="New User",
            session_expires_at=expires,
            session_token="register-session-token",
        ),
    )
    monkeypatch.setattr(
        auth_routes,
        "login_user",
        lambda *args, **kwargs: LoginResult(
            user_id=user_id,
            email="new@example.test",
            display_name="New User",
            session_expires_at=expires,
            session_token="login-session-token",
        ),
    )
    authenticated = AuthenticatedRequest(
        current_user=SimpleNamespace(user_id=user_id, session_id=uuid4()),
        session_token="logout-session-token",
    )
    app.dependency_overrides[get_authenticated_request] = lambda: authenticated
    app.dependency_overrides[require_csrf] = lambda: authenticated
    monkeypatch.setattr(auth_routes, "revoke_session", lambda *args, **kwargs: True)

    with _client(app, "203.0.113.13") as client:
        registered = client.post(
            "/api/auth/register",
            headers={"Origin": ORIGIN},
            json={"email": "new@example.test", "password": "StrongPass123!", "account_type": "cash"},
        )
        logged_in = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "new@example.test", "password": "StrongPass123!"},
        )
        logged_out = client.post(
            "/api/auth/logout",
            headers={"Origin": ORIGIN, "X-CSRF-Token": "csrf"},
        )

    assert registered.status_code == 201
    assert registered.json()["email"] == "new@example.test"
    assert logged_in.status_code == 200
    assert logged_in.json()["email"] == "new@example.test"
    assert logged_out.status_code == 204
