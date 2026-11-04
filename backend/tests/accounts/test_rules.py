"""The age gate, rating limit, content preferences and owner list, enforced in code (F7, F8, K7)."""

from datetime import date

import pytest

from accounts import rules
from lucid.env import Env
from lucid.errors import ApiError


def test_age_counts_whole_years_and_turns_on_the_birthday():
    born = date(2009, 6, 15)

    assert rules.age_on(born, date(2026, 6, 14)) == 16
    assert rules.age_on(born, date(2026, 6, 15)) == 17


def test_a_leap_day_birthday_comes_on_the_first_of_march_in_other_years():
    born = date(2008, 2, 29)

    assert rules.age_on(born, date(2025, 2, 28)) == 16
    assert rules.age_on(born, date(2025, 3, 1)) == 17


def test_under_17_is_teen_only_and_the_limit_lifts_on_the_17th_birthday():
    born = date(2009, 6, 15)

    assert rules.max_rating(born, date(2026, 6, 14)) == "teen"
    assert rules.max_rating(born, date(2026, 6, 15)) == "mature"


def test_an_account_without_a_birth_date_is_teen_only():
    assert rules.max_rating(None) == "teen"
    assert rules.allows_rating(None, "teen")
    assert not rules.allows_rating(None, "mature")
    assert rules.allows_rating(date(1990, 1, 1), "mature")


@pytest.mark.parametrize(
    ("born", "error_type"),
    [
        (date(2026, 11, 4), "future"),
        (date(1890, 1, 1), "implausible"),
        (date(2014, 11, 4), "too_young"),
    ],
)
def test_birth_dates_that_cant_sign_up(born, error_type, settings):
    settings.MIN_SIGNUP_AGE = 13

    with pytest.raises(ApiError) as raised:
        rules.check_birth_date(born, on=date(2026, 11, 3))

    assert raised.value.code == "validation_error"
    [field] = raised.value.details["fields"]
    assert (field["field"], field["type"]) == ("birth_date", error_type)


def test_the_youngest_age_that_can_sign_up_is_a_setting(settings):
    settings.MIN_SIGNUP_AGE = 13

    rules.check_birth_date(date(2013, 11, 3), on=date(2026, 11, 3))
    settings.MIN_SIGNUP_AGE = 14
    with pytest.raises(ApiError):
        rules.check_birth_date(date(2013, 11, 3), on=date(2026, 11, 3))


def test_content_preferences_fill_in_defaults_and_drop_junk():
    assert rules.content_prefs(None) == {"gore": "medium", "romance": True, "dark_themes": True}
    assert rules.content_prefs({"gore": "high", "romance": False, "x": 1, "dark_themes": "no"}) == {
        "gore": "high",
        "romance": False,
        "dark_themes": True,
    }
    assert rules.content_prefs({"gore": "extreme"})["gore"] == "medium"


def test_no_owner_email_is_built_in():
    """K7: the owner's address comes only from OWNER_EMAILS, so none is in the public repo."""
    assert Env.model_fields["owner_emails"].default == ""


def test_owner_emails_come_from_the_setting(settings):
    settings.OWNER_EMAILS = ["owner@example.com"]

    assert rules.is_owner_email(" Owner@Example.com ")
    assert not rules.is_owner_email("someone@gmail.com")
    settings.OWNER_EMAILS = []
    assert not rules.is_owner_email("owner@example.com")
