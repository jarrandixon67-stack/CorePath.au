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


def member_token(
    key, *, subject="test-member", scope="persy:research", purpose="research_approval"
):
    now = int(time.time())
    claims = {
        "iss": "corepath-member-gateway",
        "aud": "corepath-persy",
        "sub": subject,
        "actor": "member",
        "domain": "*",
        "scope": [scope],
        "purpose": purpose,
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


def test_pilot_member_allowlist_requires_explicit_approval(gateway, monkeypatch):
    client, member_key, _ = gateway
    from service_gateway.main import settings

    original = settings()
    pilot = Settings(
        **{
            **original.model_dump(),
            "allowed_member_subject": None,
            "allowed_member_subjects": "test-member,second-member",
        }
    )
    monkeypatch.setattr("service_gateway.main.settings", lambda: pilot)
    headers = {"Authorization": "Bearer " + "p" * 40}
    for subject, expected in (("test-member", 200), ("second-member", 200), ("other", 403)):
        response = client.post(
            "/exchange/percy",
            headers=headers,
            json={
                "target": "coordinator",
                "action": "research",
                "request_id": str(uuid4()),
                "member_capability": member_token(member_key, subject=subject),
            },
        )
        assert response.status_code == expected


def test_pilot_member_allowlist_fails_closed_on_bad_configuration():
    from service_gateway.main import member_is_enabled

    assert not member_is_enabled(Settings(allowed_member_subjects=""), "test-member")
    assert not member_is_enabled(Settings(allowed_member_subjects="x,x"), "x")
    assert not member_is_enabled(Settings(allowed_member_subjects="*"), "test-member")
    assert not member_is_enabled(Settings(allowed_member_subjects="x,"), "x")
    assert not member_is_enabled(
        Settings(allowed_member_subjects=",".join(str(i) for i in range(21))), "1"
    )
    assert member_is_enabled(
        Settings(allowed_member_subjects=",".join(str(i) for i in range(20))), "19"
    )


PROFILE_ACTIONS = {
    "context": (
        "persy:chat",
        "conversation_reply",
        "profile:context",
        "personalisation",
    ),
    "review": (
        "persy:profile:review",
        "profile_review",
        "profile:review",
        "owner_review",
    ),
    "consent": (
        "persy:profile:control",
        "profile_control",
        "profile:consent",
        "owner_control",
    ),
    "analyse": (
        "persy:profile:analyse",
        "profile_analysis",
        "profile:analyse",
        "profile_analysis",
    ),
    "decision": (
        "persy:profile:control",
        "profile_control",
        "profile:decide",
        "owner_control",
    ),
    "delete_item": (
        "persy:profile:control",
        "profile_control",
        "profile:delete",
        "owner_control",
    ),
    "delete_profile": (
        "persy:profile:control",
        "profile_control",
        "profile:delete",
        "owner_control",
    ),
}


@pytest.mark.parametrize("action", list(PROFILE_ACTIONS))
def test_life_profile_delegates_only_current_member_and_requested_action(
    gateway, monkeypatch, action
):
    client, member_key, service_key = gateway
    from service_gateway.main import settings

    profile_key = Ed25519PrivateKey.generate()
    original = settings()
    config = Settings(
        **{
            **original.model_dump(),
            "profile_signing_private_key": profile_key.private_bytes(
                Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
            ).decode(),
        }
    )
    monkeypatch.setattr("service_gateway.main.settings", lambda: config)

    incoming_scope, incoming_purpose, delegated_scope, delegated_purpose = PROFILE_ACTIONS[action]
    request_id = str(uuid4())
    body = {
        "target": "life_profile",
        "action": action,
        "request_id": request_id,
        "member_capability": member_token(
            member_key, scope=incoming_scope, purpose=incoming_purpose
        ),
    }
    response = client.post(
        "/exchange/percy", headers={"Authorization": "Bearer " + "p" * 40}, json=body
    )
    assert response.status_code == 200
    token = response.json()["capability"]
    claims = jwt.decode(
        token,
        profile_key.public_key(),
        algorithms=["EdDSA"],
        issuer="corepath-personal-ai",
        audience="corepath-life-profile",
    )
    assert claims["sub"] == "test-member"
    assert claims["actor"] == "personal_ai"
    assert claims["scope"] == [delegated_scope]
    assert claims["purpose"] == delegated_purpose
    assert claims["jti"] == request_id
    assert claims["domain"] == "*"
    assert claims["exp"] <= int(time.time()) + 120
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(
            token,
            service_key.public_key(),
            algorithms=["EdDSA"],
            audience="corepath-coordinator",
        )

    # Profile actions cannot be requested using a general research or wrong-person token.
    for bad_token in (
        member_token(member_key),
        member_token(
            member_key, scope=incoming_scope, purpose=incoming_purpose, subject="other-member"
        ),
    ):
        denied = client.post(
            "/exchange/percy",
            headers={"Authorization": "Bearer " + "p" * 40},
            json={**body, "member_capability": bad_token},
        )
        assert denied.status_code in (401, 403)


def test_profile_delegation_fails_closed_without_separate_signing_key(gateway):
    client, member_key, _ = gateway
    response = client.post(
        "/exchange/percy",
        headers={"Authorization": "Bearer " + "p" * 40},
        json={
            "target": "life_profile",
            "action": "review",
            "request_id": str(uuid4()),
            "member_capability": member_token(
                member_key, scope="persy:profile:review", purpose="profile_review"
            ),
        },
    )
    assert response.status_code == 503


def test_profile_delegation_rejects_administrative_claims(gateway):
    client, member_key, _ = gateway
    response = client.post(
        "/exchange/percy",
        headers={"Authorization": "Bearer " + "p" * 40},
        json={
            "target": "life_profile",
            "action": "admin",
            "request_id": str(uuid4()),
            "member_capability": member_token(member_key),
        },
    )
    assert response.status_code == 422
