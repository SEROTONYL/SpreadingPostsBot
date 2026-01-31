from __future__ import annotations

import asyncio
import json

from app import db
from app.settings import get_settings
from app.webhook import extract_status_events


async def run() -> None:
    settings = get_settings()
    await db.init_db(settings.db_path)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "original").mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "prepared").mkdir(parents=True, exist_ok=True)

    sample_payload = {
        "event_id": "sample-event-1",
        "messages": [
            {
                "id": "status-123",
                "from_me": True,
                "type": "status",
                "media": {"id": "media-abc"},
                "caption": "Sample status",
            }
        ],
    }

    events = extract_status_events(sample_payload)
    if not events:
        raise RuntimeError("Failed to parse sample payload")
    event = events[0]
    payload_hash_value = db.payload_hash({"event": event.raw_event, "source_status_id": event.source_status_id})
    row_id = await db.insert_event(
        settings.db_path,
        whapi_event_id=event.whapi_event_id,
        source_status_id=event.source_status_id,
        payload_hash_value=payload_hash_value,
        media_type=event.media_type,
        media_remote_id=event.media_remote_id,
        media_url=event.media_url,
        caption=event.caption,
    )
    if not row_id:
        raise RuntimeError("Failed to insert sample payload")

    print(json.dumps({"status": "ok", "row_id": row_id}))


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
