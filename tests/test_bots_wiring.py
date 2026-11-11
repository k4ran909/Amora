"""Smoke tests: both adapters import and build without network access."""

from aiogram.fsm.storage.memory import MemoryStorage

from amora.core.admin import AdminService
from amora.core.profiles import ProfileService


def test_telegram_dispatcher_builds(settings, face_engine):
    from amora.adapters.telegram.bot import build_dispatcher

    profiles = ProfileService(None, settings, face_engine)
    dp = build_dispatcher(settings, profiles, AdminService(settings, profiles), storage=MemoryStorage())
    names = [r.name for r in dp.sub_routers]
    assert names == ["admin", "menu", "onboarding", "fallback"]


def test_callback_data_fits_telegram_limit():
    from amora.adapters.telegram.keyboards import Adm, Onb

    assert len(Adm(action="underage_confirm", uid=2_147_483_647, arg="inappropriate").pack()) <= 64
    assert len(Onb(field="looking_for", value="relationship").pack()) <= 64


def test_discord_client_registers_commands(settings, face_engine):
    from amora.adapters.discord.bot import AmoraDiscord

    profiles = ProfileService(None, settings, face_engine)
    client = AmoraDiscord(settings, profiles, AdminService(settings, profiles))
    assert {c.name for c in client.tree.get_commands()} == {"dating", "admin"}
