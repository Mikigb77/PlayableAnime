"""Billing reads the model layer's telemetry records as they are (`graph.llm`, T5)."""

from decimal import Decimal

import pytest

from billing import meter
from billing.models import EntryKind
from billing.pricing import bill
from graph.llm import CallRecord, TurnTelemetry

pytestmark = pytest.mark.django_db


def _record(node: str, model: str, cost: str, *, byok: bool = False, known: bool = True):
    return CallRecord(
        node=node,
        model=model,
        provider="gemini" if byok else "vertex",
        byok=byok,
        outcome="ok",
        input_tokens=8000,
        output_tokens=800,
        thinking_tokens=0,
        images=0,
        latency_ms=900,
        first_token_ms=400,
        attempts=1,
        retries=0,
        retry_reasons=(),
        blocked=False,
        block_categories=(),
        block_stage=None,
        cost_usd=Decimal(cost),
        price_known=known,
    )


def test_a_turns_telemetry_is_charged_at_its_billable_cost_plus_the_margin(player):
    telemetry = TurnTelemetry()
    telemetry.record(_record("interpret", "gemini-3.5-flash-lite", "0.0014"))
    telemetry.record(_record("narrator", "gemini-3.5-flash", "0.0192"))
    telemetry.record(_record("checker", "gemini-3.5-flash-lite", "0.0010", byok=True))
    ticket = meter.start(player, meter.TURN)

    entry = meter.charge(ticket, telemetry.calls, turn=3)

    assert bill(telemetry.calls, Decimal(0)).cost_usd == telemetry.billable_cost_usd
    assert entry.cost_usd == telemetry.billable_cost_usd == Decimal("0.0206")
    assert entry.amount_cents == Decimal("-3.09")
    assert entry.kind == EntryKind.TURN


def test_a_model_missing_from_the_price_table_is_charged_and_flagged(player, log_lines):
    """The model layer prices it at the dearest fallback, so we never undercount (T5)."""
    ticket = meter.start(player, meter.TURN)

    entry = meter.charge(ticket, [_record("narrator", "gemini-9-ultra", "0.0256", known=False)])

    assert entry.amount_cents == Decimal("-3.84")
    assert entry.detail["price_known"] is False
    assert any("no price in the table" in line["message"] for line in log_lines())
