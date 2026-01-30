from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from bot.config import Settings
from bot.db import (
    get_pending_task_ids,
    get_task,
    get_task_caption,
    increment_attempt,
    set_task_downloaded,
    set_task_failed,
    set_task_prepared,
    set_task_preparing,
    set_task_status,
)
from bot.services.prepare_media import prepare_to_story

logger = logging.getLogger(__name__)

_QUEUE: asyncio.Queue[int] | None = None
_IN_PROGRESS: set[int] = set()
_BOT: Bot | None = None
_SETTINGS: Settings | None = None
_INBOX_DIR = Path("bot/storage/inbox")
_PREPARED_DIR = Path("bot/storage/prepared")
_RETRY_DELAYS = [2, 5, 15]


def init_queue(bot: Bot, settings: Settings) -> None:
    """Initialize queue service with bot and settings."""

    global _QUEUE, _BOT, _SETTINGS
    _BOT = bot
    _SETTINGS = settings
    if _QUEUE is None:
        _QUEUE = asyncio.Queue()


def start_workers() -> None:
    """Start background workers for processing the queue."""

    if _QUEUE is None or _SETTINGS is None:
        raise RuntimeError("Queue service is not initialized.")

    for worker_id in range(_SETTINGS.WORKER_CONCURRENCY):
        asyncio.create_task(worker_loop(worker_id + 1))


def enqueue_task(task_id: int) -> None:
    """Enqueue a task by its ID."""

    if _QUEUE is None:
        raise RuntimeError("Queue service is not initialized.")

    _QUEUE.put_nowait(task_id)
    logger.info("enqueue task_id %s", task_id)


def requeue_pending_tasks(sqlite_path: str) -> list[int]:
    """Requeue tasks that were pending before restart."""

    task_ids = get_pending_task_ids(sqlite_path)
    for task_id in task_ids:
        enqueue_task(task_id)
    return task_ids


def _next_delay(attempt_number: int) -> int:
    if attempt_number <= 0:
        return _RETRY_DELAYS[0]
    if attempt_number <= len(_RETRY_DELAYS):
        return _RETRY_DELAYS[attempt_number - 1]
    return _RETRY_DELAYS[-1]


async def worker_loop(worker_id: int) -> None:
    """Worker loop for processing queued tasks."""

    if _QUEUE is None or _BOT is None or _SETTINGS is None:
        raise RuntimeError("Queue service is not initialized.")

    while True:
        task_id = await _QUEUE.get()
        if task_id in _IN_PROGRESS:
            _QUEUE.task_done()
            continue

        _IN_PROGRESS.add(task_id)
        try:
            logger.info("worker %s start processing task_id %s", worker_id, task_id)
            await _process_task(task_id)
        finally:
            _IN_PROGRESS.discard(task_id)
            _QUEUE.task_done()


async def _process_task(task_id: int) -> None:
    if _BOT is None or _SETTINGS is None:
        raise RuntimeError("Queue service is not initialized.")

    task = get_task(_SETTINGS.SQLITE_PATH, task_id)
    if not task:
        logger.error("task %s not found", task_id)
        return

    (
        user_id,
        tg_message_id,
        media_type,
        file_id,
        _caption,
        src_path,
        prepared_path,
        status,
        attempts,
    ) = task

    if media_type == "text":
        logger.info("task %s is text, skipping", task_id)
        return
    if status == "failed":
        logger.info("task %s already failed, skipping", task_id)
        return
    if status == "prepared" and prepared_path:
        try:
            await _notify_prepared_media(
                user_id=user_id,
                task_id=task_id,
                media_type=media_type,
                prepared_path=Path(prepared_path),
            )
        except Exception as exc:
            logger.error("notify failed task_id %s error %s", task_id, exc)
            await _handle_notify_failure(
                task_id=task_id,
                user_id=user_id,
                attempts=attempts,
                error=exc,
            )
        return

    if src_path and status in {"queued", "downloading"}:
        set_task_status(_SETTINGS.SQLITE_PATH, task_id, "downloaded")
        status = "downloaded"
    elif not src_path and status in {"downloaded", "preparing"}:
        set_task_status(_SETTINGS.SQLITE_PATH, task_id, "queued")
        status = "queued"

    if status in {"queued", "downloading"} and not src_path:
        set_task_status(_SETTINGS.SQLITE_PATH, task_id, "downloading")
        try:
            if not file_id:
                raise ValueError("missing file_id")
            target_path = await _download_file(
                bot=_BOT,
                task_id=task_id,
                tg_message_id=tg_message_id,
                media_type=media_type,
                file_id=file_id,
                timeout_seconds=_SETTINGS.DOWNLOAD_TIMEOUT_SECONDS,
            )
            set_task_downloaded(_SETTINGS.SQLITE_PATH, task_id, target_path.as_posix())
            logger.info("download ok task %s path %s", task_id, target_path.as_posix())
            src_path = target_path.as_posix()
            status = "downloaded"
        except Exception as exc:
            await _handle_failure(
                task_id=task_id,
                user_id=user_id,
                attempts=attempts,
                error=exc,
                failure_message="Не смог скачать после попыток. Задача",
            )
            return

    if status in {"downloaded", "preparing"} and src_path:
        try:
            logger.info("prepare start task %s src %s", task_id, src_path)
            set_task_preparing(_SETTINGS.SQLITE_PATH, task_id)
            prepared_path = await _prepare_media(
                task_id=task_id,
                tg_message_id=tg_message_id,
                media_type=media_type,
                src_path=Path(src_path),
            )
            set_task_prepared(_SETTINGS.SQLITE_PATH, task_id, prepared_path.as_posix())
            logger.info("prepare ok task %s path %s", task_id, prepared_path.as_posix())
            try:
                await _notify_prepared_media(
                    user_id=user_id,
                    task_id=task_id,
                    media_type=media_type,
                    prepared_path=prepared_path,
                )
            except Exception as exc:
                logger.error("notify failed task_id %s error %s", task_id, exc)
                await _handle_notify_failure(
                    task_id=task_id,
                    user_id=user_id,
                    attempts=attempts,
                    error=exc,
                )
                return
        except Exception as exc:
            logger.error("prepare failed task %s error %s", task_id, exc)
            await _handle_failure(
                task_id=task_id,
                user_id=user_id,
                attempts=attempts,
                error=exc,
                failure_message="Не смог подготовить 9:16. Задача",
            )


