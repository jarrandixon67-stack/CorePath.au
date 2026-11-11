from typing import Literal
from uuid import UUID

from pydantic import Field

from coordinator.models import ResearchRequest
from specialists.models import ShortText, StrictModel


class Privacy(StrictModel):
    model_processing_enabled: bool = False
    history_enabled: bool = False
    profile_context_enabled: bool = False
    communication_style: Literal["plain", "balanced", "detailed"] = "plain"


class PrivacyChange(Privacy):
    expected_revision: int = Field(ge=0)


class Message(StrictModel):
    message: str = Field(min_length=1, max_length=4000)
    use_profile_context: bool = False


class ResearchProposal(ResearchRequest):
    max_specialist_calls: int = Field(ge=1, le=4)
    allow_collaboration: bool


class Reply(StrictModel):
    message: str = Field(min_length=1, max_length=2400)
    next_steps: list[ShortText] = Field(max_length=3)
    follow_up: str | None = Field(max_length=400)
    research_proposal: ResearchProposal | None


class Approval(StrictModel):
    approve: Literal[True]


class ProfileAnalysis(StrictModel):
    turn_ids: list[UUID] = Field(min_length=1, max_length=5)
    purpose: str = Field(min_length=3, max_length=500)


class Missing(Exception):
    pass


class PrivacyRequired(Exception):
    pass
