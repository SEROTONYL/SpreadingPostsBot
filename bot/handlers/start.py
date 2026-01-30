from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Respond to /start command."""

    await message.answer("Бот запущен. Готов к работе.")
