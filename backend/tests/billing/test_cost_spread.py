"""K8: a living world doesn't inflate the bill.

On a normal account (the owner plays free, K7), a quiet turn, a montage turn and a turn with a W16
event are charged within `K8_MAX_COST_MULTIPLE` of each other.

The turns' token budgets below are estimates until T5 gives real numbers (T14). They follow K8's
bounds: the world tick, catch-up, rolls, rumors and the director are code with no model call, so
a montage or an event turn makes the same two model calls as a quiet one (interpret, then
narrate), with a bounded digest of what happened added to the narrator's context. The prices
are Vertex AI's for the default models (ARCHITECTURE.md), as the model layer's telemetry would
price them. The same check runs on the turn graph's own telemetry once the turn endpoint lands:
pass its calls to `meter.charge` and the charges to `cost_spread`.
"""

from decimal import Decimal

import pytest

from billing import credits, meter
from billing.pricing import K8_MAX_COST_MULTIPLE, ModelCall, cost_spread

pytestmark = pytest.mark.django_db

# Dollars per million tokens, in and out.
PRICES = {
    "gemini-3.5-flash-lite": (Decimal("0.30"), Decimal("2.50")),
    "gemini-3.5-flash": (Decimal("1.50"), Decimal("9.00")),
}


def _call(model: str, tokens_in: int, tokens_out: int) -> ModelCall:
    price_in, price_out = PRICES[model]
    cost = (tokens_in * price_in + tokens_out * price_out) / Decimal(1_000_000)
    return ModelCall(model, input_tokens=tokens_in, output_tokens=tokens_out, cost_usd=cost)


def _turn(narrator_in: int, narrator_out: int) -> list[ModelCall]:
    return [
        _call("gemini-3.5-flash-lite", 2_500, 250),  # interpret
        _call("gemini-3.5-flash", narrator_in, narrator_out),  # narrate
    ]


TURNS = {
    # About 8,000 tokens in and under 1,000 out: about 2 cents (REQUIREMENTS.md).
    "quiet": _turn(8_000, 800),
    # A time skip: catch-up runs in a fixed number of code steps (E7), and the narrator gets a
    # bounded digest of them and writes a longer passage.
    "montage": _turn(9_500, 1_400),
    # A W16 event arrives: its description joins the context, and the narration plays it.
    "event": _turn(9_000, 1_100),
}


def _charge(user, calls: list[ModelCall], turn: int) -> Decimal:
    ticket = meter.start(user, meter.TURN)
    entry = meter.charge(ticket, calls, turn=turn)
    return -entry.amount_cents


def test_quiet_montage_and_event_turns_cost_within_the_set_multiple(player):
    charges = {kind: _charge(player, calls, n) for n, (kind, calls) in enumerate(TURNS.items())}

    assert all(charge > 0 for charge in charges.values())  # a normal account pays each one
    assert Decimal("2.5") < charges["quiet"] < Decimal("3.5")  # about 2 cents plus the margin
    assert cost_spread(charges) <= K8_MAX_COST_MULTIPLE


def test_billing_adds_nothing_that_changes_the_spread(player):
    """The spread of what the player pays is the spread of what the model calls cost."""
    charges = {kind: _charge(player, calls, n) for n, (kind, calls) in enumerate(TURNS.items())}
    costs = {kind: sum(c.cost_usd for c in calls) for kind, calls in TURNS.items()}

    assert cost_spread(charges) == pytest.approx(cost_spread(costs), rel=Decimal("0.001"))


def test_a_world_that_called_the_model_off_screen_would_break_the_multiple(player):
    """What K8 rules out: catch-up that runs a model call per NPC per step after a time skip."""
    unbounded = _turn(9_500, 1_400) + [_call("gemini-3.5-flash", 3_000, 400)] * 8 * 6
    credits.credit(player, Decimal(1000))  # so the charge isn't stopped at a zero balance

    charges = {
        "quiet": _charge(player, TURNS["quiet"], 1),
        "montage": _charge(player, unbounded, 2),
    }

    assert cost_spread(charges) > K8_MAX_COST_MULTIPLE
