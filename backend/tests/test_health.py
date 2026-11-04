from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_application_starts() -> None:
    assert app.title == "VibeWealth API"
    assert app.version == "0.1.0"


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
