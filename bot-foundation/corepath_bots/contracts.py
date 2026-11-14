"""Validated hand-offs. Model output is always a proposal, never authority."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Domain(StrEnum):
    PERSONAL = "personal-development"
    PHYSICAL = "physical-development"
    NUTRITION = "nutrition"
    MENTAL = "mental-wellbeing"
    RELATIONSHIPS = "relationships"
    LEARNING = "learning-intelligence"
    FINANCIAL = "financial-capability"
    CAREER = "career-business"
    PRACTICAL = "practical-life-skills"
    PARENTING = "parenting-family"
    RECREATION = "recreation-discovery"


class Source(Model):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2000)
    checked_at: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=12000)
    domains: list[Domain] = Field(min_length=1, max_length=11)
    approved_for_model: Literal[True]
    public: Literal[True]


class Assignment(Model):
    domain: Domain
    task: str = Field(min_length=5, max_length=2200)
    expected_result: str = Field(min_length=5, max_length=600)
    criteria: list[str] = Field(min_length=1, max_length=8)
    priority: Literal["routine", "important", "urgent"]
    completion_criteria: str = Field(min_length=5, max_length=800)


class Citation(Model):
    source_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=3, max_length=600)


class Claim(Model):
    statement: str = Field(min_length=3, max_length=800)
    citations: list[Citation] = Field(min_length=1, max_length=4)
    confidence: Literal["low", "moderate", "high"]
    limitations: str = Field(min_length=3, max_length=600)


class Contribution(Model):
    relevant: bool
    summary: str = Field(min_length=3, max_length=700)
    claims: list[Claim] = Field(max_length=3)
    questions: list[str] = Field(max_length=2)
    gaps: list[str] = Field(max_length=4)
    peer_requests: list[Domain] = Field(max_length=10)
    referral_reason: str | None = Field(max_length=500)

    @model_validator(mode="after")
    def relevance(self):
        if not self.relevant and (self.claims or self.peer_requests or self.referral_reason):
            raise ValueError("No relevant contribution cannot contain claims or referrals")
        if len(set(self.peer_requests)) != len(self.peer_requests):
            raise ValueError("Duplicate peer requests")
        return self


class ClaimRef(Model):
    domain: Domain
    index: int = Field(ge=0, le=2)


class Conclusion(Model):
    statement: str = Field(min_length=3, max_length=1000)
    references: list[ClaimRef] = Field(min_length=1, max_length=11)
    confidence: Literal["low", "moderate", "high"]
    limitations: str = Field(min_length=3, max_length=700)


class Disagreement(Model):
    description: str = Field(min_length=3, max_length=700)
    supporting: list[ClaimRef] = Field(min_length=1, max_length=11)
    challenging: list[ClaimRef] = Field(min_length=1, max_length=11)


class Feedback(Model):
    domain: Domain
    contribution: str = Field(min_length=3, max_length=500)
    improvement: str = Field(min_length=3, max_length=500)


class Synthesis(Model):
    conclusions: list[Conclusion] = Field(max_length=6)
    disagreements: list[Disagreement] = Field(max_length=6)
    gaps: list[str] = Field(max_length=12)
    questions: list[str] = Field(max_length=3)
    feedback: list[Feedback] = Field(min_length=11, max_length=11)


class PersyReply(Model):
    opening: str = Field(min_length=3, max_length=700)
    # Advice text is assembled by the server from selected validated conclusions.
    conclusion_indexes: list[int] = Field(max_length=6)
    closing_question: str | None = Field(max_length=300)


class Idea(Model):
    title: str = Field(min_length=3, max_length=150)
    beneficiaries: str = Field(min_length=3, max_length=500)
    proposal: str = Field(min_length=3, max_length=1200)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    objections_and_uncertainty: str = Field(min_length=3, max_length=1000)
    established_vs_original: str = Field(min_length=3, max_length=600)
    transfer_assumptions: str = Field(min_length=3, max_length=600)
    proposed_test: str = Field(min_length=3, max_length=700)
    permissions_needed: list[str] = Field(max_length=8)


class TwelveReport(Model):
    ideas: list[Idea] = Field(max_length=5)
    issues: list[str] = Field(max_length=10)
