"""Rendering profiles as Telegram messages."""

from html import escape

from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InputMediaPhoto, Message

from amora.core.catalog import GENDERS, INTERESTS, LOOKING_FOR, show_me_label
from amora.db.models import Photo, User


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def photo_input(photo: Photo):
    return photo.tg_file_id or FSInputFile(photo.local_path)


def profile_caption(user: User) -> str:
    verified = " ✅" if user.is_verified else ""
    place = escape(user.city) if user.city else "Location shared"
    lines = [
        f"<b>{escape(user.display_name or '?')}, {user.age() or '?'}</b>{verified}",
        f"📍 {place}",
        f"🎯 {LOOKING_FOR.get(user.looking_for or '', '?')}",
        "",
        escape(user.bio or ""),
    ]
    if user.interests:
        lines += ["", "🏷 " + " · ".join(INTERESTS.get(i, i) for i in user.interests)]
    if len(user.photos) > 1:
        lines += ["", f"📸 {len(user.photos)} photos"]
    return "\n".join(lines)


def admin_caption(user: User) -> str:
    accounts = ", ".join(
        f"{a.platform}: {'@' + escape(a.username) if a.username else a.platform_user_id}" for a in user.accounts
    )
    faces = " ".join(
        f"#{p.position + 1}:{p.face_score:.2f}" + (f"/m{p.match_score:.2f}" if p.match_score is not None else "")
        for p in user.photos
    )
    location = escape(user.city) if user.city else f"{user.lat:.3f}, {user.lon:.3f}" if user.lat is not None else "?"
    return "\n".join([
        f"🆕 <b>Profile #{user.id}</b> · {accounts}",
        f"<b>{escape(user.display_name or '?')}, {user.age()}</b> · {GENDERS.get(user.gender or '', '?')} → "
        f"{show_me_label(user.show_me or [])}",
        f"📍 {location} · 🎯 {LOOKING_FOR.get(user.looking_for or '', '?')}",
        f"📝 {escape(_shorten(user.bio or '', 250))}",
        "🏷 " + ", ".join(INTERESTS.get(i, i) for i in user.interests or []),
        f"📸 {len(user.photos)} photos · face scores {faces}",
        f"🕐 joined {user.created_at:%Y-%m-%d %H:%M}",
    ])


async def send_profile_card(bot: Bot, chat_id: int, user: User, *, caption: str | None = None,
                            reply_markup: InlineKeyboardMarkup | None = None) -> Message:
    caption = caption or profile_caption(user)
    if user.photos:
        return await bot.send_photo(chat_id, photo_input(user.photos[0]), caption=caption, reply_markup=reply_markup)
    return await bot.send_message(chat_id, caption, reply_markup=reply_markup)


async def send_all_photos(bot: Bot, chat_id: int, user: User) -> None:
    if not user.photos:
        return
    if len(user.photos) == 1:
        await bot.send_photo(chat_id, photo_input(user.photos[0]))
        return
    await bot.send_media_group(chat_id, [InputMediaPhoto(media=photo_input(p)) for p in user.photos])


async def append_to_card(message: Message, note: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Add a status line (e.g. 'Approved by X') to a card, whether it's a photo or a text message."""
    if message.photo:
        caption = (message.html_text or "") + f"\n\n{note}"
        if len(caption) <= 1024:
            await message.edit_caption(caption=caption, reply_markup=reply_markup)
        else:  # caption limit reached: keep the card, post the note as a reply
            await message.edit_reply_markup(reply_markup=reply_markup)
            await message.reply(note)
    else:
        await message.edit_text((message.html_text or "") + f"\n\n{note}", reply_markup=reply_markup)
