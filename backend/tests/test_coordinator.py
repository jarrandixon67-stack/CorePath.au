from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg_pool import ConnectionPool
from pydantic import ValidationError
from test_specialists_repository import EvidenceProvider, capability, evidence, specialist_store  # noqa: F401

from coordinator.models import Assignment, CollaborationPlan, Plan, ResearchRequest, Synthesis
from coordinator.repository import Repository
from coordinator.runtime import Runtime, evidence_inventory, grounded_synthesis
from coordinator.settings import Settings
from specialists.models import (
    AccessDenied,
    BudgetExceeded,
    InvalidEvidence,
    ProviderUnavailable,
    RunConflict,
)
from specialists.registry import Domain
from specialists.runtime import Runtime as SpecialistRuntime
from specialists.settings import Settings as SpecialistSettings


def assignment(domain):
    return Assignment.model_validate(
        {
            "domain": domain,
            "rationale": "Review this discipline's relevant evidence.",
            "task": {
                "question": "Investigate evidence limitations",
                "search_terms": ["evidence"],
                "max_sources": 3,
            },
        }
    )


def request(domains=(Domain.NUTRITION,), **changes):
    return ResearchRequest(
        question="What does our general evidence support?", allowed_domains=list(domains), **changes
    )


class CoordinatorProvider:
    def __init__(
        self, domains, *, decision="research", followups=(), effect=None, synthesis_error=False
    ):
        self.domains, self.decision, self.followups = domains, decision, followups
        self.calls, self.effect, self.synthesis_error = [], effect, synthesis_error

    def plan(self, context):
        self.calls.append("plan")
        if self.effect:
            self.effect()
        return Plan(
            decision=self.decision,
            rationale="This team can investigate the question.",
            questions=["Which goal should this research address?"]
            if self.decision == "clarify"
            else [],
            assignments=[] if self.decision == "clarify" else [assignment(d) for d in self.domains],
        )

    def collaborate(self, context):
        self.calls.append("collaborate")
        return CollaborationPlan(
            rationale="Compare an explicitly requested discipline.",
            assignments=[assignment(d) for d in self.followups],
        )

    def synthesise(self, context):
        self.calls.append("synthesise")
        if self.synthesis_error:
            raise InvalidEvidence("synthetic-private-provider-detail")
        task = next(
            t for t in context["specialist_results"] if t["result"] and t["result"]["findings"]
        )
        return Synthesis.model_validate(
            {
                "conclusions": [
                    {
                        "statement": "The synthetic evidence has limitations.",
                        "references": [{"task_id": task["task_id"], "finding_index": 0}],
                        "confidence": "high",
                        "limitations": "Synthetic evidence, not a real-world finding.",
                    }
                ],
                "options": [],
                "disagreements": [],
                "knowledge_gaps": [],
            }
        )


class LocalSpecialists:
    def __init__(self, repo, *, failures=(), collaboration=False):
        self.repo, self.calls, self.failures, self.collaboration = repo, [], failures, collaboration

    def dispatch(self, task, task_id):
        self.calls.append(task.domain)
        if task.domain in self.failures:
            raise ProviderUnavailable("synthetic-private-provider-detail")
        cap = replace(capability(task.domain), request_id=str(task_id))
        result = SpecialistRuntime(self.repo, EvidenceProvider(), SpecialistSettings()).execute(
            cap, task.domain, task.task
        )
        if self.collaboration:
            result["collaboration_requests"] = [
                {
                    "domain": Domain.PHYSICAL.value,
                    "reason": "Compare a relevant second perspective.",
                }
            ]
        return result


@pytest.fixture
def coordinator_store(specialist_store):  # noqa: F811
    specialist_repo, libraries, conn = specialist_store
    client = conn.execute(
        "INSERT INTO service_identities (service_key, display_name, service_role) VALUES ('synthetic-personal-ai', 'Synthetic Personal AI', 'personal_ai') RETURNING id"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO access_permissions (service_identity_id, action, granted_by) VALUES (%s, 'coordinate', 'synthetic-test')",
        (client,),
    )
    caller = replace(capability(), subject="synthetic-personal-ai", actor="personal_ai", domain="*")
    settings = Settings(service_subject="synthetic-coordinator")
    return Repository(specialist_repo.pool), specialist_repo, libraries, conn, caller, settings


