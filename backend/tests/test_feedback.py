import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from cryptography.fernet import Fernet
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from app.migrations import load_migrations, migrate
from feedback.bot import FeedbackBot
from feedback.models import Analysis, FeedbackEntry, ImportedReview, Resolution, Theme
from feedback.repository import Repository
from feedback.settings import Settings
from partners.repository import Conflict, Denied, Missing

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def feedback_store():
    dsn = os.getenv("FEEDBACK_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("requires isolated PostgreSQL")
    schema = "feedback_test_" + uuid4().hex
    cfg = Settings(
        encryption_key=Fernet.generate_key().decode(),
        owner_hash_key="synthetic-feedback-owner-hash-key-32",
    )
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        c.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        migrations = load_migrations(ROOT / "feedback/database/migrations")
        migrate(c, migrations)
        assert migrate(c, migrations) == []
        c.row_factory = dict_row
        for subject, role, permissions in [
            ("founder", "founder", []),
            ("one", "member", []),
            ("two", "member", []),
            ("three", "member", []),
            ("bot", "service", ["feedback.analyse"]),
        ]:
            c.execute(
                "INSERT INTO feedback_actors(subject,role,permissions) VALUES (%s,%s,%s)",
                (subject, role, permissions),
            )
        pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=4,
            open=True,
            kwargs={
                "options": f"-c search_path={schema} -c statement_timeout=5000",
                "client_encoding": "UTF8",
            },
        )
        pool.wait(timeout=10)
        try:
            yield Repository(pool, cfg), c, schema, cfg
        finally:
            pool.close()
            c.execute("SET search_path TO public")
            c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def entry(**changes):
    fields = {
        "positive": "The staff were helpful and clear.",
        "negative": "The prices were unclear.",
        "suggestions": "Show the full price before booking.",
        "allow_ai_analysis": True,
    }
    fields.update(changes)
    return FeedbackEntry(**fields)


def submit_three(repo, target="corepath"):
    return [repo.submit(owner, target, entry())["id"] for owner in ("one", "two", "three")]


def analysis(
    snapshot, *, kind="concern", category="pricing", severity="ordinary", field="negative"
):
    return Analysis(
        themes=[
            Theme(
                kind=kind,
                category=category,
                severity=severity,
                title="Possible pricing clarity issue",
                summary="These reports describe unclear pricing; a person should review them.",
                citations=[
                    {"record_id": r["id"], "field": field, "quote": r["content"][field]}
                    for r in snapshot
                ],
            )
        ],
        limitations=["Synthetic reports; no claim that allegations are established."],
    )


class Model:
    def __init__(self, effect=None, kind="concern", severity="ordinary", field="negative"):
        self.calls = 0
        self.effect = effect
        self.kind = kind
        self.severity = severity
        self.field = field

    def analyse(self, snapshot):
        self.calls += 1
        if self.effect:
            self.effect()
        return analysis(snapshot, kind=self.kind, severity=self.severity, field=self.field)


def test_prompts_ask_good_bad_and_suggestions_without_nagging(feedback_store):
    repo, _, _, _ = feedback_store
    first = repo.prompt("one", "corepath")
    assert first["show_prompt"] and len(first["questions"]) == 3
    assert "What worked" in first["questions"][0]
    assert "did not work" in first["questions"][1]
    assert not repo.prompt("one", "corepath")["show_prompt"]
    repo.preference("two", False)
    assert not repo.prompt("two", "corepath")["show_prompt"]
    assert repo.prompt("three", "corepath")["show_prompt"]


def test_feedback_defaults_to_no_external_analysis_but_is_available_for_human_review(
    feedback_store,
):
    repo, c, _, _ = feedback_store
    saved = repo.submit("one", "corepath", entry(allow_ai_analysis=False))
    provider = Model()
    assert FeedbackBot(repo, provider).analyse("bot", "corepath")["records_considered"] == 0
    assert provider.calls == 0
    assert repo.staff_records("founder", "corepath")[0]["id"] == saved["id"]
    raw = c.execute("SELECT payload,owner_key FROM feedback_records").fetchone()
    assert b"The prices" not in bytes(raw["payload"]) and raw["owner_key"] != "one"
    assert b"The prices" not in str(c.execute("SELECT * FROM feedback_audit").fetchall()).encode()


def test_both_positive_and_negative_themes_survive_without_cancelling_one_another(feedback_store):
    repo, _, _, _ = feedback_store
    submit_three(repo)
    assert FeedbackBot(repo, Model()).analyse("bot", "corepath")["theme_ids"]
    assert FeedbackBot(repo, Model(kind="praise", field="positive")).analyse("bot", "corepath")[
        "theme_ids"
    ]
    themes = repo.themes("founder", "corepath")
    assert {t["content"]["kind"] for t in themes} == {"concern", "praise"}
    assert all(t["state"] == "open" for t in themes)
    assert all(t["content"]["contributor_count"] == 3 for t in themes)
    assert all("Unverified" in t["content"]["finding_status"] for t in themes)


