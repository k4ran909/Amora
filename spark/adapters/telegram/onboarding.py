"""Profile creation flow. Every step saves straight to the DB, and `ask_next` always resumes at the first
missing step, so a bot restart (or /start mid-way) never loses progress."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from spark.adapters.telegram import keyboards as kb
from spark.adapters.telegram import texts as t
from spark.adapters.telegram.admin import notify_new_submission
from spark.adapters.telegram.cards import send_profile_card
from spark.adapters.telegram.keyboards import Onb
from spark.config import Settings
from spark.core.catalog import GENDERS, INTERESTS, LOOKING_FOR, SHOW_ME
from spark.core.profiles import ProfileError, ProfileService
from spark.core.validation import ValidationError, age_on, clean_bio, clean_city, clean_name, parse_dob
from spark.db.models import User, UserStatus

log = logging.getLogger(__name__)

router = Router(name="onboarding")
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)


class Onboarding(StatesGroup):
    terms = State()
    dob = State()
    gender = State()
    show_me = State()
    looking_for = State()
    name = State()
    location = State()
    bio = State()
    interests = State()
    consent = State()
    photos = State()
    preview = State()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ====================================================================== step router
async def ask_next(msg: Message, user: User, state: FSMContext, profiles: ProfileService, settings: Settings) -> None:
    """Prompt for the first missing piece of the profile (or show the preview when complete)."""
    missing = profiles.missing_steps(user)
    step = missing[0] if missing else "preview"
    app = escape(settings.app_name)

    if step == "terms":
        await state.set_state(Onboarding.terms)
        await msg.answer(t.WELCOME.format(app=app), reply_markup=kb.terms())
    elif step == "dob":
        await state.set_state(Onboarding.dob)
        await msg.answer(t.ASK_DOB, reply_markup=ReplyKeyboardRemove())
    elif step == "gender":
        await state.set_state(Onboarding.gender)
        await msg.answer(t.ASK_GENDER, reply_markup=kb.gender())
    elif step == "show_me":
        await state.set_state(Onboarding.show_me)
        await msg.answer(t.ASK_SHOW_ME, reply_markup=kb.show_me())
    elif step == "looking_for":
        await state.set_state(Onboarding.looking_for)
        await msg.answer(t.ASK_LOOKING_FOR, reply_markup=kb.looking_for())
    elif step == "name":
        await state.set_state(Onboarding.name)
        first_name = msg.chat.first_name
        await msg.answer(t.ASK_NAME, reply_markup=kb.name_suggestion(first_name) or ReplyKeyboardRemove())
    elif step == "location":
        await state.set_state(Onboarding.location)
        await msg.answer(t.ASK_LOCATION, reply_markup=kb.location())
    elif step == "bio":
        await state.set_state(Onboarding.bio)
        await msg.answer(t.ASK_BIO, reply_markup=ReplyKeyboardRemove())
    elif step == "interests":
        await state.set_state(Onboarding.interests)
        selected = list(user.interests or [])
        await state.update_data(interests=selected)
        await msg.answer(t.ASK_INTERESTS.format(min=settings.min_interests, max=settings.max_interests),
                         reply_markup=kb.interests(selected, settings.min_interests, settings.max_interests))
    elif step == "consent":
        await state.set_state(Onboarding.consent)
        await msg.answer(t.PHOTO_CONSENT.format(app=app), reply_markup=kb.photo_consent())
    elif step == "photos":
        await state.set_state(Onboarding.photos)
        await msg.answer(t.ASK_PHOTOS.format(extra=settings.max_photos - 1))
    else:
        await show_preview(msg, user, state)


async def show_preview(msg: Message, user: User, state: FSMContext) -> None:
    await state.set_state(Onboarding.preview)
    await msg.answer(t.PREVIEW_HEADER, reply_markup=ReplyKeyboardRemove())
    await send_profile_card(msg.bot, msg.chat.id, user, reply_markup=kb.preview())


async def _choice_made(callback: CallbackQuery, question: str, answer: str) -> None:
    """Replace the question's buttons with the chosen answer, keeping the chat tidy."""
    await callback.answer()
    try:
        await callback.message.edit_text(f"{question}\n<b>{answer}</b> ✓")
    except Exception:  # message too old or already edited; harmless
        pass


def _still_onboarding(user: User) -> bool:
    return user.status == UserStatus.ONBOARDING


# ====================================================================== commands
@router.message(CommandStart())
async def cmd_start(message: Message, user: User, state: FSMContext, profiles: ProfileService,
                    settings: Settings) -> None:
    await state.clear()
    app = escape(settings.app_name)
    status = user.status
    if status == UserStatus.UNDERAGE:
        await message.answer(t.UNDERAGE.format(app=app), reply_markup=ReplyKeyboardRemove())
    elif status == UserStatus.ONBOARDING:
        await ask_next(message, user, state, profiles, settings)
    elif status == UserStatus.PENDING:
        await message.answer(t.UNDER_REVIEW, reply_markup=kb.main_menu())
    elif status == UserStatus.REJECTED:
        await message.answer(t.REJECTED.format(reason=escape(user.rejection_reason or "not specified")),
                             reply_markup=kb.fix_profile())
    else:
        await message.answer(t.WELCOME_BACK.format(name=escape(user.display_name or "")), reply_markup=kb.main_menu())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, user: User, state: FSMContext) -> None:
    await state.clear()
    markup = kb.main_menu() if user.status not in (UserStatus.ONBOARDING, UserStatus.UNDERAGE) else ReplyKeyboardRemove()
    await message.answer("Stopped. Send /start any time to continue.", reply_markup=markup)


