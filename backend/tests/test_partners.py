import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from app.migrations import load_migrations, migrate
from partners.discovery import DiscoveryUnavailable, discover
from partners.mail import DeliveryUnknown, ResendTransport, invitation, process_one
from partners.models import (
    BusinessSeed,
    Contact,
    Criterion,
    DiscoveryRequest,
    Evidence,
    Kind,
    Policy,
    Review,
    email_address,
    public_url,
)
from partners.qualification import ALLOWED_KINDS, assess
from partners.repository import (
    POLICY,
    QUEUE,
    READ,
    RESEARCH,
    SEND,
    VERIFY,
    Conflict,
    Denied,
    Repository,
)
from partners.research import ResearchUnavailable, propose
from partners.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime.now(UTC)
REVIEW = Review(verified=True, reason="Reviewed synthetic evidence; this is not a real business")


@pytest.fixture
def partner_store():
    dsn = os.getenv("PARTNERS_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("requires isolated PostgreSQL")
    schema = "partner_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        migrations = load_migrations(ROOT / "partners/database/migrations")
        migrate(conn, migrations)
        assert migrate(conn, migrations) == []
        assert migrate(conn, migrations, check_only=True) == []
        conn.row_factory = dict_row
        for subject, role, permissions in [
            ("founder", "founder", []),
            ("executive", "executive_administrator", []),
            ("ungranted", "administrator", []),
            ("worker", "service", [READ, RESEARCH, QUEUE, SEND]),
            ("sender", "service", [SEND]),
        ]:
            conn.execute(
                "INSERT INTO partner_actors(subject,role,permissions) VALUES (%s,%s,%s)",
                (subject, role, permissions),
            )
        pool = ConnectionPool(
            dsn,
            open=True,
            min_size=1,
            max_size=6,
            kwargs={
                "options": f"-c search_path={schema} -c statement_timeout=5000",
                "client_encoding": "UTF8",
            },
        )
        pool.wait(timeout=10)
        try:
            yield Repository(pool), conn, schema
        finally:
            pool.close()
            conn.execute("SET search_path TO public")
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def seed(**changes):
    values = {
        "name": "Synthetic health business",
        "country": "AU",
        "category": "fitness",
        "sector": "health_and_wellbeing",
        "website": "https://business-" + uuid4().hex + ".example.test",
        "source_url": "https://registry.example.test/business",
        "attribution": "Synthetic records only",
    }
    values.update(changes)
    return BusinessSeed(**values)


def evidence(criterion, **changes):
    values = {
        "criterion": criterion,
        "result": "pass",
        "kind": min(ALLOWED_KINDS[criterion]),
        "source_url": "https://evidence.example.test/source",
        "title": "Synthetic source",
        "excerpt": "A precise synthetic source excerpt for qualification testing.",
        "rationale": "Reviewed against this requirement",
        "checked_at": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=30),
    }
    values.update(changes)
    return Evidence(**values)


def contact(email="partner@example.test", **changes):
    values = {
        "email": email,
        "basis": "express_consent",
        "consent_source_url": "https://business.example.test/contact-permission",
        "consent_notes": "Synthetic explicit permission for a partner invitation",
        "commission_compatible": True,
        "commission_review_url": "https://regulator.example.test/commercial-rules",
        "commission_review_notes": "Synthetic review confirms compatibility for this test only",
        "consent_at": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=30),
    }
    values.update(changes)
    return Contact(**values)


def settings(**changes):
    values = {
        "email_delivery_enabled": True,
        "email_api_key": "synthetic-provider-key",
        "sender_email": "partners@corepath.example.test",
        "reply_to": "partners@corepath.example.test",
        "sender_legal_name": "Synthetic CorePath Test",
        "sender_contact": "Synthetic contact details for tests only",
        "public_base_url": "https://partners.corepath.example.test",
    }
    values.update(changes)
    return Settings(**values)


