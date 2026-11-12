from pydantic import ValidationError

from coordinator.limits import MAX_SPECIALIST_CALLS, MAX_TEAM_BOTS
from coordinator.models import ResearchRequest, SpecialistResult, Synthesis
from coordinator.provider import Provider
from coordinator.repository import Repository
from coordinator.settings import Settings
from coordinator.transport import SpecialistClient
from specialists.models import (
    AccessDenied,
    BudgetExceeded,
    InvalidEvidence,
    ProviderUnavailable,
    RunConflict,
)
from specialists.registry import catalogue

CONFIDENCE = {"low": 0, "moderate": 1, "high": 2}


def validate_assignments(assignments, allowed, remaining, used=()):
    domains = [assignment.domain for assignment in assignments]
    if (
        len(domains) > min(remaining, MAX_SPECIALIST_CALLS - len(set(used)))
        or len(set(domains)) != len(domains)
        or set(domains) & set(used)
        or not set(domains) <= set(allowed)
    ):
        raise InvalidEvidence("The Coordinator plan exceeded its domain/call boundary")


def grounded_synthesis(synthesis: Synthesis, tasks: list[dict]):
    findings = {}
    for task in tasks:
        if task["result"]:
            for index, finding in enumerate(task["result"]["findings"]):
                findings[(task["task_id"], index)] = {
                    "task_id": task["task_id"],
                    "finding_index": index,
                    "specialist": task["domain"],
                    "finding": finding,
                }

    def resolve(references):
        keys = [(str(ref.task_id), ref.finding_index) for ref in references]
        if len(set(keys)) != len(keys) or any(key not in findings for key in keys):
            raise InvalidEvidence("Synthesis referenced absent or duplicate evidence")
        return [findings[key] for key in keys]

    conclusions = []
    for conclusion in synthesis.conclusions:
        evidence = resolve(conclusion.references)
        cap = min(CONFIDENCE[item["finding"]["confidence"]] for item in evidence)
        confidence = min(CONFIDENCE[conclusion.confidence], cap)
        conclusions.append(
            {
                "statement": conclusion.statement,
                "evidence": evidence,
                "confidence": next(
                    name for name, score in CONFIDENCE.items() if score == confidence
                ),
                "confidence_adjusted": confidence != CONFIDENCE[conclusion.confidence],
                "limitations": conclusion.limitations,
            }
        )
    options = [
        {
            "action": item.action,
            "evidence": resolve(item.references),
            "limitations": item.limitations,
        }
        for item in synthesis.options
    ]
    disagreements = []
    for disagreement in synthesis.disagreements:
        support, challenge = resolve(disagreement.supporting), resolve(disagreement.challenging)
        a = {(item["task_id"], item["finding_index"]) for item in support}
        b = {(item["task_id"], item["finding_index"]) for item in challenge}
        if a & b or len({item["task_id"] for item in support + challenge}) < 2:
            raise InvalidEvidence("Cross-specialist disagreement needs distinct opposing evidence")
        disagreements.append(
            {
                "description": disagreement.description,
                "supporting": support,
                "challenging": challenge,
            }
        )
    if findings and not conclusions:
        raise InvalidEvidence("Synthesis omitted all available findings")
    return {
        "conclusions": conclusions,
        "options": options,
        "disagreements": disagreements,
        "knowledge_gaps": synthesis.knowledge_gaps,
    }


def evidence_inventory(tasks):
    sources, count = set(), 0
    gaps, disagreements = [], []
    for task in tasks:
        result = task["result"]
        if not result:
            continue
        gaps.extend(result["knowledge_gaps"])
        disagreements.extend(
            {"task_id": task["task_id"], "domain": task["domain"], **item}
            for item in result["contradictions"]
        )
        for finding in result["findings"]:
            for citation in finding["citations"]:
                count += 1
                sources.add(citation["source_id"])
    return {
        "specialist_knowledge_gaps": list(dict.fromkeys(gaps)),
        "specialist_disagreements": disagreements,
        "distinct_source_count": len(sources),
        "citation_count": count,
        "source_independence_assessed": False,
    }


