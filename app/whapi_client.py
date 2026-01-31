from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import httpx


class WhapiError(RuntimeError):
    pass


def _extract_media_id(payload: dict[str, Any]) -> Optional[str]:
    for key in ("media", "file", "data"):
        if isinstance(payload.get(key), dict):
            candidate = payload[key].get("id") or payload[key].get("media_id")
            if candidate:
                return str(candidate)
    return payload.get("id") or payload.get("media_id")


class WhapiClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def download_media(self, *, media_url: Optional[str], media_id: Optional[str]) -> tuple[bytes, str]:
        if not media_url and not media_id:
            raise WhapiError("Missing media reference")
        url = media_url
        if not url:
            url = f"{self.base_url}/media/{media_id}/download"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url, headers=self._headers())
            if response.status_code >= 400:
                raise WhapiError(f"Media download failed: {response.status_code}")
            content_type = response.headers.get("content-type", "application/octet-stream")
            if content_type.startswith("application/json") and not media_url and media_id:
                data = response.json()
                resolved_url = data.get("url") or data.get("link")
                if resolved_url:
                    follow = await client.get(resolved_url, headers=self._headers())
                    if follow.status_code >= 400:
                        raise WhapiError(f"Media download failed: {follow.status_code}")
                    content_type = follow.headers.get("content-type", "application/octet-stream")
                    return follow.content, content_type
            return response.content, content_type

    async def upload_media(self, file_path: Path) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            with file_path.open("rb") as handle:
                response = await client.post(
                    f"{self.base_url}/media",
                    headers=self._headers(),
                    files={"file": handle},
                )
            if response.status_code >= 400:
                raise WhapiError(f"Media upload failed: {response.status_code}")
            payload = response.json()
            media_id = _extract_media_id(payload)
            if not media_id:
                raise WhapiError("Media upload returned no media id")
            return media_id

    async def post_status(self, *, media_id: str, media_type: str, caption: Optional[str]) -> str:
        payload: dict[str, Any] = {
            "type": media_type,
            "media": {"id": media_id},
        }
        if caption:
            payload["caption"] = caption
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/messages/status",
                headers={**self._headers(), "Content-Type": "application/json"},
                content=json.dumps(payload),
            )
        if response.status_code >= 400:
            raise WhapiError(f"Status post failed: {response.status_code}")
        data = response.json()
        status_id = data.get("id") or data.get("message_id") or data.get("status_id")
        return str(status_id) if status_id else ""
