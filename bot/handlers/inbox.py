from datetime import datetime, timezone
import logging

from aiogram import F, Router
from aiogram.types import Message

from bot.config import load_settings
from bot.db import create_task

router = Router()
logger = logging.getLogger(__name__)
settings = load_settings()


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
    task_id = create_task(
        settings.SQLITE_PATH,
        user_id=message.from_user.id,
        tg_message_id=message.message_id,
        media_type="photo",
        file_id=photo.file_id,
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
    await message.answer(f"Принял. Задача #{task_id}.")


@router.message(F.chat.type == "private", F.video)
async def handle_video(message: Message) -> None:
    """Handle incoming videos in private chats."""

    if not is_whitelisted(message):
        await message.answer("Нет доступа.")
        return

    task_id = create_task(
        settings.SQLITE_PATH,
        user_id=message.from_user.id,
        tg_message_id=message.message_id,
        media_type="video",
        file_id=message.video.file_id if message.video else None,
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
    await message.answer(f"Принял. Задача #{task_id}.")


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