def qualified(store, *, email="partner@example.test", approve=True):
    repo, _conn, _schema = store
    business = repo.ingest("founder", seed())
    policy = repo.create_policy(
        "founder", Policy(name="Synthetic AU health standard", country="AU")
    )
    if approve:
        repo.approve_policy("founder", policy["id"], REVIEW)
    sources = []
    for criterion in Criterion:
        item = repo.add_evidence("worker", business["id"], evidence(criterion))
        repo.review_evidence("founder", item["id"], REVIEW)
        sources.append(item)
    report = repo.assess("worker", business["id"], policy["id"])
    repo.save_contact("founder", business["id"], contact(email))
    return business, policy, sources, report


class Mailbox:
    def __init__(self, fail=False):
        self.messages, self.fail = [], fail

    def send(self, payload, key):
        self.messages.append((payload, key))
        if self.fail:
            raise DeliveryUnknown("Synthetic uncertain acknowledgement")
        return "synthetic-provider-id"


def test_missing_and_conflicting_evidence_are_review_not_failed_reputation():
    policy = Policy(name="Synthetic", country="AU")
    assert assess(policy, [])["decision"] == "review"
    assert assess(policy, [])["score"] is None
    records = [
        {"document": evidence(c).model_dump(mode="json"), "verified": True, "active": True}
        for c in Criterion
    ]
    assert assess(policy, records)["decision"] == "qualified"
    records.append(
        {
            "document": evidence(Criterion.SAFETY, result="fail").model_dump(mode="json"),
            "verified": True,
            "active": True,
        }
    )
    assert assess(policy, records)["decision"] == "review"
    records.pop()
    records[0]["document"]["result"] = "fail"
    result = assess(policy, records)
    assert result["decision"] == "not_qualified" and result["score"] < 100


@pytest.mark.parametrize("criterion", list(Criterion))
def test_each_health_requirement_is_mandatory_and_withdrawal_retracts_eligibility(
    partner_store, criterion
):
    repo, _, _ = partner_store
    business, policy, sources, report = qualified(partner_store)
    assert report["document"]["decision"] == "qualified"
    target = next(s for s in sources if s["document"]["criterion"] == criterion)
    repo.review_evidence(
        "founder",
        target["id"],
        Review(verified=False, reason="Withdraw this synthetic evidence source"),
    )
    updated = repo.assess("worker", business["id"], policy["id"])
    assert updated["document"]["decision"] == "review"
    with pytest.raises(Conflict, match="changed"):
        repo.enqueue("worker", business["id"], report["id"], settings())
    with pytest.raises(Conflict, match="every partner"):
        repo.enqueue("worker", business["id"], updated["id"], settings())


@pytest.mark.parametrize("change", ["unverified", "withdrawn", "expired", "stale", "wrong_kind"])
def test_unreliable_evidence_does_not_qualify(change):
    item = evidence(Criterion.IDENTITY)
    if change == "expired":
        item = evidence(
            Criterion.IDENTITY,
            checked_at=NOW - timedelta(days=10),
            valid_until=NOW - timedelta(days=1),
        )
    if change == "stale":
        item = evidence(Criterion.IDENTITY, checked_at=NOW - timedelta(days=100))
    if change == "wrong_kind":
        item = evidence(Criterion.IDENTITY, kind=Kind.OTHER)
    record = {
        "document": item.model_dump(mode="json"),
        "verified": change != "unverified",
        "active": change != "withdrawn",
    }
    assert (
        assess(Policy(name="Synthetic", country="AU"), [record])["criteria"][0]["result"]
        == "review"
    )


