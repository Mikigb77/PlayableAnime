"""Estimated model cost per call (T5), the raw cost that billing adds its margin to (K2, M7).

Prices are Vertex AI's standard prices on the `global` endpoint, in US dollars, read from
https://cloud.google.com/vertex-ai/generative-ai/pricing on 2026-11-03. Regional endpoints cost
10% more. Thinking tokens bill as output. Gemini API prices for BYOK calls are close enough for
an estimate, and BYOK turns are free to the player anyway (K6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from graph.llm.types import Usage

_MILLION = Decimal(1_000_000)
REGIONAL_MULTIPLIER = Decimal("1.1")
TOKENS_PER_1K_IMAGE = 1120  # what Google bills for one 1K picture, in or out


@dataclass(frozen=True)
class Price:
    input_per_m: Decimal
    output_per_m: Decimal
    image_output_per_m: Decimal | None = None  # image models bill a picture's output tokens
    # Prompt tokens Gemini had just seen (implicit caching, on by default) bill at this rate.
    # None bills them as ordinary input.
    cached_input_per_m: Decimal | None = None


def _price(
    input_per_m: str,
    output_per_m: str,
    image_output_per_m: str | None = None,
    *,
    cached: str | None = None,
) -> Price:
    return Price(
        Decimal(input_per_m),
        Decimal(output_per_m),
        Decimal(image_output_per_m) if image_output_per_m else None,
        Decimal(cached) if cached else None,
    )


# Cached input is a tenth of the input price for every text and image model below (checked
# 2026-11-04). The price list gives Transcribe no cached rate.
PRICES: dict[str, Price] = {
    "gemini-3.5-flash": _price("1.50", "9.00", cached="0.15"),
    "gemini-3.5-flash-lite": _price("0.30", "2.50", cached="0.03"),
    "gemini-3.1-flash-lite": _price("0.25", "1.50", cached="0.025"),
    # Prompts up to 200K tokens.
    "gemini-3.1-pro-preview": _price("2.00", "12.00", cached="0.20"),
    # A 1K picture is 1,120 output tokens at $30 per million: $0.034 (M8). Bigger sizes bill more.
    "gemini-3.1-flash-lite-image": _price("0.25", "1.50", "30.00", cached="0.025"),
    # Nano Banana 2.1, the same $0.034 at 1K with dearer input, so a reference portrait adds about
    # $0.002 (M8). Text out at $7.50 per million (checked 2026-11-07).
    "gemini-nano-banana-2.1": _price("1.50", "7.50", "30.00", cached="0.15"),
    # Speech to text (V6), the file version: audio in at $2.00 and text out at $12 per million
    # tokens, about $0.005 a minute of speech. Its preview name, `-preview`, matches this entry.
    "gemini-3.5-transcribe": _price("2.00", "12.00"),
    # Text to speech (V9): text in, audio out at 25 tokens a second of speech. These are the
    # prices from 2027-01-01 (checked 2026-11-06); until then Google gives half the audio back
    # as credits ($6 and $9 a million). About 1.8 cents a minute of speech for Flash-Lite TTS.
    "gemini-3.8-flash-lite-tts": _price("1.00", "12.00"),
    "gemini-3.8-flash-tts": _price("1.00", "18.00"),
}

# An unknown model is priced like the dearest models we know of, so estimates never undercount:
# Gemini 3.1 Pro for text, and Gemini 3 Pro Image ($0.134 a 1K picture) for pictures.
FALLBACK_PRICE = _price("2.00", "12.00", "120.00")

# What may follow a known id and still be the same model: `-001`, `-09-2026`, `-preview`...
_VERSION_SUFFIX = re.compile(r"-(\d{3}|\d{2}-\d{4}|preview|exp|latest)(-|$)")


def price_for(model: str) -> tuple[Price, bool]:
    """The price for a model id, and whether it was in the table.

    A versioned id such as `gemini-3.5-flash-001` matches its family, but a different model
    that only starts the same way, such as `gemini-3.5-flash-image`, does not.
    """
    if model in PRICES:
        return PRICES[model], True
    for known in sorted(PRICES, key=len, reverse=True):
        if model.startswith(known) and _VERSION_SUFFIX.match(model, len(known)):
            return PRICES[known], True
    return FALLBACK_PRICE, False


def estimate_cost(
    model: str, usage: Usage, *, images: int = 0, location: str = "global"
) -> tuple[Decimal, bool]:
    """Estimated cost in dollars, and whether the model's price is known.

    A picture call bills its output tokens at the image rate, and never less than a 1K picture
    each, in case the provider left the image tokens out of the usage.
    Cached prompt tokens bill at the model's cached rate.
    """
    price, known = price_for(model)
    if images and price.image_output_per_m is None:
        price, known = FALLBACK_PRICE, False  # a text price would undercount a picture
    cached = min(usage.cached_tokens, usage.input_tokens)
    cached_rate = price.cached_input_per_m
    if cached_rate is None:
        cached_rate = price.input_per_m
    cost = (usage.input_tokens - cached) * price.input_per_m / _MILLION
    cost += cached * cached_rate / _MILLION
    if images and price.image_output_per_m is not None:
        tokens = max(usage.output_tokens, images * TOKENS_PER_1K_IMAGE)
        cost += tokens * price.image_output_per_m / _MILLION
    else:
        cost += usage.output_tokens * price.output_per_m / _MILLION
    if location != "global":
        cost *= REGIONAL_MULTIPLIER
    return cost, known
