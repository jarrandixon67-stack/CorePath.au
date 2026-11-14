"""Relevant-specialist routing with optional full-team review and explicit budgets."""

from dataclasses import dataclass
from time import monotonic

from pydantic import ValidationError

from .contracts import Assignment, Contribution, Domain, PersyReply, RoutingPlan, Source, Synthesis
from .provider import Provider, ProviderError
from .registry import VERSION, policy_hash, roles

CONFIDENCE = {"low": 0, "moderate": 1, "high": 2}


class InvalidEvidence(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    max_calls: int = 24  # 11 initial + 11 review + coordinator + Persy
    deadline_seconds: float = 1200
    max_sources: int = 30

    def __post_init__(self):
        if not 4 <= self.max_calls <= 25 or not 1 <= self.deadline_seconds <= 1800:
            raise ValueError("Auto routing needs at least 4 calls; maximum is 25")
        if not 1 <= self.max_sources <= 100:
            raise ValueError("Source count must be bounded")


def validate_contribution(domain: Domain, contribution: Contribution, sources: list[Source]):
    allowed = {s.id: s for s in sources if domain in s.domains}
    if domain in contribution.peer_requests:
        raise InvalidEvidence("A peer request cannot name the requesting specialist")
    for claim in contribution.claims:
        for citation in claim.citations:
            if citation.source_id not in allowed or citation.quote not in allowed[citation.source_id].content:
                raise InvalidEvidence("A claim cited missing, out-of-scope or mismatched evidence")


def validate_synthesis(synthesis: Synthesis, contributions: dict[Domain, Contribution], expected_domains=None):
    expected = set(Domain) if expected_domains is None else set(expected_domains)
    if len(synthesis.feedback) != len(expected) or {f.domain for f in synthesis.feedback} != expected:
        raise InvalidEvidence("Feedback must cover each assigned specialist exactly once")

    def resolve(refs):
        keys = [(ref.domain, ref.index) for ref in refs]
        if len(set(keys)) != len(keys):
            raise InvalidEvidence("Duplicate evidence references")
        claims = []
        for domain, index in keys:
            contribution = contributions.get(domain)
            if contribution is None or index >= len(contribution.claims):
                raise InvalidEvidence("Synthesis referenced an absent finding")
            claims.append(contribution.claims[index])
        return claims

    for conclusion in synthesis.conclusions:
        claims = resolve(conclusion.references)
        cap = min(CONFIDENCE[c.confidence] for c in claims)
        if CONFIDENCE[conclusion.confidence] > cap:
            conclusion.confidence = next(name for name, score in CONFIDENCE.items() if score == cap)
    for disagreement in synthesis.disagreements:
        resolve(disagreement.supporting)
        resolve(disagreement.challenging)
        a = {(r.domain, r.index) for r in disagreement.supporting}
        b = {(r.domain, r.index) for r in disagreement.challenging}
        if a & b or len({domain for domain, _ in a | b}) < 2:
            raise InvalidEvidence("A disagreement needs distinct opposing contributions")
    if any(c.claims for c in contributions.values()) and not synthesis.conclusions:
        raise InvalidEvidence("Synthesis omitted all available evidence")


class Team:
    def __init__(self, provider: Provider, limits: Limits | None = None):
        self.provider = provider
        self.limits = limits or Limits()

    def discuss(self, question: str, sources: list[Source], *,
                approved_for_all_specialists: bool, review_round: bool | None = None,
                priority: str = "routine", mode: str = "auto",
                max_specialists: int = 11) -> dict:
        """Authorisation makes the team available; it does not require calling every bot.

        No private profile is silently included. Sources are supplied public approved
        excerpts, not fetched by the model. The returned answer remains a draft.
        """
        if not approved_for_all_specialists:
            raise PermissionError("The exact question must be approved for all eleven specialists")
        question = question.strip()
        if not 5 <= len(question) <= 2000:
            raise ValueError("Question must be between 5 and 2000 characters")
        sources = [Source.model_validate(s) for s in sources]
        if len(sources) > self.limits.max_sources or len({s.id for s in sources}) != len(sources):
            raise ValueError("Source limit exceeded or source IDs duplicated")
        if sum(len(s.content) for s in sources) > 50000:
            raise ValueError("Source text exceeds the team context budget")
        if priority not in {"routine", "important", "urgent"}:
            raise ValueError("Invalid task priority")
        if mode not in {"auto", "full"}:
            raise ValueError("Mode must be auto or full")
        if type(max_specialists) is not int or not 1 <= max_specialists <= 11:
            raise ValueError("Specialist ceiling must be an integer from 1 to 11")
        if mode == "full" and max_specialists != 11:
            raise ValueError("Full team requires an eleven-specialist ceiling")
        if review_round is None:
            review_round = mode == "full"
        # Choose before any specialist dispatch. The router has no sources, tools
        # or profile access and cannot enlarge the caller's approved call ceiling.
        start = monotonic()
        routing = None
        routing_calls = 0
        routing_receipts = []
        if mode == "auto":
            routing = RoutingPlan.model_validate(self.provider.generate(
                "chief-of-staff", "select_necessary_specialists", {
                    "question": question,
                    "available_specialists": {d.value: roles()[d.value]["scope"] for d in Domain},
                    "instructions": "Select only disciplines necessary to answer this question, including material risk and cross-field dependencies. Do not fill a quota. Return all necessary domains even if a later spending ceiling might prevent dispatch. No evidence claims or answers at this stage.",
                }, RoutingPlan))
            routing_calls = 1
            routing_receipts = [{"role": "chief-of-staff", "stage": "select_necessary_specialists",
                                 "policy_hash": policy_hash("chief-of-staff", "select_necessary_specialists")}]
        if monotonic() - start >= self.limits.deadline_seconds:
            raise ProviderError("Discussion deadline reached during routing")
        selected = list(Domain) if routing is None else routing.domains
        requested_review = bool(review_round)
        minimum_calls = routing_calls + len(selected) + 2
        if len(selected) > max_specialists or minimum_calls > self.limits.max_calls:
            return {
                "version": VERSION, "state": "needs_selection_change", "review_required": True,
                "mode": mode, "max_specialists": max_specialists,
                "recommended_domains": [d.value for d in selected], "assessed_domains": [],
                "selection_rationale": routing.rationale if routing else "Full team explicitly requested.",
                "issues": ["Necessary coverage exceeds the approved ceiling; broaden permission or narrow the question before dispatch."],
                "contributions": {}, "synthesis": None, "persy_draft": None,
                "full_team_assessed": False, "calls_attempted": routing_calls,
                "receipts": routing_receipts,
            }
        assignments = {d: Assignment(
            domain=d, task=question,
            expected_result="A concise, evidence-grounded assessment from your discipline.",
            criteria=["Relevance", "Evidence and counterevidence", "Applicability and risk",
                      "Respect scope, uncertainty, privacy and referral limits"],
            priority=priority,
            completion_criteria="Return a validated contribution, or explain no relevant evidence; identify gaps and peer needs.",
        ) for d in selected}
        calls = routing_calls
        receipts, issues = routing_receipts, []
        results: dict[Domain, Contribution] = {}

        def generate(role_id, stage, context, contract):
            nonlocal calls
            if calls >= self.limits.max_calls:
                raise ProviderError("Call budget exhausted")
            if monotonic() - start >= self.limits.deadline_seconds:
                raise ProviderError("Discussion deadline reached")
            calls += 1
            output = self.provider.generate(role_id, stage, context, contract)
            if monotonic() - start >= self.limits.deadline_seconds:
                raise ProviderError("Discussion deadline reached before result acceptance")
            validated = contract.model_validate(output)
            receipts.append({"role": role_id, "stage": stage, "policy_hash": policy_hash(role_id, stage)})
            return validated

        def specialist(domain, stage, peers=None):
            context = {
                "assignment": assignments[domain].model_dump(mode="json"),
                "approved_sources": [s.model_dump(mode="json") for s in sources if domain in s.domains],
            }
            if peers is not None:
                context["peer_briefs_routed_by_chief_of_staff"] = peers
                context["your_previous_contribution"] = results[domain].model_dump(mode="json")
            contribution = generate(domain.value, stage, context, Contribution)
            validate_contribution(domain, contribution, sources)
            return contribution

        for domain in selected:
            try:
                results[domain] = specialist(domain, "initial_assessment")
            except (ProviderError, ValidationError, InvalidEvidence):
                issues.append(f"{domain.value}:initial_unavailable_or_invalid")

        initial = {d: c.model_dump(mode="json") for d, c in results.items()}
        # One bounded shared review. Each sees the same initial snapshot, so
        # ordering cannot silently give later specialists a privileged review.
        if review_round and self.limits.max_calls >= calls + len(selected) + 2 and len(results) == len(selected):
            for domain in selected:
                peers = {d.value: c for d, c in initial.items() if d != domain}
                try:
                    results[domain] = specialist(domain, "peer_review", peers)
                except (ProviderError, ValidationError, InvalidEvidence):
                    issues.append(f"{domain.value}:review_unavailable_or_invalid")
        elif review_round:
            issues.append("peer_review_skipped_due_to_budget_or_incomplete_initial_team")

        unconsulted_peers = {peer for c in results.values() for peer in c.peer_requests} - set(selected)
        if unconsulted_peers:
            issues.append("additional_specialist_review_needed:" + ",".join(sorted(d.value for d in unconsulted_peers)))

        public_results = {d.value: c.model_dump(mode="json") for d, c in results.items()}
        # Keep these outside model-written synthesis so a shorter response
        # cannot silently remove a specialist's warning, referral or question.
        specialist_gaps = list(dict.fromkeys(gap for c in results.values() for gap in c.gaps))
        specialist_questions = list(dict.fromkeys(q for c in results.values() for q in c.questions))
        referrals = [{"domain": d.value, "reason": c.referral_reason}
                     for d, c in results.items() if c.referral_reason]
        report = {
            "version": VERSION, "state": "partial", "review_required": True,
            "mode": mode, "max_specialists": max_specialists,
            "full_team_requested": mode == "full",
            "recommended_domains": [d.value for d in selected],
            "assessed_domains": [d.value for d in results],
            "selection_rationale": routing.rationale if routing else "Full team explicitly requested.",
            "full_team_assessed": len(results) == len(Domain),
            "peer_review_requested": requested_review,
            "question": question, "assignments": [a.model_dump(mode="json") for a in assignments.values()],
            "contributions": public_results, "initial_contributions": {d.value: c for d, c in initial.items()},
            "source_catalogue": [{"id": s.id, "title": s.title, "url": s.url,
                                  "checked_at": s.checked_at} for s in sources],
            "issues": issues, "receipts": receipts, "synthesis": None, "persy_draft": None,
            "specialist_knowledge_gaps": specialist_gaps,
            "specialist_questions": specialist_questions, "referral_needs": referrals,
            "supporting_evidence": [],
            "evidence_note": "Exact quotes establish traceability, not truth or semantic entailment. Human review remains required.",
        }
        try:
            synthesis = generate("chief-of-staff", "evaluate_and_give_feedback", {
                "question": question, "contributions": public_results, "issues": issues,
                "assigned_domains": [d.value for d in selected],
                "instructions": "Evaluate reasonable arguments, not votes. Cite actual claim indexes. Provide feedback exactly once for each assigned domain, identifying unavailable contributions honestly. Never claim unconsulted domains contributed.",
            }, Synthesis)
            validate_synthesis(synthesis, results, selected)
            report["synthesis"] = synthesis.model_dump(mode="json")
            referenced = {(ref.domain, ref.index) for c in synthesis.conclusions for ref in c.references}
            referenced.update((ref.domain, ref.index) for d in synthesis.disagreements
                              for ref in d.supporting + d.challenging)
            report["supporting_evidence"] = [
                {"domain": domain.value, "claim_index": index,
                 "claim": results[domain].claims[index].model_dump(mode="json")}
                for domain, index in sorted(referenced)
            ]
            reply = generate("persy", "present_reviewed_team_draft", {
                "question": question, "synthesis": report["synthesis"], "issues": issues,
                "specialist_knowledge_gaps": specialist_gaps,
                "specialist_questions": specialist_questions, "referral_needs": referrals,
                "instructions": "Use a brief non-factual greeting/opening. Select all material conclusions by index, omit no significant uncertainty. No new factual advice in opening or closing. Draft only; do not claim a user has already received it.",
            }, PersyReply)
            indexes = reply.conclusion_indexes
            if len(set(indexes)) != len(indexes) or set(indexes) != set(range(len(synthesis.conclusions))):
                raise InvalidEvidence("Persy must retain all validated conclusions without duplication")
            # Evidence, disagreements and limitations cannot be rewritten away.
            blocks = [reply.opening]
            for i in indexes:
                c = synthesis.conclusions[i]
                blocks.append(c.statement + "\nLimitations: " + c.limitations)
            blocks.extend("Different perspectives: " + d.description for d in synthesis.disagreements)
            blocks.extend("Uncertainty: " + gap for gap in synthesis.gaps)
            blocks.extend("Specialist uncertainty: " + gap for gap in specialist_gaps)
            blocks.extend("Referral needed (" + item["domain"] + "): " + item["reason"] for item in referrals)
            blocks.extend("Specialist clarification: " + q for q in specialist_questions)
            caveats = dict.fromkeys(item["claim"]["limitations"] for item in report["supporting_evidence"])
            blocks.extend("Supporting evidence limitation: " + caveat for caveat in caveats)
            cited_ids = {citation["source_id"] for item in report["supporting_evidence"]
                         for citation in item["claim"]["citations"]}
            blocks.extend("Source: " + s.title + " — " + s.url for s in sources if s.id in cited_ids)
            blocks.extend("Team issue: " + issue for issue in issues)
            blocks.extend("Clarification needed: " + q for q in synthesis.questions)
            if reply.closing_question:
                blocks.append(reply.closing_question)
            report["persy_draft"] = "\n\n".join(blocks)
            report["state"] = ("partial" if issues or len(results) != len(selected) else
                               "completed" if any(c.claims for c in results.values()) else "needs_evidence")
        except (ProviderError, ValidationError, InvalidEvidence):
            issues.append("coordination_or_persy_output_unavailable_or_invalid")
        report["calls_attempted"] = calls
        report["duration_seconds"] = round(monotonic() - start, 3)
        return report