def test_database_roles_not_model_claims_control_authority(partner_store):
    repo, _, _ = partner_store
    business, policy, sources, _ = qualified(partner_store)
    for operation in [
        lambda: repo.review_evidence("worker", sources[0]["id"], REVIEW),
        lambda: repo.approve_policy("worker", policy["id"], REVIEW),
        lambda: repo.save_contact("worker", business["id"], contact()),
    ]:
        with pytest.raises(Denied):
            operation()
    for subject in ["ungranted", "unknown"]:
        with pytest.raises(Denied):
            repo.list_businesses(subject)
    assert repo.list_businesses("executive")


def test_draft_policy_foreign_country_and_sector_cannot_authorise_outreach(partner_store):
    repo, _, _ = partner_store
    business, policy, _, report = qualified(partner_store, approve=False)
    with pytest.raises(Conflict, match="not been approved"):
        repo.enqueue("worker", business["id"], report["id"], settings())
    repo.approve_policy("founder", policy["id"], REVIEW)
    with pytest.raises(Conflict, match="Country"):
        repo.enqueue("worker", business["id"], report["id"], settings(allowed_countries={"GB"}))
    other = repo.ingest("founder", seed(sector="unclassified"))
    with pytest.raises(Conflict, match="sector"):
        repo.assess("worker", other["id"], policy["id"])


def test_invitation_is_idempotent_clear_about_commission_and_sent_once(partner_store):
    repo, _, _ = partner_store
    business, _, _, report = qualified(partner_store)
    first = repo.enqueue("worker", business["id"], report["id"], settings())
    assert repo.enqueue("worker", business["id"], report["id"], settings())["id"] == first["id"]
    box = Mailbox()
    assert process_one(repo, "sender", settings(), transport=box)["state"] == "sent"
    assert process_one(repo, "sender", settings(), transport=box)["state"] == "idle"
    assert len(box.messages) == 1
    payload, key = box.messages[0]
    assert "10%" in payload["text"] and "does not buy a better rating" in payload["text"]
    assert payload["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert key == str(first["id"])
    assert "unsubscribe_token" not in repo.list_invitations("founder")[0]
    with pytest.raises(Conflict):
        repo.enqueue("worker", business["id"], report["id"], settings())


def test_uncertain_delivery_and_crashes_never_automatically_resend(partner_store):
    repo, conn, _ = partner_store
    business, _, _, report = qualified(partner_store)
    row = repo.enqueue("worker", business["id"], report["id"], settings())
    box = Mailbox(fail=True)
    assert process_one(repo, "sender", settings(), transport=box)["state"] == "unknown"
    assert process_one(repo, "sender", settings(), transport=box)["state"] == "idle"
    assert len(box.messages) == 1
    conn.execute("UPDATE partner_outbox SET state='queued' WHERE id=%s", (row["id"],))
    repo.reserve("sender", settings(), invitation)
    assert process_one(repo, "sender", settings(), transport=box)["state"] == "idle"
    assert len(box.messages) == 1


@pytest.mark.parametrize(
    "withdrawal", ["policy", "evidence", "consent", "changed_contact", "opt_out"]
)
def test_dispatch_rechecks_after_queuing(partner_store, withdrawal):
    repo, conn, _ = partner_store
    business, policy, sources, report = qualified(partner_store)
    repo.enqueue("worker", business["id"], report["id"], settings())
    if withdrawal == "policy":
        repo.approve_policy(
            "founder", policy["id"], Review(verified=False, reason="Withdraw this trial policy")
        )
    elif withdrawal == "evidence":
        repo.review_evidence(
            "founder",
            sources[0]["id"],
            Review(verified=False, reason="Withdraw this synthetic source"),
        )
    elif withdrawal == "consent":
        conn.execute(
            "UPDATE partner_contacts SET active=false WHERE business_id=%s", (business["id"],)
        )
    elif withdrawal == "changed_contact":
        repo.save_contact("founder", business["id"], contact("changed@example.test"))
    else:
        repo.suppress("founder", "partner@example.test", "Do not invite this address")
    box = Mailbox()
    process_one(repo, "sender", settings(), transport=box)
    assert not box.messages
    assert repo.list_invitations("founder")[0]["state"] == "blocked"


def test_opt_out_after_reservation_still_blocks_transport(partner_store):
    repo, conn, _ = partner_store
    business, _, _, report = qualified(partner_store)
    repo.enqueue("worker", business["id"], report["id"], settings())
    reserved = repo.reserve("sender", settings(), invitation)
    token = conn.execute("SELECT unsubscribe_token FROM partner_outbox").fetchone()[
        "unsubscribe_token"
    ]
    repo.unsubscribe(token)
    box = Mailbox()
    assert repo.deliver_reserved("sender", reserved, settings(), box)["state"] == "blocked"
    assert not box.messages


def test_concurrent_workers_obey_the_global_daily_cap(partner_store):
    repo, _, _ = partner_store
    for email in ["first@example.test", "second@example.test"]:
        business, _, _, report = qualified(partner_store, email=email)
        repo.enqueue("worker", business["id"], report["id"], settings())
    box = Mailbox()

    def run():
        try:
            return process_one(repo, "sender", settings(daily_email_limit=1), transport=box)
        except Conflict:
            return {"state": "limited"}

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run(), range(2)))
    assert len(box.messages) == 1 and sum(r["state"] == "sent" for r in results) == 1


