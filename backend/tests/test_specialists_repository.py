import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from test_specialists_runtime import proposal_for

from app.migrations import DEFAULT_DIRECTORY, load_migrations, migrate
from specialists.models import (
    AccessDenied,
    BudgetExceeded,
    Capability,
    InvalidEvidence,
    ProviderUnavailable,
    RunConflict,
    Task,
)
from specialists.registry import SPECIALISTS, Domain
from specialists.repository import Repository
from specialists.runtime import Runtime
from specialists.settings import Settings

TASK = Task(question="Investigate evidence limitations", search_terms=["evidence"])


@pytest.fixture
def specialist_store():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("requires a configured PostgreSQL service")
    schema = "specialists_test_" + uuid4().hex
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        pool = None
        try:
            conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            migrate(conn, load_migrations(DEFAULT_DIRECTORY))
            conn.execute("UPDATE knowledge_libraries SET status = 'active'")
            coordinator = conn.execute(
                "INSERT INTO service_identities (service_key, display_name, service_role) VALUES ('synthetic-coordinator', 'Synthetic Coordinator', 'coordinator') RETURNING id"
            ).fetchone()[0]
            for action in ("research", "retrieve"):
                conn.execute(
                    "INSERT INTO access_permissions (service_identity_id, action, granted_by) VALUES (%s, %s, 'synthetic-test')",
                    (coordinator, action),
                )
            libraries = dict(
                conn.execute(
                    "SELECT d.slug, l.id FROM specialist_domains d JOIN knowledge_libraries l ON l.domain_id = d.id"
                ).fetchall()
            )
            for domain in Domain:
                identity = conn.execute(
                    "INSERT INTO service_identities (service_key, display_name, service_role, domain_id) SELECT %s, %s, 'specialist', id FROM specialist_domains WHERE slug = %s RETURNING id",
                    ("synthetic-" + domain.value, domain.value, domain.value),
                ).fetchone()[0]
                for action in ("research", "retrieve"):
                    conn.execute(
                        "INSERT INTO access_permissions (service_identity_id, library_id, action, granted_by) VALUES (%s, %s, %s, 'synthetic-test')",
                        (identity, libraries[domain.value], action),
                    )
            pool = ConnectionPool(
                database_url,
                min_size=1,
                max_size=5,
                open=True,
                kwargs={
                    "autocommit": False,
                    "options": f"-c search_path={schema} -c statement_timeout=5000",
                },
            )
            pool.wait(timeout=10)
            yield Repository(pool), libraries, conn
        finally:
            if pool:
                pool.close()
            conn.execute("SET search_path TO public")
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def capability(domain=Domain.NUTRITION, *, independent=False):
    return Capability(
        "synthetic-" + domain.value if independent else "synthetic-coordinator",
        "specialist_ai" if independent else "coordinator_ai",
        domain.value,
        str(uuid4()),
        int(time.time()) + 120,
    )


def evidence(
    conn, library, *, verified=True, approved=True, extracted=True, active=True, linked=True
):
    source = conn.execute(
        "INSERT INTO knowledge_sources (source_type, title, authors, canonical_url, source_status, verification_status) VALUES ('report', 'Synthetic evidence source', ARRAY['Synthetic Author'], 'https://example.org/evidence', %s, %s) RETURNING id",
        ("active" if active else "withdrawn", "verified" if verified else "unverified"),
    ).fetchone()[0]
    if linked:
        conn.execute(
            "INSERT INTO source_library_links (source_id, library_id) VALUES (%s, %s)",
            (source, library),
        )
    document = conn.execute(
        "INSERT INTO knowledge_documents (source_id, library_id, document_title, extraction_status, document_metadata) VALUES (%s, %s, 'Synthetic extracted document', %s, %s) RETURNING id",
        (
            source,
            library,
            "completed" if extracted else "pending",
            Jsonb({"model_use_allowed": approved}),
        ),
    ).fetchone()[0]
    section = conn.execute(
        "INSERT INTO document_sections (document_id, section_number, content_text, locator) VALUES (%s, 0, 'Evidence for this synthetic test is limited.', 'p. 2') RETURNING id",
        (document,),
    ).fetchone()[0]
    return source, document, section


class EvidenceProvider:
    def __init__(self, effect=None):
        self.calls = []
        self.effect = effect

    def propose(self, specialist, context):
        self.calls.append((specialist, context))
        if self.effect:
            self.effect(context)
        return proposal_for(context["library_excerpts"][0])


@pytest.mark.parametrize("domain", list(Domain))
def test_all_eleven_specialists_execute_and_store_drafts_in_their_own_library(
    specialist_store, domain
):
    repo, libraries, conn = specialist_store
    _, _, section = evidence(conn, libraries[domain.value])
    provider = EvidenceProvider()
    cap = capability(domain)
    result = Runtime(repo, provider, Settings()).execute(cap, domain, TASK)
    assert result["state"] == "completed" and result["review_required"]
    assert result["findings"][0]["citations"][0]["section_id"] == str(section)
    assert len(provider.calls) == 1
    saved = repo.read_run(cap, domain, UUID(result["run_id"]))
    assert saved["result"]["specialist"] == domain.value
    assert conn.execute("SELECT count(*) FROM research_findings").fetchone()[0] == 0
    assert TASK.question not in str(
        conn.execute("SELECT row_to_json(r) FROM specialist_runs r").fetchall()
    )
    assert TASK.question not in str(
        conn.execute("SELECT row_to_json(a) FROM audit_events a").fetchall()
    )


