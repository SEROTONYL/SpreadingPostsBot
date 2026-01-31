import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings


load_dotenv()


class Settings(BaseSettings):
    tg_api_id: int
    tg_api_hash: str
    tg_phone: str
    tg_session_path: str = "publisher/session/mom.session"
    sqlite_path: str
    publish_peer: str = "me"
    story_privacy: str = "all"
    story_period_seconds: int = 86400
    poll_interval_seconds: int = 5
    max_per_batch: int = 3

    class Config:
        env_prefix = ""


def get_settings() -> Settings:
    settings = Settings()
    session_dir = Path(settings.tg_session_path).expanduser().resolve().parent
    os.makedirs(session_dir, exist_ok=True)
    return settings