def test_duplicate_entities_recipient_suppression_and_revocation(partner_store):
    repo, conn, _ = partner_store
    item = seed()
    assert repo.ingest("worker", item)["id"] == repo.ingest("worker", item)["id"]
    business, _, _, report = qualified(partner_store)
    repo.enqueue("worker", business["id"], report["id"], settings())
    other, _, _, other_report = qualified(partner_store)
    with pytest.raises(Conflict, match="already has"):
        repo.enqueue("worker", other["id"], other_report["id"], settings())
    conn.execute("UPDATE partner_actors SET active=false WHERE subject='sender'")
    with pytest.raises(Denied):
        process_one(repo, "sender", settings(), transport=Mailbox())


def test_default_delivery_is_disabled_and_health_baseline_cannot_be_lowered(partner_store):
    with pytest.raises(Conflict, match="not enabled"):
        process_one(partner_store[0], "sender", Settings(), transport=Mailbox())
    with pytest.raises(ValidationError):
        Policy(name="Lowered", country="AU", requirements=list(Criterion)[:5])


@pytest.mark.parametrize(
    "address",
    [
        "a@example.test\r\nBcc: victim@example.test",
        "a@example.test,b@example.test",
        "Name <a@example.test>",
        "a..b@example.test",
        "a@example..test",
    ],
)
def test_malformed_contact_addresses_are_rejected(address):
    with pytest.raises(ValueError):
        email_address(address)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test",
        "https://127.0.0.1",
        "https://user:pass@example.test",
        "https://example.test:8443",
        "https://internal.local",
        "file:///tmp/private",
    ],
)
def test_evidence_sources_do_not_accept_internal_or_credential_urls(url):
    with pytest.raises(ValueError):
        public_url(url)


def test_discovery_has_bounded_coverage_attribution_and_no_inferred_email_permission():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "elements": [
                    {
                        "type": "node",
                        "id": 123,
                        "tags": {
                            "name": "Synthetic Fitness",
                            "leisure": "fitness_centre",
                            "email": "not-consent@example.test",
                            "website": "https://fitness.example.test",
                        },
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        records = discover(DiscoveryRequest(bbox=(-34, 151, -33.9, 151.1)), client=client)
    assert len(records) == 1 and records[0].sector == "health_and_wellbeing"
    assert (
        "OpenStreetMap" in records[0].attribution
        and "not-consent" not in records[0].model_dump_json()
    )
    assert seen[0].url.host == "overpass-api.de"
    with pytest.raises(ValidationError):
        DiscoveryRequest(bbox=(-90, -180, 90, 180))
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"remark": "timeout", "elements": []})
            )
        ) as client,
        pytest.raises(DiscoveryUnavailable),
    ):
        discover(DiscoveryRequest(bbox=(-34, 151, -33.9, 151.1)), client=client)


