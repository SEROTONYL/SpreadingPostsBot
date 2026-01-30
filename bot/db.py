from __future__ import annotations

import sqlite3
from pathlib import Path


def get_connection(sqlite_path: str) -> sqlite3.Connection:
    """Create a SQLite connection for the given path."""

    return sqlite3.connect(sqlite_path)


def init_db(sqlite_path: str) -> None:
    """Initialize the SQLite database and required tables."""

    db_path = Path(sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                tg_message_id INTEGER,
                media_type TEXT,
                file_id TEXT,
                caption TEXT,
                src_path TEXT,
                prepared_path TEXT,
                status TEXT,
                created_at TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                target TEXT,
                status TEXT,
                external_id TEXT,
                error TEXT,
                created_at TEXT
            )
            """
        )
        connection.commit()


def create_task(
    sqlite_path: str,
    user_id: int,
    tg_message_id: int,
    media_type: str,
    file_id: str | None,
    caption: str | None,
    status: str,
    created_at: str,
) -> int:
    """Create a new task record and return its ID."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (
                user_id,
                tg_message_id,
                media_type,
                file_id,
                caption,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                tg_message_id,
                media_type,
                file_id,
                caption,
                status,
                created_at,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