# ====================================================================== terms
@router.callback_query(Onb.filter(F.field == "terms"))
async def on_terms(callback: CallbackQuery, callback_data: Onb, user: User, state: FSMContext,
                   profiles: ProfileService, settings: Settings) -> None:
    if not _still_onboarding(user):
        await callback.answer(t.EXPIRED_BUTTON)
        return
    if callback_data.value == "rules":
        await callback.answer()
        await callback.message.answer(t.RULES)
        return
    await callback.answer("Welcome! 🎉")
    await callback.message.edit_reply_markup(reply_markup=None)
    user = await profiles.update(user.id, terms_accepted_at=_now())
    await ask_next(callback.message, user, state, profiles, settings)


# ====================================================================== date of birth
@router.message(Onboarding.dob, F.text)
async def on_dob(message: Message, user: User, state: FSMContext, profiles: ProfileService,
                 settings: Settings) -> None:
    try:
        dob = parse_dob(message.text)
    except ValidationError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    if age_on(dob, datetime.now().date()) < settings.min_age:
        await profiles.mark_underage(user.id)
        await state.clear()
        await message.answer(t.UNDERAGE.format(app=escape(settings.app_name)), reply_markup=ReplyKeyboardRemove())
        log.info("user %s blocked: underage", user.id)
        return
    user = await profiles.update(user.id, dob=dob)
    await ask_next(message, user, state, profiles, settings)


# ====================================================================== single-choice questions
@router.callback_query(Onb.filter(F.field.in_({"gender", "show_me", "looking_for"})))
async def on_choice(callback: CallbackQuery, callback_data: Onb, user: User, state: FSMContext,
                    profiles: ProfileService, settings: Settings) -> None:
    if not _still_onboarding(user):
        await callback.answer(t.EXPIRED_BUTTON)
        return
    field, value = callback_data.field, callback_data.value
    if field == "gender" and value in GENDERS:
        user = await profiles.update(user.id, gender=value)
        await _choice_made(callback, t.ASK_GENDER, GENDERS[value])
    elif field == "show_me" and value in SHOW_ME:
        label, genders = SHOW_ME[value]
        user = await profiles.update(user.id, show_me=genders)
        await _choice_made(callback, t.ASK_SHOW_ME, label)
    elif field == "looking_for" and value in LOOKING_FOR:
        user = await profiles.update(user.id, looking_for=value)
        await _choice_made(callback, t.ASK_LOOKING_FOR, LOOKING_FOR[value])
    else:
        await callback.answer(t.EXPIRED_BUTTON)
        return
    await ask_next(callback.message, user, state, profiles, settings)


# ====================================================================== name / location / bio
@router.message(Onboarding.name, F.text)
async def on_name(message: Message, user: User, state: FSMContext, profiles: ProfileService,
                  settings: Settings) -> None:
    try:
        name = clean_name(message.text)
    except ValidationError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    user = await profiles.update(user.id, display_name=name)
    await ask_next(message, user, state, profiles, settings)


@router.message(Onboarding.location, F.location)
async def on_location_pin(message: Message, user: User, state: FSMContext, profiles: ProfileService,
                          settings: Settings) -> None:
    user = await profiles.update(user.id, lat=message.location.latitude, lon=message.location.longitude, city=None)
    await message.answer("📍 Location saved.", reply_markup=ReplyKeyboardRemove())
    await ask_next(message, user, state, profiles, settings)


@router.message(Onboarding.location, F.text)
async def on_location_city(message: Message, user: User, state: FSMContext, profiles: ProfileService,
                           settings: Settings) -> None:
    try:
        city = clean_city(message.text)
    except ValidationError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    user = await profiles.update(user.id, city=city, lat=None, lon=None)
    await ask_next(message, user, state, profiles, settings)


@router.message(Onboarding.bio, F.text)
async def on_bio(message: Message, user: User, state: FSMContext, profiles: ProfileService,
                 settings: Settings) -> None:
    try:
        bio = clean_bio(message.text)
    except ValidationError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    user = await profiles.update(user.id, bio=bio)
    await ask_next(message, user, state, profiles, settings)