@pytest.mark.parametrize("domain", list(Domain))
def test_coordinator_executes_each_of_the_eleven_real_scoped_runtimes(coordinator_store, domain):
    repo, specialists, libraries, conn, caller, settings = coordinator_store
    evidence(conn, libraries[domain.value])
    provider, client = CoordinatorProvider([domain]), LocalSpecialists(specialists)
    result = Runtime(repo, provider, client, settings).execute(caller, request([domain]))
    assert result["state"] == "completed"
    assert client.calls == [domain] and provider.calls == ["plan", "synthesise"]
    conclusion = result["conclusions"][0]
    assert conclusion["confidence"] == "low" and conclusion["confidence_adjusted"]
    assert (
        conclusion["evidence"][0]["finding"]["citations"][0]["canonical_url"]
        == "https://example.org/evidence"
    )
    assert result["review_required"] and result["life_profile_access"] is False
    saved = repo.read(caller, UUID(result["run_id"]), settings)
    assert saved["report"] == {k: v for k, v in result.items() if k not in ("run_id", "state")}
    assert saved["calls_used"] == 1 and len(saved["tasks"]) == 1
    assert conn.execute("SELECT count(*) FROM research_findings").fetchone()[0] == 0


def test_nine_specialists_plus_coordinator_fit_the_ten_bot_team(coordinator_store):
    repo, specialists, libraries, conn, caller, settings = coordinator_store
    domains = list(Domain)[:9]
    for domain in domains:
        evidence(conn, libraries[domain.value])
    provider, client = CoordinatorProvider(domains), LocalSpecialists(specialists)
    result = Runtime(repo, provider, client, settings).execute(
        caller, request(list(Domain), max_specialist_calls=9)
    )
    assert result["state"] == "completed" and len(result["tasks"]) == 9
    assert client.calls == domains and result["call_budget"] == 9
    assert result["team_bot_limit"] == 10
    assert result["team_count_includes"] == "coordinator_and_dispatched_specialists"


def test_server_reservation_caps_legacy_or_unvalidated_budgets(coordinator_store):
    repo, _, _, conn, caller, settings = coordinator_store
    # Defence in depth even when an alternate caller bypasses Pydantic validation.
    request_value = request(list(Domain)).model_copy(update={"max_specialist_calls": 11})
    settings = settings.model_copy(update={"max_specialist_calls": 11})
    run_id = repo.start(caller, request_value, settings)
    assert repo.read(caller, run_id, settings)["max_calls"] == 9
    # Preserve old stored history; enforce today's cap at the dispatch boundary.
    conn.execute("UPDATE coordinator_runs SET max_calls = 11 WHERE id = %s", (run_id,))
    conn.commit()
    for domain in list(Domain)[:9]:
        repo.reserve(caller, run_id, assignment(domain), "initial", settings)
    with pytest.raises(BudgetExceeded):
        repo.reserve(caller, run_id, assignment(list(Domain)[9]), "initial", settings)
    assert repo.read(caller, run_id, settings)["calls_used"] == 9


def test_ambiguity_requests_clarification_before_dispatch(coordinator_store):
    repo, specialists, _, _, caller, settings = coordinator_store
    provider, client = CoordinatorProvider([], decision="clarify"), LocalSpecialists(specialists)
    result = Runtime(repo, provider, client, settings).execute(caller, request())
    assert result["state"] == "needs_clarification" and result["clarifying_questions"]
    assert not client.calls and provider.calls == ["plan"]


def test_empty_evidence_does_not_trigger_synthesis_or_invent_advice(coordinator_store):
    repo, specialists, _, _, caller, settings = coordinator_store
    provider = CoordinatorProvider([Domain.NUTRITION])
    result = Runtime(repo, provider, LocalSpecialists(specialists), settings).execute(
        caller, request()
    )
    assert result["state"] == "needs_evidence" and not result["conclusions"]
    assert result["specialist_knowledge_gaps"] and provider.calls == ["plan"]