def test_many_submissions_by_one_person_do_not_make_a_recurring_theme(feedback_store):
    repo, _, _, _ = feedback_store
    for _ in range(3):
        repo.submit("one", "corepath", entry())
    assert FeedbackBot(repo, Model()).analyse("bot", "corepath")["theme_ids"] == []
    assert FeedbackBot(repo, Model(severity="urgent")).analyse("bot", "corepath")["theme_ids"]
    assert repo.themes("founder", "corepath")[0]["content"]["contributor_count"] == 1


def test_invented_citations_and_cross_target_evidence_cannot_raise_concerns(feedback_store):
    repo, _, _, _ = feedback_store
    submit_three(repo)
    snapshot = repo.snapshot("bot", "corepath")
    proposed = analysis(snapshot)
    proposed.themes[0].citations[0].quote = "Invented text that no customer supplied"
    with pytest.raises(Conflict, match="exact"):
        repo.save_themes("bot", "corepath", snapshot, proposed)
    proposed = analysis(snapshot)
    proposed.themes[0].citations[0].record_id = uuid4()
    with pytest.raises(Conflict):
        repo.save_themes("bot", "corepath", snapshot, proposed)
    assert repo.themes("founder", "corepath") == []


def test_feedback_targets_are_separate_and_the_bot_cannot_register_or_moderate_them(feedback_store):
    repo, _, _, _ = feedback_store
    target = repo.register_target("founder", "business:" + str(uuid4()))["target"]
    submit_three(repo, target)
    assert repo.snapshot("bot", "corepath") == []
    assert FeedbackBot(repo, Model()).analyse("bot", target)["theme_ids"]
    with pytest.raises(Denied):
        repo.register_target("bot", "business:" + str(uuid4()))
    theme_id = UUID(repo.themes("founder", target)[0]["id"])
    with pytest.raises(Denied):
        repo.resolve(
            "bot",
            theme_id,
            Resolution(
                state="resolved", reason="A bot cannot decide that this concern is resolved"
            ),
        )
    with pytest.raises(Denied):
        repo.staff_records("bot", target)
    with pytest.raises(Denied):
        repo.themes("one", target)


def test_withdrawal_removes_source_text_and_retracts_all_dependent_themes(feedback_store):
    repo, c, _, _ = feedback_store
    saved = submit_three(repo)
    FeedbackBot(repo, Model()).analyse("bot", "corepath")
    repo.change("one", UUID(saved[0]), delete=True)
    row = c.execute(
        "SELECT payload,active FROM feedback_records WHERE id=%s", (saved[0],)
    ).fetchone()
    assert row["payload"] is None and not row["active"]
    assert all(
        t["state"] == "retracted" and t["content"] is None
        for t in repo.themes("founder", "corepath")
    )
    assert repo.own("one") == []
    with pytest.raises(Missing):
        repo.change("two", UUID(saved[0]), delete=True)


def test_consent_change_during_analysis_blocks_late_results(feedback_store):
    repo, _, _, _ = feedback_store
    saved = submit_three(repo)
    model = Model(effect=lambda: repo.change("one", UUID(saved[0]), allow=False))
    with pytest.raises(Conflict, match="changed"):
        FeedbackBot(repo, model).analyse("bot", "corepath")
    assert repo.themes("founder", "corepath") == []
    assert not repo.own("one")[0]["allow_ai_analysis"]
    assert repo.own("one")[0]["content"]["allow_ai_analysis"] is False


def test_retry_references_never_restore_deleted_feedback_or_changed_consent(feedback_store):
    repo, _, _, _ = feedback_store
    data = entry()
    first = repo.submit("one", "corepath", data)
    assert repo.submit("one", "corepath", data) == first
    with pytest.raises(Conflict, match="different"):
        repo.submit("one", "corepath", data.model_copy(update={"positive": "Changed text"}))
    repo.change("one", UUID(first["id"]), delete=True)
    with pytest.raises(Conflict, match="withdrawn"):
        repo.submit("one", "corepath", data)


def review(**changes):
    now = datetime.now(UTC)
    values = {
        "source_url": "https://licensed.example.test/review",
        "source_reference": str(uuid4()),
        "contributor_reference": "external-reviewer-one",
        "text": "The prices were unclear.",
        "rights_and_analysis_basis_reviewed": True,
        "permission_notes": "Synthetic permission and analysis basis reviewed for this test",
        "reviewed_at": now - timedelta(hours=1),
        "published_at": now - timedelta(days=1),
    }
    values.update(changes)
    return ImportedReview(**values)