def test_email_transport_validates_acknowledgement_and_stable_idempotency():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "synthetic-ack"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert (
            ResendTransport("synthetic", client=client).send({"text": "synthetic"}, "fixed")
            == "synthetic-ack"
        )
    assert seen[0].headers["Idempotency-Key"] == "corepath-partner/fixed"
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
        ) as client,
        pytest.raises(DeliveryUnknown),
    ):
        ResendTransport("synthetic", client=client).send({}, "fixed")


def test_model_proposals_must_cite_exact_registered_excerpts():
    source_id = uuid4()
    snapshot = {
        "business": {"document": {"name": "Synthetic", "country": "AU", "category": "fitness"}},
        "evidence": [
            {
                "id": source_id,
                "active": True,
                "document": {
                    "criterion": Criterion.IDENTITY,
                    "kind": Kind.REGISTRY,
                    "excerpt": "Synthetic verified registry excerpt",
                },
            }
        ],
    }

    def response(quote):
        import json

        draft = {
            "proposals": [
                {
                    "criterion": "identity_and_licensing",
                    "result": "pass",
                    "source_id": str(source_id),
                    "quote": quote,
                    "rationale": "Synthetic interpretation",
                }
            ],
            "limitations": ["Synthetic only"],
        }
        return httpx.Response(
            200,
            json={"output": [{"content": [{"type": "output_text", "text": json.dumps(draft)}]}]},
        )

    def grounded_response(request):
        import json

        from bot_standards import STANDARD

        body = json.loads(request.content)
        assert STANDARD in body["input"][0]["content"]
        assert "Do not make a partnership decision or send messages" in body["input"][0]["content"]
        assert "tools" not in body and body["store"] is False
        return response("verified registry excerpt")

    with httpx.Client(transport=httpx.MockTransport(grounded_response)) as client:
        assert propose(
            snapshot, settings(openai_api_key="synthetic", model="synthetic"), client=client
        ).proposals
    with (
        httpx.Client(transport=httpx.MockTransport(lambda r: response("invented quote"))) as client,
        pytest.raises(ResearchUnavailable),
    ):
        propose(snapshot, settings(openai_api_key="synthetic", model="synthetic"), client=client)


@pytest.fixture
def partner_api(partner_store, monkeypatch):
    import partners.main as api

    key = Ed25519PrivateKey.generate()
    cfg = settings(
        gateway_public_key=key.public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    monkeypatch.setattr(api, "get_settings", lambda: cfg)
    box = Mailbox()
    monkeypatch.setattr(
        api,
        "process_one",
        lambda repo, subject, config: process_one(repo, subject, config, transport=box),
    )
    api.app.dependency_overrides[api.repository] = lambda: partner_store[0]

    def token(action=READ, **changes):
        now = int(time.time())
        claims = {
            "sub": "worker",
            "actor": "partner_gateway",
            "scope": [action],
            "purpose": "business_partnerships",
            "domain": "*",
            "iat": now,
            "nbf": now,
            "exp": now + 120,
            "jti": str(uuid4()),
            "iss": cfg.gateway_issuer,
            "aud": cfg.gateway_audience,
        }
        claims.update(changes)
        return {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="EdDSA")}

    try:
        with TestClient(api.app) as client:
            yield client, token, box
    finally:
        api.app.dependency_overrides.clear()