@pytest.mark.parametrize(
    "domains",
    [[Domain.PHYSICAL], [Domain.NUTRITION, Domain.NUTRITION], [Domain.NUTRITION, Domain.PHYSICAL]],
)
def test_injected_out_of_scope_duplicate_or_over_budget_plans_never_dispatch(
    coordinator_store, domains
):
    repo, specialists, _, conn, caller, settings = coordinator_store
    client = LocalSpecialists(specialists)
    with pytest.raises(InvalidEvidence):
        Runtime(repo, CoordinatorProvider(domains), client, settings).execute(
            caller, request(max_specialist_calls=1)
        )
    assert client.calls == []
    assert conn.execute("SELECT state, error_code FROM coordinator_runs").fetchone() == (
        "failed",
        "planning_unavailable_or_invalid",
    )


@pytest.mark.parametrize(
    "enabled,followups,expected",
    [
        (False, [Domain.PHYSICAL], [Domain.NUTRITION]),
        (True, [Domain.PHYSICAL], [Domain.NUTRITION, Domain.PHYSICAL]),
        (True, [Domain.FINANCIAL], [Domain.NUTRITION]),
    ],
)
def test_only_explicit_coordinator_approved_requested_peers_execute_once(
    coordinator_store, enabled, followups, expected
):
    repo, specialists, libraries, conn, caller, settings = coordinator_store
    for domain in (Domain.NUTRITION, Domain.PHYSICAL, Domain.FINANCIAL):
        evidence(conn, libraries[domain.value])
    client = LocalSpecialists(specialists, collaboration=True)
    provider = CoordinatorProvider([Domain.NUTRITION], followups=followups)
    result = Runtime(repo, provider, client, settings).execute(
        caller,
        request([Domain.NUTRITION, Domain.PHYSICAL, Domain.FINANCIAL], allow_collaboration=enabled),
    )
    assert client.calls == expected
    assert len(client.calls) <= 2  # Follow-up requests never recursively expand the team.
    if enabled and followups == [Domain.FINANCIAL]:
        assert result["state"] == "partial" and result["issues"]


@pytest.mark.parametrize("failure_mode", ["one_specialist", "all_specialists", "synthesis"])
def test_failure_reports_preserve_valid_work_without_claiming_completion(
    coordinator_store, failure_mode
):
    repo, specialists, libraries, conn, caller, settings = coordinator_store
    for domain in (Domain.NUTRITION, Domain.PHYSICAL):
        evidence(conn, libraries[domain.value])
    failures = (
        [Domain.PHYSICAL]
        if failure_mode == "one_specialist"
        else list(Domain)
        if failure_mode == "all_specialists"
        else []
    )
    client = LocalSpecialists(specialists, failures=failures)
    provider = CoordinatorProvider(
        [Domain.NUTRITION, Domain.PHYSICAL], synthesis_error=failure_mode == "synthesis"
    )
    result = Runtime(repo, provider, client, settings).execute(
        caller, request([Domain.NUTRITION, Domain.PHYSICAL])
    )
    assert result["state"] == ("failed" if failure_mode == "all_specialists" else "partial")
    assert len(result["tasks"]) == 2
    assert "synthetic-private-provider-detail" not in str(result)
    if failure_mode == "synthesis":
        assert not result["conclusions"] and all(t["result"] for t in result["tasks"])


def test_revoked_personal_ai_grant_stops_work_after_planning(coordinator_store):
    repo, specialists, _, conn, caller, settings = coordinator_store
    client = LocalSpecialists(specialists)
    provider = CoordinatorProvider(
        [Domain.NUTRITION],
        effect=lambda: conn.execute("DELETE FROM access_permissions WHERE action = 'coordinate'"),
    )
    with pytest.raises(AccessDenied):
        Runtime(repo, provider, client, settings).execute(caller, request())
    assert client.calls == []
    assert conn.execute("SELECT state FROM coordinator_runs").fetchone()[0] == "failed"


