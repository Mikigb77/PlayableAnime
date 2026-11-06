"""Billing settings, read from `settings.BILLING` on every use so tests can override them."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class Use(StrEnum):
    """What a model call is for. Each has its own hold, rate limit and daily quota."""

    TURN = "turn"
    # Drafting and revising a world and a character call a model like a turn does (API.md).
    DRAFT = "draft"
    IMAGE = "image"
    # Turning a dictation into text on our account (V6). Always our key: see `speech.api`.
    SPEECH = "speech"
    # Reading a scene aloud in the studio voice (V9, V10), a part at a time. Always our key.
    VOICE = "voice"


class StarterPolicy(StrEnum):
    VERIFIED = "verified"
    ALL = "all"


@dataclass(frozen=True)
class BillingConfig:
    starter_cents: Decimal
    starter_policy: StarterPolicy
    # K1, M7: the most the house pays for an account's first pictures, in credits.
    house_pictures_cents: Decimal
    margin: Decimal
    reserve_cents: dict[Use, Decimal]
    hold_ttl_s: int
    per_minute: dict[Use, int]
    per_day: dict[Use, int]


def get_config() -> BillingConfig:
    raw = settings.BILLING
    config = BillingConfig(
        starter_cents=Decimal(raw["STARTER_CENTS"]),
        starter_policy=StarterPolicy(raw["STARTER_POLICY"]),
        house_pictures_cents=Decimal(raw["HOUSE_PICTURES_CENTS"]),
        margin=Decimal(raw["MARGIN"]),
        reserve_cents={Use(k): Decimal(v) for k, v in raw["RESERVE_CENTS"].items()},
        hold_ttl_s=int(raw["HOLD_TTL_S"]),
        per_minute={Use(k): int(v) for k, v in raw["PER_MINUTE"].items()},
        per_day={Use(k): int(v) for k, v in raw["PER_DAY"].items()},
    )
    if any(cents <= 0 for cents in config.reserve_cents.values()):
        # A zero hold would let a request start with no credits at all.
        raise ImproperlyConfigured("Every BILLING['RESERVE_CENTS'] must be more than zero.")
    if config.house_pictures_cents < 0:
        raise ImproperlyConfigured("BILLING['HOUSE_PICTURES_CENTS'] can't be negative.")
    return config
