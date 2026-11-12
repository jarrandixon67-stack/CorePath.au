from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from partners.models import email_address, public_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PARTNERS_", env_file=".env", extra="ignore")
    database_url: str | None = None
    gateway_public_key: str | None = None
    gateway_issuer: str = "corepath-partner-gateway"
    gateway_audience: str = "corepath-partners"
    email_delivery_enabled: bool = False
    email_api_key: str | None = None
    sender_email: str | None = None
    sender_legal_name: str | None = None
    sender_contact: str | None = None
    reply_to: str | None = None
    public_base_url: str | None = None
    allowed_countries: set[str] = {"AU"}
    allowed_sectors: set[str] = {"health_and_wellbeing"}
    daily_email_limit: int = Field(default=10, ge=1, le=10000)
    openai_api_key: str | None = None
    model: str | None = None
    worker_subject: str | None = None

    @model_validator(mode="after")
    def validate_sender(self):
        for name in ("sender_email", "reply_to"):
            value = getattr(self, name)
            if value:
                setattr(self, name, email_address(value))
        if self.public_base_url:
            self.public_base_url = public_url(self.public_base_url).rstrip("/")
            from urllib.parse import urlsplit

            url = urlsplit(self.public_base_url)
            if url.path or url.query:
                raise ValueError("Public base URL must be an HTTPS origin")
        for value in (self.sender_legal_name, self.sender_contact):
            if value and (len(value) > 500 or "\r" in value or "\n" in value):
                raise ValueError("Sender identity must be one bounded line")
        return self

    def delivery_ready(self):
        return self.email_delivery_enabled and all(
            [
                self.email_api_key,
                self.sender_email,
                self.sender_legal_name,
                self.sender_contact,
                self.reply_to,
                self.public_base_url,
            ]
        )


@lru_cache
def get_settings():
    return Settings()