# ====================================================================== interests (multi-select)
@router.callback_query(Onb.filter(F.field == "interest"))
async def on_interest(callback: CallbackQuery, callback_data: Onb, user: User, state: FSMContext,
                      profiles: ProfileService, settings: Settings) -> None:
    if not _still_onboarding(user):
        await callback.answer(t.EXPIRED_BUTTON)
        return
    data = await state.get_data()
    selected: list[str] = list(data.get("interests", user.interests or []))
    lo, hi = settings.min_interests, settings.max_interests

    if callback_data.value == "__done":
        if len(selected) < lo:
            await callback.answer(f"Pick at least {lo} interests.", show_alert=True)
            return
        user = await profiles.update(user.id, interests=selected)
        await _choice_made(callback, "🏷 <b>Interests</b>", " · ".join(INTERESTS[i] for i in selected))
        await ask_next(callback.message, user, state, profiles, settings)
        return

    key = callback_data.value
    if key not in INTERESTS:
        await callback.answer(t.EXPIRED_BUTTON)
        return
    if key in selected:
        selected.remove(key)
    elif len(selected) >= hi:
        await callback.answer(f"You can pick up to {hi}.", show_alert=True)
        return
    else:
        selected.append(key)
    await state.update_data(interests=selected)
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=kb.interests(selected, lo, hi))


# ====================================================================== photos
@router.callback_query(Onb.filter(F.field == "consent"))
async def on_consent(callback: CallbackQuery, callback_data: Onb, user: User, state: FSMContext,
                     profiles: ProfileService, settings: Settings) -> None:
    if not _still_onboarding(user):
        await callback.answer(t.EXPIRED_BUTTON)
        return
    if callback_data.value == "why":
        await callback.answer()
        await callback.message.answer(t.CONSENT_WHY.format(app=escape(settings.app_name)))
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    user = await profiles.update(user.id, biometric_consent_at=_now())
    await ask_next(callback.message, user, state, profiles, settings)


@router.message(Onboarding.photos, F.photo | F.document)
async def on_photo(message: Message, user: User, bot: Bot, profiles: ProfileService, settings: Settings) -> None:
    if message.document and not (message.document.mime_type or "").startswith("image/"):
        await message.answer(t.PHOTO_ONLY)
        return
    file = message.photo[-1] if message.photo else message.document
    if file.file_size and file.file_size > settings.max_upload_bytes:
        await message.answer("⚠️ That file is too big (max 10 MB).")
        return

    status_msg = await message.reply(t.PHOTO_CHECKING)
    buffer = await bot.download(file)
    try:
        check, user = await profiles.add_photo(user.id, buffer.getvalue())
    except ProfileError as exc:
        await status_msg.edit_text(f"⚠️ {exc}", reply_markup=kb.photos(len(user.photos), settings.max_photos))
        return

    count = len(user.photos)
    if check.ok:
        text = t.PHOTO_OK_MAIN.format(max=settings.max_photos) if count == 1 else t.PHOTO_OK_EXTRA.format(n=count)
    else:
        text = t.PHOTO_REJECTED.format(reason=check.message)
    await status_msg.edit_text(text, reply_markup=kb.photos(count, settings.max_photos) if count else None)


@router.message(Onboarding.photos)
async def on_photo_wrong_type(message: Message) -> None:
    await message.answer(t.PHOTO_ONLY)


@router.callback_query(Onb.filter(F.field == "photos"))
async def on_photos_button(callback: CallbackQuery, callback_data: Onb, user: User, state: FSMContext,
                           profiles: ProfileService, settings: Settings) -> None:
    if not _still_onboarding(user):
        await callback.answer(t.EXPIRED_BUTTON)
        return
    if callback_data.value == "remove":
        user = await profiles.remove_last_photo(user.id)
        count = len(user.photos)
        await callback.answer("Removed.")
        await state.set_state(Onboarding.photos)
        if count:
            await callback.message.edit_text(f"🗑 Removed. You have {count} photo(s).",
                                             reply_markup=kb.photos(count, settings.max_photos))
        else:
            await callback.message.edit_text("🗑 Removed. " + t.ASK_PHOTOS.format(extra=settings.max_photos - 1))
        return
    # done
    if len(user.photos) < settings.min_photos:
        await callback.answer("Add your main photo first.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await ask_next(callback.message, user, state, profiles, settings)


# ====================================================================== preview / submit
@router.callback_query(Onb.filter(F.field == "preview"))
async def on_preview(callback: CallbackQuery, callback_data: Onb, user: User, state: FSMContext, bot: Bot,
                     profiles: ProfileService, settings: Settings) -> None:
    if not _still_onboarding(user):
        await callback.answer(t.EXPIRED_BUTTON)
        return
    action = callback_data.value
    if action == "photos":
        if len(user.photos) >= settings.max_photos:
            await callback.answer(f"You already have {settings.max_photos} photos.", show_alert=True)
            return
        await callback.answer()
        await state.set_state(Onboarding.photos)
        await callback.message.answer("📸 Send more photos of you. Every one must include your face.",
                                      reply_markup=kb.photos(len(user.photos), settings.max_photos))
        return
    if action == "restart":
        await callback.answer()
        await callback.message.edit_reply_markup(reply_markup=None)
        user = await profiles.reset_profile(user.id)
        await ask_next(callback.message, user, state, profiles, settings)
        return
    # submit
    try:
        user = await profiles.submit(user.id)
    except ProfileError as exc:
        await callback.answer(str(exc)[:200], show_alert=True)
        return
    await callback.answer("Submitted! 🎉")
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    await callback.message.answer(t.SUBMITTED, reply_markup=kb.main_menu())
    await notify_new_submission(bot, settings, user)
