from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CorePath Knowledge API"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str | None = None
    internal_api_token: str | None = None
    db_pool_min_size: int = Field(default=1, ge=1)
    db_pool_max_size: int = Field(default=5, ge=1)

    def validate_pool_bounds(self) -> None:
        if self.db_pool_max_size < self.db_pool_min_size:
            raise ValueError("DB_POOL_MAX_SIZE must be greater than or equal to DB_POOL_MIN_SIZE")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_pool_bounds()
    return settings
