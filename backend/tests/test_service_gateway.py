import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from fastapi.testclient import TestClient

from service_gateway.main import Settings, app
from specialists.registry import Domain


@pytest.fixture
def gateway(monkeypatch):
    member_key = Ed25519PrivateKey.generate()
    service_key = Ed25519PrivateKey.generate()
    config = Settings(
        signing_private_key=service_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        ).decode(),
        member_public_key=member_key.public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        .decode(),
        percy_machine_token="p" * 40,
        coordinator_machine_token="c" * 40,
        allowed_member_subject="test-member",
    )
    monkeypatch.setattr("service_gateway.main.settings", lambda: config)
    return TestClient(app), member_key, service_key


def member_token(key, *, subject="test-member", scope="persy:research"):
    now = int(time.time())
    claims = {
        "iss": "corepath-member-gateway",
        "aud": "corepath-persy",
        "sub": subject,
        "actor": "member",
        "domain": "*",
        "scope": [scope],
        "purpose": "research_approval",
        "iat": now,
        "nbf": now,
        "exp": now + 120,
        "jti": str(uuid4()),
    }
    return jwt.encode(claims, key, algorithm="EdDSA")


def test_research_exchange_is_owner_scoped_and_expiry_bounded(gateway):
    client, member_key, service_key = gateway
    incoming = member_token(member_key)
    request_id = str(uuid4())
    response = client.post(
        "/exchange/percy",
        headers={"Authorization": "Bearer " + "p" * 40},
        json={
            "target": "coordinator",
            "action": "research",
            "request_id": request_id,
            "member_capability": incoming,
        },
    )
    assert response.status_code == 200
    claims = jwt.decode(
        response.json()["capability"],
        service_key.public_key(),
        algorithms=["EdDSA"],
        issuer="corepath-service-gateway",
        audience="corepath-coordinator",
    )
    assert claims["sub"] == "corepath-persy"
    assert claims["scope"] == ["coordinator:research"]
    assert claims["jti"] == request_id
    assert (
        claims["exp"]
        <= jwt.decode(
            incoming, member_key.public_key(), algorithms=["EdDSA"], audience="corepath-persy"
        )["exp"]
    )
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("domain", list(Domain))
def test_coordinator_can_dispatch_every_registered_domain_only(gateway, domain):
    client, _, key = gateway
    body = {
        "domain": domain.value,
        "purpose": "dispatch",
        "scope": ["specialist:dispatch"],
        "request_id": str(uuid4()),
    }
    response = client.post(
        "/exchange/coordinator", headers={"Authorization": "Bearer " + "c" * 40}, json=body
    )
    assert response.status_code == 200
    claims = jwt.decode(
        response.json()["capability"],
        key.public_key(),
        algorithms=["EdDSA"],
        audience="corepath-specialists",
    )
    assert claims["domain"] == domain.value
    assert claims["actor"] == "coordinator_ai"
    assert claims["sub"] == "corepath-coordinator"
    assert claims["scope"] == ["specialist:dispatch"]


def test_exchange_rejects_wrong_machine_scope_owner_and_arbitrary_claims(gateway):
    client, key, _ = gateway
    body = {
        "target": "coordinator",
        "action": "research",
        "request_id": str(uuid4()),
        "member_capability": member_token(key),
    }
    assert client.post("/exchange/percy", json=body).status_code == 401
    headers = {"Authorization": "Bearer " + "p" * 40}
    for token in [member_token(key, subject="other"), member_token(key, scope="persy:chat")]:
        assert client.post(
            "/exchange/percy", headers=headers, json={**body, "member_capability": token}
        ).status_code in (401, 403)
    assert (
        client.post("/exchange/percy", headers=headers, json={**body, "sub": "admin"}).status_code
        == 422
    )
    assert (
        client.post(
            "/exchange/percy", headers=headers, json={**body, "target": "life_profile"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/exchange/coordinator",
            headers=headers,
            json={
                "domain": "nutrition",
                "purpose": "dispatch",
                "scope": ["specialist:dispatch"],
                "request_id": str(uuid4()),
            },
        ).status_code
        == 401
    )


def test_body_size_is_bounded(gateway):
    client, _, _ = gateway
    assert client.post("/exchange/percy", content="x" * 17000).status_code == 413