def test_no_evidence_records_a_gap_without_a_model_call(specialist_store):
    repo, _, _ = specialist_store
    provider = EvidenceProvider()
    result = Runtime(repo, provider, Settings()).execute(capability(), Domain.NUTRITION, TASK)
    assert result["state"] == "needs_evidence" and result["findings"] == []
    assert result["knowledge_gaps"] and provider.calls == []


def test_retrieval_requires_own_verified_active_approved_extracted_and_linked_material(
    specialist_store,
):
    repo, libraries, conn = specialist_store
    library = libraries[Domain.NUTRITION.value]
    good = evidence(conn, library)[2]
    for flags in (
        {"verified": False},
        {"active": False},
        {"approved": False},
        {"extracted": False},
        {"linked": False},
    ):
        evidence(conn, library, **flags)
    _, string_approval, _ = evidence(conn, library)
    conn.execute(
        "UPDATE knowledge_documents SET document_metadata = %s WHERE id = %s",
        (Jsonb({"model_use_allowed": "true"}), string_approval),
    )
    other = evidence(conn, libraries[Domain.PHYSICAL.value])
    # A source linked to both libraries still cannot expose another library's document.
    conn.execute(
        "INSERT INTO source_library_links (source_id, library_id) VALUES (%s, %s)",
        (other[0], library),
    )
    sections = repo.retrieve(capability(), Domain.NUTRITION, TASK, Settings())
    assert [s["section_id"] for s in sections] == [str(good)]
    assert sections[0]["claim_assessment"] == "not_assessed_by_this_runtime"


@pytest.mark.parametrize(
    "change", ["inactive", "role", "planned", "no_retrieve", "expired_research", "expired_token"]
)
def test_db_authorisation_is_checked_independently_of_signed_capability(specialist_store, change):
    repo, _, conn = specialist_store
    cap = capability()
    if change == "inactive":
        conn.execute(
            "UPDATE service_identities SET is_active = FALSE WHERE service_key = %s", (cap.subject,)
        )
    elif change == "role":
        conn.execute(
            "UPDATE service_identities SET service_role = 'api_service' WHERE service_key = %s",
            (cap.subject,),
        )
    elif change == "planned":
        conn.execute("UPDATE knowledge_libraries SET status = 'planned'")
    elif change == "no_retrieve":
        conn.execute("DELETE FROM access_permissions WHERE action = 'retrieve'")
    elif change == "expired_research":
        conn.execute(
            "UPDATE access_permissions SET granted_at = now() - interval '2 hours', expires_at = now() - interval '1 hour' WHERE action = 'research'"
        )
    else:
        cap = replace(cap, expires_at=1)
    with pytest.raises(AccessDenied):
        repo.start(cap, SPECIALISTS[Domain.NUTRITION], TASK, Settings())
    assert conn.execute("SELECT count(*) FROM specialist_runs").fetchone()[0] == 0


def test_independent_specialist_cannot_retrieve_a_peer_library_even_with_global_grants(
    specialist_store,
):
    repo, _, conn = specialist_store
    cap = capability(independent=True)
    assert repo.retrieve(cap, Domain.NUTRITION, TASK, Settings()) == []
    conn.execute("UPDATE access_permissions SET library_id = NULL")
    with pytest.raises(AccessDenied):
        repo.retrieve(replace(cap, domain=Domain.PHYSICAL.value), Domain.PHYSICAL, TASK, Settings())
    with pytest.raises(AccessDenied):
        repo.catalogue(replace(cap, domain="*"))


def test_replays_daily_limits_and_atomic_concurrent_limits_precede_model_calls(specialist_store):
    repo, _, conn = specialist_store
    cap = capability()
    first, access = repo.start(
        cap, SPECIALISTS[Domain.NUTRITION], TASK, Settings(max_concurrent_runs=1)
    )
    with pytest.raises(RunConflict):
        repo.start(cap, SPECIALISTS[Domain.NUTRITION], TASK, Settings())
    with pytest.raises(BudgetExceeded):
        repo.start(
            capability(), SPECIALISTS[Domain.NUTRITION], TASK, Settings(max_concurrent_runs=1)
        )
    repo.fail(access, first, "synthetic_finished")
    with pytest.raises(BudgetExceeded):
        repo.start(capability(), SPECIALISTS[Domain.NUTRITION], TASK, Settings(max_runs_per_24h=1))
    conn.execute("DELETE FROM audit_events")
    conn.execute("DELETE FROM specialist_runs")

    def simultaneous_start(_):
        try:
            repo.start(
                capability(), SPECIALISTS[Domain.NUTRITION], TASK, Settings(max_concurrent_runs=1)
            )
            return "started"
        except BudgetExceeded:
            return "limited"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(simultaneous_start, range(2))) == ["limited", "started"]