def test_api_authenticates_and_ignores_forged_founder_claims(partner_api):
    client, token, _ = partner_api
    assert client.get("/v1/businesses").status_code == 401
    assert client.get("/v1/businesses", headers=token()).status_code == 200
    for changes in [
        {"actor": "personal_ai"},
        {"purpose": "life_profile"},
        {"sub": "forged-founder", "role": "founder"},
    ]:
        assert client.get("/v1/businesses", headers=token(**changes)).status_code == 403
    assert (
        client.post(
            "/v1/policies",
            headers=token(POLICY),
            json=Policy(name="Synthetic", country="AU").model_dump(mode="json"),
        ).status_code
        == 403
    )
    assert client.get("/v1/businesses", headers=token(VERIFY)).status_code == 403


@pytest.mark.parametrize("near_expiry", [False, True])
def test_api_dispatch_nonce_and_safe_opt_out(partner_api, partner_store, near_expiry):
    client, token, box = partner_api
    repo, conn, _ = partner_store
    business, _, _, report = qualified(partner_store)
    repo.enqueue("worker", business["id"], report["id"], settings())
    unsub = conn.execute("SELECT unsubscribe_token FROM partner_outbox").fetchone()[
        "unsubscribe_token"
    ]
    assert client.get("/unsubscribe/" + unsub).status_code == 200
    assert not conn.execute("SELECT 1 FROM partner_suppressions").fetchone()
    now = int(time.time())
    headers = token(
        SEND, **({"iat": now - 121, "nbf": now - 121, "exp": now - 1} if near_expiry else {})
    )
    assert client.post("/v1/process-one", headers=headers).json()["state"] == "sent"
    assert (
        client.post("/v1/process-one", headers=headers).status_code == 409
        and len(box.messages) == 1
    )
    assert client.post("/unsubscribe/" + unsub).status_code == 200
    assert conn.execute("SELECT 1 FROM partner_suppressions").fetchone()
    assert client.get("/unsubscribe/not-a-token").status_code == 404


def test_bounded_workflow_queues_only_eligible_contacts(partner_store):
    from partners.runtime import evaluate_batch

    repo, _, _ = partner_store
    business, policy, _, _ = qualified(partner_store)
    missing = repo.ingest("worker", seed())
    result = evaluate_batch(
        repo, "worker", [business["id"], business["id"], missing["id"]], policy["id"], settings()
    )
    assert len(result["results"]) == 2 and result["emails_sent"] == 0
    assert result["results"][0]["invitation_state"] == "queued"
    assert result["results"][1]["decision"] == "review"
    assert len(repo.list_invitations("founder")) == 1


def test_tampered_queued_payload_cannot_redirect_or_replace_invitation(partner_store):
    from psycopg.types.json import Jsonb

    repo, conn, _ = partner_store
    business, _, _, report = qualified(partner_store)
    repo.enqueue("worker", business["id"], report["id"], settings())
    reserved = repo.reserve("sender", settings(), invitation)
    altered = {**reserved["payload"], "to": ["someone-else@example.test"]}
    conn.execute(
        "UPDATE partner_outbox SET content=%s WHERE id=%s", (Jsonb(altered), reserved["id"])
    )
    box = Mailbox()
    assert repo.deliver_reserved("sender", reserved, settings(), box)["state"] == "blocked"
    assert not box.messages


