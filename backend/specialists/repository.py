import hashlib
import json
import time
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from specialists.models import Access, AccessDenied, BudgetExceeded, Capability, RunConflict, Task
from specialists.registry import Domain, Specialist
from specialists.settings import Settings

EVIDENCE_SQL = """
    SELECT sec.id AS section_id, sec.content_text, sec.heading, sec.section_number,
           sec.locator, sec.page_start, sec.page_end,
           doc.id AS document_id, doc.document_title, doc.retrieved_at,
           src.id AS source_id, src.title, src.authors, src.canonical_url, src.publication_date
    FROM document_sections sec
    JOIN knowledge_documents doc ON doc.id = sec.document_id
    JOIN knowledge_sources src ON src.id = doc.source_id
    JOIN source_library_links link ON link.source_id = src.id AND link.library_id = doc.library_id
    WHERE doc.library_id = %s
      AND src.source_status = 'active' AND src.verification_status = 'verified'
      AND doc.extraction_status = 'completed'
      AND doc.document_metadata->'model_use_allowed' = 'true'::jsonb
"""


def section_payload(row: dict) -> dict:
    data = {
        "section_id": str(row["section_id"]),
        "source_id": str(row["source_id"]),
        "document_id": str(row["document_id"]),
        "title": row["title"][:400],
        "document_title": row["document_title"][:400],
        "authors": [author[:200] for author in row["authors"][:10]],
        "canonical_url": row["canonical_url"]
        if row["canonical_url"] and len(row["canonical_url"]) <= 2000
        else None,
        "publication_date": row["publication_date"].isoformat()
        if row["publication_date"]
        else None,
        "retrieved_at": row["retrieved_at"].isoformat() if row["retrieved_at"] else None,
        "locator": row["locator"][:400] if row["locator"] else f"section:{row['section_number']}",
        "page_start": row["page_start"],
        "page_end": row["page_end"],
        "content": row["content_text"][:2000],
        "source_verification": "verified",
        "claim_assessment": "not_assessed_by_this_runtime",
    }
    data["fingerprint"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return data


class Repository:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def _identity(self, conn, capability: Capability):
        if capability.expires_at <= time.time():
            raise AccessDenied("The service capability expired.")
        identity = (
            conn.cursor(row_factory=dict_row)
            .execute(
                "SELECT * FROM service_identities WHERE service_key = %s AND is_active = TRUE",
                (capability.subject,),
            )
            .fetchone()
        )
        expected = {"coordinator_ai": "coordinator", "specialist_ai": "specialist"}.get(
            capability.actor
        )
        if identity is None or identity["service_role"] != expected:
            raise AccessDenied("The service identity is inactive or its role does not match.")
        return identity

    def _authorise(self, conn, capability: Capability, domain: Domain) -> Access:
        if capability.domain != domain.value:
            raise AccessDenied("The capability names another specialist.")
        identity = self._identity(conn, capability)
        library = (
            conn.cursor(row_factory=dict_row)
            .execute(
                """SELECT d.id AS domain_id, l.id AS library_id, d.is_active, l.status
               FROM specialist_domains d JOIN knowledge_libraries l ON l.domain_id = d.id
               WHERE d.slug = %s""",
                (domain.value,),
            )
            .fetchone()
        )
        if library is None or not library["is_active"] or library["status"] != "active":
            raise AccessDenied("The specialist library has not been activated.")
        if (
            identity["service_role"] == "specialist"
            and identity["domain_id"] != library["domain_id"]
        ):
            raise AccessDenied("The specialist identity belongs to another discipline.")
        for action in ("research", "retrieve"):
            grant = conn.execute(
                """SELECT 1 FROM access_permissions
                   WHERE service_identity_id = %s AND action = %s
                     AND (library_id = %s OR library_id IS NULL)
                     AND (expires_at IS NULL OR expires_at > now()) LIMIT 1""",
                (identity["id"], action, library["library_id"]),
            ).fetchone()
            if grant is None:
                raise AccessDenied("The required research/retrieval grant is missing or expired.")
        return Access(
            identity["id"], library["domain_id"], library["library_id"], identity["service_key"]
        )

    def catalogue(self, capability: Capability) -> dict[str, str]:
        with self.pool.connection() as conn:
            identity = self._identity(conn, capability)
            if identity["service_role"] != "coordinator" or capability.domain != "*":
                raise AccessDenied("Only the Coordinator may inspect the specialist network.")
            return dict(
                conn.execute(
                    """SELECT d.slug, l.status FROM specialist_domains d
                   JOIN knowledge_libraries l ON l.domain_id = d.id"""
                ).fetchall()
            )

    def _audit(self, conn, access: Access, run_id: UUID, action: str, outcome: str):
        conn.execute(
            """INSERT INTO audit_events
               (actor_identity_id, actor_label, action, target_type, target_id, purpose, outcome)
               VALUES (%s, %s, %s, 'specialist_run', %s, 'Scoped general-knowledge research', %s)""",
            (access.identity_id, access.service_key, action, run_id, outcome),
        )

    def start(self, capability: Capability, specialist: Specialist, task: Task, settings: Settings):
        with self.pool.connection() as conn:
            # Serialise budget checks across processes without granting write
            # authority over the service identity or permission tables.
            conn.execute("SET LOCAL lock_timeout = '5s'")
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (capability.subject,)
            )
            access = self._authorise(conn, capability, specialist.domain)
            if conn.execute(
                "SELECT 1 FROM specialist_runs WHERE requester_id = %s AND request_id = %s",
                (access.identity_id, capability.request_id),
            ).fetchone():
                raise RunConflict("This capability request was already used.")
            conn.execute(
                """UPDATE specialist_runs SET state = 'failed', error_code = 'execution_lease_expired',
                   completed_at = now() WHERE requester_id = %s AND state = 'running'
                   AND lease_expires_at <= now()""",
                (access.identity_id,),
            )
            recent, running = conn.execute(
                """SELECT count(*), count(*) FILTER (WHERE state = 'running')
                   FROM specialist_runs WHERE requester_id = %s AND created_at > now() - interval '24 hours'""",
                (access.identity_id,),
            ).fetchone()
            if recent >= settings.max_runs_per_24h or running >= settings.max_concurrent_runs:
                raise BudgetExceeded
            digest = hashlib.sha256(task.model_dump_json().encode()).hexdigest()
            run_id = conn.execute(
                """INSERT INTO specialist_runs
                   (requester_id, request_id, domain_id, library_id, run_kind, input_hash, policy_hash, model_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    access.identity_id,
                    capability.request_id,
                    access.domain_id,
                    access.library_id,
                    "coordinator_task"
                    if capability.actor == "coordinator_ai"
                    else "independent_research",
                    digest,
                    specialist.policy_hash,
                    settings.model_for(specialist.domain),
                ),
            ).fetchone()[0]
            self._audit(conn, access, run_id, "specialist.run.start", "allowed")
            return run_id, access

    def retrieve(
        self, capability: Capability, domain: Domain, task: Task, settings: Settings
    ) -> list[dict]:
        with self.pool.connection() as conn:
            access = self._authorise(conn, capability, domain)
            search = " OR ".join('"' + term.replace('"', " ") + '"' for term in task.search_terms)
            rows = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    EVIDENCE_SQL
                    + """
                AND to_tsvector('english', coalesce(sec.heading, '') || ' ' || sec.content_text)
                    @@ websearch_to_tsquery('english', %s)
                ORDER BY ts_rank_cd(to_tsvector('english', coalesce(sec.heading, '') || ' ' || sec.content_text),
                    websearch_to_tsquery('english', %s)) DESC, sec.id
                LIMIT %s
                """,
                    (
                        access.library_id,
                        search,
                        search,
                        min(task.max_sources, settings.max_sources),
                    ),
                )
                .fetchall()
            )
            return [section_payload(row) for row in rows]

    def finish(
        self,
        capability: Capability,
        domain: Domain,
        run_id: UUID,
        result: dict,
        sections: list[dict],
        state: str,
    ):
        with self.pool.connection() as conn:
            access = self._authorise(conn, capability, domain)
            if sections:
                rows = (
                    conn.cursor(row_factory=dict_row)
                    .execute(
                        EVIDENCE_SQL + " AND sec.id = ANY(%s)",
                        (access.library_id, [UUID(s["section_id"]) for s in sections]),
                    )
                    .fetchall()
                )
                current = {
                    str(row["section_id"]): section_payload(row)["fingerprint"] for row in rows
                }
                if any(current.get(s["section_id"]) != s["fingerprint"] for s in sections):
                    raise RunConflict("Evidence was changed, withdrawn or no longer permitted.")
            updated = conn.execute(
                """UPDATE specialist_runs SET state = %s, result = %s, completed_at = now()
                   WHERE id = %s AND requester_id = %s AND domain_id = %s AND state = 'running'
                     AND lease_expires_at > now() RETURNING id""",
                (state, Jsonb(result), run_id, access.identity_id, access.domain_id),
            ).fetchone()
            if updated is None:
                raise RunConflict("This run is no longer active.")
            self._audit(conn, access, run_id, "specialist.run." + state, "succeeded")

    def fail(self, access: Access, run_id: UUID, error_code: str):
        with self.pool.connection() as conn:
            updated = conn.execute(
                """UPDATE specialist_runs SET state = 'failed', error_code = %s, completed_at = now()
                   WHERE id = %s AND requester_id = %s AND state = 'running' RETURNING id""",
                (error_code, run_id, access.identity_id),
            ).fetchone()
            if updated:
                self._audit(conn, access, run_id, "specialist.run.failed", "failed")

    def read_run(self, capability: Capability, domain: Domain, run_id: UUID) -> dict | None:
        with self.pool.connection() as conn:
            access = self._authorise(conn, capability, domain)
            row = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    """SELECT id, state, result, error_code, policy_hash, model_id, created_at, completed_at
                   FROM specialist_runs WHERE id = %s AND requester_id = %s AND domain_id = %s""",
                    (run_id, access.identity_id, access.domain_id),
                )
                .fetchone()
            )
            return dict(row) if row else None