class Runtime:
    def __init__(
        self,
        repository: Repository,
        provider: Provider,
        specialists: SpecialistClient,
        settings: Settings,
    ):
        self.repository, self.provider, self.specialists, self.settings = (
            repository,
            provider,
            specialists,
            settings,
        )

    def execute(self, caller, request: ResearchRequest):
        repo, settings = self.repository, self.settings
        run_id = repo.start(caller, request, settings)
        tasks, issues = [], []
        try:
            row = repo.check(caller, run_id, settings)
            context = {
                "question": request.question,
                "allowed_specialists": [
                    bot for bot in catalogue() if bot["domain"] in request.allowed_domains
                ],
                "remaining_calls": row["max_calls"],
            }
            plan = self.provider.plan(context)
            validate_assignments(plan.assignments, request.allowed_domains, row["max_calls"])
            repo.save_plan(caller, run_id, plan, settings)
            report = {
                "audience": "personal_ai_internal",
                "review_required": True,
                "life_profile_access": False,
                "selection_rationale": plan.rationale,
                "clarifying_questions": plan.questions,
                "allowed_domains": [domain.value for domain in request.allowed_domains],
                "call_budget": row["max_calls"],
                "team_bot_limit": MAX_TEAM_BOTS,
                "team_count_includes": "coordinator_and_dispatched_specialists",
                "confidence_note": "Uncalibrated model judgement; citations establish traceability, not truth or entailment.",
            }
            if plan.decision == "clarify":
                report.update(
                    {
                        "tasks": [],
                        "conclusions": [],
                        "options": [],
                        "disagreements": [],
                        "knowledge_gaps": [],
                        "issues": [],
                        "synthesis_state": "not_attempted",
                    }
                )
                repo.finish(caller, run_id, report, "needs_clarification", settings)
                return {"run_id": str(run_id), "state": "needs_clarification", **report}

            def dispatch(assignments, phase):
                for assignment in assignments:
                    task_id = repo.reserve(caller, run_id, assignment, phase, settings)
                    task = {
                        "task_id": str(task_id),
                        "domain": assignment.domain.value,
                        "phase": phase,
                        "rationale": assignment.rationale,
                        "state": "failed",
                        "result": None,
                        "error_code": None,
                    }
                    try:
                        result = self.specialists.dispatch(assignment, task_id)
                        # Revalidate even alternate transport adapters at this boundary.
                        result = SpecialistResult.model_validate(result)
                        if result.specialist != assignment.domain:
                            raise InvalidEvidence("Mismatched specialist domain")
                        repo.task_done(caller, run_id, task_id, result, settings)
                        task.update(state=result.state, result=result.model_dump(mode="json"))
                    except (ProviderUnavailable, InvalidEvidence, ValidationError) as exc:
                        code = (
                            "specialist_unavailable"
                            if isinstance(exc, ProviderUnavailable)
                            else "specialist_output_invalid"
                        )
                        repo.task_failed(run_id, task_id, code)
                        task["error_code"] = code
                    tasks.append(task)

            dispatch(plan.assignments, "initial")
            row = repo.check(caller, run_id, settings)
            used = {task["domain"] for task in tasks}
            requested = {
                item["domain"]
                for task in tasks
                if task["result"]
                for item in task["result"]["collaboration_requests"]
            }
            eligible = requested & {domain.value for domain in request.allowed_domains} - used
            report["collaboration_review"] = {
                "state": "not_attempted",
                "rationale": "No eligible authorised follow-up was selected.",
            }
            if request.allow_collaboration and eligible and row["calls_used"] < row["max_calls"]:
                try:
                    followup = self.provider.collaborate(
                        {
                            "question": request.question,
                            "specialist_results": tasks,
                            "eligible_requested_peers": sorted(eligible),
                            "remaining_calls": row["max_calls"] - row["calls_used"],
                        }
                    )
                    validate_assignments(
                        followup.assignments, eligible, row["max_calls"] - row["calls_used"], used
                    )
                    report["collaboration_review"] = {
                        "state": "reviewed",
                        "rationale": followup.rationale,
                    }
                except (InvalidEvidence, ProviderUnavailable, BudgetExceeded):
                    issues.append("collaboration_review_unavailable_or_invalid")
                else:
                    dispatch(followup.assignments, "collaboration")

            repo.check(caller, run_id, settings)
            has_findings = any(task["result"] and task["result"]["findings"] for task in tasks)
            report.update(
                {
                    "conclusions": [],
                    "options": [],
                    "disagreements": [],
                    "knowledge_gaps": [],
                    "synthesis_state": "not_attempted",
                }
            )
            if has_findings:
                try:
                    synthesis = self.provider.synthesise(
                        {"question": request.question, "specialist_results": tasks}
                    )
                    report.update(grounded_synthesis(synthesis, tasks))
                    report["synthesis_state"] = "completed"
                except (InvalidEvidence, ProviderUnavailable, BudgetExceeded):
                    report["synthesis_state"] = "unavailable_or_invalid"
                    issues.append("synthesis_unavailable_or_invalid")
            else:
                report["knowledge_gaps"] = [
                    "No supported findings were returned; further approved evidence or clarification is required."
                ]
            report.update(evidence_inventory(tasks))
            report.update({"tasks": tasks, "issues": issues, "calls_used": len(tasks)})
            if has_findings:
                state = (
                    "partial"
                    if issues or any(task["state"] != "completed" for task in tasks)
                    else "completed"
                )
            else:
                state = (
                    "failed"
                    if all(task["state"] == "failed" for task in tasks)
                    else "partial"
                    if any(task["state"] == "failed" for task in tasks)
                    else "needs_evidence"
                )
            repo.finish(caller, run_id, report, state, settings)
            return {"run_id": str(run_id), "state": state, **report}
        except (AccessDenied, RunConflict):
            repo.fail(caller, run_id, "permission_or_lease_changed")
            raise
        except (ProviderUnavailable, InvalidEvidence, BudgetExceeded):
            repo.fail(caller, run_id, "planning_unavailable_or_invalid")
            raise
        except Exception:
            repo.fail(caller, run_id, "execution_failed")
            raise
