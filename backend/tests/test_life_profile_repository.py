import os
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet, InvalidToken
from psycopg_pool import ConnectionPool
from test_life_profile_bot import ModelDouble, proposal, request

from life_profile.bot import LifeProfileBot
from life_profile.models import Consent, Decision
from life_profile.repository import (
    ConsentRequired,
    ProfileConflict,
    ProfileMissing,
    ProfileRepository,
)


@pytest.fixture
def profiles():
    database_url = os.getenv("LIFE_PROFILE_DATABASE_URL")
    if not database_url:
        pytest.skip("requires a separate disposable Life Profile PostgreSQL database")
    with ConnectionPool(database_url, min_size=1, max_size=2, kwargs={"autocommit": False}) as pool:
        with pool.connection() as conn:
            database_name = conn.execute("SELECT current_database()").fetchone()[0]
            if not database_name.endswith("_test"):
                pytest.fail("Life Profile integration tests require a disposable *_test database.")
            assert (
                conn.execute("SELECT to_regclass('public.knowledge_libraries')").fetchone()[0]
                is None
            )
        store = ProfileRepository(pool, Fernet(Fernet.generate_key()))
        owner_a, owner_b = "test-" + uuid4().hex, "test-" + uuid4().hex
        permission = Consent(
            analysis_enabled=True,
            external_model_processing=True,
            personalisation_enabled=True,
            sensitive_observations_enabled=True,
            categories=["personal_growth_development"],
            purpose="Adapt communication",
        )
        store.set_consent(owner_a, permission, "synthetic-consent-a")
        store.set_consent(owner_b, permission, "synthetic-consent-b")
        try:
            yield store, pool, owner_a, owner_b, permission
        finally:
            store.delete_profile(owner_a)
            store.delete_profile(owner_b)


def add_proposal(store, owner):
    result = LifeProfileBot(store, ModelDouble()).analyse(owner, request(), "synthetic-analysis")
    return result["proposals"][0]


def test_observations_and_consent_are_encrypted_with_payload_free_audits(profiles):
    store, pool, owner, _, _ = profiles
    item = add_proposal(store, owner)
    with pool.connection() as conn:
        raw = conn.execute(
            "SELECT payload_ciphertext FROM life_profile_items WHERE id = %s", (UUID(item["id"]),)
        ).fetchone()[0]
        assert b"Prefers concise explanations" not in bytes(raw)
        assert b"I prefer short answers" not in bytes(raw)
        assert store.decrypt(raw)["statement"] == "Prefers concise explanations."
        rows = conn.execute(
            "SELECT action, request_id FROM life_profile_audit WHERE subject = %s", (owner,)
        ).fetchall()
        assert {row[0] for row in rows} >= {"consent.update", "observation.propose"}
        assert "short answers" not in str(rows)


def test_an_incorrect_encryption_key_does_not_return_an_empty_or_plaintext_profile(profiles):
    store, pool, owner, _, _ = profiles
    add_proposal(store, owner)
    wrong_key = ProfileRepository(pool, Fernet(Fernet.generate_key()))
    with pytest.raises(InvalidToken):
        wrong_key.snapshot(owner, "synthetic-wrong-key")
    assert len(store.snapshot(owner, "synthetic-correct-key")["items"]) == 1


def test_only_owner_accepted_and_explicitly_shared_understanding_is_returned(profiles):
    store, _, owner, _, _ = profiles
    item = add_proposal(store, owner)
    assert store.context(owner, "synthetic-context") == []
    accepted = store.decide(
        owner, UUID(item["id"]), Decision(expected_version=1, action="accept"), "synthetic-accept"
    )
    assert accepted["understanding_level"] == "confirmed_understanding"
    assert store.context(owner, "synthetic-context") == []
    store.decide(
        owner,
        UUID(item["id"]),
        Decision(expected_version=2, action="accept", share_with_personal_ai=True),
        "synthetic-share",
    )
    context = store.context(owner, "synthetic-context")
    assert context[0]["statement"] == item["statement"]
    assert "evidence" not in context[0]
    assert "confidence_reason" not in context[0]


