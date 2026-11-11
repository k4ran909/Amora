"""Telegram private channel used as the permanent profile store.

* Each photo is posted once; its file_id is permanent for this bot, so photos are served from Telegram for free.
* Each profile has a JSON document (edited in place on every change) tagged #u<id>, so the database can be
  rebuilt from the channel.
"""

from __future__ import annotations

import json
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, InputMediaDocument

from amora.core.vault import StoredPhoto

log = logging.getLogger(__name__)


class TelegramVault:
    def __init__(self, bot: Bot, channel_id: int):
        self.bot = bot
        self.channel_id = channel_id

    async def store_photo(self, user_id: int, jpeg: bytes) -> StoredPhoto:
        msg = await self.bot.send_photo(
            self.channel_id, BufferedInputFile(jpeg, filename=f"u{user_id}.jpg"),
            caption=f"#u{user_id} #photo", disable_notification=True,
        )
        return StoredPhoto(tg_file_id=msg.photo[-1].file_id, vault_msg_id=msg.message_id)

    async def delete_photo(self, user_id: int, photo: StoredPhoto) -> None:
        if photo.vault_msg_id:
            await self._delete(photo.vault_msg_id)

    async def store_snapshot(self, user_id: int, snapshot: dict, previous_msg_id: int | None) -> int | None:
        data = json.dumps(snapshot, indent=2, ensure_ascii=False, default=str).encode()
        document = BufferedInputFile(data, filename=f"profile_u{user_id}.json")
        caption = f"#u{user_id} #profile status:{snapshot.get('status')}"
        if previous_msg_id:
            try:
                await self.bot.edit_message_media(
                    InputMediaDocument(media=document, caption=caption),
                    chat_id=self.channel_id, message_id=previous_msg_id,
                )
                return previous_msg_id
            except TelegramBadRequest as exc:
                if "not modified" in str(exc).lower():
                    return previous_msg_id
                log.warning("snapshot edit failed for u%s (%s); posting a new one", user_id, exc)
                await self._delete(previous_msg_id)
        msg = await self.bot.send_document(self.channel_id, document, caption=caption, disable_notification=True)
        return msg.message_id

    async def delete_snapshot(self, user_id: int, msg_id: int | None) -> None:
        if msg_id:
            await self._delete(msg_id)

    async def _delete(self, msg_id: int) -> None:
        try:
            await self.bot.delete_message(self.channel_id, msg_id)
        except TelegramBadRequest as exc:  # already gone, or older than Telegram allows bots to delete
            log.warning("vault delete of message %s failed: %s", msg_id, exc)
