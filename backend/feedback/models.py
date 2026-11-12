from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from partners.models import Model, public_url


class FeedbackEntry(Model):
    client_reference: UUID = Field(default_factory=uuid4)
    positive: str = Field(default="", max_length=3000)
    negative: str = Field(default="", max_length=3000)
    suggestions: str = Field(default="", max_length=2000)
    allow_ai_analysis: bool = False

    @model_validator(mode="after")
    def meaningful(self):
        if not any([self.positive, self.negative, self.suggestions]):
            raise ValueError("Share what worked, what did not, or a suggestion")
        return self


class ImportedReview(Model):
    source_url: str = Field(max_length=2000)
    source_reference: str = Field(min_length=1, max_length=300)
    contributor_reference: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=6000)
    rights_and_analysis_basis_reviewed: bool = False
    permission_notes: str = Field(min_length=20, max_length=2000)
    reviewed_at: datetime
    published_at: datetime

    @model_validator(mode="after")
    def permission(self):
        self.source_url = public_url(self.source_url)
        if (
            not self.rights_and_analysis_basis_reviewed
            or self.reviewed_at.tzinfo is None
            or self.published_at.tzinfo is None
            or self.reviewed_at > datetime.now(UTC)
            or self.published_at > datetime.now(UTC)
        ):
            raise ValueError(
                "A reviewed source permission/analysis basis and timezone are required"
            )
        return self


class Citation(Model):
    record_id: UUID
    field: Literal["positive", "negative", "suggestions", "review"]
    quote: str = Field(min_length=1, max_length=600)


class Theme(Model):
    kind: Literal["praise", "improvement", "concern"]
    severity: Literal["ordinary", "urgent"]
    category: Literal[
        "service_quality",
        "pricing",
        "privacy",
        "safety",
        "claims",
        "accessibility",
        "experience",
        "other",
    ]
    title: str = Field(min_length=1, max_length=150)
    summary: str = Field(min_length=1, max_length=1500)
    citations: list[Citation] = Field(min_length=1, max_length=30)


class Analysis(Model):
    themes: list[Theme] = Field(max_length=15)
    limitations: list[str] = Field(max_length=15)


class Resolution(Model):
    state: Literal["acknowledged", "investigating", "resolved", "dismissed"]
    reason: str = Field(min_length=20, max_length=2000)


class PromptPreference(Model):
    allow_requests: bool


class ConsentChange(Model):
    allow_ai_analysis: bool