def test_correction_replaces_current_understanding_and_preserves_encrypted_history(profiles):
    store, pool, owner, _, _ = profiles
    item = add_proposal(store, owner)
    corrected = store.decide(
        owner,
        UUID(item["id"]),
        Decision(
            expected_version=1,
            action="correct",
            corrected_statement="Prefers a worked example.",
            share_with_personal_ai=True,
        ),
        "synthetic-correction",
    )
    assert corrected["user_corrected"] is True
    assert corrected["sensitive"] is True
    assert store.context(owner, "synthetic-context")[0]["statement"] == "Prefers a worked example."
    with pool.connection() as conn:
        version = conn.execute(
            "SELECT payload_ciphertext FROM life_profile_item_versions WHERE item_id = %s",
            (UUID(item["id"]),),
        ).fetchone()[0]
        assert store.decrypt(version)["statement"] == item["statement"]
        assert b"Prefers concise explanations" not in bytes(version)


def test_another_owner_cannot_review_change_or_delete_an_observation(profiles):
    store, _, owner_a, owner_b, _ = profiles
    item = add_proposal(store, owner_a)
    assert store.snapshot(owner_b, "synthetic-review")["items"] == []
    assert store.context(owner_b, "synthetic-context") == []
    with pytest.raises(ProfileMissing):
        store.decide(
            owner_b,
            UUID(item["id"]),
            Decision(expected_version=1, action="accept"),
            "synthetic-cross-user",
        )
    with pytest.raises(ProfileMissing):
        store.delete_item(owner_b, UUID(item["id"]), "synthetic-cross-user")
    assert len(store.snapshot(owner_a, "synthetic-review")["items"]) == 1


def test_stale_decision_does_not_overwrite_a_newer_owner_correction(profiles):
    store, _, owner, _, _ = profiles
    item = add_proposal(store, owner)
    store.decide(
        owner,
        UUID(item["id"]),
        Decision(
            expected_version=1, action="correct", corrected_statement="Prefers practical examples."
        ),
        "synthetic-first-correction",
    )
    with pytest.raises(ProfileConflict):
        store.decide(
            owner,
            UUID(item["id"]),
            Decision(expected_version=1, action="reject"),
            "synthetic-stale",
        )
    assert (
        store.snapshot(owner, "synthetic-review")["items"][0]["statement"]
        == "Prefers practical examples."
    )


def test_rejected_interpretations_are_never_sent_back_for_personalisation(profiles):
    store, _, owner, _, _ = profiles
    item = add_proposal(store, owner)
    store.decide(
        owner, UUID(item["id"]), Decision(expected_version=1, action="reject"), "synthetic-reject"
    )
    assert store.context(owner, "synthetic-context") == []
    model = ModelDouble()
    LifeProfileBot(store, model).analyse(owner, request(), "synthetic-next-analysis")
    assert model.inputs[0]["previously_accepted_understanding"] == []


def test_withdrawn_consent_blocks_further_analysis_and_context(profiles):
    store, _, owner, _, permission = profiles
    item = add_proposal(store, owner)
    store.decide(
        owner,
        UUID(item["id"]),
        Decision(expected_version=1, action="accept", share_with_personal_ai=True),
        "synthetic-share",
    )
    store.set_consent(
        owner,
        permission.model_copy(update={"analysis_enabled": False, "personalisation_enabled": False}),
        "synthetic-withdrawal",
    )
    model = ModelDouble()
    with pytest.raises(ConsentRequired):
        LifeProfileBot(store, model).analyse(owner, request(), "synthetic-blocked")
    with pytest.raises(ConsentRequired):
        store.context(owner, "synthetic-blocked")
    assert model.inputs == []
    assert len(store.snapshot(owner, "synthetic-owner-review", owner_review=True)["items"]) == 1


def test_consent_change_during_model_call_prevents_persistence(profiles):
    store, _, owner, _, permission = profiles

    class RevokingModel:
        def propose(self, _context):
            store.set_consent(
                owner,
                permission.model_copy(update={"analysis_enabled": False}),
                "synthetic-withdrawal",
            )
            return proposal()

    with pytest.raises(ProfileConflict, match="Consent changed"):
        LifeProfileBot(store, RevokingModel()).analyse(owner, request(), "synthetic-race")
    assert store.snapshot(owner, "synthetic-review")["items"] == []