def test_public_reviews_need_reviewed_permissions_and_preserve_original_age(feedback_store):
    repo, _, _, _ = feedback_store
    item = review()
    saved = repo.import_review("founder", "corepath", item)
    assert repo.snapshot("bot", "corepath")[0]["source_kind"] == "public_review"
    assert repo.snapshot("bot", "corepath")[0]["reported_at"] == item.published_at
    with pytest.raises(Conflict):
        repo.import_review("founder", "corepath", item)
    with pytest.raises(Denied):
        repo.import_review("bot", "corepath", review())
    with pytest.raises(ValidationError):
        review(rights_and_analysis_basis_reviewed=False)
    repo.change("founder", UUID(saved["id"]), delete=True, moderate=True)
    repo.import_review(
        "founder", "corepath", review(published_at=datetime.now(UTC) - timedelta(days=400))
    )
    assert repo.snapshot("bot", "corepath") == []


def test_distinct_concern_topics_are_not_lost_as_duplicate_batches(feedback_store):
    repo, _, _, _ = feedback_store
    submit_three(repo)
    snapshot = repo.snapshot("bot", "corepath")
    assert repo.save_themes("bot", "corepath", snapshot, analysis(snapshot, category="pricing"))[
        "theme_ids"
    ]
    assert repo.save_themes("bot", "corepath", snapshot, analysis(snapshot, category="privacy"))[
        "theme_ids"
    ]
    assert not repo.save_themes(
        "bot", "corepath", snapshot, analysis(snapshot, category="privacy")
    )["theme_ids"]


def test_staff_resolution_is_auditable_and_cannot_restore_retracted_text(feedback_store):
    repo, _, _, _ = feedback_store
    saved = submit_three(repo)
    FeedbackBot(repo, Model()).analyse("bot", "corepath")
    theme = repo.themes("founder", "corepath")[0]
    assert (
        repo.resolve(
            "founder",
            UUID(theme["id"]),
            Resolution(
                state="investigating", reason="A human is checking the reported pricing information"
            ),
        )["state"]
        == "investigating"
    )
    repo.change("one", UUID(saved[0]), allow=False)
    with pytest.raises(Conflict, match="Retracted"):
        repo.resolve(
            "founder",
            UUID(theme["id"]),
            Resolution(
                state="resolved", reason="A late resolution must not restore withdrawn quotes"
            ),
        )


