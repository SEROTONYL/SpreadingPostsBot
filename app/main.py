from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from app import db
from app.settings import Settings, get_settings
from app.webhook import extract_status_events, verify_webhook
from app.worker import Worker


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    await db.init_db(settings.db_path)
    worker = Worker(settings)
    await worker.start()
    app.state.worker = worker
    yield
    await worker.stop()


app = FastAPI(lifespan=lifespan)


@app.post("/webhook/whapi")
async def whapi_webhook(request: Request) -> dict[str, Any]:
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("X-Whapi-Signature")
    provided_secret = request.headers.get("X-Webhook-Secret") or request.query_params.get("secret")

    if not verify_webhook(
        body=body,
        secret=settings.webhook_secret,
        signature_header=signature,
        provided_secret=provided_secret,
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    events = extract_status_events(payload)
    if not events:
        return {"status": "ignored"}

    inserted = 0
    for event in events:
        event_payload = {"event": event.raw_event, "source_status_id": event.source_status_id}
        payload_hash_value = db.payload_hash(event_payload)
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
        if row_id:
            inserted += 1
    return {"status": "accepted", "inserted": inserted}