def test_deleting_an_item_removes_its_encrypted_versions(profiles):
    store, pool, owner, _, _ = profiles
    item = add_proposal(store, owner)
    store.decide(
        owner, UUID(item["id"]), Decision(expected_version=1, action="accept"), "synthetic-accept"
    )
    store.delete_item(owner, UUID(item["id"]), "synthetic-delete")
    with pool.connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM life_profile_item_versions WHERE item_id = %s",
                (UUID(item["id"]),),
            ).fetchone()[0]
            == 0
        )
    assert store.snapshot(owner, "synthetic-review")["items"] == []


def test_deleting_a_profile_removes_its_items_versions_and_audits_only(profiles):
    store, pool, owner_a, owner_b, _ = profiles
    item = add_proposal(store, owner_a)
    store.decide(
        owner_a, UUID(item["id"]), Decision(expected_version=1, action="accept"), "synthetic-accept"
    )
    store.delete_profile(owner_a)
    with pool.connection() as conn:
        for table in ("life_profiles", "life_profile_items", "life_profile_audit"):
            from psycopg import sql

            count = conn.execute(
                sql.SQL("SELECT count(*) FROM {} WHERE subject = %s").format(sql.Identifier(table)),
                (owner_a,),
            ).fetchone()[0]
            assert count == 0
        assert (
            conn.execute(
                "SELECT count(*) FROM life_profile_item_versions WHERE item_id = %s",
                (UUID(item["id"]),),
            ).fetchone()[0]
            == 0
        )
    assert store.snapshot(owner_b, "synthetic-other-owner")["items"] == []


def test_http_flow_requires_owner_review_before_personalisation(profiles):
    import time

    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from fastapi.testclient import TestClient

    from life_profile.main import app, bot, repository
    from life_profile.settings import Settings, get_settings

    store, _, owner, other_owner, permission = profiles
    private = Ed25519PrivateKey.generate()
    public = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    app.dependency_overrides[get_settings] = lambda: Settings(gateway_public_key=public)
    app.dependency_overrides[repository] = lambda: store
    app.dependency_overrides[bot] = lambda: LifeProfileBot(store, ModelDouble())

    def headers(scope, purpose, subject=owner):
        now = int(time.time())
        token = jwt.encode(
            {
                "sub": subject,
                "iat": now,
                "nbf": now,
                "exp": now + 120,
                "iss": "corepath-personal-ai",
                "aud": "corepath-life-profile",
                "actor": "personal_ai",
                "scope": [scope],
                "purpose": purpose,
                "jti": str(uuid4()),
            },
            private,
            algorithm="EdDSA",
        )
        return {"Authorization": "Bearer " + token}

    try:
        with TestClient(app) as client:
            response = client.put(
                "/v1/life-profile/consent",
                headers=headers("profile:consent", "owner_control"),
                json=permission.model_dump(mode="json"),
            )
            assert response.status_code == 200
            response = client.post(
                "/v1/life-profile/analyse",
                headers=headers("profile:analyse", "profile_analysis"),
                json=request().model_dump(mode="json"),
            )
            assert response.status_code == 200
            item = response.json()["proposals"][0]
            assert item["state"] == "pending"
            context = client.get(
                "/v1/life-profile/context", headers=headers("profile:context", "personalisation")
            )
            assert context.json()["approved_understanding"] == []
            path = f"/v1/life-profile/items/{item['id']}/decision"
            response = client.post(
                path,
                headers=headers("profile:decide", "owner_control", other_owner),
                json={"expected_version": 1, "action": "accept"},
            )
            assert response.status_code == 404
            response = client.post(
                path,
                headers=headers("profile:decide", "owner_control"),
                json={"expected_version": 1, "action": "accept", "share_with_personal_ai": True},
            )
            assert response.status_code == 200
            context = client.get(
                "/v1/life-profile/context", headers=headers("profile:context", "personalisation")
            )
            assert len(context.json()["approved_understanding"]) == 1
            assert "evidence" not in context.json()["approved_understanding"][0]
            invalid = request().model_dump(mode="json") | {"user_id": other_owner}
            assert (
                client.post(
                    "/v1/life-profile/analyse",
                    headers=headers("profile:analyse", "profile_analysis"),
                    json=invalid,
                ).status_code
                == 422
            )
    finally:
        app.dependency_overrides.clear()