def test_replay_and_caller_isolation_are_database_enforced(coordinator_store):
    repo, _, _, conn, caller, settings = coordinator_store
    run_id = repo.start(caller, request(), settings)
    with pytest.raises(RunConflict):
        repo.start(caller, request(), settings)
    with pytest.raises(BudgetExceeded):
        repo.start(replace(caller, request_id=str(uuid4())), request(), settings)
    other = conn.execute(
        "INSERT INTO service_identities (service_key, display_name, service_role) VALUES ('another-personal-ai', 'Another synthetic client', 'personal_ai') RETURNING id"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO access_permissions (service_identity_id, action, granted_by) VALUES (%s, 'coordinate', 'synthetic-test')",
        (other,),
    )
    assert repo.read(replace(caller, subject="another-personal-ai"), run_id, settings) is None


@pytest.mark.parametrize(
    "change",
    ["caller_role", "inactive_coordinator", "expired_token", "wrong_action", "scoped_grant"],
)
def test_db_roles_active_services_and_global_coordination_grant_are_required(
    coordinator_store, change
):
    repo, _, libraries, conn, caller, settings = coordinator_store
    if change == "caller_role":
        conn.execute(
            "UPDATE service_identities SET service_role = 'api_service' WHERE service_key = %s",
            (caller.subject,),
        )
    elif change == "inactive_coordinator":
        conn.execute(
            "UPDATE service_identities SET is_active = FALSE WHERE service_key = %s",
            (settings.service_subject,),
        )
    elif change == "expired_token":
        caller = replace(caller, expires_at=1)
    elif change == "wrong_action":
        conn.execute(
            "UPDATE access_permissions SET action = 'discover' WHERE action = 'coordinate'"
        )
    else:
        conn.execute(
            "UPDATE access_permissions SET library_id = %s WHERE action = 'coordinate'",
            (libraries[Domain.NUTRITION.value],),
        )
    with pytest.raises(AccessDenied):
        repo.start(caller, request(), settings)


def test_database_reservations_prevent_duplicate_domains_and_unapproved_collaboration(
    coordinator_store,
):
    repo, _, _, conn, caller, settings = coordinator_store
    run_id = repo.start(
        caller, request([Domain.NUTRITION, Domain.PHYSICAL], max_specialist_calls=1), settings
    )
    with pytest.raises(AccessDenied):
        repo.reserve(caller, run_id, assignment(Domain.PHYSICAL), "collaboration", settings)
    repo.reserve(caller, run_id, assignment(Domain.NUTRITION), "initial", settings)
    with pytest.raises(BudgetExceeded):
        repo.reserve(caller, run_id, assignment(Domain.PHYSICAL), "initial", settings)
    assert conn.execute("SELECT calls_used FROM coordinator_runs").fetchone()[0] == 1


def test_unrecognised_synthesis_references_cannot_become_conclusions():
    data = {
        "conclusions": [
            {
                "statement": "Invented conclusion",
                "references": [{"task_id": str(uuid4()), "finding_index": 0}],
                "confidence": "high",
                "limitations": "No real evidence.",
            }
        ],
        "options": [],
        "disagreements": [],
        "knowledge_gaps": [],
    }
    with pytest.raises(InvalidEvidence):
        grounded_synthesis(Synthesis.model_validate(data), [])


def test_request_rejects_profile_payloads_and_inconsistent_plans():
    with pytest.raises(ValidationError):
        ResearchRequest(
            question="Analyse this request",
            allowed_domains=[Domain.NUTRITION],
            life_profile={"private": True},
        )
    with pytest.raises(ValidationError):
        Plan(decision="clarify", rationale="Unclear request", questions=[], assignments=[])


