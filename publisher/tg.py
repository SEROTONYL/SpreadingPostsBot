import logging
from pathlib import Path
from typing import Optional

from telethon import TelegramClient, functions, types

from publisher.config import Settings
from publisher.story import VideoInfo, build_privacy_rules, extract_story_id, is_photo, probe_video

logger = logging.getLogger(__name__)


class PublisherClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Optional[TelegramClient] = None

    async def connect(self) -> TelegramClient:
        if self._client is None:
            self._client = TelegramClient(
                self._settings.tg_session_path,
                self._settings.tg_api_id,
                self._settings.tg_api_hash,
            )
            await self._client.start(phone=self._settings.tg_phone)
        return self._client

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()

    async def can_send_story(self, peer: str) -> bool:
        client = await self.connect()
        result = await client(functions.stories.CanSendStoryRequest(peer=peer))
        if isinstance(result, bool):
            return result
        if hasattr(result, "can_send"):
            return bool(result.can_send)
        if hasattr(result, "allowed"):
            return bool(result.allowed)
        return True

    async def send_story(
        self,
        prepared_path: str,
        caption: str,
        media_type: Optional[str],
        peer: str,
    ) -> str:
        client = await self.connect()
        privacy_rules = build_privacy_rules(self._settings.story_privacy)
        period = self._settings.story_period_seconds

        if is_photo(media_type, prepared_path):
            upload = await client.upload_file(prepared_path)
            media = types.InputMediaUploadedPhoto(file=upload)
        else:
            video_info: VideoInfo = await probe_video(prepared_path)
            upload = await client.upload_file(prepared_path)
            media = types.InputMediaUploadedDocument(
                file=upload,
                mime_type="video/mp4",
                attributes=[
                    types.DocumentAttributeVideo(
                        duration=video_info.duration,
                        w=video_info.width,
                        h=video_info.height,
                        supports_streaming=True,
                    ),
                    types.DocumentAttributeFilename(
                        file_name=Path(prepared_path).name
                    ),
                ],
            )

        result = await client(
            functions.stories.SendStoryRequest(
                peer=peer,
                media=media,
                caption=caption,
                privacy_rules=privacy_rules,
                period=period,
            )
        )
        story_id = extract_story_id(result)
        if story_id:
            return story_id
        return repr(result)
