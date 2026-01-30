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
                created_at TEXT,
                attempts INTEGER DEFAULT 0,
                last_error TEXT
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
        _ensure_column(cursor, "tasks", "attempts", "INTEGER DEFAULT 0")
        _ensure_column(cursor, "tasks", "last_error", "TEXT")
        connection.commit()


def _ensure_column(cursor: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    """Add a missing column without failing on repeated runs."""

    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError:
        return


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


def get_task(
    sqlite_path: str, task_id: int
) -> tuple[int, int, str, str | None, str | None, str | None, str, int] | None:
    """Fetch a task with key download metadata."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT user_id, tg_message_id, media_type, file_id, caption, src_path, status, attempts
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return (
            int(row[0]),
            int(row[1]),
            str(row[2]),
            row[3],
            row[4],
            row[5],
            str(row[6]),
            int(row[7] or 0),
        )


def set_task_status(sqlite_path: str, task_id: int, status: str) -> None:
    """Update the status field for a task."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = ?
            WHERE id = ?
            """,
            (status, task_id),
        )
        connection.commit()


def increment_attempt(sqlite_path: str, task_id: int, error_text: str) -> None:
    """Increment attempts counter and store the last error."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET attempts = COALESCE(attempts, 0) + 1,
                last_error = ?
            WHERE id = ?
            """,
            (error_text, task_id),
        )
        connection.commit()


def set_task_downloaded(sqlite_path: str, task_id: int, src_path: str) -> None:
    """Update the task after a successful download."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET src_path = ?, status = ?, last_error = NULL
            WHERE id = ?
            """,
            (src_path, "downloaded", task_id),
        )
        connection.commit()


def update_task_src_path(
    sqlite_path: str,
    task_id: int,
    src_path: str | None,
    status: str,
) -> None:
    """Update the src_path and status fields for a task."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET src_path = ?, status = ?
            WHERE id = ?
            """,
            (src_path, status, task_id),
        )
        connection.commit()


def get_pending_task_ids(sqlite_path: str) -> list[int]:
    """Return task ids that should be requeued on startup."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id
            FROM tasks
            WHERE status IN ("queued", "downloading")
              AND (src_path IS NULL OR src_path = "")
            ORDER BY id
            """
        )
        rows = cursor.fetchall()
    return [int(row[0]) for row in rows]
