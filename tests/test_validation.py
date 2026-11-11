from datetime import date

import pytest

from amora.config import Settings
from amora.core.validation import ValidationError, age_on, clean_bio, clean_city, clean_name, parse_dob

TODAY = date(2026, 11, 12)


@pytest.mark.parametrize("text", ["21/04/2001", "21-04-2001", "21.04.2001", " 1/4/2001 "])
def test_dob_formats(text):
    assert parse_dob(text, TODAY) in (date(2001, 4, 21), date(2001, 4, 1))


@pytest.mark.parametrize("text", ["2001-04-21", "31/02/2001", "12/11/2030", "01/01/1900", "hello"])
def test_dob_rejected(text):
    with pytest.raises(ValidationError):
        parse_dob(text, TODAY)


def test_age_birthday_boundary():
    assert age_on(date(2008, 11, 12), TODAY) == 18
    assert age_on(date(2008, 11, 13), TODAY) == 17


@pytest.mark.parametrize("bio", [
    "dm me on t.me/someone", "visit www.example.com", "insta @my_handle", "call +91 98765 43210",
    "mail me a@b.com", "join discord.gg/abc",
])
def test_bio_blocks_contact_info(bio):
    with pytest.raises(ValidationError):
        clean_bio(bio)


def test_bio_ok_and_limits():
    assert clean_bio("  I love hiking and coffee.  ") == "I love hiking and coffee."
    with pytest.raises(ValidationError):
        clean_bio("short")
    with pytest.raises(ValidationError):
        clean_bio("x" * 501)


@pytest.mark.parametrize("name", ["Priya", "Anne-Marie", "José", "O'Neil", "Mary Jane"])
def test_names_ok(name):
    assert clean_name(name) == name


@pytest.mark.parametrize("name", ["A", "John123", "😀😀", "@admin", "x" * 40])
def test_names_rejected(name):
    with pytest.raises(ValidationError):
        clean_name(name)


def test_city():
    assert clean_city(" New   Delhi ") == "New Delhi"
    with pytest.raises(ValidationError):
        clean_city("www.city.com")


def test_owner_ids_parsing():
    s = Settings(_env_file=None, fernet_key="x", owner_tg_ids="123, 456", owner_dc_ids="")
    assert s.owner_tg_ids == [123, 456]
    assert s.owner_dc_ids == []
