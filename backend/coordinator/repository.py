import hashlib
import time
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from coordinator.limits import MAX_SPECIALIST_CALLS
from coordinator.models import Assignment, ResearchRequest, SpecialistResult
from coordinator.policy import POLICY_HASH
from coordinator.settings import Settings
from specialists.models import AccessDenied, BudgetExceeded, Capability, RunConflict


def digest(value):
    return hashlib.sha256(value.model_dump_json().encode()).hexdigest()


class Repository:
    def __init__(self, pool):
        self.pool = pool

    def _authorise(self, conn, caller: Capability, settings: Settings):
        if (
            caller.actor != "personal_ai"
            or caller.domain != "*"
            or caller.expires_at <= time.time()
        ):
            raise AccessDenied
        requester = conn.execute(
            "SELECT id FROM service_identities WHERE service_key = %s AND service_role = 'personal_ai' AND is_active",
            (caller.subject,),
        ).fetchone()
        coordinator = conn.execute(
            "SELECT id FROM service_identities WHERE service_key = %s AND service_role = 'coordinator' AND is_active",
            (settings.service_subject,),
        ).fetchone()
        if not requester or not coordinator:
            raise AccessDenied
        if not conn.execute(
            "SELECT 1 FROM access_permissions WHERE service_identity_id = %s AND action = 'coordinate' AND library_id IS NULL AND (expires_at IS NULL OR expires_at > now()) LIMIT 1",
            (requester[0],),
        ).fetchone():
            raise AccessDenied
        return requester[0], coordinator[0]

    def _active(self, conn, caller, run_id, settings, *, lock=False):
        requester, coordinator = self._authorise(conn, caller, settings)
        row = (
            conn.cursor(row_factory=dict_row)
            .execute(
                "SELECT * FROM coordinator_runs WHERE id = %s AND requester_id = %s AND coordinator_id = %s AND state = 'running' AND lease_expires_at > clock_timestamp()"
                + (" FOR UPDATE" if lock else ""),
                (run_id, requester, coordinator),
            )
            .fetchone()
        )
        if not row:
            raise RunConflict
        # Enforce the current cap even for historical or unvalidated callers.
        row["max_calls"] = min(row["max_calls"], MAX_SPECIALIST_CALLS)
        return row

    def _audit(self, conn, caller, requester, run_id, action, outcome, metadata=None):
        conn.execute(
            "INSERT INTO audit_events (actor_identity_id, actor_label, action, target_type, target_id, purpose, outcome, event_metadata) VALUES (%s, %s, %s, 'coordinator_run', %s, 'Scoped general-knowledge orchestration', %s, %s)",
            (requester, caller.subject, action, run_id, outcome, Jsonb(metadata or {})),
        )

    def start(self, caller: Capability, request: ResearchRequest, settings: Settings):
        with self.pool.connection() as conn:
            conn.execute("SET LOCAL lock_timeout = '5s'")
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 1))", (caller.subject,))
            requester, coordinator = self._authorise(conn, caller, settings)
            if conn.execute(
                "SELECT 1 FROM coordinator_runs WHERE requester_id = %s AND request_id = %s",
                (requester, caller.request_id),
            ).fetchone():
                raise RunConflict
            expired = conn.execute(
                "UPDATE coordinator_runs SET state = 'failed', completed_at = now(), error_code = 'execution_lease_expired' WHERE requester_id = %s AND state = 'running' AND lease_expires_at <= now() RETURNING id",
                (requester,),
            ).fetchall()
            if expired:
                conn.execute(
                    "UPDATE coordinator_tasks SET state = 'failed', completed_at = now(), error_code = 'execution_lease_expired' WHERE run_id = ANY(%s) AND state = 'running'",
                    ([row[0] for row in expired],),
                )
            recent, running = conn.execute(
                "SELECT count(*), count(*) FILTER (WHERE state = 'running') FROM coordinator_runs WHERE requester_id = %s AND created_at > now() - interval '24 hours'",
                (requester,),
            ).fetchone()
            if recent >= settings.max_runs_per_24h or running >= settings.max_concurrent_runs:
                raise BudgetExceeded
            run_id = conn.execute(
                "INSERT INTO coordinator_runs (requester_id, coordinator_id, request_id, input_hash, policy_hash, model_id, allowed_domains, allow_collaboration, max_calls, lease_expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s)) RETURNING id",
                (
                    requester,
                    coordinator,
                    caller.request_id,
                    digest(request),
                    POLICY_HASH,
                    settings.model,
                    [d.value for d in request.allowed_domains],
                    request.allow_collaboration,
                    min(
                        MAX_SPECIALIST_CALLS,
                        request.max_specialist_calls,
                        settings.max_specialist_calls,
                        len(request.allowed_domains),
                    ),
                    min(caller.expires_at, time.time() + settings.max_duration_seconds),
                ),
            ).fetchone()[0]
            self._audit(conn, caller, requester, run_id, "coordinator.run.start", "allowed")
            return run_id

    def check(self, caller, run_id, settings):
        with self.pool.connection() as conn:
            return dict(self._active(conn, caller, run_id, settings))

    def save_plan(self, caller, run_id, plan, settings):
        with self.pool.connection() as conn:
            self._active(conn, caller, run_id, settings, lock=True)
            conn.execute(
                "UPDATE coordinator_runs SET plan = %s WHERE id = %s",
                (Jsonb(plan.model_dump(mode="json")), run_id),
            )

    def reserve(self, caller, run_id, assignment: Assignment, phase, settings):
        with self.pool.connection() as conn:
            row = self._active(conn, caller, run_id, settings, lock=True)
            if assignment.domain.value not in row["allowed_domains"] or (
                phase == "collaboration" and not row["allow_collaboration"]
            ):
                raise AccessDenied
            if row["calls_used"] >= min(row["max_calls"], MAX_SPECIALIST_CALLS):
                raise BudgetExceeded
            domain = conn.execute(
                "SELECT id FROM specialist_domains WHERE slug = %s AND is_active",
                (assignment.domain.value,),
            ).fetchone()
            if not domain:
                raise AccessDenied
            if conn.execute(
                "SELECT 1 FROM coordinator_tasks WHERE run_id = %s AND domain_id = %s",
                (run_id, domain[0]),
            ).fetchone():
                raise RunConflict
            task_id = uuid4()
            conn.execute(
                "INSERT INTO coordinator_tasks (id, run_id, domain_id, phase, task_hash, rationale) VALUES (%s, %s, %s, %s, %s, %s)",
                (task_id, run_id, domain[0], phase, digest(assignment.task), assignment.rationale),
            )
            conn.execute(
                "UPDATE coordinator_runs SET calls_used = calls_used + 1 WHERE id = %s", (run_id,)
            )
            self._audit(
                conn,
                caller,
                row["requester_id"],
                run_id,
                "coordinator.task.authorise",
                "allowed",
                {"task_id": str(task_id), "domain": assignment.domain.value, "phase": phase},
            )
            return task_id

    def task_done(self, caller, run_id, task_id, result: SpecialistResult, settings):
        with self.pool.connection() as conn:
            row = self._active(conn, caller, run_id, settings, lock=True)
            updated = conn.execute(
                "UPDATE coordinator_tasks SET state = %s, result = %s, specialist_run_id = %s, completed_at = now() WHERE id = %s AND run_id = %s AND state = 'running' AND domain_id = (SELECT id FROM specialist_domains WHERE slug = %s) RETURNING id",
                (
                    result.state,
                    Jsonb(result.model_dump(mode="json")),
                    result.run_id,
                    task_id,
                    run_id,
                    result.specialist.value,
                ),
            ).fetchone()
            if not updated:
                raise RunConflict
            self._audit(
                conn,
                caller,
                row["requester_id"],
                run_id,
                "coordinator.task.complete",
                "succeeded",
                {"task_id": str(task_id)},
            )

    def task_failed(self, run_id, task_id, code):
        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE coordinator_tasks SET state = 'failed', error_code = %s, completed_at = now() WHERE id = %s AND run_id = %s AND state = 'running'",
                (code, task_id, run_id),
            )

    def finish(self, caller, run_id, report, state, settings):
        with self.pool.connection() as conn:
            row = self._active(conn, caller, run_id, settings, lock=True)
            if conn.execute(
                "SELECT 1 FROM coordinator_tasks WHERE run_id = %s AND state = 'running' LIMIT 1",
                (run_id,),
            ).fetchone():
                raise RunConflict
            conn.execute(
                "UPDATE coordinator_runs SET state = %s, report = %s, completed_at = now() WHERE id = %s",
                (state, Jsonb(report), run_id),
            )
            self._audit(
                conn,
                caller,
                row["requester_id"],
                run_id,
                "coordinator.run." + state,
                "failed" if state == "failed" else "succeeded",
            )

    def fail(self, caller, run_id, code):
        with self.pool.connection() as conn:
            row = conn.execute(
                "UPDATE coordinator_runs SET state = 'failed', error_code = %s, completed_at = now() WHERE id = %s AND requester_id = (SELECT id FROM service_identities WHERE service_key = %s) AND state = 'running' RETURNING requester_id",
                (code, run_id, caller.subject),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE coordinator_tasks SET state = 'failed', error_code = 'execution_interrupted', completed_at = now() WHERE run_id = %s AND state = 'running'",
                    (run_id,),
                )
                self._audit(conn, caller, row[0], run_id, "coordinator.run.failed", "failed")

    def read(self, caller, run_id: UUID, settings):
        with self.pool.connection() as conn:
            requester, coordinator = self._authorise(conn, caller, settings)
            row = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    "SELECT id, state, plan, report, error_code, calls_used, max_calls, policy_hash, model_id, created_at, completed_at FROM coordinator_runs WHERE id = %s AND requester_id = %s AND coordinator_id = %s",
                    (run_id, requester, coordinator),
                )
                .fetchone()
            )
            if not row:
                return None
            tasks = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    "SELECT t.id, d.slug AS domain, t.phase, t.rationale, t.state, t.specialist_run_id, t.result, t.error_code FROM coordinator_tasks t JOIN specialist_domains d ON d.id = t.domain_id WHERE run_id = %s ORDER BY t.created_at, t.id",
                    (run_id,),
                )
                .fetchall()
            )
            return dict(row) | {"tasks": [dict(task) for task in tasks]}
