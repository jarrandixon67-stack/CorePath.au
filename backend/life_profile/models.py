from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Category(StrEnum):
    HEALTH = "health_wellbeing"
    RELATIONSHIPS = "relationships_connections"
    ANIMALS = "pets_animals"
    CULTURE = "culture_heritage"
    GROWTH = "personal_growth_development"
    CAREER = "career_finances"
    ENVIRONMENT = "nature_environment"
    HOME = "home_living"
    OTHER = "other_connections_interests"


class Dimension(StrEnum):
    IDENTITY = "self_identity"
    EMOTIONAL = "emotional"
    MENTAL = "mental"
    SPIRITUAL = "spiritual"
    PHYSICAL = "physical"
    SOCIAL = "social"
    FINANCIAL = "financial"
    BIOLOGICAL = "biological"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Consent(StrictModel):
    analysis_enabled: bool = False
    external_model_processing: bool = False
    personalisation_enabled: bool = False
    sensitive_observations_enabled: bool = False
    categories: list[Category] = Field(default_factory=list, max_length=9)
    purpose: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_permissions(self):
        if self.analysis_enabled and not self.categories:
            raise ValueError("Select the categories the bot may analyse.")
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Categories must be unique.")
        return self


class SourceMessage(StrictModel):
    message_id: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)
    source_type: Literal["conversation", "reflection", "user_update", "journal_entry"]
    speaker: Literal["user"]
    content: str = Field(min_length=1, max_length=4000)
    observed_at: AwareDatetime | None = None


class AnalyseRequest(StrictModel):
    purpose: str = Field(min_length=3, max_length=500)
    messages: list[SourceMessage] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_messages(self):
        if len({m.message_id for m in self.messages}) != len(self.messages):
            raise ValueError("Message IDs must be unique.")
        if sum(len(m.content) for m in self.messages) > 20000:
            raise ValueError("Select at most 20,000 characters of relevant conversation.")
        return self


class Evidence(StrictModel):
    message_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=1000)


class Observation(StrictModel):
    category: Category
    dimensions: list[Dimension] = Field(min_length=1, max_length=8)
    kind: Literal["user_statement", "observed_pattern", "hypothesis"]
    statement: str = Field(min_length=3, max_length=1000)
    evidence: list[Evidence] = Field(min_length=1, max_length=8)
    confidence: Literal["low", "moderate", "high"]
    confidence_reason: str = Field(min_length=3, max_length=1000)
    sensitive: bool
    collection_reason: str = Field(min_length=3, max_length=500)


class FollowUp(StrictModel):
    question: str = Field(min_length=3, max_length=500)
    reason: str = Field(min_length=3, max_length=500)
    category: Category


class Proposal(StrictModel):
    observations: list[Observation] = Field(max_length=5)
    follow_up: FollowUp | None


class Decision(StrictModel):
    expected_version: int = Field(ge=1)
    action: Literal["accept", "correct", "reject"]
    corrected_statement: str | None = Field(default=None, min_length=3, max_length=1000)
    share_with_personal_ai: bool = False

    @model_validator(mode="after")
    def validate_correction(self):
        if (self.action == "correct") != (self.corrected_statement is not None):
            raise ValueError("A correction must provide the corrected statement, and only then.")
        if self.action == "reject" and self.share_with_personal_ai:
            raise ValueError("Rejected observations cannot be shared.")
        return self
