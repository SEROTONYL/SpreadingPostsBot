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
                file_unique_id TEXT,
                file_name TEXT,
                mime_type TEXT,
                file_size INTEGER,
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
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS deliveries_target_task_unique
            ON deliveries(target, task_id)
            """
        )
        _ensure_column(cursor, "tasks", "attempts", "INTEGER DEFAULT 0")
        _ensure_column(cursor, "tasks", "last_error", "TEXT")
        _ensure_column(cursor, "tasks", "ocr_text", "TEXT")
        _ensure_column(cursor, "tasks", "file_unique_id", "TEXT")
        _ensure_column(cursor, "tasks", "file_name", "TEXT")
        _ensure_column(cursor, "tasks", "mime_type", "TEXT")
        _ensure_column(cursor, "tasks", "file_size", "INTEGER")
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
    file_unique_id: str | None,
    file_name: str | None,
    mime_type: str | None,
    file_size: int | None,
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
                file_unique_id,
                file_name,
                mime_type,
                file_size,
                caption,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                tg_message_id,
                media_type,
                file_id,
                file_unique_id,
                file_name,
                mime_type,
                file_size,
                caption,
                status,
                created_at,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def enqueue_delivery(sqlite_path: str, task_id: int, target: str = "tg_story") -> None:
    """Create a queued delivery record for a prepared task."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO deliveries (task_id, target, status, error, external_id)
            VALUES (?, ?, ?, NULL, NULL)
            ON CONFLICT(target, task_id) DO NOTHING
            """,
            (task_id, target, "queued"),
        )
        connection.commit()


def get_task(
    sqlite_path: str, task_id: int
) -> tuple[int, int, str, str | None, str | None, str | None, str | None, str, int] | None:
    """Fetch a task with key download metadata."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT user_id,
                   tg_message_id,
                   media_type,
                   file_id,
                   caption,
                   src_path,
                   prepared_path,
                   status,
                   attempts
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
            row[6],
            str(row[7]),
            int(row[8] or 0),
        )


def get_task_caption(sqlite_path: str, task_id: int) -> str | None:
    """Fetch the caption for a task."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT caption
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return row[0]


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


def set_task_preparing(sqlite_path: str, task_id: int) -> None:
    """Mark task as preparing."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = ?, last_error = NULL
            WHERE id = ?
            """,
            ("preparing", task_id),
        )
        connection.commit()


def set_task_prepared(sqlite_path: str, task_id: int, prepared_path: str) -> None:
    """Mark task as prepared with the prepared path."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET prepared_path = ?, status = ?, last_error = NULL
            WHERE id = ?
            """,
            (prepared_path, "prepared", task_id),
        )
        connection.commit()


def set_task_failed(sqlite_path: str, task_id: int, error_text: str) -> None:
    """Mark task as failed with an error."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = ?, last_error = ?
            WHERE id = ?
            """,
            ("failed", error_text, task_id),
        )
        connection.commit()


def set_task_ocr_text(sqlite_path: str, task_id: int, ocr_text: str | None) -> None:
    """Store OCR text for a task."""

    with get_connection(sqlite_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET ocr_text = ?
            WHERE id = ?
            """,
            (ocr_text, task_id),
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
            WHERE (
                status IN ("queued", "downloading")
                AND (src_path IS NULL OR src_path = "")
            )
            OR (
                status IN ("downloaded", "preparing")
                AND src_path IS NOT NULL
                AND src_path != ""
            )
            ORDER BY id
            """
        )
        rows = cursor.fetchall()
    return [int(row[0]) for row in rows]
