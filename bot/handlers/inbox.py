import logging
from datetime import datetime, timezone
from pathlib import Path

from aiogram import F, Router
from aiogram.types import Message

from bot.config import load_settings
from bot.db import create_task, update_task_src_path

router = Router()
logger = logging.getLogger(__name__)
settings = load_settings()

INBOX_DIR = Path("bot/storage/inbox")


def is_whitelisted(message: Message) -> bool:
    """Check if the sender is allowed to use the bot."""

    return bool(message.from_user and message.from_user.id == settings.ADMIN_USER_ID)


def now_iso() -> str:
    """Return the current UTC time in ISO 8601 format."""

    return datetime.now(timezone.utc).isoformat()


@router.message(F.chat.type == "private", F.photo)
async def handle_photo(message: Message) -> None:
    """Handle incoming photos in private chats."""

    if not is_whitelisted(message):
        await message.answer("Нет доступа.")
        return

    photo = message.photo[-1]
    file_id = photo.file_id
    task_id = create_task(
        settings.SQLITE_PATH,
        user_id=message.from_user.id,
        tg_message_id=message.message_id,
        media_type="photo",
        file_id=file_id,
        caption=message.caption,
        status="new",
        created_at=now_iso(),
    )
    logger.info(
        "Accepted photo from user %s message %s -> task %s",
        message.from_user.id,
        message.message_id,
        task_id,
    )
    try:
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        file = await message.bot.get_file(file_id)
        file_path = file.file_path
        logger.info(
            "Download start task %s file_id %s file_path %s",
            task_id,
            file_id,
            file_path,
        )
        extension = Path(file_path).suffix or ".jpg"
        filename = f"task_{task_id}_{message.message_id}{extension}"
        target_path = INBOX_DIR / filename
        await message.bot.download_file(file_path, destination=target_path)
    except Exception as exc:
        update_task_src_path(settings.SQLITE_PATH, task_id, None, "failed")
        logger.exception("Download failed task %s: %s", task_id, exc)
        await message.answer(f"Не смог скачать файл. Задача #{task_id}.")
        return

    src_path = target_path.as_posix()
    update_task_src_path(settings.SQLITE_PATH, task_id, src_path, "downloaded")
    logger.info("Download ok task %s src_path %s", task_id, src_path)
    await message.answer(f"Принял. Скачал. Задача #{task_id}.")


@router.message(F.chat.type == "private", F.video)
async def handle_video(message: Message) -> None:
    """Handle incoming videos in private chats."""

    if not is_whitelisted(message):
        await message.answer("Нет доступа.")
        return

    file_id = message.video.file_id if message.video else None
    task_id = create_task(
        settings.SQLITE_PATH,
        user_id=message.from_user.id,
        tg_message_id=message.message_id,
        media_type="video",
        file_id=file_id,
        caption=message.caption,
        status="new",
        created_at=now_iso(),
    )
    logger.info(
        "Accepted video from user %s message %s -> task %s",
        message.from_user.id,
        message.message_id,
        task_id,
    )
    if not file_id:
        update_task_src_path(settings.SQLITE_PATH, task_id, None, "failed")
        logger.error("Download failed task %s: missing file_id", task_id)
        await message.answer(f"Не смог скачать файл. Задача #{task_id}.")
        return

    try:
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        file = await message.bot.get_file(file_id)
        file_path = file.file_path
        logger.info(
            "Download start task %s file_id %s file_path %s",
            task_id,
            file_id,
            file_path,
        )
        extension = Path(file_path).suffix or ".mp4"
        filename = f"task_{task_id}_{message.message_id}{extension}"
        target_path = INBOX_DIR / filename
        await message.bot.download_file(file_path, destination=target_path)
    except Exception as exc:
        update_task_src_path(settings.SQLITE_PATH, task_id, None, "failed")
        logger.exception("Download failed task %s: %s", task_id, exc)
        await message.answer(f"Не смог скачать файл. Задача #{task_id}.")
        return

    src_path = target_path.as_posix()
    update_task_src_path(settings.SQLITE_PATH, task_id, src_path, "downloaded")
    logger.info("Download ok task %s src_path %s", task_id, src_path)
    await message.answer(f"Принял. Скачал. Задача #{task_id}.")


@router.message(F.chat.type == "private", F.text, ~F.photo, ~F.video)
async def handle_text(message: Message) -> None:
    """Handle incoming text in private chats."""

    if not is_whitelisted(message):
        await message.answer("Нет доступа.")
        return

    task_id = create_task(
        settings.SQLITE_PATH,
        user_id=message.from_user.id,
        tg_message_id=message.message_id,
        media_type="text",
        file_id=None,
        caption=message.text,
        status="new",
        created_at=now_iso(),
    )
    logger.info(
        "Accepted text from user %s message %s -> task %s",
        message.from_user.id,
        message.message_id,
        task_id,
    )
    await message.answer(f"Текст принят. Задача #{task_id}.")
