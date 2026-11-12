from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FEEDBACK_", env_file=".env", extra="ignore")
    database_url: str | None = None
    encryption_key: str | None = None
    owner_hash_key: str | None = Field(default=None, min_length=32)
    gateway_public_key: str | None = None
    gateway_issuer: str = "corepath-feedback-gateway"
    gateway_audience: str = "corepath-feedback"
    openai_api_key: str | None = None
    model: str | None = None
    max_context_chars: int = Field(default=50000, ge=10000, le=200000)
    min_contributors: int = Field(default=3, ge=3, le=30)
    analysis_window_days: int = Field(default=90, ge=1, le=365)
    global_prompt_cooldown_days: int = Field(default=7, ge=1, le=90)
    prompt_cooldown_days: int = Field(default=30, ge=7, le=365)


@lru_cache
def get_settings():
    return Settings()
