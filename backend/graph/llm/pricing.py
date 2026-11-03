"""Estimated model cost per call (T5), the raw cost that billing adds its margin to (K2, M7).

Prices are Vertex AI's standard prices on the `global` endpoint, in US dollars, read from
https://cloud.google.com/vertex-ai/generative-ai/pricing on 2026-11-03. Regional endpoints cost
10% more. Thinking tokens bill as output. Gemini API prices for BYOK calls are close enough for
an estimate, and BYOK turns are free to the player anyway (K6).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from graph.llm.types import Usage

_MILLION = Decimal(1_000_000)
REGIONAL_MULTIPLIER = Decimal("1.1")


@dataclass(frozen=True)
class Price:
    input_per_m: Decimal
    output_per_m: Decimal
    per_image: Decimal | None = None


def _price(input_per_m: str, output_per_m: str, per_image: str | None = None) -> Price:
    return Price(
        Decimal(input_per_m), Decimal(output_per_m), Decimal(per_image) if per_image else None
    )


PRICES: dict[str, Price] = {
    "gemini-3.5-flash": _price("1.50", "9.00"),
    "gemini-3.5-flash-lite": _price("0.30", "2.50"),
    "gemini-3.1-flash-lite": _price("0.25", "1.50"),
    "gemini-3.1-pro-preview": _price("2.00", "12.00"),  # prompts up to 200K tokens
    # A 1K picture is 1,120 output tokens at $30 per million, which Google rounds to $0.034.
    "gemini-3.1-flash-lite-image": _price("0.25", "1.50", "0.034"),
}

# An unknown model is priced like the dearest text model above, so estimates never undercount.
FALLBACK_PRICE = _price("2.00", "12.00", "0.134")


def price_for(model: str) -> tuple[Price, bool]:
    """The price for a model id, matching versioned ids like `gemini-3.5-flash-001` by prefix.

    The flag says whether the model was in the table.
    """
    if model in PRICES:
        return PRICES[model], True
    for known in sorted(PRICES, key=len, reverse=True):
        if model.startswith(f"{known}-"):
            return PRICES[known], True
    return FALLBACK_PRICE, False


def estimate_cost(
    model: str, usage: Usage, *, images: int = 0, location: str = "global"
) -> tuple[Decimal, bool]:
    """Estimated cost in dollars, and whether the model's price is known.

    A picture call bills its input tokens plus a flat price per image; its few text tokens are
    left out.
    """
    price, known = price_for(model)
    cost = usage.input_tokens * price.input_per_m / _MILLION
    if images and price.per_image is not None:
        cost += images * price.per_image
    else:
        cost += usage.output_tokens * price.output_per_m / _MILLION
    if location != "global":
        cost *= REGIONAL_MULTIPLIER
    return cost, known
