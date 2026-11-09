from fastapi.testclient import TestClient

from app.main import app


def test_liveness_is_available_without_database() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_reports_missing_database() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Database is not configured"