def test_parallel_reservations_daily_limits_and_abandoned_lease_recovery(coordinator_store):
    repo, _, _, conn, caller, settings = coordinator_store
    run_id = repo.start(
        caller, request([Domain.NUTRITION, Domain.PHYSICAL], max_specialist_calls=1), settings
    )

    def reserve(domain):
        try:
            repo.reserve(caller, run_id, assignment(domain), "initial", settings)
            return "authorised"
        except BudgetExceeded:
            return "limited"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(reserve, [Domain.NUTRITION, Domain.PHYSICAL])) == [
            "authorised",
            "limited",
        ]
    conn.execute("UPDATE coordinator_runs SET lease_expires_at = now() - interval '1 second'")
    new_run = repo.start(replace(caller, request_id=str(uuid4())), request(), settings)
    assert repo.read(caller, run_id, settings)["error_code"] == "execution_lease_expired"
    assert repo.read(caller, run_id, settings)["tasks"][0]["state"] == "failed"
    repo.fail(caller, new_run, "synthetic_cleanup")
    with pytest.raises(BudgetExceeded):
        repo.start(
            replace(caller, request_id=str(uuid4())),
            request(),
            settings.model_copy(update={"max_runs_per_24h": 2}),
        )


def test_shared_sources_are_counted_once_and_specialist_disagreements_survive_summary():
    source = str(uuid4())
    tasks = []
    for domain in (Domain.NUTRITION, Domain.PHYSICAL):
        tasks.append(
            {
                "task_id": str(uuid4()),
                "domain": domain.value,
                "result": {
                    "findings": [
                        {
                            "confidence": "low",
                            "statement": "Synthetic finding",
                            "citations": [{"source_id": source}],
                        }
                    ],
                    "knowledge_gaps": ["Important missing evidence"],
                    "contradictions": [{"description": "Unresolved source disagreement"}],
                },
            }
        )
    inventory = evidence_inventory(tasks)
    assert inventory["distinct_source_count"] == 1 and inventory["citation_count"] == 2
    assert inventory["source_independence_assessed"] is False
    assert len(inventory["specialist_disagreements"]) == 2
    assert inventory["specialist_knowledge_gaps"] == ["Important missing evidence"]
    data = {
        "conclusions": [
            {
                "statement": "Synthetic summary",
                "confidence": "high",
                "limitations": "Important limitations",
                "references": [{"task_id": tasks[0]["task_id"], "finding_index": 0}],
            }
        ],
        "options": [],
        "disagreements": [
            {
                "description": "A claimed disagreement",
                "supporting": [{"task_id": tasks[0]["task_id"], "finding_index": 0}],
                "challenging": [{"task_id": tasks[1]["task_id"], "finding_index": 0}],
            }
        ],
        "knowledge_gaps": [],
    }
    assert len(grounded_synthesis(Synthesis.model_validate(data), tasks)["disagreements"]) == 1
    data["disagreements"][0]["challenging"] = data["disagreements"][0]["supporting"]
    with pytest.raises(InvalidEvidence):
        grounded_synthesis(Synthesis.model_validate(data), tasks)


def test_restricted_coordinator_role_can_orchestrate_without_library_or_profile_read_access(
    coordinator_store,
):
    repo, specialists, libraries, conn, caller, settings = coordinator_store
    evidence(conn, libraries[Domain.NUTRITION.value])
    schema = conn.execute("SELECT current_schema()").fetchone()[0]
    role = "coordinator_role_test_" + uuid4().hex
    template = (
        Path(__file__).resolve().parents[2] / "coordinator/database/runtime-role.sql"
    ).read_text()
    conn.execute(
        template.replace("corepath_coordinator_runtime", role).replace(
            "SCHEMA public", "SCHEMA " + schema
        )
    )
    restricted_pool = None

    def assume_role(connection):
        connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        connection.commit()

    try:
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
        runtime = Runtime(
            Repository(restricted_pool),
            CoordinatorProvider([Domain.NUTRITION]),
            LocalSpecialists(specialists),
            settings,
        )
        assert runtime.execute(caller, request())["state"] == "completed"
        for forbidden in (
            "SELECT * FROM knowledge_sources",
            "SELECT * FROM document_sections",
            "SELECT * FROM life_profiles",
            "UPDATE service_identities SET is_active = FALSE",
            "DELETE FROM access_permissions",
            "UPDATE specialist_runs SET state = 'failed'",
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
