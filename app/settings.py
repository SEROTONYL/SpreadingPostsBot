from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    whapi_api_url: str = Field(default="https://gate.whapi.cloud", alias="WHAPI_API_URL")
    whapi_source_token: str = Field(alias="WHAPI_SOURCE_TOKEN")
    whapi_target_token: str = Field(alias="WHAPI_TARGET_TOKEN")
    webhook_secret: str = Field(alias="WEBHOOK_SECRET")

    db_path: Path = Field(default=Path("data/wa_mirror.db"), alias="DB_PATH")
    storage_dir: Path = Field(default=Path("data/storage"), alias="STORAGE_DIR")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    poll_interval_s: int = Field(default=10, alias="POLL_INTERVAL_S")
    max_attempts: int = Field(default=8, alias="MAX_ATTEMPTS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
