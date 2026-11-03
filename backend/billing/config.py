"""Billing settings, read from `settings.BILLING` on every use so tests can override them."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from django.conf import settings


class Use(StrEnum):
    """What a model call is for. Each has its own hold, rate limit and daily quota."""

    TURN = "turn"
    # Drafting and revising a world and a character call a model like a turn does (API.md).
    DRAFT = "draft"
    IMAGE = "image"


class StarterPolicy(StrEnum):
    VERIFIED = "verified"
    ALL = "all"


@dataclass(frozen=True)
class BillingConfig:
    starter_cents: Decimal
    starter_policy: StarterPolicy
    margin: Decimal
    reserve_cents: dict[Use, Decimal]
    hold_ttl_s: int
    per_minute: dict[Use, int]
    per_day: dict[Use, int]


def get_config() -> BillingConfig:
    raw = settings.BILLING
    return BillingConfig(
        starter_cents=Decimal(raw["STARTER_CENTS"]),
        starter_policy=StarterPolicy(raw["STARTER_POLICY"]),
        margin=Decimal(raw["MARGIN"]),
        reserve_cents={Use(k): Decimal(v) for k, v in raw["RESERVE_CENTS"].items()},
        hold_ttl_s=int(raw["HOLD_TTL_S"]),
        per_minute={Use(k): int(v) for k, v in raw["PER_MINUTE"].items()},
        per_day={Use(k): int(v) for k, v in raw["PER_DAY"].items()},
    )