async def _handle_failure(
    *,
    task_id: int,
    user_id: int,
    attempts: int,
    error: Exception,
    failure_message: str,
) -> None:
    if _BOT is None or _SETTINGS is None:
        raise RuntimeError("Queue service is not initialized.")

    attempt_number = attempts + 1
    increment_attempt(_SETTINGS.SQLITE_PATH, task_id, str(error))
    logger.error(
        "task %s attempt %s error %s",
        task_id,
        attempt_number,
        error,
    )
    if attempt_number >= _SETTINGS.MAX_RETRIES:
        set_task_failed(_SETTINGS.SQLITE_PATH, task_id, str(error))
        await _BOT.send_message(user_id, f"{failure_message} #{task_id}.")
        return
    delay = _next_delay(attempt_number)
    logger.info("retry scheduled task_id %s delay %s", task_id, delay)
    asyncio.create_task(delayed_reenqueue(task_id, delay))


async def _handle_notify_failure(
    *,
    task_id: int,
    user_id: int,
    attempts: int,
    error: Exception,
) -> None:
    if _BOT is None or _SETTINGS is None:
        raise RuntimeError("Queue service is not initialized.")

    attempt_number = attempts + 1
    error_text = f"notify failed: {error}"
    increment_attempt(_SETTINGS.SQLITE_PATH, task_id, error_text)
    if attempt_number >= _SETTINGS.MAX_RETRIES:
        set_task_failed(_SETTINGS.SQLITE_PATH, task_id, error_text)
        await _BOT.send_message(
            user_id, f"Не смог отправить готовый файл. Задача #{task_id}."
        )
        return
    delay = _next_delay(attempt_number)
    logger.info("retry scheduled task_id %s delay %s", task_id, delay)
    asyncio.create_task(delayed_reenqueue(task_id, delay))


async def delayed_reenqueue(task_id: int, delay_seconds: int) -> None:
    """Re-enqueue a task after a delay."""

    await asyncio.sleep(delay_seconds)
    enqueue_task(task_id)


async def _download_file(
    *,
    bot: Bot,
    task_id: int,
    tg_message_id: int,
    media_type: str,
    file_id: str,
    timeout_seconds: int | None,
) -> Path:
    """Download a file to the inbox directory and return the local path."""

    _INBOX_DIR.mkdir(parents=True, exist_ok=True)
    file = await bot.get_file(file_id)
    file_path = file.file_path
    extension = Path(file_path).suffix if file_path else ""
    if not extension:
        extension = ".jpg" if media_type == "photo" else ".mp4"
    filename = f"task_{task_id}_{tg_message_id}{extension}"
    target_path = _INBOX_DIR / filename

    async def _do_download() -> None:
        await bot.download_file(file_path, destination=target_path)

    if timeout_seconds:
        await asyncio.wait_for(_do_download(), timeout=timeout_seconds)
    else:
        await _do_download()
    return target_path


async def _prepare_media(
    *,
    task_id: int,
    tg_message_id: int,
    media_type: str,
    src_path: Path,
) -> Path:
    _PREPARED_DIR.mkdir(parents=True, exist_ok=True)
    if media_type == "photo":
        out_path = _PREPARED_DIR / f"task_{task_id}_{tg_message_id}_story.jpg"
    elif media_type == "video":
        out_path = _PREPARED_DIR / f"task_{task_id}_{tg_message_id}_story.mp4"
    else:
        raise ValueError(f"Unsupported media_type {media_type}")

    return await prepare_to_story(src_path, media_type, out_path)


async def _notify_prepared_media(
    *,
    user_id: int,
    task_id: int,
    media_type: str,
    prepared_path: Path,
) -> None:
    if _BOT is None or _SETTINGS is None:
        raise RuntimeError("Queue service is not initialized.")

    caption = f"Готово (9:16). Задача #{task_id}."
    logger.info("notify start task_id %s", task_id)
    input_file = FSInputFile(prepared_path)
    if media_type == "photo":
        await _BOT.send_photo(user_id, input_file, caption=caption)
    elif media_type == "video":
        await _BOT.send_video(user_id, input_file, caption=caption)
    else:
        raise ValueError(f"Unsupported media_type {media_type}")

    task_caption = get_task_caption(_SETTINGS.SQLITE_PATH, task_id)
    caption_text = task_caption.strip() if task_caption else ""
    if caption_text:
        body = f"Подпись для сторис (задача #{task_id}):\n\n{caption_text}"
    else:
        body = f"Подпись для сторис (задача #{task_id}):\n\n(пусто)"
    await _BOT.send_message(user_id, body)
    logger.info("notify ok task_id %s", task_id)
