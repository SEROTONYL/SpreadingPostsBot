from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    BOT_TOKEN: str
    ADMIN_USER_ID: int | None = None
    SQLITE_PATH: str = "bot/data.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


def load_settings() -> Settings:
    """Load settings for the application."""

    return Settings()
