from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from amora.core.catalog import GENDERS, INTERESTS, LOOKING_FOR, SHOW_ME


class Onb(CallbackData, prefix="onb"):
    """Onboarding answers: field = which question, value = chosen option."""
    field: str
    value: str


class Menu(CallbackData, prefix="mn"):
    action: str


class Adm(CallbackData, prefix="adm"):
    action: str
    uid: int = 0
    arg: str = ""


# ---------------------------------------------------------------- main menu (reply keyboard)
BTN_BROWSE = "🔥 Browse"
BTN_MATCHES = "💌 Matches"
BTN_PROFILE = "👤 My Profile"
BTN_LIKES = "❤️ Who Liked Me"
BTN_SETTINGS = "⚙️ Settings"
BTN_VERIFY = "✅ Get Verified"
BTN_HELP = "🆘 Help & Safety"


def main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for text in (BTN_BROWSE, BTN_MATCHES, BTN_PROFILE, BTN_LIKES, BTN_SETTINGS, BTN_VERIFY, BTN_HELP):
        kb.button(text=text)
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup(resize_keyboard=True, input_field_placeholder="Choose an option")


# ---------------------------------------------------------------- onboarding
def terms() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ I'm 18+ and I agree", callback_data=Onb(field="terms", value="agree"))
    kb.button(text="📄 Read the rules", callback_data=Onb(field="terms", value="rules"))
    kb.adjust(1)
    return kb.as_markup()


def options(field: str, items: dict[str, str], columns: int = 2) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, label in items.items():
        kb.button(text=label, callback_data=Onb(field=field, value=key))
    kb.adjust(columns)
    return kb.as_markup()


def gender() -> InlineKeyboardMarkup:
    return options("gender", GENDERS, columns=3)


def show_me() -> InlineKeyboardMarkup:
    return options("show_me", {k: label for k, (label, _) in SHOW_ME.items()}, columns=3)


def looking_for() -> InlineKeyboardMarkup:
    return options("looking_for", LOOKING_FOR, columns=2)


def name_suggestion(first_name: str | None) -> ReplyKeyboardMarkup | None:
    if not first_name:
        return None
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=first_name[:32])]],
                               resize_keyboard=True, one_time_keyboard=True)


def location() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Share my location", request_location=True)]],
        resize_keyboard=True, one_time_keyboard=True,
        input_field_placeholder="…or type your city",
    )


def interests(selected: list[str], minimum: int, maximum: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, label in INTERESTS.items():
        mark = "✅ " if key in selected else ""
        kb.button(text=f"{mark}{label}", callback_data=Onb(field="interest", value=key))
    kb.adjust(3)
    done = InlineKeyboardBuilder()
    count = len(selected)
    done.button(text=f"✔️ Done ({count}/{maximum})" if count >= minimum else f"Pick at least {minimum} ({count})",
                callback_data=Onb(field="interest", value="__done"))
    kb.attach(done)
    return kb.as_markup()


def photo_consent() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ I agree, continue", callback_data=Onb(field="consent", value="agree"))
    kb.button(text="❓ Why do you check faces?", callback_data=Onb(field="consent", value="why"))
    kb.adjust(1)
    return kb.as_markup()


def photos(count: int, maximum: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✔️ Done ({count}/{maximum})", callback_data=Onb(field="photos", value="done"))
    kb.button(text="🗑 Remove last", callback_data=Onb(field="photos", value="remove"))
    kb.adjust(2)
    return kb.as_markup()


def preview() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Submit for review", callback_data=Onb(field="preview", value="submit"))
    kb.button(text="🖼 See all photos", callback_data=Menu(action="photos"))
    kb.button(text="➕ Add photos", callback_data=Onb(field="preview", value="photos"))
    kb.button(text="✏️ Start over", callback_data=Onb(field="preview", value="restart"))
    kb.adjust(1, 2, 1)
    return kb.as_markup()


# ---------------------------------------------------------------- my profile
def my_profile(status: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Edit profile", callback_data=Menu(action="edit"))
    kb.button(text="🖼 All photos", callback_data=Menu(action="photos"))
    if status == "active":
        kb.button(text="⏸ Pause profile", callback_data=Menu(action="pause"))
    elif status == "paused":
        kb.button(text="▶️ Resume profile", callback_data=Menu(action="resume"))
    kb.button(text="🗑 Delete account", callback_data=Menu(action="delete"))
    kb.adjust(2, 1, 1) if status in ("active", "paused") else kb.adjust(2, 1)
    return kb.as_markup()


def confirm(yes_action: str, yes_text: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=yes_text, callback_data=Menu(action=yes_action))
    kb.button(text="↩️ Cancel", callback_data=Menu(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def fix_profile() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Fix my profile", callback_data=Menu(action="edit_confirmed"))
    return kb.as_markup()


# ---------------------------------------------------------------- admin
REJECT_REASONS: dict[str, str] = {
    "face": "No clear face in the photos",
    "fake": "Photos look fake or stolen",
    "inappropriate": "Inappropriate photos or text",
    "spam": "Spam, scam or advertising",
    "incomplete": "Profile looks incomplete or low-effort",
}


def admin_panel(pending: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"📋 Review queue ({pending})", callback_data=Adm(action="queue"))
    kb.button(text="📊 Stats", callback_data=Adm(action="stats"))
    kb.adjust(1)
    return kb.as_markup()


def review(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Approve", callback_data=Adm(action="approve", uid=user_id))
    kb.button(text="❌ Reject…", callback_data=Adm(action="reject_menu", uid=user_id))
    kb.button(text="🔞 Underage: block", callback_data=Adm(action="underage_confirm", uid=user_id))
    kb.button(text="⏭ Next in queue", callback_data=Adm(action="next", uid=user_id))
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def reject_reasons(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, label in REJECT_REASONS.items():
        kb.button(text=label, callback_data=Adm(action="reject", uid=user_id, arg=key))
    kb.button(text="⬅️ Back", callback_data=Adm(action="back", uid=user_id))
    kb.adjust(1)
    return kb.as_markup()


def underage_confirm(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔞 Yes, block permanently", callback_data=Adm(action="underage", uid=user_id))
    kb.button(text="⬅️ Back", callback_data=Adm(action="back", uid=user_id))
    kb.adjust(1)
    return kb.as_markup()
