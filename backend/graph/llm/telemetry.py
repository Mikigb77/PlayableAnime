"""One record per model call (T5), collected per request so a turn can log and bill its total.

A call that retried counts the tokens of both attempts, since the provider bills both. Records
hold numbers and names only, never prompt or story text (T6).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Literal, Protocol

Outcome = Literal["ok", "blocked", "unavailable", "bad_key", "cancelled"]


@dataclass(frozen=True)
class CallRecord:
    node: str
    model: str
    provider: str
    byok: bool
    outcome: Outcome
    input_tokens: int
    output_tokens: int  # includes thinking tokens
    thinking_tokens: int
    images: int
    latency_ms: int
    first_token_ms: int | None  # streamed calls: time to the first visible text (S3)
    attempts: int
    retries: int
    retry_reasons: tuple[str, ...]
    blocked: bool
    block_categories: tuple[str, ...]
    block_stage: str | None
    cost_usd: Decimal
    price_known: bool
    error_kind: str | None = None

    def as_log(self) -> dict[str, Any]:
        data = asdict(self)
        data["cost_usd"] = float(self.cost_usd)
        data["retry_reasons"] = list(self.retry_reasons)
        data["block_categories"] = list(self.block_categories)
        return data


class CallRecorder(Protocol):
    def record(self, call: CallRecord) -> None: ...


class TurnTelemetry:
    """Collects the calls of one request (a turn, a draft or a picture).

    WS7 debits `billable_cost_usd` for a completed turn (K2), and the turn endpoint logs
    `summary()` as the T5 line.
    """

    def __init__(self) -> None:
        self.calls: list[CallRecord] = []

    def record(self, call: CallRecord) -> None:
        self.calls.append(call)

    @property
    def cost_usd(self) -> Decimal:
        """What the calls cost, whoever paid: the T5 figure."""
        return sum((c.cost_usd for c in self.calls), Decimal(0))

    @property
    def billable_cost_usd(self) -> Decimal:
        """What the calls on our own account cost: the figure billing debits plus its margin.

        Calls on a player's own key are free to them (K6), though they are still logged.
        """
        return sum((c.cost_usd for c in self.calls if not c.byok), Decimal(0))

    def summary(self) -> dict[str, Any]:
        calls = self.calls
        return {
            "calls": len(calls),
            "models": sorted({c.model for c in calls}),
            "input_tokens": sum(c.input_tokens for c in calls),
            "output_tokens": sum(c.output_tokens for c in calls),
            "thinking_tokens": sum(c.thinking_tokens for c in calls),
            "images": sum(c.images for c in calls),
            "latency_ms": sum(c.latency_ms for c in calls),
            "cost_usd": float(self.cost_usd),
            "billable_cost_usd": float(self.billable_cost_usd),
            "price_known": all(c.price_known for c in calls),
            "retries": sum(c.retries for c in calls),
            "blocks": sum(1 for c in calls if c.blocked),
            "block_categories": sorted(_flatten(c.block_categories for c in calls)),
            "failures": sum(1 for c in calls if c.outcome in ("unavailable", "bad_key")),
            "byok": any(c.byok for c in calls),
            "by_node": {
                node: _node_summary(calls, node) for node in dict.fromkeys(c.node for c in calls)
            },
        }


def _node_summary(calls: list[CallRecord], node: str) -> dict[str, Any]:
    mine = [c for c in calls if c.node == node]
    return {
        "model": mine[-1].model,
        "calls": len(mine),
        "cost_usd": float(sum((c.cost_usd for c in mine), Decimal(0))),
    }


def _flatten(groups: Iterable[tuple[str, ...]]) -> set[str]:
    return {item for group in groups for item in group}
