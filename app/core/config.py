"""Application configuration via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = Field(default="dev")
    log_level: str = Field(default="INFO")

    postgres_user: str = Field(default="app")
    postgres_password: str = Field(default="secret")
    postgres_db: str = Field(default="tasks")

    database_url: str = Field(
        default="postgresql+asyncpg://app:secret@localhost:5432/tasks",
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    jwt_secret: str = Field(default="change-me-super-secret-key-min-32-chars")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_ttl: int = Field(default=900, description="Access token TTL in seconds")
    jwt_refresh_ttl: int = Field(default=604800, description="Refresh token TTL in seconds")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
