"""Media preparation utilities for 9:16 stories."""

from __future__ import annotations

import asyncio
import logging
import re
import shlex
from pathlib import Path

logger = logging.getLogger(__name__)

_TARGET_WIDTH = 1080
_TARGET_HEIGHT = 1920
_STORY_RATIO = 9 / 16
_RATIO_TOLERANCE = 0.02
_TASK_ID_PATTERN = re.compile(r"task_(\d+)")
_STORY_SCALE_FILTER = (
    f"scale={_TARGET_WIDTH}:{_TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
    f"crop={_TARGET_WIDTH}:{_TARGET_HEIGHT},"
    "setsar=1"
)


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


def _log_ffmpeg_command(command: list[str]) -> None:
    logger.info("ffmpeg command: %s", shlex.join(command))


async def _log_output_dimensions(out_path: Path) -> None:
    width, height = await probe_dimensions(out_path)
    logger.info("ffprobe output size: %sx%s path %s", width, height, out_path.as_posix())


async def _run_ffmpeg(command: list[str], out_path: Path, error_message: str) -> None:
    _log_ffmpeg_command(command)
    return_code, stdout_text, stderr_text = await _run_command(command)
    if return_code != 0:
        raise RuntimeError(f"{error_message}: {stderr_text or stdout_text}")
    await _log_output_dimensions(out_path)


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


def is_story_like(width: int, height: int) -> bool:
    """Return True if media already fits story-friendly dimensions."""

    if width <= 0 or height <= 0:
        return False
    if is_already_story_ratio(width, height):
        return True
    if width == _TARGET_WIDTH and height == _TARGET_HEIGHT:
        return True
    if height > width and width <= 1100 and height >= 1700:
        return True
    return False


def _extract_task_id(out_path: Path) -> str | None:
    match = _TASK_ID_PATTERN.search(out_path.stem)
    if match:
        return match.group(1)
    return None


async def prepare_photo_story(src_path: Path, out_path: Path) -> Path:
    """Prepare a photo into a 9:16 story using center crop."""

    command = [
        "ffmpeg",
        "-y",
        "-i",
        src_path.as_posix(),
        "-vf",
        _STORY_SCALE_FILTER,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        out_path.as_posix(),
    ]
    await _run_ffmpeg(command, out_path, "ffmpeg photo failed")
    return out_path


async def prepare_photo_cover(src_path: Path, out_path: Path) -> Path:
    """Prepare a photo into a 9:16 story using cover crop."""

    command = [
        "ffmpeg",
        "-y",
        "-i",
        src_path.as_posix(),
        "-vf",
        _STORY_SCALE_FILTER,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        out_path.as_posix(),
    ]
    await _run_ffmpeg(command, out_path, "ffmpeg photo cover failed")
    return out_path


async def convert_photo_to_jpg(src_path: Path, out_path: Path) -> Path:
    """Convert a photo to JPEG without resizing."""

    command = [
        "ffmpeg",
        "-y",
        "-i",
        src_path.as_posix(),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        out_path.as_posix(),
    ]
    await _run_ffmpeg(command, out_path, "ffmpeg photo convert failed")
    return out_path


async def prepare_video_story(src_path: Path, out_path: Path) -> Path:
    """Prepare a video into a 9:16 story using center crop."""

    command = [
        "ffmpeg",
        "-y",
        "-i",
        src_path.as_posix(),
        "-vf",
        _STORY_SCALE_FILTER,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level:v",
        "4.1",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-r",
        "30",
        "-maxrate",
        "4500k",
        "-bufsize",
        "9000k",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-metadata:s:v:0",
        "rotate=0",
        out_path.as_posix(),
    ]
    await _run_ffmpeg(command, out_path, "ffmpeg video failed")
    return out_path


async def prepare_video_cover(src_path: Path, out_path: Path) -> Path:
    """Prepare a video into a 9:16 story using cover crop."""

    command = [
        "ffmpeg",
        "-y",
        "-i",
        src_path.as_posix(),
        "-vf",
        _STORY_SCALE_FILTER,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level:v",
        "4.1",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-r",
        "30",
        "-maxrate",
        "4500k",
        "-bufsize",
        "9000k",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-metadata:s:v:0",
        "rotate=0",
        out_path.as_posix(),
    ]
    await _run_ffmpeg(command, out_path, "ffmpeg video cover failed")
    return out_path


async def convert_video_to_mp4(src_path: Path, out_path: Path) -> Path:
    """Convert a video to MP4 without resizing."""

    command = [
        "ffmpeg",
        "-y",
        "-i",
        src_path.as_posix(),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level:v",
        "4.1",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-r",
        "30",
        "-maxrate",
        "4500k",
        "-bufsize",
        "9000k",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-metadata:s:v:0",
        "rotate=0",
        out_path.as_posix(),
    ]
    await _run_ffmpeg(command, out_path, "ffmpeg video convert failed")
    return out_path


async def prepare_to_story(src_path: Path, media_type: str, out_path: Path) -> Path:
    """Prepare media for 9:16 stories and return the prepared path."""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    task_id = _extract_task_id(out_path)
    if task_id:
        logger.info("prepare mode: story_scale task_id %s", task_id)
    else:
        logger.info("prepare mode: story_scale src %s", src_path.as_posix())
    if media_type == "photo":
        return await prepare_photo_cover(src_path, out_path)
    if media_type == "video":
        return await prepare_video_cover(src_path, out_path)

    raise ValueError(f"unsupported media_type for prepare: {media_type}")
