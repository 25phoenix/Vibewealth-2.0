"""Configuration, CORS, origin, and CSRF unit tests for the HTTP layer."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
from starlette.requests import Request
from pydantic import SecretStr, ValidationError

from app.api import dependencies
from app.api.dependencies import require_csrf, require_trusted_origin
from app.core.database import engine, get_db
from app.core.config import Settings
from app.core.origins import is_trusted_request_origin
from app.main import create_app
from app.services.authentication import AuthenticationError

FRONTEND_ORIGIN = "http://localhost:5173"
CSRF_SECRET = "local-test-csrf-signing-secret-0123456789"


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "database_url": engine.url.render_as_string(hide_password=False),
        "app_environment": "development",
        "allowed_frontend_origins": [FRONTEND_ORIGIN],
        "allow_insecure_cookies": True,
        "csrf_signing_secret": CSRF_SECRET,
    }
    values.update(overrides)
    return Settings(**values)


def _request(headers):
    items = headers.items() if hasattr(headers, "items") else headers
    raw_headers = [(name.encode("latin-1"), value.encode("latin-1")) for name, value in items]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw_headers})


def test_development_cookie_is_insecure_only_when_explicitly_enabled():
    secure_default = Settings(
        _env_file=None, app_environment="development", allow_insecure_cookies=False
    )
    local_http = _settings()

    assert secure_default.auth_cookie_name == "vibewealth_session"
    assert secure_default.auth_cookie_secure is True
    assert local_http.auth_cookie_name == "vibewealth_session"
    assert local_http.auth_cookie_secure is False


def test_production_requires_explicit_origins_and_csrf_secret():
    with pytest.raises(ValidationError, match="ALLOWED_FRONTEND_ORIGINS"):
        Settings(
            _env_file=None,
            app_environment="production",
            csrf_signing_secret=SecretStr(CSRF_SECRET),
        )

    with pytest.raises(ValidationError, match="CSRF_SIGNING_SECRET"):
        Settings(
            _env_file=None,
            app_environment="production",
            allowed_frontend_origins=["https://app.example.test"],
        )


def test_production_rejects_http_frontend_origins_including_localhost():
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
            _env_file=None,
            app_environment="production",
            allowed_frontend_origins=["http://localhost:5173"],
            csrf_signing_secret=SecretStr(CSRF_SECRET),
        )


def test_app_environment_is_required_and_supported(monkeypatch):
    monkeypatch.delenv("APP_ENVIRONMENT", raising=False)
    with pytest.raises(ValidationError, match="app_environment"):
        Settings(_env_file=None)

    for value in ("", "staging", "Development"):
        monkeypatch.setenv("APP_ENVIRONMENT", value)
        with pytest.raises(ValidationError, match="app_environment"):
            Settings(_env_file=None)


def test_production_cookie_policy_cannot_be_weakened():
    settings = Settings(
        _env_file=None,
        app_environment="production",
        allowed_frontend_origins=["https://app.example.test"],
        csrf_signing_secret=SecretStr(CSRF_SECRET),
    )

    assert settings.auth_cookie_name.startswith("__Host-")
    assert settings.auth_cookie_secure is True

    with pytest.raises(ValidationError, match="only in development"):
        Settings(
            _env_file=None,
            app_environment="production",
            allowed_frontend_origins=["https://app.example.test"],
            csrf_signing_secret=SecretStr(CSRF_SECRET),
            allow_insecure_cookies=True,
        )

    with pytest.raises(ValidationError, match="development CSRF key"):
        Settings(
            _env_file=None,
            app_environment="production",
            allowed_frontend_origins=["https://app.example.test"],
            csrf_signing_secret="vibewealth-local-development-csrf-secret-rotate-for-production",
        )


@pytest.mark.parametrize(
    "origins",
    [
        ["*"],
        ["http://*.example.test"],
        ["http://localhost:5173/path"],
        ["http://localhost:5173?"],
        ["file://localhost"],
        ["http://localhost:99999"],
        ["http://localhost:5173", "http://localhost:5173/"],
    ],
)
def test_invalid_or_wildcard_origins_are_rejected(origins):
    with pytest.raises(ValidationError):
        _settings(allowed_frontend_origins=origins)


def test_settings_repr_does_not_expose_csrf_secret():
    settings = _settings()

    assert CSRF_SECRET not in repr(settings)


def test_origin_matching_is_exact_and_referer_fallback_is_parsed():
    allowed = [FRONTEND_ORIGIN]

    assert is_trusted_request_origin(
        _request({"origin": FRONTEND_ORIGIN}), allowed
    )
    assert is_trusted_request_origin(
        _request({"referer": "http://localhost:5173/register?next=%2F"}), allowed
    )
    assert not is_trusted_request_origin(
        _request({"origin": "https://localhost:5173"}), allowed
    )
    assert not is_trusted_request_origin(
        _request({"origin": "http://localhost:5174"}), allowed
    )
    assert not is_trusted_request_origin(
        _request({"origin": "http://sub.localhost:5173"}), allowed
    )
    assert not is_trusted_request_origin(
        _request({"origin": "not an origin"}), allowed
    )
    assert not is_trusted_request_origin(_request({}), allowed)
    assert not is_trusted_request_origin(
        _request({"origin": "not an origin", "referer": f"{FRONTEND_ORIGIN}/"}),
        allowed,
    )


def test_origin_validation_rejects_duplicate_raw_headers_and_matches_names_case_insensitively():
    allowed = [FRONTEND_ORIGIN]
    cases = [
        ([("Origin", FRONTEND_ORIGIN)], True),
        ([("Origin", "https://evil.example")], False),
        ([("Origin", FRONTEND_ORIGIN), ("oRiGiN", FRONTEND_ORIGIN)], False),
        ([("Origin", FRONTEND_ORIGIN), ("Origin", "https://evil.example")], False),
        ([("Referer", FRONTEND_ORIGIN + "/a"), ("referer", FRONTEND_ORIGIN + "/b")], False),
        (
            [
                ("Origin", FRONTEND_ORIGIN),
                ("Referer", "https://evil.example/a"),
                ("rEfErEr", "https://evil.example/b"),
            ],
            False,
        ),
        ([("oRiGiN", FRONTEND_ORIGIN)], True),
    ]

    for headers, expected in cases:
        assert is_trusted_request_origin(_request(headers), allowed) is expected


def test_create_app_rejects_database_settings_that_diverge_from_shared_engine():
    mismatched_url = engine.url.set(database=f"{engine.url.database}_other")
    settings = _settings(
        database_url=mismatched_url.render_as_string(hide_password=False)
    )

    with pytest.raises(ValueError, match="must match the configured database engine"):
        create_app(settings)


def _dependency_calls(route):
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        yield dependency.call
        pending.extend(dependency.dependencies)


def _assert_unsafe_routes_protected(routes):
    public_pre_session_routes = {"/api/auth/register", "/api/auth/login"}
    unsafe_methods = {"POST", "PUT", "PATCH", "DELETE"}
    for route in routes:
        if not isinstance(route, APIRoute):
            continue
        if not (route.methods & unsafe_methods):
            continue
        calls = set(_dependency_calls(route))
        if route.path in public_pre_session_routes:
            assert require_trusted_origin in calls, route.path
        else:
            assert require_csrf in calls, route.path


def test_all_unsafe_routes_have_origin_or_csrf_protection():
    application = create_app(_settings())
    _assert_unsafe_routes_protected(application.routes)


def test_route_inventory_detects_an_unprotected_future_write():
    def future_write():
        return {"ok": True}

    unprotected = APIRoute(
        "/api/transactions",
        future_write,
        methods=["POST"],
    )
    with pytest.raises(AssertionError):
        _assert_unsafe_routes_protected([unprotected])


def test_csrf_token_is_deterministic_domain_bound_and_session_bound():
    from app.api.dependencies import create_csrf_token

    settings = _settings()
    first = create_csrf_token("session-token-a", settings)

    assert first == create_csrf_token("session-token-a", settings)
    assert first != create_csrf_token("session-token-b", settings)
    assert first != create_csrf_token(
        "session-token-a", _settings(csrf_signing_secret="another-test-secret-value-123456789")
    )
    assert "session-token-a" not in first


def test_csrf_dependency_uses_constant_time_comparison(monkeypatch):
    request = _request({"origin": FRONTEND_ORIGIN})
    settings = _settings()
    authenticated = dependencies.AuthenticatedRequest(
        current_user=SimpleNamespace(user_id="user", session_id="session"),
        session_token="session-token-a",
    )
    expected = dependencies.create_csrf_token("session-token-a", settings)
    calls = []

    def compare_digest(left, right):
        calls.append((left, right))
        return left == right

    monkeypatch.setattr(dependencies.hmac, "compare_digest", compare_digest)
    assert dependencies.require_csrf(
        request, expected, authenticated, settings
    ) is authenticated
    assert calls == [(expected.encode("ascii"), expected.encode("ascii"))]

    with pytest.raises(HTTPException) as raised:
        dependencies.require_csrf(request, "modified", authenticated, settings)
    assert raised.value.status_code == 403
    assert "modified" not in str(raised.value.detail)
    with pytest.raises(HTTPException) as raised:
        dependencies.require_csrf(request, "påssword", authenticated, settings)
    assert raised.value.status_code == 403


def test_cors_preflight_is_limited_to_explicit_origin_and_auth_headers():
    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.options(
            "/api/auth/login",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        rejected = client.options(
            "/api/auth/login",
            headers={
                "Origin": "http://localhost:5174",
                "Access-Control-Request-Method": "POST",
            },
        )
        account_patch = client.options(
            "/api/accounts/00000000-0000-0000-0000-000000000001",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        budget_delete = client.options(
            "/api/budgets/00000000-0000-0000-0000-000000000001",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        rejected_method = client.options(
            "/api/auth/login",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "PUT",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert account_patch.status_code == 200
    assert "PATCH" in account_patch.headers["access-control-allow-methods"]
    assert budget_delete.status_code == 200
    assert "DELETE" in budget_delete.headers["access-control-allow-methods"]
    assert "x-csrf-token" in response.headers["access-control-allow-headers"].lower()
    assert "POST" in response.headers["access-control-allow-methods"]
    assert rejected.status_code == 400
    assert rejected_method.status_code == 400


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://localhost:5173"},
        {"Origin": "http://localhost:5174"},
        {"Origin": "http://sub.localhost:5173"},
        {"Origin": "malformed"},
        {"Referer": "http://localhost:5174/login"},
    ],
)
def test_login_rejects_missing_or_untrusted_request_origin(headers):
    app = create_app(_settings())
    session = MagicMock()
    session.in_transaction.return_value = False

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/login",
                headers=headers,
                json={"email": "user@example.test", "password": "a password"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    session.execute.assert_not_called()
    assert response.headers.get("set-cookie") is None


def test_login_accepts_trusted_referer_only_when_origin_is_absent():
    app = create_app(_settings())
    session = MagicMock()
    session.in_transaction.return_value = False

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    with patch(
        "app.api.auth_routes.login_user",
        side_effect=AuthenticationError("Invalid email or password"),
    ) as login_service:
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/auth/login",
                    headers={"Referer": f"{FRONTEND_ORIGIN}/login"},
                    json={"email": "user@example.test", "password": "a password"},
                )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}
    login_service.assert_called_once()
