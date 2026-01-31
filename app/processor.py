from __future__ import annotations

import logging
import mimetypes
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

from app import db
from app.settings import Settings
from app.whapi_client import WhapiClient, WhapiError

logger = logging.getLogger(__name__)


def _extension_from_content_type(content_type: str) -> str:
    ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
    if not ext:
        return ".bin"
    return ext


def _sanitize_caption(caption: Optional[str]) -> Optional[str]:
    if caption is None:
        return None
    return caption.strip() or None


def _ensure_dirs(settings: Settings) -> tuple[Path, Path]:
    original_dir = settings.storage_dir / "original"
    prepared_dir = settings.storage_dir / "prepared"
    original_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir.mkdir(parents=True, exist_ok=True)
    return original_dir, prepared_dir


def _next_attempt(attempts: int) -> Optional[str]:
    backoff = [60, 300, 900, 3600, 7200, 14400, 28800, 57600]
    if attempts <= 0:
        return None
    if attempts > len(backoff):
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=backoff[attempts - 1])).isoformat()


def _probe_video(path: Path) -> dict[str, str]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,pix_fmt,avg_frame_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return {}
    except subprocess.CalledProcessError:
        return {}
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 5:
        return {}
    return {
        "codec": lines[0],
        "width": lines[1],
        "height": lines[2],
        "pix_fmt": lines[3],
        "fps": lines[4],
    }


def _video_needs_reencode(probe: dict[str, str]) -> bool:
    if not probe:
        return True
    if probe.get("codec") != "h264":
        return True
    if probe.get("pix_fmt") != "yuv420p":
        return True
    if probe.get("width") != "1080" or probe.get("height") != "1920":
        return True
    return False


def _has_audio(path: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return bool(result.stdout.strip())


def _prepare_image(source: Path, dest: Path) -> None:
    with Image.open(source) as img:
        img = img.convert("RGB")
        fitted = ImageOps.contain(img, (1080, 1920))
        canvas = Image.new("RGB", (1080, 1920), color=(0, 0, 0))
        offset = ((1080 - fitted.width) // 2, (1920 - fitted.height) // 2)
        canvas.paste(fitted, offset)
        canvas.save(dest, format="JPEG", quality=92)


def _prepare_video(source: Path, dest: Path) -> None:
    audio_args = ["-c:a", "aac", "-b:a", "128k"] if _has_audio(source) else ["-an"]
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v",
        "libx264",
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "fast",
        "-r",
        "30",
        "-movflags",
        "+faststart",
        *audio_args,
        str(dest),
    ]
    subprocess.run(command, check=True)


async def process_event(settings: Settings, event: db.InboundStatusEvent) -> None:
    original_dir, prepared_dir = _ensure_dirs(settings)
    source_client = WhapiClient(settings.whapi_api_url, settings.whapi_source_token)
    target_client = WhapiClient(settings.whapi_api_url, settings.whapi_target_token)

    try:
        content, content_type = await source_client.download_media(
            media_url=event.media_url, media_id=event.media_remote_id
        )
        extension = _extension_from_content_type(content_type)
        original_path = original_dir / f"event_{event.id}{extension}"
        original_path.write_bytes(content)

        prepared_path = original_path
        if event.media_type == "photo":
            prepared_path = prepared_dir / f"event_{event.id}.jpg"
            _prepare_image(original_path, prepared_path)
        elif event.media_type == "video":
            probe = _probe_video(original_path)
            if _video_needs_reencode(probe):
                prepared_path = prepared_dir / f"event_{event.id}.mp4"
                _prepare_video(original_path, prepared_path)
        await db.mark_processing_paths(
            settings.db_path,
            event_id=event.id,
            stored_original_path=str(original_path),
            stored_prepared_path=str(prepared_path),
        )

        media_id = await target_client.upload_media(prepared_path)
        target_status_id = await target_client.post_status(
            media_id=media_id,
            media_type=event.media_type,
            caption=_sanitize_caption(event.caption),
        )
        await db.mark_posted(settings.db_path, event_id=event.id, target_status_id=target_status_id)
        logger.info("status.posted", extra={"event_id": event.id, "target_status_id": target_status_id})
    except (WhapiError, subprocess.CalledProcessError, OSError) as exc:
        logger.exception("status.failed", extra={"event_id": event.id})
        next_attempt = _next_attempt(event.attempts + 1)
        await db.mark_failed(settings.db_path, event_id=event.id, error_message=str(exc), next_attempt_at=next_attempt)
    except Exception as exc:  # noqa: BLE001
        logger.exception("status.failed.unexpected", extra={"event_id": event.id})
        next_attempt = _next_attempt(event.attempts + 1)
        await db.mark_failed(settings.db_path, event_id=event.id, error_message=str(exc), next_attempt_at=next_attempt)
        raise
