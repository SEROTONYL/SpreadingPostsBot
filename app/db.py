from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite


@dataclass
class InboundStatusEvent:
    id: int
    whapi_event_id: Optional[str]
    source_status_id: Optional[str]
    received_at: str
    payload_hash: str
    media_type: str
    media_remote_id: Optional[str]
    media_url: Optional[str]
    caption: Optional[str]
    state: str
    attempts: int
    last_error: Optional[str]
    target_status_id: Optional[str]
    stored_original_path: Optional[str]
    stored_prepared_path: Optional[str]
    next_attempt_at: Optional[str]
    posted_at: Optional[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS inbound_status_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                whapi_event_id TEXT UNIQUE,
                source_status_id TEXT UNIQUE,
                received_at TEXT NOT NULL,
                payload_hash TEXT UNIQUE NOT NULL,
                media_type TEXT NOT NULL,
                media_remote_id TEXT,
                media_url TEXT,
                caption TEXT,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                target_status_id TEXT,
                stored_original_path TEXT,
                stored_prepared_path TEXT,
                next_attempt_at TEXT,
                posted_at TEXT
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_inbound_state_next ON inbound_status_events(state, next_attempt_at)"
        )
        await db.commit()


async def insert_event(
    db_path: Path,
    *,
    whapi_event_id: Optional[str],
    source_status_id: Optional[str],
    payload_hash_value: str,
    media_type: str,
    media_remote_id: Optional[str],
    media_url: Optional[str],
    caption: Optional[str],
) -> Optional[int]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO inbound_status_events (
                whapi_event_id,
                source_status_id,
                received_at,
                payload_hash,
                media_type,
                media_remote_id,
                media_url,
                caption,
                state,
                attempts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0)
            """,
            (
                whapi_event_id,
                source_status_id,
                utc_now(),
                payload_hash_value,
                media_type,
                media_remote_id,
                media_url,
                caption,
            ),
        )
        await db.commit()
        if cursor.rowcount == 0:
            return None
        return cursor.lastrowid


async def fetch_next_event(db_path: Path, *, now: str, max_attempts: int) -> Optional[InboundStatusEvent]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute(
            """
            SELECT id, whapi_event_id, source_status_id, received_at, payload_hash, media_type,
                   media_remote_id, media_url, caption, state, attempts, last_error, target_status_id,
                   stored_original_path, stored_prepared_path, next_attempt_at, posted_at
            FROM inbound_status_events
            WHERE state IN ('queued', 'failed')
              AND attempts < ?
              AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
            ORDER BY received_at ASC
            LIMIT 1
            """,
            (max_attempts, now),
        )
        row = await cursor.fetchone()
        if not row:
            await db.execute("COMMIT")
            return None
        await db.execute(
            """
            UPDATE inbound_status_events
            SET state = 'processing',
                attempts = attempts + 1
            WHERE id = ?
            """,
            (row[0],),
        )
        await db.execute("COMMIT")
        return InboundStatusEvent(*row)


async def mark_processing_paths(
    db_path: Path,
    *,
    event_id: int,
    stored_original_path: Optional[str],
    stored_prepared_path: Optional[str],
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE inbound_status_events
            SET stored_original_path = ?,
                stored_prepared_path = ?
            WHERE id = ?
            """,
            (stored_original_path, stored_prepared_path, event_id),
        )
        await db.commit()


async def mark_posted(
    db_path: Path,
    *,
    event_id: int,
    target_status_id: Optional[str],
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE inbound_status_events
            SET state = 'posted',
                target_status_id = ?,
                posted_at = ?,
                last_error = NULL
            WHERE id = ?
            """,
            (target_status_id, utc_now(), event_id),
        )
        await db.commit()


async def mark_failed(
    db_path: Path,
    *,
    event_id: int,
    error_message: str,
    next_attempt_at: Optional[str],
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE inbound_status_events
            SET state = 'failed',
                last_error = ?,
                next_attempt_at = ?
            WHERE id = ?
            """,
            (error_message, next_attempt_at, event_id),
        )
        await db.commit()


async def get_event(db_path: Path, event_id: int) -> Optional[InboundStatusEvent]:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            SELECT id, whapi_event_id, source_status_id, received_at, payload_hash, media_type,
                   media_remote_id, media_url, caption, state, attempts, last_error, target_status_id,
                   stored_original_path, stored_prepared_path, next_attempt_at, posted_at
            FROM inbound_status_events
            WHERE id = ?
            """,
            (event_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return InboundStatusEvent(*row)
