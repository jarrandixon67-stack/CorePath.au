import hashlib
import re
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Criterion(StrEnum):
    IDENTITY = "identity_and_licensing"
    PRICING = "pricing_and_terms"
    QUALITY = "quality_evidence"
    COMPLAINTS = "complaints_process"
    SAFETY = "safety_and_regulatory"
    HEALTH_SCOPE = "health_credentials_and_scope"
    HEALTH_CLAIMS = "health_claims_and_evidence"
    HEALTH_CONSENT = "health_consent_and_referral"
    HEALTH_PRIVACY = "health_privacy_and_conflicts"


class Kind(StrEnum):
    REGISTRY = "official_registry"
    REGULATOR = "regulator"
    WEBSITE = "business_website"
    INDEPENDENT = "independent_quality"
    TRADITIONAL = "traditional_knowledge"
    EXPERIENCE = "practitioner_experience"
    OTHER = "other"


def public_url(value: str) -> str:
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.port not in (None, 443)
        or any(ord(c) < 33 for c in value)
    ):
        raise ValueError("Use a public HTTPS source without credentials")
    host = url.hostname.encode("idna").decode().lower()
    if "." not in host or host.endswith((".local", ".localhost", ".internal")):
        raise ValueError("Use a public source hostname")
    import ipaddress

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP literal sources are not supported")
    return urlunsplit(("https", host, url.path or "/", url.query, ""))


def email_address(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(
        r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value
    ):
        raise ValueError("Use one business email address without display names or headers")
    if ".." in value or value.startswith(".") or ".@" in value:
        raise ValueError("Invalid business email")
    return value


class BusinessSeed(Model):
    name: str = Field(min_length=1, max_length=240)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    category: str = Field(min_length=1, max_length=100)
    sector: str = Field(default="unclassified", pattern=r"^[a-z][a-z0-9_]{1,79}$")
    locality: str = Field(default="", max_length=200)
    registration_number: str | None = Field(default=None, max_length=80)
    website: str | None = Field(default=None, max_length=2000)
    source_url: str = Field(max_length=2000)
    attribution: str = Field(min_length=1, max_length=300)

    @field_validator("source_url", "website")
    @classmethod
    def urls(cls, value):
        return public_url(value) if value else value

    def identity_key(self):
        if self.registration_number:
            basis = "registration:" + re.sub(r"\s", "", self.registration_number).casefold()
        elif self.website:
            basis = "domain:" + urlsplit(self.website).hostname.removeprefix("www.")
        else:
            basis = "source:" + self.source_url
        return hashlib.sha256((self.country + ":" + basis).encode()).hexdigest()


class Evidence(Model):
    id: UUID = Field(default_factory=uuid4)
    criterion: Criterion
    result: str = Field(pattern=r"^(pass|fail|unknown)$")
    kind: Kind
    source_url: str = Field(max_length=2000)
    title: str = Field(min_length=1, max_length=300)
    excerpt: str = Field(min_length=1, max_length=6000)
    rationale: str = Field(min_length=1, max_length=2000)
    checked_at: datetime
    valid_until: datetime

    @field_validator("source_url")
    @classmethod
    def url(cls, value):
        return public_url(value)

    @model_validator(mode="after")
    def dates(self):
        if self.checked_at.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("Evidence dates must include a timezone")
        if self.checked_at > datetime.now(UTC) or self.valid_until <= self.checked_at:
            raise ValueError("Evidence needs a past check and later expiry")
        return self


class Policy(Model):
    name: str = Field(min_length=1, max_length=150)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    sector: str = Field(default="health_and_wellbeing", pattern=r"^[a-z][a-z0-9_]{1,79}$")
    max_age_days: int = Field(default=90, ge=1, le=365)
    requirements: list[Criterion] = Field(default_factory=lambda: list(Criterion))

    @model_validator(mode="after")
    def baseline(self):
        baseline = {
            Criterion.IDENTITY,
            Criterion.PRICING,
            Criterion.QUALITY,
            Criterion.COMPLAINTS,
            Criterion.SAFETY,
        }
        if self.sector == "health_and_wellbeing":
            baseline = set(Criterion)
        if not baseline.issubset(self.requirements) or len(set(self.requirements)) != len(
            self.requirements
        ):
            raise ValueError(
                "All baseline and sector-specific requirements are mandatory exactly once"
            )
        return self


class Contact(Model):
    email: str
    basis: str = Field(pattern=r"^(express_consent|reviewed_inferred_consent)$")
    consent_source_url: str = Field(max_length=2000)
    consent_notes: str = Field(min_length=20, max_length=2000)
    commission_compatible: bool = False
    commission_review_url: str | None = Field(default=None, max_length=2000)
    commission_review_notes: str = Field(default="", max_length=2000)
    commission_basis_points: int = Field(default=1000, ge=1000, le=1000)
    consent_at: datetime
    valid_until: datetime

    _email = field_validator("email")(email_address)
    _source = field_validator("consent_source_url")(public_url)

    @field_validator("commission_review_url")
    @classmethod
    def commission_source(cls, value):
        return public_url(value) if value else value

    @model_validator(mode="after")
    def dates(self):
        if self.consent_at.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("Consent dates must include a timezone")
        if self.consent_at > datetime.now(UTC) or self.valid_until <= datetime.now(UTC):
            raise ValueError("Consent must be current")
        return self


class DiscoveryRequest(Model):
    country: str = Field(default="AU", pattern=r"^[A-Z]{2}$")
    bbox: tuple[float, float, float, float]
    sector: str = Field(default="health_and_wellbeing", pattern=r"^health_and_wellbeing$")
    limit: int = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def bounded_area(self):
        south, west, north, east = self.bbox
        if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
            raise ValueError("Use south, west, north, east in valid geographic bounds")
        if (north - south) * (east - west) > 1:
            raise ValueError("Search one small area at a time (at most one square degree)")
        return self


class AssessmentRequest(Model):
    policy_id: UUID


class Review(Model):
    verified: bool
    reason: str = Field(min_length=10, max_length=1000)


class Suppression(Model):
    email: str
    reason: str = Field(min_length=3, max_length=300)
    _email = field_validator("email")(email_address)


class InvitationRequest(Model):
    assessment_id: UUID


class BatchRequest(Model):
    policy_id: UUID
    business_ids: list[UUID] = Field(min_length=1, max_length=25)
