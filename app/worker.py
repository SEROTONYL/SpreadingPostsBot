from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app import db
from app.processor import process_event
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task:
            return
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task

    async def run(self) -> None:
        logger.info("worker.started")
        while not self._stop_event.is_set():
            event = await db.fetch_next_event(
                self.settings.db_path,
                now=db.utc_now(),
                max_attempts=self.settings.max_attempts,
            )
            if not event:
                await asyncio.sleep(self.settings.poll_interval_s)
                continue
            logger.info("worker.processing", extra={"event_id": event.id})
            await process_event(self.settings, event)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    async def runner() -> None:
        await db.init_db(settings.db_path)
        worker = Worker(settings)
        await worker.start()
        try:
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            await worker.stop()

    asyncio.run(runner())


if __name__ == "__main__":
    main()
