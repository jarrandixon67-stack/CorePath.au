from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from specialists.registry import Domain

ShortText = Annotated[str, Field(min_length=3, max_length=600)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Task(StrictModel):
    question: str = Field(min_length=5, max_length=2000)
    search_terms: list[Annotated[str, Field(min_length=2, max_length=80)]] = Field(
        min_length=1, max_length=6
    )
    max_sources: int = Field(default=4, ge=1, le=6)


class Citation(StrictModel):
    section_id: UUID
    quote: str = Field(min_length=3, max_length=600)


class Finding(StrictModel):
    statement: str = Field(min_length=3, max_length=1200)
    citations: list[Citation] = Field(min_length=1, max_length=6)
    confidence: Literal["low", "moderate", "high"]
    limitations: ShortText


class Option(StrictModel):
    action: ShortText
    finding_indexes: list[Annotated[int, Field(ge=0, le=4)]] = Field(min_length=1, max_length=5)
    limitations: ShortText


class Contradiction(StrictModel):
    description: ShortText
    supporting_sections: list[UUID] = Field(min_length=1, max_length=6)
    challenging_sections: list[UUID] = Field(min_length=1, max_length=6)


class Collaboration(StrictModel):
    domain: Domain
    reason: ShortText


class Proposal(StrictModel):
    findings: list[Finding] = Field(max_length=5)
    options: list[Option] = Field(max_length=3)
    contradictions: list[Contradiction] = Field(max_length=3)
    knowledge_gaps: list[ShortText] = Field(max_length=5)
    collaboration_requests: list[Collaboration] = Field(max_length=3)


class ToolNeed(StrictModel):
    name: str = Field(min_length=3, max_length=100)
    priority: Literal["minimum_required", "next", "later"]
    purpose: ShortText
    required_data: list[ShortText] = Field(max_length=6)
    privacy_requirements: ShortText
    source_requirements: ShortText
    validation_before_use: ShortText
    alternative_without_tool: ShortText


class ToolNeeds(StrictModel):
    requests: list[ToolNeed] = Field(max_length=6)
    knowledge_gaps: list[ShortText] = Field(max_length=5)
    evaluation_needs: list[ShortText] = Field(min_length=1, max_length=5)


@dataclass(frozen=True)
class Capability:
    subject: str
    actor: str
    domain: str
    request_id: str
    expires_at: int


@dataclass(frozen=True)
class Access:
    identity_id: UUID
    domain_id: UUID
    library_id: UUID
    service_key: str


class AccessDenied(Exception):
    pass


class RunConflict(Exception):
    pass


class BudgetExceeded(Exception):
    pass


class InvalidEvidence(Exception):
    pass


class ProviderUnavailable(Exception):
    pass
