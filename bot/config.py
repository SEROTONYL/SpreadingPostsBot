from __future__ import annotations

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    BOT_TOKEN: str
    ADMIN_USER_ID: int
    SQLITE_PATH: str = "bot/data.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


def load_settings() -> Settings:
    """Load settings for the application."""

    try:
        return Settings()
    except ValidationError as error:
        raise RuntimeError(
            "Missing required configuration. Ensure BOT_TOKEN and ADMIN_USER_ID are set in the environment."
        ) from error
