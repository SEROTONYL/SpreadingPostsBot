import logging
from dataclasses import dataclass
from typing import List, Optional

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class DeliveryTask:
    delivery_id: int
    task_id: int
    prepared_path: Optional[str]
    caption: Optional[str]
    media_type: Optional[str]


class Database:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def ensure_indexes(self) -> None:
        try:
            async with await self._connect() as conn:
                await conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS deliveries_target_task_unique "
                    "ON deliveries(target, task_id)"
                )
                await conn.commit()
        except Exception:
            logger.warning("failed to ensure unique index on deliveries", exc_info=True)

    async def fetch_queued(self, limit: int) -> List[DeliveryTask]:
        query = (
            "SELECT d.id AS delivery_id, d.task_id, t.prepared_path, t.caption, t.media_type "
            "FROM deliveries d "
            "JOIN tasks t ON t.id = d.task_id "
            "WHERE d.target = ? AND d.status = ? "
            "ORDER BY d.id "
            "LIMIT ?"
        )
        async with await self._connect() as conn:
            cursor = await conn.execute(query, ("tg_story", "queued", limit))
            rows = await cursor.fetchall()
        return [
            DeliveryTask(
                delivery_id=row["delivery_id"],
                task_id=row["task_id"],
                prepared_path=row["prepared_path"],
                caption=row["caption"],
                media_type=row["media_type"],
            )
            for row in rows
        ]

    async def mark_failed(self, delivery_id: int, error: str) -> None:
        async with await self._connect() as conn:
            await conn.execute(
                "UPDATE deliveries SET status = ?, error = ? WHERE id = ?",
                ("failed", error, delivery_id),
            )
            await conn.commit()

    async def mark_posted(self, delivery_id: int, external_id: str) -> None:
        async with await self._connect() as conn:
            await conn.execute(
                "UPDATE deliveries SET status = ?, external_id = ?, error = NULL WHERE id = ?",
                ("posted", external_id, delivery_id),
            )
            await conn.commit()
