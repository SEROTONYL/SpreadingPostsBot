from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.config import load_settings

router = Router()
settings = load_settings()


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Respond to /start command."""

    if not message.from_user or message.from_user.id != settings.ADMIN_USER_ID:
        await message.answer("Нет доступа.")
        return

    await message.answer("Скинь фото/видео с подписью или текст. Я сохраню задачу.")