def test_analysis_database_role_cannot_read_unconsented_raw_feedback_or_change_ratings(
    feedback_store,
):
    repo, c, schema, cfg = feedback_store
    submit_three(repo)
    repo.submit(
        "one",
        "corepath",
        entry(allow_ai_analysis=False, negative="Private feedback not approved for AI analysis"),
    )
    api_role = "feedback_api_" + uuid4().hex
    analysis_role = "feedback_analysis_" + uuid4().hex
    for role in (api_role, analysis_role):
        c.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
    try:
        c.execute("CREATE TABLE partner_rating_canary(rating int)")
        script = (
            (ROOT / "feedback/database/runtime-grants.sql")
            .read_text()
            .replace(':"feedback_api_role"', sql.Identifier(api_role).as_string(c))
            .replace(':"feedback_analysis_role"', sql.Identifier(analysis_role).as_string(c))
            .replace("SCHEMA public", "SCHEMA " + sql.Identifier(schema).as_string(c))
        )
        c.execute(script)
        for query in [
            "SELECT * FROM feedback_records",
            "UPDATE feedback_records SET ai_allowed=true",
            "UPDATE feedback_actors SET role='founder'",
            "UPDATE partner_rating_canary SET rating=100",
            "DELETE FROM feedback_audit",
        ]:
            with c.transaction():
                c.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(analysis_role)))
                with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
                    c.execute(query)
        dsn = os.getenv("FEEDBACK_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
        with ConnectionPool(
            dsn,
            min_size=1,
            max_size=2,
            kwargs={
                "options": f"-c search_path={schema} -c role={analysis_role}",
                "client_encoding": "UTF8",
            },
        ) as pool:
            restricted = Repository(pool, cfg)
            snapshot = restricted.snapshot("bot", "corepath")
            assert len(snapshot) == 3
            assert all("not approved" not in r["content"]["negative"] for r in snapshot)
            assert FeedbackBot(restricted, Model()).analyse("bot", "corepath")["theme_ids"]
    finally:
        for role in (analysis_role, api_role):
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_global_prompt_cooldown_prevents_cross_business_nagging(feedback_store):
    repo, _, _, _ = feedback_store
    target = repo.register_target("founder", "business:" + str(uuid4()))["target"]
    assert repo.prompt("one", "corepath")["show_prompt"]
    assert not repo.prompt("one", target)["show_prompt"]


@pytest.fixture
def feedback_api(feedback_store, monkeypatch):
    import time

    import jwt
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from fastapi.testclient import TestClient

    import feedback.main as api

    repo, _, _, cfg = feedback_store
    key = Ed25519PrivateKey.generate()
    cfg.gateway_public_key = (
        key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    )
    monkeypatch.setattr(api, "get_settings", lambda: cfg)
    api.app.dependency_overrides[api.repository] = lambda: repo

    def token(scope="feedback.own", subject="one", **changes):
        now = int(time.time())
        claims = {
            "sub": subject,
            "actor": "feedback_gateway",
            "domain": "*",
            "scope": [scope],
            "purpose": "feedback_quality",
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
            yield client, token
    finally:
        api.app.dependency_overrides.clear()


def test_feedback_api_enforces_owner_roles_and_separate_service_purpose(feedback_api):
    client, token = feedback_api
    assert client.get("/v1/own-feedback").status_code == 401
    saved = client.post(
        "/v1/targets/corepath/feedback",
        headers=token("feedback.submit"),
        json={"positive": "A useful place to connect."},
    ).json()
    assert client.get("/v1/own-feedback", headers=token()).json()[0]["id"] == saved["id"]
    assert client.get("/v1/own-feedback", headers=token(subject="two")).json() == []
    assert (
        client.delete("/v1/own-feedback/" + saved["id"], headers=token(subject="two")).status_code
        == 404
    )
    assert (
        client.get(
            "/v1/targets/corepath/records", headers=token("feedback.read", role="founder")
        ).status_code
        == 403
    )
    assert client.get("/v1/own-feedback", headers=token(purpose="life_profile")).status_code == 403
    assert (
        client.post(
            "/v1/targets/corepath/feedback",
            headers=token("feedback.submit"),
            json={"positive": "Hi", "owner": "two"},
        ).status_code
        == 422
    )
    assert client.post("/v1/targets/corepath/prompt", headers=token("feedback.prompt")).json()[
        "show_prompt"
    ]
    assert (
        client.put(
            "/v1/prompt-preference", headers=token(), json={"allow_requests": False}
        ).status_code
        == 200
    )
    assert not client.post("/v1/targets/corepath/prompt", headers=token("feedback.prompt")).json()[
        "show_prompt"
    ]


def test_model_request_uses_only_authorised_feedback_and_strict_citations(feedback_store):
    import json

    import httpx

    from feedback.bot import Provider

    repo, _, _, cfg = feedback_store
    submit_three(repo)
    repo.submit(
        "one", "corepath", entry(allow_ai_analysis=False, negative="PRIVATE UNCONSENTED CANARY")
    )
    snapshot = repo.snapshot("bot", "corepath")
    cfg.openai_api_key = "synthetic-model-key"
    cfg.model = "synthetic-model"
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        from bot_standards import STANDARD

        assert STANDARD in requests[-1]["input"][0]["content"]
        assert "Do not send messages or decide sanctions" in requests[-1]["input"][0]["content"]
        assert "tools" not in requests[-1]
        draft = analysis(snapshot).model_dump_json()
        return httpx.Response(
            200, json={"output": [{"content": [{"type": "output_text", "text": draft}]}]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = Provider(cfg, client).analyse(snapshot)
    assert result.themes and requests[0]["store"] is False
    assert "PRIVATE UNCONSENTED CANARY" not in json.dumps(requests)
    assert "reported_at" in requests[0]["input"][1]["content"]


def test_ciphertext_cannot_be_swapped_between_owners_or_opened_with_a_wrong_key(feedback_store):
    from cryptography.fernet import InvalidToken

    repo, c, _, cfg = feedback_store
    first = repo.submit("one", "corepath", entry())
    second = repo.submit("two", "corepath", entry(positive="Another owner private text"))
    original = c.execute(
        "SELECT payload FROM feedback_records WHERE id=%s", (first["id"],)
    ).fetchone()["payload"]
    c.execute("UPDATE feedback_records SET payload=%s WHERE id=%s", (original, second["id"]))
    with pytest.raises(InvalidToken):
        repo.own("two")
    wrong = cfg.model_copy(update={"encryption_key": Fernet.generate_key().decode()})
    with pytest.raises(InvalidToken):
        Repository(repo.pool, wrong).own("one")


def test_consent_metadata_tampering_cannot_release_private_feedback_to_a_model(feedback_store):
    from cryptography.fernet import InvalidToken

    repo, c, _, _ = feedback_store
    saved = repo.submit("one", "corepath", entry(allow_ai_analysis=False))
    c.execute("UPDATE feedback_records SET ai_allowed=true WHERE id=%s", (saved["id"],))
    with pytest.raises(InvalidToken):
        repo.snapshot("bot", "corepath")
