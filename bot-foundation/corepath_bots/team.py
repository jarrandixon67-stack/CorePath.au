"""Bounded all-eleven discussion and evidence-referenced coordination."""

from dataclasses import dataclass
from time import monotonic

from pydantic import ValidationError

from .contracts import Assignment, Contribution, Domain, PersyReply, Source, Synthesis
from .provider import Provider, ProviderError
from .registry import SPECIALIST_IDS, VERSION, policy_hash

CONFIDENCE = {"low": 0, "moderate": 1, "high": 2}


class InvalidEvidence(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    max_calls: int = 24  # 11 initial + 11 review + coordinator + Persy
    deadline_seconds: float = 1200
    max_sources: int = 30

    def __post_init__(self):
        if not 13 <= self.max_calls <= 24 or not 1 <= self.deadline_seconds <= 1800:
            raise ValueError("A full initial team needs 13 calls; maximum is 24")
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


def validate_synthesis(synthesis: Synthesis, contributions: dict[Domain, Contribution]):
    if {f.domain for f in synthesis.feedback} != set(Domain):
        raise InvalidEvidence("Feedback must cover every specialist exactly once")

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
                approved_for_all_specialists: bool, review_round: bool = True,
                priority: str = "routine") -> dict:
        """The caller must authorise the exact question for the whole team.

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
        assignments = {d: Assignment(
            domain=d, task=question,
            expected_result="A concise, evidence-grounded assessment from your discipline.",
            criteria=["Relevance", "Evidence and counterevidence", "Applicability and risk",
                      "Respect scope, uncertainty, privacy and referral limits"],
            priority=priority,
            completion_criteria="Return a validated contribution, or explain no relevant evidence; identify gaps and peer needs.",
        ) for d in Domain}
        start, calls = monotonic(), 0
        receipts, issues = [], []
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
            receipts.append({"role": role_id, "stage": stage, "policy_hash": policy_hash(role_id)})
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

        for domain in Domain:
            try:
                results[domain] = specialist(domain, "initial_assessment")
            except (ProviderError, ValidationError, InvalidEvidence):
                issues.append(f"{domain.value}:initial_unavailable_or_invalid")

        initial = {d: c.model_dump(mode="json") for d, c in results.items()}
        # One bounded shared review. Each sees the same initial snapshot, so
        # ordering cannot silently give later specialists a privileged review.
        if review_round and self.limits.max_calls >= 24 and len(results) == 11:
            for domain in Domain:
                peers = {d.value: c for d, c in initial.items() if d != domain}
                try:
                    results[domain] = specialist(domain, "peer_review", peers)
                except (ProviderError, ValidationError, InvalidEvidence):
                    issues.append(f"{domain.value}:review_unavailable_or_invalid")
        elif review_round:
            issues.append("peer_review_skipped_due_to_budget_or_incomplete_initial_team")

        public_results = {d.value: c.model_dump(mode="json") for d, c in results.items()}
        report = {
            "version": VERSION, "state": "partial", "review_required": True,
            "question": question, "assignments": [a.model_dump(mode="json") for a in assignments.values()],
            "contributions": public_results, "initial_contributions": {d.value: c for d, c in initial.items()},
            "source_catalogue": [{"id": s.id, "title": s.title, "url": s.url,
                                  "checked_at": s.checked_at} for s in sources],
            "issues": issues, "receipts": receipts, "synthesis": None, "persy_draft": None,
            "evidence_note": "Exact quotes establish traceability, not truth or semantic entailment. Human review remains required.",
        }
        try:
            synthesis = generate("chief-of-staff", "evaluate_and_give_feedback", {
                "question": question, "contributions": public_results, "issues": issues,
                "instructions": "Evaluate reasonable arguments, not votes. Cite actual claim indexes. Provide feedback for all eleven, identifying unavailable contributions honestly.",
            }, Synthesis)
            validate_synthesis(synthesis, results)
            report["synthesis"] = synthesis.model_dump(mode="json")
            reply = generate("persy", "present_reviewed_team_draft", {
                "question": question, "synthesis": report["synthesis"], "issues": issues,
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
            blocks.extend("Team issue: " + issue for issue in issues)
            blocks.extend("Clarification needed: " + q for q in synthesis.questions)
            if reply.closing_question:
                blocks.append(reply.closing_question)
            report["persy_draft"] = "\n\n".join(blocks)
            report["state"] = "completed" if not issues and len(results) == 11 else "partial"
        except (ProviderError, ValidationError, InvalidEvidence):
            issues.append("coordination_or_persy_output_unavailable_or_invalid")
        report["calls_attempted"] = calls
        report["duration_seconds"] = round(monotonic() - start, 3)
        return report
