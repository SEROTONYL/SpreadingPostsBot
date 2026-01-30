"""Media preparation utilities for 9:16 stories."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_TARGET_WIDTH = 1080
_TARGET_HEIGHT = 1920
_STORY_RATIO = 9 / 16
_RATIO_TOLERANCE = 0.02
_TASK_ID_PATTERN = re.compile(r"task_(\d+)")


async def _run_command(command: list[str]) -> tuple[int, str, str]:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing executable: {command[0]}") from exc

    stdout, stderr = await process.communicate()
    stdout_text = stdout.decode().strip() if stdout else ""
    stderr_text = stderr.decode().strip() if stderr else ""
    return process.returncode, stdout_text, stderr_text


async def probe_dimensions(path: Path) -> tuple[int, int]:
    """Probe width/height using ffprobe for images or videos."""

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        path.as_posix(),
    ]
    return_code, stdout_text, stderr_text = await _run_command(command)
    if return_code != 0:
        raise RuntimeError(f"ffprobe failed: {stderr_text or stdout_text}")

    if not stdout_text or "x" not in stdout_text:
        raise RuntimeError("ffprobe did not return dimensions")

    width_text, height_text = stdout_text.split("x", maxsplit=1)
    try:
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise RuntimeError(f"invalid dimensions: {stdout_text}") from exc

    if width <= 0 or height <= 0:
        raise RuntimeError(f"invalid dimensions: {stdout_text}")

    return width, height


def is_already_story_ratio(width: int, height: int) -> bool:
    """Return True if the media is already close to a 9:16 ratio."""

    if height == 0:
        return False
    ratio = width / height
    return abs(ratio - _STORY_RATIO) / _STORY_RATIO <= _RATIO_TOLERANCE


def _extract_task_id(out_path: Path) -> str | None:
    match = _TASK_ID_PATTERN.search(out_path.stem)
    if match:
        return match.group(1)
    return None


async def prepare_photo_story(src_path: Path, out_path: Path) -> Path:
    """Prepare a photo into a 9:16 story with blur background."""

    filter_graph = (
        "[0:v]"
        f"scale={_TARGET_WIDTH}:{_TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={_TARGET_WIDTH}:{_TARGET_HEIGHT},"
        "boxblur=20:1[bg];"
        "[0:v]"
        f"scale={_TARGET_WIDTH}:{_TARGET_HEIGHT}:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        src_path.as_posix(),
        "-filter_complex",
        filter_graph,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        out_path.as_posix(),
    ]
    return_code, stdout_text, stderr_text = await _run_command(command)
    if return_code != 0:
        raise RuntimeError(f"ffmpeg photo failed: {stderr_text or stdout_text}")
    return out_path


async def prepare_video_story(src_path: Path, out_path: Path) -> Path:
    """Prepare a video into a 9:16 story with blur background."""

    filter_graph = (
        "[0:v]"
        f"scale={_TARGET_WIDTH}:{_TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={_TARGET_WIDTH}:{_TARGET_HEIGHT},"
        "boxblur=20:1[bg];"
        "[0:v]"
        f"scale={_TARGET_WIDTH}:{_TARGET_HEIGHT}:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        src_path.as_posix(),
        "-filter_complex",
        filter_graph,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        out_path.as_posix(),
    ]
    return_code, stdout_text, stderr_text = await _run_command(command)
    if return_code != 0:
        raise RuntimeError(f"ffmpeg video failed: {stderr_text or stdout_text}")
    return out_path


async def prepare_to_story(src_path: Path, media_type: str, out_path: Path) -> Path:
    """Prepare media for 9:16 stories and return the prepared path."""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = await probe_dimensions(src_path)
    if is_already_story_ratio(width, height):
        task_id = _extract_task_id(out_path)
        if task_id:
            logger.info("prepare skip (already 9:16) task_id %s", task_id)
        else:
            logger.info("prepare skip (already 9:16) src %s", src_path.as_posix())
        shutil.copy2(src_path, out_path)
        return out_path

    if media_type == "photo":
        return await prepare_photo_story(src_path, out_path)
    if media_type == "video":
        return await prepare_video_story(src_path, out_path)

    raise ValueError(f"unsupported media_type for prepare: {media_type}")
