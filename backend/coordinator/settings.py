from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COORDINATOR_", env_file=".env", extra="ignore")
    database_url: str | None = None
    gateway_public_key: str | None = None
    gateway_issuer: str = "corepath-service-gateway"
    gateway_audience: str = "corepath-coordinator"
    service_subject: str = "corepath-coordinator"
    specialist_url: str | None = None
    exchange_url: str | None = None
    exchange_token: str | None = None
    specialist_public_key: str | None = None
    specialist_issuer: str = "corepath-service-gateway"
    specialist_audience: str = "corepath-specialists"
    openai_api_key: str | None = None
    model: str | None = None
    max_output_tokens: int = Field(default=3000, ge=256, le=5000)
    model_timeout_seconds: float = Field(default=30, ge=1, le=60)
    specialist_timeout_seconds: float = Field(default=45, ge=1, le=90)
    max_context_chars: int = Field(default=80000, ge=4000, le=200000)
    max_specialist_calls: int = Field(default=4, ge=1, le=11)
    max_runs_per_24h: int = Field(default=20, ge=1, le=1000)
    max_concurrent_runs: int = Field(default=1, ge=1, le=10)
    max_duration_seconds: int = Field(default=180, ge=30, le=240)

    @model_validator(mode="after")
    def trusted_urls(self):
        for value in (self.specialist_url, self.exchange_url):
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
                    raise ValueError(
                        "Service endpoints require fixed HTTPS URLs without credentials/query/fragment"
                    )
        if not self.service_subject.strip() or len(self.service_subject) > 200:
            raise ValueError("Invalid Coordinator service subject")
        return self


@lru_cache
def get_settings():
    return Settings()
