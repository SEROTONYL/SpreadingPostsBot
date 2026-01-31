from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher

from bot.config import load_settings
from bot.db import init_db
from bot.handlers import inbox, start
from bot.logging_setup import setup_logging
from bot.services.queue import init_queue, requeue_pending_tasks, start_workers


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
    prepared_dir = Path("bot/storage/prepared")
    prepared_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Prepared directory ready at %s", prepared_dir.as_posix())
    ocr_frames_dir = Path("bot/storage/ocr_frames")
    ocr_frames_dir.mkdir(parents=True, exist_ok=True)
    logger.info("OCR frames directory ready at %s", ocr_frames_dir.as_posix())

    bot = Bot(token=settings.BOT_TOKEN)
    dispatcher = Dispatcher()
    dispatcher.include_router(start.router)
    dispatcher.include_router(inbox.router)

    init_queue(bot, settings)
    start_workers()
    requeued = requeue_pending_tasks(settings.SQLITE_PATH)
    if requeued:
        logger.info("Requeued pending tasks: %s", requeued)

    logger.info("Starting bot polling")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
