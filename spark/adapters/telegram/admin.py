"""Telegram admin tools: /admin panel, review queue, approve / reject / block-underage, stats.

Review cards go to TG_ADMIN_CHAT_ID if set, otherwise to every owner's DM.
"""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InputMediaPhoto, Message, User as TgUser

from spark.adapters.telegram import keyboards as kb
from spark.adapters.telegram import texts as t
from spark.adapters.telegram.cards import admin_caption, append_to_card, photo_input
from spark.adapters.telegram.keyboards import Adm
from spark.config import Settings
from spark.core.admin import AdminService
from spark.core.profiles import ProfileError, ProfileService
from spark.db.models import Platform, Role, User

log = logging.getLogger(__name__)
router = Router(name="admin")


def _admin_name(tg_user: TgUser) -> str:
    return f"@{tg_user.username}" if tg_user.username else tg_user.full_name


# ---------------------------------------------------------------------- helpers used by other modules
async def send_review_card(bot: Bot, chat_id: int, user: User) -> None:
    if len(user.photos) > 1:
        await bot.send_media_group(chat_id, [InputMediaPhoto(media=photo_input(p)) for p in user.photos])
    caption = admin_caption(user)
    if len(user.photos) == 1:
        await bot.send_photo(chat_id, photo_input(user.photos[0]), caption=caption, reply_markup=kb.review(user.id))
    else:
        await bot.send_message(chat_id, caption, reply_markup=kb.review(user.id))


async def notify_new_submission(bot: Bot, settings: Settings, user: User) -> None:
    targets = [settings.tg_admin_chat_id] if settings.tg_admin_chat_id else settings.owner_tg_ids
    if not targets:
        log.warning("profile %s submitted but no TG_ADMIN_CHAT_ID / OWNER_TG_IDS configured", user.id)
    for chat_id in targets:
        try:
            await send_review_card(bot, chat_id, user)
        except TelegramAPIError as exc:  # e.g. owner never pressed /start on the bot
            log.warning("could not deliver review card to %s: %s", chat_id, exc)


async def notify_user(bot: Bot, user: User, text: str, reply_markup=None) -> None:
    account = user.account(Platform.TELEGRAM)
    if account is None:
        log.info("user %s has no Telegram account; Discord notifications arrive in phase 3", user.id)
        return
    try:
        await bot.send_message(int(account.platform_user_id), text, reply_markup=reply_markup)
    except TelegramAPIError as exc:  # user blocked the bot
        log.info("could not notify user %s: %s", user.id, exc)


async def _guard(callback: CallbackQuery, admin: AdminService) -> bool:
    if await admin.has_role(Platform.TELEGRAM, callback.from_user.id, Role.MOD):
        return True
    await callback.answer("⛔ Staff only.", show_alert=True)
    return False


# ---------------------------------------------------------------------- /admin
@router.message(Command("admin"))
async def cmd_admin(message: Message, admin: AdminService, profiles: ProfileService) -> None:
    role = await admin.role_of(Platform.TELEGRAM, message.from_user.id)
    if role == Role.USER:
        return  # stay invisible to normal users
    pending = (await profiles.count_by_status()).get("pending", 0)
    badge = {Role.OWNER: "👑 Owner", Role.ADMIN: "🛡 Admin", Role.MOD: "🧹 Moderator"}[role]
    await message.answer(f"🛠 <b>Admin panel</b> · {badge}", reply_markup=kb.admin_panel(pending))


@router.callback_query(Adm.filter(F.action == "stats"))
async def on_stats(callback: CallbackQuery, admin: AdminService, profiles: ProfileService) -> None:
    if not await _guard(callback, admin):
        return
    by_status = await profiles.count_by_status()
    by_platform = await profiles.count_by_platform()
    total = sum(by_status.values())
    lines = [f"📊 <b>Stats</b>\n\n👥 Total accounts: <b>{total}</b>"]
    lines += [f"• {status}: {count}" for status, count in sorted(by_status.items())]
    lines += ["", "<b>By platform</b>"] + [f"• {p}: {c}" for p, c in sorted(by_platform.items())]
    await callback.answer()
    await callback.message.answer("\n".join(lines))