def test_expired_leases_release_concurrency_and_result_reads_are_requester_scoped(specialist_store):
    repo, _, conn = specialist_store
    cap = capability()
    first, _ = repo.start(cap, SPECIALISTS[Domain.NUTRITION], TASK, Settings())
    conn.execute("UPDATE specialist_runs SET lease_expires_at = now() - interval '1 second'")
    repo.start(capability(), SPECIALISTS[Domain.NUTRITION], TASK, Settings(max_concurrent_runs=1))
    assert repo.read_run(cap, Domain.NUTRITION, first)["error_code"] == "execution_lease_expired"
    assert repo.read_run(capability(independent=True), Domain.NUTRITION, first) is None
    assert repo.read_run(capability(Domain.PHYSICAL), Domain.PHYSICAL, first) is None


@pytest.mark.parametrize("change", ["revoke", "withdraw", "remove_approval", "edit_text"])
def test_revocation_or_changed_evidence_during_inference_cannot_save_a_result(
    specialist_store, change
):
    repo, libraries, conn = specialist_store
    source, document, section = evidence(conn, libraries[Domain.NUTRITION.value])

    def mutate(_context):
        if change == "revoke":
            conn.execute("DELETE FROM access_permissions WHERE action = 'retrieve'")
        elif change == "withdraw":
            conn.execute(
                "UPDATE knowledge_sources SET source_status = 'withdrawn' WHERE id = %s", (source,)
            )
        elif change == "remove_approval":
            conn.execute(
                "UPDATE knowledge_documents SET document_metadata = '{}' WHERE id = %s", (document,)
            )
        else:
            conn.execute(
                "UPDATE document_sections SET content_text = 'Changed evidence' WHERE id = %s",
                (section,),
            )

    with pytest.raises((AccessDenied, RunConflict)):
        Runtime(repo, EvidenceProvider(mutate), Settings()).execute(
            capability(), Domain.NUTRITION, TASK
        )
    state, result, error = conn.execute(
        "SELECT state, result, error_code FROM specialist_runs"
    ).fetchone()
    assert (state, result, error) == ("failed", None, "scope_or_evidence_changed")


@pytest.mark.parametrize(
    "error,code",
    [(ProviderUnavailable, "model_unavailable"), (InvalidEvidence, "invalid_evidence")],
)
def test_provider_failures_are_audited_without_accepting_findings(specialist_store, error, code):
    repo, libraries, conn = specialist_store
    evidence(conn, libraries[Domain.NUTRITION.value])

    def fail(_context):
        raise error("synthetic-private-upstream-detail")

    with pytest.raises(error):
        Runtime(repo, EvidenceProvider(fail), Settings()).execute(
            capability(), Domain.NUTRITION, TASK
        )
    state, result, stored_error = conn.execute(
        "SELECT state, result, error_code FROM specialist_runs"
    ).fetchone()
    assert (state, result, stored_error) == ("failed", None, code)
    assert "synthetic-private-upstream-detail" not in str(
        conn.execute("SELECT row_to_json(a) FROM audit_events a").fetchall()
    )


def test_restricted_runtime_role_can_research_but_cannot_edit_sources_grants_or_profiles(
    specialist_store,
):
    repo, libraries, conn = specialist_store
    evidence(conn, libraries[Domain.NUTRITION.value])
    schema = conn.execute("SELECT current_schema()").fetchone()[0]
    role = "specialist_role_test_" + uuid4().hex
    template = (
        Path(__file__).resolve().parents[2] / "specialists/database/runtime-role.sql"
    ).read_text()
    # Both replacements are generated identifiers, never caller-controlled text.
    conn.execute(
        template.replace("corepath_specialist_runtime", role).replace(
            "SCHEMA public", "SCHEMA " + schema
        )
    )
    restricted_pool = None

    def assume_role(connection):
        connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        connection.commit()

    try:
        # A profile-like table here proves default-denied SELECT even in the
        # unlikely event an operator co-locates private data in this schema.
        conn.execute("CREATE TABLE life_profiles (private_value TEXT)")
        restricted_pool = ConnectionPool(
            repo.pool.conninfo,
            min_size=1,
            max_size=2,
            open=True,
            kwargs={"options": f"-c search_path={schema}", "autocommit": False},
            configure=assume_role,
        )
        restricted_pool.wait(timeout=10)
        runtime = Runtime(Repository(restricted_pool), EvidenceProvider(), Settings())
        result = runtime.execute(capability(), Domain.NUTRITION, TASK)
        assert result["state"] == "completed"
        for forbidden in (
            "UPDATE knowledge_sources SET title = 'forbidden'",
            "DELETE FROM access_permissions",
            "SELECT * FROM life_profiles",
            "INSERT INTO research_findings (claim) VALUES ('forbidden')",
        ):
            with (
                pytest.raises(psycopg.errors.InsufficientPrivilege),
                restricted_pool.connection() as restricted,
            ):
                restricted.execute(forbidden)
    finally:
        if restricted_pool:
            restricted_pool.close()
        conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
