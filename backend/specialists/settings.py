from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from specialists.registry import Domain


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPECIALISTS_", env_file=".env", extra="ignore")
    database_url: str | None = None
    gateway_public_key: str | None = None
    gateway_issuer: str = "corepath-service-gateway"
    gateway_audience: str = "corepath-specialists"
    openai_api_key: str | None = None
    model: str | None = None
    model_overrides: dict[str, str] = Field(default_factory=dict)
    max_output_tokens: int = Field(default=2400, ge=256, le=4000)
    model_timeout_seconds: float = Field(default=30, ge=1, le=60)
    max_runs_per_24h: int = Field(default=20, ge=1, le=1000)
    max_concurrent_runs: int = Field(default=2, ge=1, le=10)
    max_sources: int = Field(default=6, ge=1, le=6)

    @model_validator(mode="after")
    def valid_overrides(self):
        if any(
            key not in {d.value for d in Domain} or not value.strip()
            for key, value in self.model_overrides.items()
        ):
            raise ValueError("Model overrides must name a known specialist and a nonempty model.")
        return self

    def model_for(self, domain: Domain) -> str | None:
        return self.model_overrides.get(domain.value, self.model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
