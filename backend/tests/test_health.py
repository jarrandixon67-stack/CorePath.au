from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_liveness_is_available_without_database(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}
    finally:
        get_settings.cache_clear()


def test_readiness_reports_missing_database(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["detail"] == "Database is not configured"
    finally:
        get_settings.cache_clear()


def test_readiness_reports_connected_database() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}
