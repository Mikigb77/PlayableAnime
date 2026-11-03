"""The cost and charge arithmetic (K2, K6, K8), with no database."""

from decimal import Decimal

import pytest

from billing.pricing import K8_MAX_COST_MULTIPLE, bill, charge_cents, cost_spread, to_cents
from tests.billing.conftest import call


def test_a_charge_is_the_model_cost_plus_the_margin_in_cents():
    # A typical turn: about 2 cents of model cost (REQUIREMENTS.md), plus half.
    assert charge_cents(Decimal("0.0206"), Decimal("0.5")) == Decimal("3.0900")
    assert charge_cents(Decimal("0.034"), Decimal("0")) == Decimal("3.4000")


def test_a_charge_is_proportional_to_the_cost_with_no_fixed_fee():
    """K8: no per-turn fee that would weigh more on a cheap turn than on a dear one."""
    margin = Decimal("0.5")

    assert charge_cents(Decimal(0), margin) == 0
    assert charge_cents(Decimal("0.04"), margin) == 2 * charge_cents(Decimal("0.02"), margin)


def test_cents_keep_four_decimals():
    assert to_cents(Decimal("0.0000123456")) == Decimal("0.0012")
    assert to_cents(Decimal("0.000000005")) == Decimal("0.0000")


def test_negative_costs_and_margins_are_refused():
    with pytest.raises(ValueError):
        charge_cents(Decimal("-0.01"), Decimal("0.5"))
    with pytest.raises(ValueError):
        charge_cents(Decimal("0.01"), Decimal("-0.1"))


def test_a_bill_charges_only_the_calls_on_our_key():
    """K6: calls on the player's own key are recorded but never charged."""
    billed = bill(
        [
            call("0.002", model="gemini-3.5-flash-lite", input_tokens=2500, output_tokens=250),
            call("0.019", byok=True, input_tokens=8000, output_tokens=800),
            call("0.034", model="gemini-3.1-flash-lite-image", images=1),
        ],
        Decimal("0.5"),
    )

    assert billed.cost_usd == Decimal("0.036")
    assert billed.byok_cost_usd == Decimal("0.019")
    assert billed.charge_cents == Decimal("5.4000")
    assert (billed.calls, billed.byok_calls, billed.images) == (3, 1, 1)
    assert (billed.input_tokens, billed.output_tokens) == (10500, 1050)
    assert billed.used_our_key
    assert billed.detail()["models"] == [
        "gemini-3.1-flash-lite-image",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
    ]


def test_a_bill_on_the_players_own_key_charges_nothing():
    billed = bill([call("0.02", byok=True)], Decimal("0.5"))

    assert (billed.cost_usd, billed.charge_cents) == (0, 0)
    assert not billed.used_our_key


def test_the_cost_spread_is_the_dearest_turn_over_the_cheapest():
    spread = cost_spread({"quiet": Decimal(2), "montage": Decimal(3), "event": Decimal("2.5")})

    assert spread == Decimal("1.5")
    assert spread <= K8_MAX_COST_MULTIPLE


def test_the_cost_spread_needs_two_turns_that_cost_something():
    with pytest.raises(ValueError):
        cost_spread({"quiet": Decimal(2)})
    with pytest.raises(ValueError):
        cost_spread({"quiet": Decimal(0), "event": Decimal(2)})
