from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


SourceType = Literal[
    "book",
    "journal_article",
    "report",
    "website",
    "manual",
    "archive",
    "dataset",
    "other",
]


class SourceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_type: SourceType
    title: str = Field(min_length=1, max_length=1000)
    authors: list[str] = Field(default_factory=list, max_length=100)
    publisher: str | None = Field(default=None, max_length=500)
    publication_date: date | None = None
    canonical_url: HttpUrl | None = None
    isbn: str | None = Field(default=None, max_length=32)
    doi: str | None = Field(default=None, max_length=255)
    language_code: str | None = Field(default=None, max_length=16)
    licence: str | None = Field(default=None, max_length=500)
    access_notes: str | None = Field(default=None, max_length=4000)
    relationship_note: str = Field(default="", max_length=2000)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    category_id: UUID | None = None


class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=1000)


class VerificationUpdate(BaseModel):
    verification_status: Literal["unverified", "under_review", "verified", "rejected"]
    verification_notes: str = Field(default="", max_length=4000)


class SourceResponse(BaseModel):
    id: UUID
    source_type: str
    title: str
    authors: list[str]
    publisher: str | None
    publication_date: date | None
    canonical_url: str | None
    isbn: str | None
    doi: str | None
    language_code: str | None
    licence: str | None
    access_notes: str | None
    source_status: str
    created_at: str
