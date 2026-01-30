from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher

from bot.config import load_settings
from bot.db import init_db
from bot.handlers import inbox, start
from bot.logging_setup import setup_logging


async def main() -> None:
    """Entrypoint for the Telegram bot."""

    setup_logging()
    logger = logging.getLogger(__name__)
    settings = load_settings()

    init_db(settings.SQLITE_PATH)
    logger.info("Database initialized at %s", settings.SQLITE_PATH)
    inbox_dir = Path("bot/storage/inbox")
    inbox_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Inbox directory ready at %s", inbox_dir.as_posix())

    bot = Bot(token=settings.BOT_TOKEN)
    dispatcher = Dispatcher()
    dispatcher.include_router(start.router)
    dispatcher.include_router(inbox.router)

    logger.info("Starting bot polling")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
