from functools import lru_cache
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PERSY_", env_file=".env", extra="ignore")
    database_url: str | None = None
    encryption_key: str | None = None
    gateway_public_key: str | None = None
    gateway_issuer: str = "corepath-member-gateway"
    gateway_audience: str = "corepath-persy"
    exchange_url: str | None = None
    exchange_token: str | None = None
    coordinator_url: str | None = None
    coordinator_public_key: str | None = None
    coordinator_issuer: str = "corepath-service-gateway"
    coordinator_audience: str = "corepath-coordinator"
    service_subject: str = "corepath-persy"
    profile_url: str | None = None
    profile_public_key: str | None = None
    profile_issuer: str = "corepath-personal-ai"
    profile_audience: str = "corepath-life-profile"
    model: str | None = None
    openai_api_key: str | None = None
    model_timeout_seconds: float = Field(default=30, ge=1, le=60)
    service_timeout_seconds: float = Field(default=60, ge=1, le=180)
    max_output_tokens: int = Field(default=1800, ge=256, le=3000)
    max_context_chars: int = Field(default=60000, ge=5000, le=100000)
    history_turns: int = Field(default=8, ge=1, le=12)
    max_operations_per_24h: int = Field(default=30, ge=1, le=1000)
    max_concurrent_operations: int = Field(default=1, ge=1, le=5)
    max_conversations: int = Field(default=50, ge=1, le=200)
    max_turns: int = Field(default=200, ge=1, le=1000)
    lease_seconds: int = Field(default=240, ge=30, le=240)
    proposal_seconds: int = Field(default=900, ge=60, le=3600)

    @model_validator(mode="after")
    def fixed_destinations(self):
        for value in (self.exchange_url, self.coordinator_url, self.profile_url):
            if value:
                url = urlsplit(value)
                if (
                    url.scheme != "https"
                    or not url.hostname
                    or url.username
                    or url.password
                    or url.query
                    or url.fragment
                ):
                    raise ValueError("Fixed trusted HTTPS service URLs are required")
        if not self.service_subject.strip() or len(self.service_subject) > 200:
            raise ValueError("Invalid Personal AI service subject")
        return self

    def cipher(self):
        if not self.encryption_key:
            raise ValueError("Persy encryption is not configured")
        return Fernet(self.encryption_key.encode("ascii"))


@lru_cache
def get_settings():
    return Settings()
