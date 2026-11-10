from specialists.models import (
    AccessDenied,
    Capability,
    InvalidEvidence,
    Proposal,
    ProviderUnavailable,
    RunConflict,
    Task,
)
from specialists.provider import Provider
from specialists.registry import SPECIALISTS, Domain
from specialists.repository import Repository
from specialists.settings import Settings


def grounded_result(domain: Domain, proposal: Proposal, sections: list[dict]) -> dict:
    sources = {section["section_id"]: section for section in sections}
    findings = []
    for finding in proposal.findings:
        citations = []
        for citation in finding.citations:
            source = sources.get(str(citation.section_id))
            if source is None or citation.quote not in source["content"]:
                raise InvalidEvidence("A citation did not match a supplied, authorised excerpt.")
            citations.append(
                {
                    "section_id": source["section_id"],
                    "source_id": source["source_id"],
                    "title": source["title"],
                    "authors": source["authors"],
                    "canonical_url": source["canonical_url"],
                    "locator": source["locator"],
                    "publication_date": source["publication_date"],
                    "quote": citation.quote,
                    "source_verification": "verified",
                    "claim_assessment": "proposed_not_accepted",
                }
            )
        findings.append(
            {
                "statement": finding.statement,
                "citations": citations,
                "confidence": finding.confidence,
                "limitations": finding.limitations,
            }
        )
    for option in proposal.options:
        if any(index >= len(findings) for index in option.finding_indexes):
            raise InvalidEvidence("A practical option referenced a finding that does not exist.")
    for conflict in proposal.contradictions:
        support = {str(s) for s in conflict.supporting_sections}
        challenge = {str(s) for s in conflict.challenging_sections}
        if support & challenge or not (support | challenge) <= sources.keys():
            raise InvalidEvidence("A contradiction used missing or identical source sections.")
    if len({c.domain for c in proposal.collaboration_requests}) != len(
        proposal.collaboration_requests
    ):
        raise InvalidEvidence("Duplicate collaboration requests are not permitted.")
    if any(c.domain == domain for c in proposal.collaboration_requests):
        raise InvalidEvidence("A specialist cannot request itself as a peer collaborator.")
    return {
        "specialist": domain.value,
        "findings": findings,
        "options": [option.model_dump(mode="json") for option in proposal.options],
        "contradictions": [item.model_dump(mode="json") for item in proposal.contradictions],
        "knowledge_gaps": proposal.knowledge_gaps,
        "collaboration_requests": [
            item.model_dump(mode="json") for item in proposal.collaboration_requests
        ],
        "collaboration_executed": False,
        "review_required": True,
        "audience": "coordinator_internal",
        "life_profile_access": False,
    }


class Runtime:
    def __init__(self, repository: Repository, provider: Provider, settings: Settings):
        self.repository, self.provider, self.settings = repository, provider, settings

    def execute(self, capability: Capability, domain: Domain, task: Task) -> dict:
        specialist = SPECIALISTS[domain]
        run_id, access = self.repository.start(capability, specialist, task, self.settings)
        try:
            sections = self.repository.retrieve(capability, domain, task, self.settings)
            if not sections:
                result = grounded_result(
                    domain,
                    Proposal(
                        findings=[],
                        options=[],
                        contradictions=[],
                        collaboration_requests=[],
                        knowledge_gaps=[
                            "No relevant, verified and model-use-approved library excerpts were available. Authorised source ingestion/review is required."
                        ],
                    ),
                    [],
                )
                state = "needs_evidence"
            else:
                context = {
                    "discipline": domain.value,
                    "question": task.question,
                    "library_excerpts": [
                        {k: v for k, v in s.items() if k != "fingerprint"} for s in sections
                    ],
                }
                proposal = self.provider.propose(specialist, context)
                result = grounded_result(domain, proposal, sections)
                state = "completed" if result["findings"] else "needs_evidence"
                if not result["findings"] and not result["knowledge_gaps"]:
                    result["knowledge_gaps"] = [
                        "The specialist returned no supported findings; further authorised evidence is needed."
                    ]
            self.repository.finish(capability, domain, run_id, result, sections, state)
            return {"run_id": str(run_id), "state": state, **result}
        except ProviderUnavailable:
            self.repository.fail(access, run_id, "model_unavailable")
            raise
        except InvalidEvidence:
            self.repository.fail(access, run_id, "invalid_evidence")
            raise
        except (AccessDenied, RunConflict):
            self.repository.fail(access, run_id, "scope_or_evidence_changed")
            raise
        except Exception:
            self.repository.fail(access, run_id, "execution_failed")
            raise
