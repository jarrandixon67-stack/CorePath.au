from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from specialists.models import Collaboration, Contradiction, Option, ShortText, StrictModel, Task
from specialists.registry import Domain


class ResearchRequest(StrictModel):
    question: str = Field(min_length=5, max_length=2000)
    allowed_domains: list[Domain] = Field(min_length=1, max_length=11)
    max_specialist_calls: int = Field(default=4, ge=1, le=11)
    allow_collaboration: bool = False

    @model_validator(mode="after")
    def distinct_domains(self):
        if len(set(self.allowed_domains)) != len(self.allowed_domains):
            raise ValueError("Allowed domains must be distinct")
        return self


class ResearchTask(Task):
    max_sources: int = Field(ge=1, le=6)


class Assignment(StrictModel):
    domain: Domain
    rationale: ShortText
    task: ResearchTask


class Plan(StrictModel):
    decision: Literal["research", "clarify"]
    rationale: ShortText
    questions: list[ShortText] = Field(max_length=3)
    assignments: list[Assignment] = Field(max_length=11)

    @model_validator(mode="after")
    def coherent_decision(self):
        if self.decision == "clarify" and (self.assignments or not self.questions):
            raise ValueError("Clarification requires questions and no dispatch")
        if self.decision == "research" and (not self.assignments or self.questions):
            raise ValueError("Research requires assignments and no pending clarification")
        return self


class CollaborationPlan(StrictModel):
    rationale: ShortText
    assignments: list[Assignment] = Field(max_length=11)


class SourceCitation(StrictModel):
    section_id: UUID
    source_id: UUID
    title: str = Field(max_length=400)
    authors: list[Annotated[str, Field(max_length=200)]] = Field(max_length=10)
    canonical_url: str | None = Field(max_length=2000)
    locator: str = Field(max_length=400)
    publication_date: str | None = Field(max_length=40)
    quote: str = Field(min_length=3, max_length=600)
    source_verification: Literal["verified"]
    claim_assessment: Literal["proposed_not_accepted"]


class SpecialistFinding(StrictModel):
    statement: str = Field(min_length=3, max_length=1200)
    citations: list[SourceCitation] = Field(min_length=1, max_length=6)
    confidence: Literal["low", "moderate", "high"]
    limitations: ShortText


class SpecialistResult(StrictModel):
    run_id: UUID
    state: Literal["completed", "needs_evidence"]
    specialist: Domain
    findings: list[SpecialistFinding] = Field(max_length=5)
    options: list[Option] = Field(max_length=3)
    contradictions: list[Contradiction] = Field(max_length=3)
    knowledge_gaps: list[ShortText] = Field(max_length=5)
    collaboration_requests: list[Collaboration] = Field(max_length=3)
    collaboration_executed: Literal[False]
    review_required: Literal[True]
    audience: Literal["coordinator_internal"]
    life_profile_access: Literal[False]

    @model_validator(mode="after")
    def coherent_evidence(self):
        if bool(self.findings) != (self.state == "completed"):
            raise ValueError("Specialist state and findings disagree")
        if any(i >= len(self.findings) for option in self.options for i in option.finding_indexes):
            raise ValueError("Unknown specialist finding reference")
        return self


class EvidenceRef(StrictModel):
    task_id: UUID
    finding_index: int = Field(ge=0, le=4)


class Conclusion(StrictModel):
    statement: str = Field(min_length=3, max_length=1200)
    references: list[EvidenceRef] = Field(min_length=1, max_length=8)
    confidence: Literal["low", "moderate", "high"]
    limitations: ShortText


class PracticalOption(StrictModel):
    action: ShortText
    references: list[EvidenceRef] = Field(min_length=1, max_length=8)
    limitations: ShortText


class Disagreement(StrictModel):
    description: ShortText
    supporting: list[EvidenceRef] = Field(min_length=1, max_length=8)
    challenging: list[EvidenceRef] = Field(min_length=1, max_length=8)


class Synthesis(StrictModel):
    conclusions: list[Conclusion] = Field(max_length=6)
    options: list[PracticalOption] = Field(max_length=4)
    disagreements: list[Disagreement] = Field(max_length=6)
    knowledge_gaps: list[ShortText] = Field(max_length=6)
