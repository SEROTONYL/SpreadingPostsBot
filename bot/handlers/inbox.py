import logging

from aiogram import F, Router
from aiogram.types import Message

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.chat.type == "private", F.photo)
async def handle_photo(message: Message) -> None:
    """Handle incoming photos in private chats."""

    logger.info("Received photo from user %s", message.from_user.id if message.from_user else "unknown")
    await message.answer("Принял")


@router.message(F.chat.type == "private", F.video)
async def handle_video(message: Message) -> None:
    """Handle incoming videos in private chats."""

    logger.info("Received video from user %s", message.from_user.id if message.from_user else "unknown")
    await message.answer("Принял")


@router.message(F.chat.type == "private", F.text)
async def handle_text(message: Message) -> None:
    """Handle incoming text in private chats."""

    logger.info("Received text from user %s", message.from_user.id if message.from_user else "unknown")
    await message.answer("Принял")
