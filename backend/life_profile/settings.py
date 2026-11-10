import os
from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIFE_PROFILE_", env_file=".env", extra="ignore")
    database_url: str | None = None
    encryption_key: str | None = None
    gateway_public_key: str | None = None
    gateway_issuer: str = "corepath-personal-ai"
    gateway_audience: str = "corepath-life-profile"
    model: str | None = None
    openai_api_key: str | None = None
    model_timeout_seconds: float = Field(default=30, ge=1, le=60)

    def validate_database_separation(self):
        if self.database_url and self.database_url == os.getenv("DATABASE_URL"):
            raise ValueError(
                "Life Profile requires a separate database from knowledge infrastructure."
            )

    def cipher(self) -> Fernet:
        if not self.encryption_key:
            raise ValueError("Life Profile encryption is not configured.")
        return Fernet(self.encryption_key.encode("ascii"))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_database_separation()
    return settings
