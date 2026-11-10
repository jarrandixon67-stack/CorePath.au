import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from specialists.main import app, repository, runtime
from specialists.registry import Domain
from specialists.settings import Settings, get_settings


@pytest.fixture
def specialist_gateway(monkeypatch):
    monkeypatch.delenv("SPECIALISTS_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    private = Ed25519PrivateKey.generate()
    public = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        gateway_public_key=public, database_url=None
    )

    class ServiceDouble:
        def execute(self, capability, domain, task):
            return {
                "subject": capability.subject,
                "domain": domain.value,
                "request_id": capability.request_id,
            }

        def read_run(self, capability, domain, run_id):
            return {"id": str(run_id), "state": "needs_evidence"}

        def catalogue(self, capability):
            return {d.value: "planned" for d in Domain}

    app.dependency_overrides[runtime] = ServiceDouble
    app.dependency_overrides[repository] = ServiceDouble

    def token(**overrides):
        now = int(time.time())
        claims = {
            "sub": "synthetic-coordinator",
            "actor": "coordinator_ai",
            "domain": "nutrition",
            "scope": ["specialist:dispatch"],
            "purpose": "dispatch",
            "iss": "corepath-service-gateway",
            "aud": "corepath-specialists",
            "iat": now,
            "nbf": now,
            "exp": now + 120,
            "jti": str(uuid4()),
        }
        return jwt.encode(claims | overrides, private, algorithm="EdDSA")

    try:
        with TestClient(app) as client:
            yield client, token
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def dispatch(client, token=None, headers=None):
    return client.post(
        "/v1/specialists/nutrition/tasks",
        headers=headers or ({"Authorization": "Bearer " + token} if token else {}),
        json={"question": "Investigate general nutrition evidence", "search_terms": ["nutrition"]},
    )


def test_coordinator_dispatch_and_status_are_signed_and_domain_bound(specialist_gateway):
    client, token = specialist_gateway
    response = dispatch(client, token())
    assert response.status_code == 200
    assert response.json()["subject"] == "synthetic-coordinator"
    assert response.headers["cache-control"] == "no-store"
    status = client.get(
        f"/v1/specialists/nutrition/tasks/{uuid4()}",
        headers={
            "Authorization": "Bearer " + token(scope=["specialist:read"], purpose="task_status")
        },
    )
    assert status.status_code == 200


@pytest.mark.parametrize(
    "actor",
    [
        "founder",
        "administrator",
        "executive_administrator",
        "personal_ai",
        "life_profiling_ai",
        "specialist_ai",
    ],
)
def test_humans_and_other_bots_cannot_dispatch_specialists(specialist_gateway, actor):
    client, token = specialist_gateway
    assert dispatch(client, token(actor=actor)).status_code == 403


@pytest.mark.parametrize(
    "changes",
    [
        {"domain": "physical-development"},
        {"domain": "*"},
        {"purpose": "independent_research"},
        {"scope": ["specialist:research"]},
    ],
)
def test_valid_signature_does_not_replace_scope_and_purpose_checks(specialist_gateway, changes):
    client, token = specialist_gateway
    assert dispatch(client, token(**changes)).status_code == 403


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "untrusted"},
        {"aud": "corepath-life-profile"},
        {"exp": 1},
        {"exp": int(time.time()) + 10000},
        {"nbf": int(time.time()) + 10000},
        {"iat": True},
        {"scope": "specialist:dispatch"},
        {"sub": ""},
        {"jti": ""},
    ],
)
def test_invalid_or_expired_capabilities_are_denied(specialist_gateway, changes):
    client, token = specialist_gateway
    assert dispatch(client, token(**changes)).status_code == 401


def test_independent_research_requires_a_different_actor_scope_and_purpose(specialist_gateway):
    client, token = specialist_gateway
    body = {"question": "Investigate nutrition evidence gaps", "search_terms": ["evidence"]}
    path = "/v1/specialists/nutrition/research"
    assert (
        client.post(path, headers={"Authorization": "Bearer " + token()}, json=body).status_code
        == 403
    )
    assert (
        client.post(
            path,
            headers={
                "Authorization": "Bearer "
                + token(
                    actor="specialist_ai",
                    scope=["specialist:research"],
                    purpose="independent_research",
                )
            },
            json=body,
        ).status_code
        == 200
    )


def test_catalogue_reports_configuration_without_claiming_live_quality(specialist_gateway):
    client, token = specialist_gateway
    response = client.get(
        "/v1/specialists",
        headers={
            "Authorization": "Bearer "
            + token(domain="*", scope=["specialist:catalogue"], purpose="catalogue")
        },
    )
    assert response.status_code == 200
    assert len(response.json()["specialists"]) == 11
    assert all(
        not item["live_model_quality_verified"] and item["library_state"] == "planned"
        for item in response.json()["specialists"]
    )


def test_unsigned_headers_shared_tokens_and_algorithm_substitution_cannot_dispatch(
    specialist_gateway,
):
    client, _ = specialist_gateway
    for headers in (
        {},
        {"oai-authenticated-user-id": "founder"},
        {"Authorization": "Bearer internal-development-token"},
    ):
        assert dispatch(client, headers=headers).status_code == 401
    forged = jwt.encode(
        {"sub": "synthetic-coordinator"},
        "synthetic-test-secret-at-least-32-bytes",
        algorithm="HS256",
    )
    assert dispatch(client, forged).status_code == 401


def test_profile_and_public_chat_routes_are_absent_and_liveness_is_not_readiness(
    specialist_gateway,
):
    client, _ = specialist_gateway
    assert client.get("/health/live").json()["status"] == "alive"
    assert client.get("/v1/life-profile").status_code == 404
    assert client.post("/v1/chat", json={}).status_code == 404
    assert client.get("/docs").status_code == 404


def test_missing_identity_configuration_fails_closed(specialist_gateway):
    client, token = specialist_gateway
    app.dependency_overrides[get_settings] = lambda: Settings(gateway_public_key=None)
    assert dispatch(client, token()).status_code == 503
