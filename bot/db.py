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