def test_database_sender_role_cannot_approve_policy_change_identity_or_read_other_tables(
    partner_store,
):
    repo, conn, schema = partner_store
    business, _, _, report = qualified(partner_store)
    repo.enqueue("worker", business["id"], report["id"], settings())
    api_role = "partner_api_" + uuid4().hex
    sender_role = "partner_sender_" + uuid4().hex
    for role in [api_role, sender_role]:
        conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
    try:
        conn.execute("CREATE TABLE private_profile_canary(secret text)")
        script = (
            (ROOT / "partners/database/runtime-grants.sql")
            .read_text()
            .replace(':"partners_api_role"', sql.Identifier(api_role).as_string(conn))
            .replace(':"partners_worker_role"', sql.Identifier(sender_role).as_string(conn))
            .replace("SCHEMA public", "SCHEMA " + sql.Identifier(schema).as_string(conn))
        )
        conn.execute(script)
        for query in [
            "UPDATE partner_actors SET role='founder'",
            "UPDATE partner_policies SET approved=true",
            "UPDATE partner_evidence SET verified=true",
            "UPDATE partner_contacts SET active=true",
            "DELETE FROM partner_suppressions",
            "DELETE FROM partner_audit",
            "SELECT * FROM private_profile_canary",
        ]:
            with conn.transaction():
                conn.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(sender_role)))
                with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    conn.execute(query)
        # Execute the real delivery code with the restricted DB role, not the migrator.
        with ConnectionPool(
            os.getenv("PARTNERS_TEST_DATABASE_URL") or os.getenv("DATABASE_URL"),
            min_size=1,
            max_size=2,
            kwargs={
                "options": f"-c search_path={schema} -c role={sender_role}",
                "client_encoding": "UTF8",
            },
        ) as restricted:
            box = Mailbox()
            assert (
                process_one(Repository(restricted), "sender", settings(), transport=box)["state"]
                == "sent"
            )
            assert len(box.messages) == 1
    finally:
        for role in [sender_role, api_role]:
            conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_commercial_compatibility_is_separate_from_quality(partner_store):
    repo, _, _ = partner_store
    business, _, _, report = qualified(partner_store)
    repo.save_contact("founder", business["id"], contact(commission_compatible=False))
    assert report["document"]["decision"] == "qualified"
    with pytest.raises(Conflict, match="commercial arrangement"):
        repo.enqueue("worker", business["id"], report["id"], settings())


def test_reassessment_refreshes_a_queue_item_without_creating_another_invitation(partner_store):
    repo, _, _ = partner_store
    business, policy, _, report = qualified(partner_store)
    original = repo.enqueue("worker", business["id"], report["id"], settings())
    fresh = repo.assess("worker", business["id"], policy["id"])
    updated = repo.enqueue("worker", business["id"], fresh["id"], settings())
    assert updated["id"] == original["id"] and updated["assessment_id"] == fresh["id"]


def test_unapproved_sector_and_altered_sender_block_delivery(partner_store):
    repo, _, _ = partner_store
    business, _, _, report = qualified(partner_store)
    with pytest.raises(Conflict, match="Sector"):
        repo.enqueue("worker", business["id"], report["id"], settings(allowed_sectors={"trades"}))
    repo.enqueue("worker", business["id"], report["id"], settings())
    reserved = repo.reserve("sender", settings(), invitation)
    box = Mailbox()
    assert (
        repo.deliver_reserved(
            "sender", reserved, settings(sender_contact="Changed synthetic sender identity"), box
        )["state"]
        == "blocked"
    )
    assert not box.messages


def test_one_substantiated_failure_cannot_be_averaged_away_by_unknown_criteria():
    source = evidence(Criterion.SAFETY, result="fail")
    result = assess(
        Policy(name="Synthetic", country="AU"),
        [{"document": source.model_dump(mode="json"), "verified": True, "active": True}],
    )
    assert result["decision"] == "not_qualified" and result["score"] is None


def test_transparent_traditional_practice_is_not_failed_for_limited_research():
    policy = Policy(name="Synthetic health policy", country="AU")
    sources = []
    for criterion in Criterion:
        changes = {}
        if criterion == Criterion.HEALTH_CLAIMS:
            changes = {
                "kind": Kind.TRADITIONAL,
                "excerpt": "This is documented traditional use with limited controlled research, not a proven cure.",
                "rationale": "Synthetic reviewer verified that the provider honestly describes limited evidence and stays within a suitably safe wellbeing scope; this does not establish efficacy.",
            }
        sources.append(
            {
                "document": evidence(criterion, **changes).model_dump(mode="json"),
                "verified": True,
                "active": True,
            }
        )
    result = assess(policy, sources)
    assert result["decision"] == "qualified"
    assert "consumer star rating" in result["meaning"]
