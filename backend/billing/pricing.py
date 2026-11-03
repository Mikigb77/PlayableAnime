"""What a request costs us and what it charges the player (K2, K6, M7, K8).

Plain Python with no Django, so the turn graph, the picture code and the evals can use it too.

The per-model prices are the model layer's (`graph/llm/pricing.py`): each model call's telemetry
record (`graph.llm.CallRecord`, T5) carries its raw cost in dollars, worked out from its tokens
and pictures. Billing adds the margin and nothing else, so a turn's charge is proportional to its
model cost, with no fixed fee that would weigh more on a cheap turn than on a dear one (K8).

A model missing from the price table is priced at the table's dearest fallback, so a charge never
undercounts what we pay. Its entry says `price_known: false` and a warning is logged, so the
table gets fixed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

# Amounts in cents are kept to this precision: a turn costs about 2 cents (API.md).
CENTS = Decimal("0.0001")

# K8: a montage turn or a turn with a W16 event may cost more than a quiet turn, but never more
# than this multiple of it. Provisional until T5 gives real numbers (T14).
K8_MAX_COST_MULTIPLE = Decimal(3)


class BillableCall(Protocol):
    """One model call, as the model layer's telemetry records it (`graph.llm.CallRecord`)."""

    @property
    def model(self) -> str: ...
    @property
    def input_tokens(self) -> int: ...
    @property
    def output_tokens(self) -> int: ...
    @property
    def images(self) -> int: ...
    @property
    def cost_usd(self) -> Decimal: ...
    @property
    def byok(self) -> bool: ...
    # False when the model wasn't in the price table, so `cost_usd` is the dearest fallback.
    @property
    def price_known(self) -> bool: ...


@dataclass(frozen=True)
class ModelCall:
    """A `BillableCall` for code that has no telemetry record of its own, and for tests."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    images: int = 0
    cost_usd: Decimal = Decimal(0)
    byok: bool = False
    price_known: bool = True


@dataclass(frozen=True)
class Bill:
    """The calls of one request, split into what we paid for and what the player's own key did."""

    # Our raw model cost, in dollars: the calls on our key only (K6).
    cost_usd: Decimal
    # The calls the player's own key paid for. Recorded, never charged.
    byok_cost_usd: Decimal
    # What the player owes for our calls: the cost plus the margin, in cents (K2).
    charge_cents: Decimal
    calls: int
    byok_calls: int
    input_tokens: int
    output_tokens: int
    images: int
    models: tuple[str, ...]
    # Whether every call on our key was priced from the table. When one wasn't, the model layer
    # priced it at the dearest fallback, so the charge never undercounts our cost.
    price_known: bool = True

    @property
    def used_our_key(self) -> bool:
        return self.calls > self.byok_calls

    def detail(self) -> dict:
        """The numbers a ledger entry keeps: never prompt or story text (T6)."""
        detail = {
            "cost_usd": str(self.cost_usd),
            "calls": self.calls,
            "byok_calls": self.byok_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "images": self.images,
            "models": list(self.models),
        }
        if not self.price_known:
            detail["price_known"] = False
        return detail


def to_cents(dollars: Decimal) -> Decimal:
    return (Decimal(dollars) * 100).quantize(CENTS, rounding=ROUND_HALF_UP)


def charge_cents(cost_usd: Decimal, margin: Decimal) -> Decimal:
    """The charge for a raw model cost: the cost plus the margin, in cents (K2)."""
    if cost_usd < 0:
        raise ValueError("A model cost can't be negative.")
    if margin < 0:
        raise ValueError("The margin can't be negative.")
    return to_cents(Decimal(cost_usd) * (1 + Decimal(margin)))


def bill(calls: Iterable[BillableCall], margin: Decimal) -> Bill:
    """Totals a request's model calls. Only the calls on our key are charged (K6, M7)."""
    calls = list(calls)
    ours = [c for c in calls if not c.byok]
    cost = sum((Decimal(c.cost_usd) for c in ours), Decimal(0))
    byok_cost = sum((Decimal(c.cost_usd) for c in calls if c.byok), Decimal(0))
    return Bill(
        cost_usd=cost,
        byok_cost_usd=byok_cost,
        charge_cents=charge_cents(cost, margin),
        calls=len(calls),
        byok_calls=len(calls) - len(ours),
        input_tokens=sum(c.input_tokens for c in calls),
        output_tokens=sum(c.output_tokens for c in calls),
        images=sum(c.images for c in calls),
        models=tuple(sorted({c.model for c in calls})),
        price_known=all(c.price_known for c in ours),
    )


def cost_spread(charges: Mapping[str, Decimal]) -> Decimal:
    """How many times the dearest of these turns costs the cheapest (K8).

    Pass a quiet turn, a montage turn and an event turn, charged on a normal account, and
    compare the result with `K8_MAX_COST_MULTIPLE`.
    """
    values = [Decimal(v) for v in charges.values()]
    if len(values) < 2:
        raise ValueError("Compare at least two turns.")
    if min(values) <= 0:
        raise ValueError("Every turn compared must cost something.")
    return max(values) / min(values)
