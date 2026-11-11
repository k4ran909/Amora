from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, TelegramObject

from amora.adapters.telegram import texts as t
from amora.core.profiles import ProfileService
from amora.db.models import Platform, UserStatus


class UserMiddleware(BaseMiddleware):
    """Loads (or creates) the profile for every private-chat update and injects it as `user`.

    Group chats (e.g. the admin group) are passed through without a user. Banned users are stopped here.
    """

    def __init__(self, profiles: ProfileService):
        self.profiles = profiles

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        chat = data.get("event_chat")
        if tg_user is None or tg_user.is_bot or chat is None or chat.type != ChatType.PRIVATE:
            return await handler(event, data)

        user = await self.profiles.get_or_create(Platform.TELEGRAM, tg_user.id, tg_user.username)
        if user.status == UserStatus.BANNED:
            if isinstance(event, CallbackQuery):
                await event.answer(t.BANNED, show_alert=True)
            else:
                await event.answer(t.BANNED)
            return None
        data["user"] = user
        return await handler(event, data)
