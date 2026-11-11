"""Validation for user-typed profile fields. Every function raises ValidationError with a user-facing message."""

import re
from datetime import date


class ValidationError(ValueError):
    pass


_DOB_RE = re.compile(r"^\s*(\d{1,2})\s*[./\-\s]\s*(\d{1,2})\s*[./\-\s]\s*(\d{4})\s*$")
_LINK_RE = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.(me|dog)/|discord\.gg|discord(app)?\.com/invite"
    r"|\b[\w-]+\.(com|net|org|io|me|gg|in|co|xyz|app|ly|link|site|online|info)\b)",
    re.IGNORECASE,
)
_HANDLE_RE = re.compile(r"(?<![\w.])@[A-Za-z0-9_]{3,}")
_PHONE_RE = re.compile(r"(?:\+?\d[\s\-().]*){8,}")
_NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-.][^\W\d_]+)*\.?$")
_CITY_RE = re.compile(r"^[^\W\d_][\w .,'()\-]*$")


def age_on(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def parse_dob(text: str, today: date | None = None) -> date:
    today = today or date.today()
    match = _DOB_RE.match(text or "")
    if not match:
        raise ValidationError("Please send your birthday as DD/MM/YYYY, for example 21/04/2001.")
    day, month, year = (int(g) for g in match.groups())
    try:
        dob = date(year, month, day)
    except ValueError:
        raise ValidationError("That date doesn't exist. Please check it and try again (DD/MM/YYYY).") from None
    if dob >= today:
        raise ValidationError("That date is in the future. Please send your real birthday (DD/MM/YYYY).")
    if age_on(dob, today) > 100:
        raise ValidationError("Please send your real birthday (DD/MM/YYYY).")
    return dob


def contact_info_error(text: str) -> str | None:
    """Profiles may not carry links, @handles, phone numbers or emails (anti-scam / anti-spam)."""
    if _LINK_RE.search(text):
        return "Links aren't allowed in your profile."
    if _HANDLE_RE.search(text) or re.search(r"[\w.+-]+@[\w-]+\.\w+", text):
        return "Usernames and emails aren't allowed. You can share contacts after you match."
    if _PHONE_RE.search(text):
        return "Phone numbers aren't allowed. You can share contacts after you match."
    return None


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def clean_name(text: str) -> str:
    name = _squash(text)
    if not 2 <= len(name) <= 32:
        raise ValidationError("Your name should be 2–32 characters.")
    if not _NAME_RE.match(name):
        raise ValidationError("Please use letters only for your name (no numbers, emoji or symbols).")
    return name


def clean_city(text: str) -> str:
    city = _squash(text)
    if not 2 <= len(city) <= 60:
        raise ValidationError("City name should be 2–60 characters.")
    if contact_info_error(city) or not _CITY_RE.match(city):
        raise ValidationError("Please type just your city name, e.g. Mumbai.")
    return city


def clean_bio(text: str) -> str:
    bio = (text or "").strip()
    bio = re.sub(r"\n{3,}", "\n\n", bio)
    if len(bio) < 10:
        raise ValidationError("Tell people a bit more about yourself (at least 10 characters).")
    if len(bio) > 500:
        raise ValidationError(f"Your bio is {len(bio)} characters; the limit is 500. Please shorten it.")
    error = contact_info_error(bio)
    if error:
        raise ValidationError(error)
    return bio
