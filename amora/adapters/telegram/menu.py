"""Main menu (reply keyboard), My Profile actions, help, and fallbacks."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from amora.adapters.telegram import keyboards as kb
from amora.adapters.telegram import texts as t
from amora.adapters.telegram.cards import profile_caption, send_all_photos, send_profile_card
from amora.adapters.telegram.keyboards import Menu
from amora.adapters.telegram.onboarding import ask_next
from amora.config import Settings
from amora.core.profiles import ProfileService
from amora.db.models import User, UserStatus

router = Router(name="menu")
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

fallback = Router(name="fallback")
fallback.message.filter(F.chat.type == ChatType.PRIVATE)

STATUS_LINE = {
    UserStatus.PENDING: "⏳ <i>Status: under review</i>",
    UserStatus.ACTIVE: "🟢 <i>Status: live</i>",
    UserStatus.PAUSED: "⏸ <i>Status: paused (hidden from others)</i>",
    UserStatus.REJECTED: "⚠️ <i>Status: needs changes</i>",
}
COMING_SOON = {
    kb.BTN_BROWSE: "Browsing profiles",
    kb.BTN_MATCHES: "Matches & chat",
    kb.BTN_LIKES: "Who liked me",
    kb.BTN_SETTINGS: "Settings",
    kb.BTN_VERIFY: "Selfie verification",
}


def _has_profile(user: User) -> bool:
    return user.status in (UserStatus.PENDING, UserStatus.ACTIVE, UserStatus.PAUSED, UserStatus.REJECTED)


@router.message(F.text == kb.BTN_PROFILE)
async def my_profile(message: Message, user: User, bot: Bot) -> None:
    if not _has_profile(user):
        await message.answer(t.NEED_PROFILE)
        return
    caption =profile_caption(user) + "\n\n" + STATUS_LINE.get(user.status, "")
    await send_profile_card(bot, message.chat.id, user, caption=caption, reply_markup=kb.my_profile(user.status))


@router.message(F.text.in_(COMING_SOON.keys()))
async def coming_soon(message: Message, user: User) -> None:
    if not _has_profile(user):
        await message.answer(t.NEED_PROFILE)
        return
    await message.answer(t.COMING_SOON.format(feature=COMING_SOON[message.text]))


@router.message(F.text == kb.BTN_HELP)
@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(t.HELP)


@router.callback_query(Menu.filter())
async def on_menu(callback: CallbackQuery, callback_data: Menu, user: User, state: FSMContext, bot: Bot,
                  profiles: ProfileService, settings: Settings) -> None:
    action = callback_data.action
    if action == "photos":
        await callback.answer()
        await send_all_photos(bot, callback.message.chat.id, user)
    elif action == "edit":
        await callback.answer()
        await callback.message.answer(t.EDIT_WARNING, reply_markup=kb.confirm("edit_confirmed", "✏️ Yes, edit my profile"))
    elif action == "edit_confirmed":
        if user.status in (UserStatus.UNDERAGE, UserStatus.BANNED):
            await callback.answer(t.EXPIRED_BUTTON)
            return
        await callback.answer()
        await callback.message.edit_reply_markup(reply_markup=None)
        user = await profiles.reset_profile(user.id)
        await ask_next(callback.message, user, state, profiles, settings)
    elif action in ("pause", "resume"):
        user = await profiles.set_paused(user.id, paused=action == "pause")
        await callback.answer("Profile paused ⏸" if action == "pause" else "Profile live again 🟢")
        await callback.message.edit_reply_markup(reply_markup=kb.my_profile(user.status))
    elif action == "delete":
        await callback.answer()
        await callback.message.answer(t.DELETE_WARNING, reply_markup=kb.confirm("delete_confirmed", "🗑 Yes, delete everything"))
    elif action == "delete_confirmed":
        await callback.answer()
        await callback.message.edit_reply_markup(reply_markup=None)
        await profiles.delete_account(user.id)
        await state.clear()
        await callback.message.answer(t.DELETED, reply_markup=ReplyKeyboardRemove())
    elif action == "cancel":
        await callback.answer("Cancelled")
        await callback.message.delete()
    else:
        await callback.answer(t.EXPIRED_BUTTON)


@fallback.message()
async def unknown_message(message: Message, user: User) -> None:
    if user.status == UserStatus.ONBOARDING:
        await message.answer("Send /start to continue setting up your profile.")
    elif _has_profile(user):
        await message.answer("Use the menu below 👇", reply_markup=kb.main_menu())


@fallback.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    await callback.answer(t.EXPIRED_BUTTON)