@router.callback_query(Adm.filter(F.action.in_({"queue", "next"})))
async def on_queue(callback: CallbackQuery, callback_data: Adm, bot: Bot, admin: AdminService,
                   profiles: ProfileService) -> None:
    if not await _guard(callback, admin):
        return
    after = callback_data.uid if callback_data.action == "next" else 0
    pending = await profiles.pending_users(after_id=after)
    if not pending and after:
        pending = await profiles.pending_users(after_id=0)  # wrap around
    if not pending:
        await callback.answer("🎉 Review queue is empty!", show_alert=True)
        return
    await callback.answer()
    await send_review_card(bot, callback.message.chat.id, pending[0])


# ---------------------------------------------------------------------- decisions
@router.callback_query(Adm.filter(F.action == "approve"))
async def on_approve(callback: CallbackQuery, callback_data: Adm, bot: Bot, admin: AdminService,
                     profiles: ProfileService) -> None:
    if not await _guard(callback, admin):
        return
    name = _admin_name(callback.from_user)
    try:
        user = await profiles.review(callback_data.uid, approve=True, reason=None, admin_platform=Platform.TELEGRAM,
                                     admin_id=callback.from_user.id, admin_name=name)
    except ProfileError as exc:
        await callback.answer(str(exc), show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return
    await callback.answer("Approved ✅")
    await append_to_card(callback.message, f"✅ <b>Approved</b> by {escape(name)}")
    await notify_user(bot, user, t.APPROVED, reply_markup=kb.main_menu())


@router.callback_query(Adm.filter(F.action == "reject_menu"))
async def on_reject_menu(callback: CallbackQuery, callback_data: Adm, admin: AdminService) -> None:
    if not await _guard(callback, admin):
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=kb.reject_reasons(callback_data.uid))


@router.callback_query(Adm.filter(F.action == "underage_confirm"))
async def on_underage_confirm(callback: CallbackQuery, callback_data: Adm, admin: AdminService) -> None:
    if not await _guard(callback, admin):
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=kb.underage_confirm(callback_data.uid))


@router.callback_query(Adm.filter(F.action == "back"))
async def on_back(callback: CallbackQuery, callback_data: Adm, admin: AdminService) -> None:
    if not await _guard(callback, admin):
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=kb.review(callback_data.uid))


@router.callback_query(Adm.filter(F.action == "reject"))
async def on_reject(callback: CallbackQuery, callback_data: Adm, bot: Bot, admin: AdminService,
                    profiles: ProfileService) -> None:
    if not await _guard(callback, admin):
        return
    reason = kb.REJECT_REASONS.get(callback_data.arg, "Profile doesn't meet our guidelines")
    name = _admin_name(callback.from_user)
    try:
        user = await profiles.review(callback_data.uid, approve=False, reason=reason,
                                     admin_platform=Platform.TELEGRAM, admin_id=callback.from_user.id,
                                     admin_name=name)
    except ProfileError as exc:
        await callback.answer(str(exc), show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return
    await callback.answer("Rejected")
    await append_to_card(callback.message, f"❌ <b>Rejected</b> by {escape(name)}: {escape(reason)}")
    await notify_user(bot, user, t.REJECTED.format(reason=escape(reason)), reply_markup=kb.fix_profile())


@router.callback_query(Adm.filter(F.action == "underage"))
async def on_underage(callback: CallbackQuery, callback_data: Adm, bot: Bot, admin: AdminService,
                      profiles: ProfileService, settings: Settings) -> None:
    if not await _guard(callback, admin):
        return
    name = _admin_name(callback.from_user)
    user = await profiles.get(callback_data.uid)
    await profiles.mark_underage(user.id)
    await profiles.log_admin_action(Platform.TELEGRAM, callback.from_user.id, name, "block_underage", user.id)
    await profiles.sync_snapshot(user.id)
    await callback.answer("Blocked")
    await append_to_card(callback.message, f"🔞 <b>Blocked as underage</b> by {escape(name)}")
    await notify_user(bot, user, t.UNDERAGE.format(app=escape(settings.app_name)))
