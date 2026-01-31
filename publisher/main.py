import argparse
import asyncio
import logging
from typing import Optional

from publisher.config import get_settings
from publisher.db import Database, DeliveryTask
from publisher.tg import PublisherClient


logger = logging.getLogger(__name__)


def _short_error(message: str) -> str:
    return message.strip().splitlines()[0][:500]


async def process_delivery(
    db: Database,
    client: PublisherClient,
    delivery: DeliveryTask,
    peer: str,
) -> None:
    logger.info(
        "picked delivery_id=%s task_id=%s path=%s",
        delivery.delivery_id,
        delivery.task_id,
        delivery.prepared_path,
    )

    if not delivery.prepared_path:
        await db.mark_failed(delivery.delivery_id, "prepared_path is empty")
        logger.error(
            "delivery failed delivery_id=%s task_id=%s error=prepared_path is empty",
            delivery.delivery_id,
            delivery.task_id,
        )
        return

    can_send = await client.can_send_story(peer)
    if not can_send:
        await db.mark_failed(delivery.delivery_id, "cannot send story for peer")
        logger.info(
            "canSendStory failed delivery_id=%s task_id=%s",
            delivery.delivery_id,
            delivery.task_id,
        )
        return

    logger.info("canSendStory ok delivery_id=%s task_id=%s", delivery.delivery_id, delivery.task_id)

    caption = delivery.caption or ""
    try:
        external_id = await client.send_story(
            prepared_path=delivery.prepared_path,
            caption=caption,
            media_type=delivery.media_type,
            peer=peer,
        )
    except Exception as exc:
        error_text = _short_error(str(exc)) or "story publish failed"
        await db.mark_failed(delivery.delivery_id, error_text)
        logger.error(
            "posted failed delivery_id=%s task_id=%s error=%s",
            delivery.delivery_id,
            delivery.task_id,
            error_text,
            exc_info=True,
        )
        return

    await db.mark_posted(delivery.delivery_id, external_id)
    logger.info(
        "posted ok delivery_id=%s task_id=%s external_id=%s",
        delivery.delivery_id,
        delivery.task_id,
        external_id,
    )


async def run_once(db: Database, client: PublisherClient, max_per_batch: int, peer: str) -> None:
    deliveries = await db.fetch_queued(max_per_batch)
    if not deliveries:
        logger.info("nothing to do")
        return

    for delivery in deliveries:
        await process_delivery(db, client, delivery, peer)


async def run_loop(poll_interval: int, max_per_batch: int, peer: str) -> None:
    settings = get_settings()
    db = Database(settings.sqlite_path)
    client = PublisherClient(settings)

    await db.ensure_indexes()

    logger.info(
        "start publisher peer=%s privacy=%s db=%s",
        settings.publish_peer,
        settings.story_privacy,
        settings.sqlite_path,
    )

    try:
        while True:
            await run_once(db, client, max_per_batch, peer)
            await asyncio.sleep(poll_interval)
    finally:
        await client.disconnect()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram story publisher")
    parser.add_argument("--once", action="store_true", help="run one batch and exit")
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    configure_logging()
    args = parse_args()
    settings = get_settings()
    if args.once:
        async def _run_once() -> None:
            db = Database(settings.sqlite_path)
            client = PublisherClient(settings)
            await db.ensure_indexes()
            logger.info(
                "start publisher peer=%s privacy=%s db=%s",
                settings.publish_peer,
                settings.story_privacy,
                settings.sqlite_path,
            )
            try:
                await run_once(db, client, settings.max_per_batch, settings.publish_peer)
            finally:
                await client.disconnect()

        asyncio.run(_run_once())
    else:
        asyncio.run(
            run_loop(
                settings.poll_interval_seconds,
                settings.max_per_batch,
                settings.publish_peer,
            )
        )


if __name__ == "__main__":
    main()
