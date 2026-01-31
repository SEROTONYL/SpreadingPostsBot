import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from aiogram import F, Router
from aiogram.types import Document
from aiogram.types import Message

from bot.config import load_settings
from bot.db import create_task
from bot.services.queue import enqueue_task

router = Router()
logger = logging.getLogger(__name__)
settings = load_settings()


_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class MediaInfo(NamedTuple):
    media_type: str
    file_id: str
    file_unique_id: str | None
    file_name: str | None
    mime_type: str | None
    file_size: int | None
    source: str
    duration: int | None


def is_whitelisted(message: Message) -> bool:
    """Check if the sender is allowed to use the bot."""

    return bool(message.from_user and message.from_user.id == settings.ADMIN_USER_ID)


def now_iso() -> str:
    """Return the current UTC time in ISO 8601 format."""

    return datetime.now(timezone.utc).isoformat()


def _detect_document_media(document: Document) -> str | None:
    mime_type = (document.mime_type or "").lower()
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("image/"):
        return "photo"
    file_name = (document.file_name or "").lower()
    extension = Path(file_name).suffix
    if extension in _VIDEO_EXTENSIONS:
        return "video"
    if extension in _PHOTO_EXTENSIONS:
        return "photo"
    return None


def extract_media_from_message(message: Message) -> MediaInfo | None:
    """Extract media info from a message (photo, video, or document media)."""

    if message.photo:
        photo = message.photo[-1]
        return MediaInfo(
            media_type="photo",
            file_id=photo.file_id,
            file_unique_id=photo.file_unique_id,
            file_name=None,
            mime_type=None,
            file_size=photo.file_size,
            source="photo",
            duration=None,
        )
    if message.video:
        video = message.video
        return MediaInfo(
            media_type="video",
            file_id=video.file_id,
            file_unique_id=video.file_unique_id,
            file_name=video.file_name,
            mime_type=video.mime_type,
            file_size=video.file_size,
            source="video",
            duration=video.duration,
        )
    if message.document:
        document = message.document
        media_type = _detect_document_media(document)
        if not media_type:
            return None
        return MediaInfo(
            media_type=media_type,
            file_id=document.file_id,
            file_unique_id=document.file_unique_id,
            file_name=document.file_name,
            mime_type=document.mime_type,
            file_size=document.file_size,
            source="document",
            duration=None,
        )
    return None


async def _handle_media_message(message: Message) -> None:
    if not is_whitelisted(message):
        await message.answer("Нет доступа.")
        return

    media_info = extract_media_from_message(message)
    if not media_info:
        await message.answer(
            "Принимаю только фото/видео (как медиа или файл-документ)."
        )
        return

    if media_info.file_size:
        size_limit = settings.MAX_UPLOAD_MB * 1024 * 1024
        if media_info.file_size > size_limit:
            size_mb = media_info.file_size / (1024 * 1024)
            logger.info(
                "reject too large input kind=%s user_id=%s msg_id=%s size_mb=%.2f",
                media_info.source,
                message.from_user.id if message.from_user else None,
                message.message_id,
                size_mb,
            )
            await message.answer("Файл слишком большой, отправь короче/сжатее.")
            return

    task_id = create_task(
        settings.SQLITE_PATH,
        user_id=message.from_user.id,
        tg_message_id=message.message_id,
        media_type=media_info.media_type,
        file_id=media_info.file_id,
        file_unique_id=media_info.file_unique_id,
        file_name=media_info.file_name,
        mime_type=media_info.mime_type,
        file_size=media_info.file_size,
        caption=message.caption,
        status="queued",
        created_at=now_iso(),
    )
    enqueue_task(task_id)
    logger.info(
        "accepted media kind=%s media_type=%s mime=%s name=%s size=%s user_id=%s task_id=%s",
        media_info.source,
        media_info.media_type,
        media_info.mime_type,
        media_info.file_name,
        media_info.file_size,
        message.from_user.id if message.from_user else None,
        task_id,
    )
    if media_info.media_type == "video" and media_info.duration:
        if media_info.duration > settings.MAX_VIDEO_SECONDS:
            logger.info("warn long video task_id %s duration %s", task_id, media_info.duration)
            await message.answer(
                f"Принял. Задача #{task_id} в очереди. Внимание: видео длиннее "
                f"{settings.MAX_VIDEO_SECONDS} сек, обработка может занять больше времени."
            )
            return
    await message.answer(f"Принял. Задача #{task_id} поставлена в очередь.")


@router.message(F.chat.type == "private", F.photo)
async def handle_photo(message: Message) -> None:
    """Handle incoming photos in private chats."""

    await _handle_media_message(message)


@router.message(F.chat.type == "private", F.video)
async def handle_video(message: Message) -> None:
    """Handle incoming videos in private chats."""

    await _handle_media_message(message)


@router.message(F.chat.type == "private", F.document)
async def handle_document(message: Message) -> None:
    """Handle incoming documents in private chats."""

    await _handle_media_message(message)


@router.message(F.chat.type == "private", F.text, ~F.photo, ~F.video)
async def handle_text(message: Message) -> None:
    """Handle incoming text in private chats."""

    if not is_whitelisted(message):
        await message.answer("Нет доступа.")
        return

    text = (message.text or "").strip()
    if not text:
        return
    if text.startswith("/"):
        return

    task_id = create_task(
        settings.SQLITE_PATH,
        user_id=message.from_user.id,
        tg_message_id=message.message_id,
        media_type="text",
        file_id=None,
        file_unique_id=None,
        file_name=None,
        mime_type=None,
        file_size=None,
        caption=message.text,
        status="prepared",
        created_at=now_iso(),
    )
    logger.info(
        "Accepted text from user %s message %s -> task %s",
        message.from_user.id,
        message.message_id,
        task_id,
    )
    await message.answer(f"Текст принят. Задача #{task_id}.")
