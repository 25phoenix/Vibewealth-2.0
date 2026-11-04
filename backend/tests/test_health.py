from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes import get_db
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_application_starts() -> None:
    assert app.title == "VibeWealth API"
    assert app.version == "0.1.0"


def test_health_endpoint_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health_endpoint_succeeds_with_session_override(
    client: TestClient,
) -> None:
    session = MagicMock(spec=Session)
    app.dependency_overrides[get_db] = lambda: session

    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "available"}
    session.execute.assert_called_once()


def test_database_health_endpoint_hides_connection_errors(client: TestClient) -> None:
    session = MagicMock(spec=Session)
    session.execute.side_effect = SQLAlchemyError("private database details")
    app.dependency_overrides[get_db] = lambda: session

    response = client.get("/health/db")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
    assert "private database details" not in response.text
