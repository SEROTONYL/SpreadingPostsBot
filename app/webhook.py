from __future__ import annotations

import hmac
import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Optional


@dataclass
class WebhookStatusEvent:
    whapi_event_id: Optional[str]
    source_status_id: Optional[str]
    media_type: str
    media_remote_id: Optional[str]
    media_url: Optional[str]
    caption: Optional[str]
    raw_event: dict[str, Any]


def verify_webhook(
    *,
    body: bytes,
    secret: str,
    signature_header: Optional[str],
    provided_secret: Optional[str],
) -> bool:
    if signature_header:
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        provided = signature_header
        if provided.startswith("sha256="):
            provided = provided.split("=", 1)[1]
        return hmac.compare_digest(expected, provided)
    return provided_secret == secret


def _as_list(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    if isinstance(payload.get("messages"), list):
        return payload["messages"]
    if isinstance(payload.get("message"), dict):
        return [payload["message"]]
    if isinstance(payload.get("status"), dict):
        return [payload["status"]]
    return []


def _is_from_me(message: dict[str, Any]) -> bool:
    for key in ("from_me", "fromMe", "from_me"):
        if key in message:
            return bool(message.get(key))
    sender = message.get("from") or message.get("author")
    if isinstance(sender, str) and sender.lower() in {"me", "self"}:
        return True
    return False


def _is_status(message: dict[str, Any]) -> bool:
    if message.get("type") in {"status", "story"}:
        return True
    if message.get("chat_type") in {"status", "story"}:
        return True
    if message.get("is_status") or message.get("isStatus"):
        return True
    return False


def _extract_media(message: dict[str, Any]) -> tuple[Optional[str], Optional[str], str]:
    media = message.get("media") or message.get("file") or message.get("data")
    media_id = None
    media_url = None
    if isinstance(media, dict):
        media_id = media.get("id") or media.get("media_id")
        media_url = media.get("url") or media.get("link")
    if not media and isinstance(message.get("image"), dict):
        media = message["image"]
        media_id = media.get("id") or media.get("media_id")
        media_url = media.get("url") or media.get("link")
    if not media and isinstance(message.get("video"), dict):
        media = message["video"]
        media_id = media.get("id") or media.get("media_id")
        media_url = media.get("url") or media.get("link")
    media_type = message.get("type") or message.get("media_type") or "unknown"
    if isinstance(message.get("image"), dict):
        media_type = "photo"
    if isinstance(message.get("video"), dict):
        media_type = "video"
    if media_type in {"image", "photo"}:
        media_type = "photo"
    elif media_type in {"video", "video/mp4"}:
        media_type = "video"
    else:
        media_type = "unknown"
    return media_id, media_url, media_type


def extract_status_events(payload: dict[str, Any]) -> list[WebhookStatusEvent]:
    events: list[WebhookStatusEvent] = []
    whapi_event_id = payload.get("event_id") or payload.get("id")
    for message in _as_list(payload):
        if not _is_from_me(message):
            continue
        if not _is_status(message):
            continue
        media_id, media_url, media_type = _extract_media(message)
        if media_type == "unknown":
            continue
        if not media_id and not media_url:
            continue
        events.append(
            WebhookStatusEvent(
                whapi_event_id=str(whapi_event_id) if whapi_event_id else None,
                source_status_id=str(message.get("id") or message.get("status_id") or "") or None,
                media_type=media_type,
                media_remote_id=str(media_id) if media_id else None,
                media_url=str(media_url) if media_url else None,
                caption=message.get("caption") or message.get("text"),
                raw_event=message,
            )
        )
    return events
