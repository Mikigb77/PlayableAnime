"""Account rules enforced in code: the age gate and rating limit (F8), content preference defaults
(F7) and who gets the owner role (K7). Plain functions, so views and other apps share them."""

from datetime import date
from typing import Any

from django.conf import settings
from django.utils import timezone

from lucid.errors import field_error

# Under this age an account gets Teen stories only (F8).
MATURE_AGE = 17
# Nobody alive is older; a birth date before this is a typo.
_OLDEST_AGE = 120

TEEN = "teen"
MATURE = "mature"

GORE_LEVELS = ("low", "medium", "high")
CONTENT_PREF_DEFAULTS: dict[str, Any] = {"gore": "medium", "romance": True, "dark_themes": True}


def today() -> date:
    return timezone.localdate()


def age_on(birth_date: date, on: date) -> int:
    """Whole years from `birth_date` to `on`. Someone born on 29 February turns a year older on
    1 March in a year without one."""
    had_birthday = (on.month, on.day) >= (birth_date.month, birth_date.day)
    return on.year - birth_date.year - (0 if had_birthday else 1)


def max_rating(birth_date: date | None, on: date | None = None) -> str:
    """The highest rating an account may play (F8). An account with no birth date is Teen only,
    and a teen's limit rises on their 17th birthday with nothing to update."""
    if birth_date is None:
        return TEEN
    return MATURE if age_on(birth_date, on or today()) >= MATURE_AGE else TEEN


def allows_rating(birth_date: date | None, rating: str) -> bool:
    return rating == TEEN or max_rating(birth_date) == MATURE


def check_birth_date(birth_date: date, on: date | None = None) -> None:
    """Raises a `validation_error` on `birth_date` unless it is a real date and the player is
    old enough to sign up (`MIN_SIGNUP_AGE`)."""
    on = on or today()
    if birth_date > on:
        raise field_error("birth_date", "Your birth date can't be in the future.", type="future")
    age = age_on(birth_date, on)
    if age > _OLDEST_AGE:
        raise field_error("birth_date", "Check your birth date.", type="implausible")
    if age < settings.MIN_SIGNUP_AGE:
        raise field_error(
            "birth_date",
            f"You need to be at least {settings.MIN_SIGNUP_AGE} to play.",
            type="too_young",
        )


def content_prefs(stored: dict[str, Any] | None) -> dict[str, Any]:
    """The stored preferences over the defaults, ignoring anything unknown or malformed."""
    prefs = dict(CONTENT_PREF_DEFAULTS)
    for key, value in (stored or {}).items():
        if key == "gore" and value in GORE_LEVELS:
            prefs[key] = value
        elif key in ("romance", "dark_themes") and isinstance(value, bool):
            prefs[key] = value
    return prefs


def is_owner_email(email: str) -> bool:
    """Whether a verified Google sign-in with this email gets the owner role (K7). The list comes
    from `OWNER_EMAILS`, never from code."""
    return email.strip().lower() in settings.OWNER_EMAILS
