import os

import pytest
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


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires a configured PostgreSQL service")
def test_readiness_reports_connected_database() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


def test_internal_route_rejects_missing_token() -> None:
    with TestClient(app) as client:
        response = client.get("/v1/libraries")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing bearer token"


def test_internal_route_requires_configured_token(monkeypatch) -> None:
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/libraries",
                headers={"Authorization": "Bearer any-value"},
            )
        assert response.status_code == 503
        assert response.json()["detail"] == "Internal API authentication is not configured"
    finally:
        get_settings.cache_clear()
