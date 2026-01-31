import asyncio
import logging
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from telethon import types

logger = logging.getLogger(__name__)


@dataclass
class VideoInfo:
    duration: int
    width: int
    height: int


def _parse_ffprobe_output(output: str) -> Optional[VideoInfo]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) < 3:
        return None
    try:
        width = int(float(lines[0]))
        height = int(float(lines[1]))
        duration = int(float(lines[2])) or 1
    except ValueError:
        return None
    return VideoInfo(duration=duration, width=width, height=height)


async def probe_video(path: str) -> VideoInfo:
    if shutil.which("ffprobe") is None:
        logger.warning("ffprobe not found, using fallback video metadata")
        return VideoInfo(duration=1, width=1080, height=1920)

    cmd = (
        "ffprobe -v error -select_streams v:0 "
        "-show_entries stream=width,height,duration -of default=nw=1:nk=1 "
        f"{shlex.quote(path)}"
    )

    def _run() -> Optional[str]:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return result.stdout
        except Exception:
            return None

    output = await asyncio.to_thread(_run)
    if not output:
        logger.warning("ffprobe failed, using fallback video metadata")
        return VideoInfo(duration=1, width=1080, height=1920)
    parsed = _parse_ffprobe_output(output)
    if parsed is None:
        logger.warning("ffprobe output could not be parsed, using fallback video metadata")
        return VideoInfo(duration=1, width=1080, height=1920)
    return parsed


def build_privacy_rules(story_privacy: str) -> list:
    if story_privacy == "contacts":
        return [types.InputPrivacyValueAllowContacts()]
    return [types.InputPrivacyValueAllowAll()]


def is_photo(media_type: Optional[str], prepared_path: str) -> bool:
    if media_type:
        return media_type.lower() in {"photo", "image"}
    ext = Path(prepared_path).suffix.lower()
    return ext in {".jpg", ".jpeg", ".png", ".webp"}


def extract_story_id(result: object) -> Optional[str]:
    updates = getattr(result, "updates", None)
    if not updates:
        return None
    for update in updates:
        if isinstance(update, types.UpdateStory):
            return str(update.story.id)
    return None
