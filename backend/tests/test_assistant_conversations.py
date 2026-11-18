"""DB-free assistant HTTP boundary, strict input and rate-limit tests."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import assistant_routes
from app.api.dependencies import AuthenticatedRequest, get_authenticated_request
from app.core.assistant_rate_limit import AssistantRateLimiter
from app.core.config import Settings
from app.core.database import engine, get_db
from app.main import create_app
from app.schemas.assistant import ErrorDto, HTTP_ERROR_MESSAGES, HttpErrorCode
from app.services.authentication import CurrentUser

ORIGIN = "http://localhost:5173"


def application():
    settings = Settings(
        _env_file=None, database_url=engine.url.render_as_string(hide_password=False),
        app_environment="development", allow_insecure_cookies=True,
        allowed_frontend_origins=[ORIGIN], csrf_signing_secret="assistant-test-signing-secret-0123456789",
    )
    return create_app(settings)


@pytest.fixture(autouse=True)
def no_application_database(monkeypatch):
    from sqlalchemy.engine import Engine
    original = Engine.connect
    attempts = []

    def guarded(self, *args, **kwargs):
        if self.url.database != "vibewealth_test":
            attempts.append(True)
            raise AssertionError("Forbidden application database connection")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Engine, "connect", guarded)
    yield
    assert not attempts


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/assistant/conversations"),
    ("GET", f"/api/assistant/conversations/{uuid4()}"),
    ("GET", f"/api/assistant/conversations/{uuid4()}/messages"),
    ("POST", "/api/assistant/conversations"),
    ("DELETE", f"/api/assistant/conversations/{uuid4()}"),
])
def test_every_endpoint_requires_session_and_errors_are_no_store(method, path):
    with TestClient(application()) as client:
        response = client.request(method, path, **({"json": {"id": str(uuid4())}} if method == "POST" else {}))
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "detail": "Authentication required", "code": "AUTHENTICATION_REQUIRED",
        "issues": [], "current_turn": None,
    }


def test_only_c3_and_c4_assistant_endpoints_are_registered():
    paths = {(method.upper(), path) for path, operations in application().openapi()["paths"].items()
             if path.startswith("/api/assistant") for method in operations}
    assert paths == {
        ("POST", "/api/assistant/conversations"), ("GET", "/api/assistant/conversations"),
        ("GET", "/api/assistant/conversations/{conversation_id}"),
        ("DELETE", "/api/assistant/conversations/{conversation_id}"),
        ("GET", "/api/assistant/conversations/{conversation_id}/messages"),
        ("POST", "/api/assistant/conversations/{conversation_id}/messages"),
        ("GET", "/api/assistant/turns/by-key"),
        ("GET", "/api/assistant/conversations/{conversation_id}/turns/{turn_id}"),
        ("POST", "/api/assistant/conversations/{conversation_id}/turns/{turn_id}/retry"),
        ("POST", "/api/assistant/conversations/{conversation_id}/turns/{turn_id}/abandon"),
    }


def test_no_store_includes_cors_and_framework_errors():
    with TestClient(application()) as client:
        responses = [
            client.get("/api/assistant/not-implemented"),
            client.patch("/api/assistant/conversations"),
            client.options("/api/assistant/conversations", headers={
                "Origin": ORIGIN, "Access-Control-Request-Method": "POST",
            }),
            client.options("/api/assistant/conversations", headers={
                "Origin": "http://untrusted.test", "Access-Control-Request-Method": "POST",
            }),
        ]
    assert [response.status_code for response in responses] == [404, 405, 200, 400]
    assert all(response.headers["cache-control"] == "no-store" for response in responses)


def test_router_errors_use_assistant_dto_preserve_allow_and_do_not_change_other_routes():
    app = application()
    app.add_api_route("/control-resource", lambda: {"ok": True}, methods=["GET"])
    with TestClient(app) as client:
        missing = client.get("/api/assistant/no-such-route", headers={"Origin": ORIGIN})
        wrong_method = client.patch("/api/assistant/conversations", headers={"Origin": ORIGIN})
        normal_missing = client.get("/no-such-route")
        normal_method = client.patch("/control-resource")
    for response, code, status in (
        (missing, HttpErrorCode.ASSISTANT_ROUTE_NOT_FOUND, 404),
        (wrong_method, HttpErrorCode.METHOD_NOT_ALLOWED, 405),
    ):
        assert response.status_code == status
        assert response.json() == {
            "detail": HTTP_ERROR_MESSAGES[code], "code": code.value, "issues": [], "current_turn": None,
        }
        assert ErrorDto.model_validate(response.json()).code == code
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["access-control-allow-origin"] == ORIGIN
        assert response.headers["access-control-allow-credentials"] == "true"
        assert int(response.headers["content-length"]) == len(response.content)
    assert wrong_method.headers["allow"] == normal_method.headers["allow"] == "GET"
    assert normal_missing.status_code == 404 and normal_missing.json() == {"detail": "Not Found"}
    assert normal_method.status_code == 405 and normal_method.json() == {"detail": "Method Not Allowed"}
    assert "cache-control" not in normal_missing.headers and "cache-control" not in normal_method.headers


def test_rolling_limits_are_independent_and_recover_at_exact_expiry():
    clock = [0.0]
    limiter = AssistantRateLimiter(clock=lambda: clock[0])
    for _ in range(120):
        assert limiter.check("owner") is None
    assert limiter.check("owner") == 60
    for _ in range(30):
        assert limiter.check("owner", write=True) is None
    assert limiter.check("owner", write=True) == 60
    assert limiter.check("other") is None
    clock[0] = 59.1
    assert limiter.check("owner") == 1
    clock[0] = 60
    assert limiter.check("owner") is None
    assert limiter.check("owner", write=True) is None


def test_limiter_fails_closed_at_bucket_bound_without_evicting_active_users():
    clock = [0.0]
    limiter = AssistantRateLimiter(clock=lambda: clock[0], max_users=1)
    assert limiter.check("owner") is None
    assert limiter.check("other") == 60
    assert len(limiter._users) == 1 and "owner" in limiter._users
    clock[0] = 60
    assert limiter.check("other") is None
    assert set(limiter._users) == {"other"}


def test_concurrent_limit_checks_are_atomic_and_nonqueuing():
    limiter = AssistantRateLimiter(clock=lambda: 0)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: limiter.check("owner", write=True), range(50)))
    assert results.count(None) == 30
    assert results.count(60) == 20


@pytest.mark.parametrize("sqlstate,constraint,expected", [
    ("23505", "pk_assistant_conversations", True),
    ("23505", "uq_assistant_turns_user_key", False),
    ("23503", "pk_assistant_conversations", False),
    (None, "pk_assistant_conversations", False),
])
def test_recovery_is_restricted_to_exact_primary_key_violation(sqlstate, constraint, expected):
    error = SimpleNamespace(orig=SimpleNamespace(sqlstate=sqlstate, diag=SimpleNamespace(constraint_name=constraint)))
    assert assistant_routes.service.is_creation_primary_key_conflict(error) is expected


@pytest.fixture
def authenticated_app():
    app = application()
    auth = AuthenticatedRequest(CurrentUser(uuid4(), "test@example.test", None, uuid4()), "test-only-token")
    app.dependency_overrides[get_authenticated_request] = lambda: auth
    db = Mock()
    app.dependency_overrides[get_db] = lambda: db
    return app, auth, db


@pytest.mark.parametrize("query", [
    "offset=-1", "limit=0", "limit=101", "limit=true", "offset=1.0", "offset=1e2",
    "offset=+1", "offset=0&offset=1", "limit=1&limit=2", "user_id=private-owner",
])
def test_query_validation_rejects_ambiguous_or_coerced_values(authenticated_app, query):
    app, _, db = authenticated_app
    with TestClient(app) as client:
        response = client.get("/api/assistant/conversations?" + query)
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert "private-owner" not in response.text
    assert response.headers["cache-control"] == "no-store"
    db.commit.assert_not_called()


def test_unexpected_errors_are_sanitized_and_no_store(authenticated_app, monkeypatch):
    app, _, _ = authenticated_app
    monkeypatch.setattr(assistant_routes, "_read_snapshot", Mock(side_effect=RuntimeError("secret-cookie-and-SQL")))
    with TestClient(app) as client:
        response = client.get("/api/assistant/conversations")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "secret-cookie-and-SQL" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_read_rate_limit_has_retry_after_and_does_not_touch_snapshot(authenticated_app, monkeypatch):
    app, auth, _ = authenticated_app
    for _ in range(120):
        app.state.assistant_rate_limiter.check(auth.current_user.user_id)
    read = Mock()
    monkeypatch.setattr(assistant_routes, "_read_snapshot", read)
    with TestClient(app) as client:
        response = client.get("/api/assistant/conversations", headers={"Origin": ORIGIN})
    assert response.status_code == 429 and int(response.headers["retry-after"]) >= 1
    assert "retry-after" in {value.strip().lower() for value in response.headers["access-control-expose-headers"].split(",")}
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.json()["code"] == "RATE_LIMITED"
    assert response.headers["cache-control"] == "no-store"
    read.assert_not_called()


@pytest.mark.parametrize("identifier", ["bad", "{123e4567-e89b-42d3-a456-426614174000}",
                                       "123E4567-E89B-42D3-A456-426614174000"])
def test_path_uuid_validation_is_canonical(authenticated_app, monkeypatch, identifier):
    app, _, _ = authenticated_app
    operation = Mock()
    monkeypatch.setattr(assistant_routes, "_read_snapshot", operation)
    with TestClient(app) as client:
        response = client.get(f"/api/assistant/conversations/{identifier}")
    assert response.status_code == 422 and response.json()["code"] == "INVALID_REQUEST"
    operation.assert_not_called()
