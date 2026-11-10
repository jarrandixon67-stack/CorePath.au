import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.main import app as knowledge_app
from life_profile.main import app, repository
from life_profile.settings import Settings, get_settings


@pytest.fixture
def gateway():
    private = Ed25519PrivateKey.generate()
    public = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    app.dependency_overrides[get_settings] = lambda: Settings(gateway_public_key=public)

    class OwnerReviewDouble:
        def snapshot(self, subject, request_id, **kwargs):
            return {"subject": subject, "request_id": request_id, "items": []}

    app.dependency_overrides[repository] = lambda: OwnerReviewDouble()

    def token(**overrides):
        now = int(time.time())
        values = {
            "sub": "synthetic-owner-a",
            "iat": now,
            "nbf": now,
            "exp": now + 120,
            "iss": "corepath-personal-ai",
            "aud": "corepath-life-profile",
            "actor": "personal_ai",
            "purpose": "owner_review",
            "scope": ["profile:review"],
            "jti": str(uuid4()),
        }
        return jwt.encode(values | overrides, private, algorithm="EdDSA")

    try:
        with TestClient(app) as client:
            yield client, token
    finally:
        app.dependency_overrides.clear()


def test_valid_capability_binds_review_to_its_verified_subject(gateway):
    client, token = gateway
    response = client.get("/v1/life-profile/review", headers={"Authorization": "Bearer " + token()})
    assert response.status_code == 200
    assert response.json()["subject"] == "synthetic-owner-a"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("actor", ["founder", "administrator", "coordinator_ai", "specialist_ai"])
def test_other_roles_cannot_access_profiles_even_with_a_signed_token(gateway, actor):
    client, token = gateway
    response = client.get(
        "/v1/life-profile/review", headers={"Authorization": "Bearer " + token(actor=actor)}
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "knowledge-api"},
        {"iss": "untrusted"},
        {"exp": 1},
        {"exp": int(time.time()) + 10000},
        {"nbf": int(time.time()) + 10000},
    ],
)
def test_invalid_expired_or_overlong_capabilities_are_denied(gateway, changes):
    client, token = gateway
    response = client.get(
        "/v1/life-profile/review", headers={"Authorization": "Bearer " + token(**changes)}
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "changes", [{"scope": ["profile:analyse"]}, {"purpose": "personalisation"}]
)
def test_purpose_and_action_permissions_are_independent(gateway, changes):
    client, token = gateway
    response = client.get(
        "/v1/life-profile/review", headers={"Authorization": "Bearer " + token(**changes)}
    )
    assert response.status_code == 403


def test_shared_internal_token_and_browser_identity_headers_cannot_bypass_signatures(gateway):
    client, _ = gateway
    for headers in [
        {},
        {"Authorization": "Bearer knowledge-development-token"},
        {"oai-authenticated-user-id": "synthetic-owner-a"},
    ]:
        assert client.get("/v1/life-profile/review", headers=headers).status_code == 401


def test_algorithm_substitution_is_denied(gateway):
    client, _ = gateway
    forged = jwt.encode(
        {"sub": "synthetic-owner-a"}, "synthetic-test-secret-at-least-32-bytes", algorithm="HS256"
    )
    assert (
        client.get(
            "/v1/life-profile/review", headers={"Authorization": "Bearer " + forged}
        ).status_code
        == 401
    )


def test_profile_routes_do_not_exist_on_the_knowledge_api():
    assert not any("life-profile" in route.path for route in knowledge_app.routes)


def test_profile_database_cannot_be_the_configured_knowledge_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/knowledge")
    with pytest.raises(ValueError, match="separate database"):
        Settings(database_url="postgresql://example/knowledge").validate_database_separation()
