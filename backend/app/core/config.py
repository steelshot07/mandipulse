"""Application settings loaded from environment variables (and backend/.env in development)."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Secrets come only from the environment, never from code."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: str = ""
    datagov_api_key: str = ""
    telegram_bot_token: str = ""
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    log_level: str = "INFO"
    rate_limit_per_minute: int = 120

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string, e.g. ``http://a.com,http://b.com``."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _no_wildcard_cors_in_production(self) -> "Settings":
        """Refuse to start in production with CORS open to every origin."""
        if self.env == "production" and "*" in self.allowed_origins:
            raise ValueError("ALLOWED_ORIGINS must list real origins in production, not '*'")
        return self

    @property
    def sqlalchemy_url(self) -> str:
        """Database URL with the psycopg 3 driver selected for SQLAlchemy."""
        url = self.database_url
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
