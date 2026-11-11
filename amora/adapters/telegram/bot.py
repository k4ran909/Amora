import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from amora.adapters.telegram import admin, menu, onboarding
from amora.adapters.telegram.middlewares import UserMiddleware
from amora.adapters.telegram.vault import TelegramVault
from amora.config import Settings
from amora.core.admin import AdminService
from amora.core.profiles import ProfileService

log = logging.getLogger(__name__)


def make_storage(settings: Settings) -> BaseStorage:
    if settings.redis_url:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage.from_url(settings.redis_url)
    return MemoryStorage()


def build_dispatcher(settings: Settings, profiles: ProfileService, admin_service: AdminService,
                     storage: BaseStorage | None = None) -> Dispatcher:
    dp = Dispatcher(storage=storage or make_storage(settings),
                    settings=settings, profiles=profiles, admin=admin_service)
    user_mw = UserMiddleware(profiles)
    dp.message.outer_middleware(user_mw)
    dp.callback_query.outer_middleware(user_mw)
    # Order matters: admin commands, then menu buttons, then the onboarding flow, then catch-alls.
    dp.include_routers(admin.router, menu.router, onboarding.router, menu.fallback)
    return dp


async def run_telegram(settings: Settings, profiles: ProfileService, admin_service: AdminService) -> None:
    bot = Bot(settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    if settings.tg_vault_channel_id:
        profiles.vault = TelegramVault(bot, settings.tg_vault_channel_id)
        log.info("Telegram vault channel: %s", settings.tg_vault_channel_id)
    else:
        log.warning("TG_VAULT_CHANNEL_ID not set: photos are stored locally in %s/vault (dev mode)",
                    settings.data_dir)

    dp = build_dispatcher(settings, profiles, admin_service)
    me = await bot.get_me()
    log.info("Telegram bot @%s online", me.username)
    await bot.set_my_commands([
        BotCommand(command="start", description="Start / main menu"),
        BotCommand(command="help", description="Help & safety"),
        BotCommand(command="cancel", description="Stop the current step"),
    ])
    try:
        await dp.start_polling(bot, handle_signals=False)
    finally:
        await bot.session.close()
