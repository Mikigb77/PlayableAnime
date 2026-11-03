"""Gemini safety settings per rating (F5), in one table so WS16 and the T15 evals can tune it.

F5 asks for the most permissive level the policy allows. Gemini on Vertex AI offers, from least
to most strict: `off` (no filter, no safety metadata), `block_none` (scores only, and restricted
to approved projects, so we don't use it), `block_only_high`, `block_medium_and_above` and
`block_low_and_above`. Gemini has no category for fictional violence, so gore is governed by the
prompt and the ratings table, never by a filter. The non-configurable filters (child safety and
personal data) stay on whatever we set; they show up as `prohibited_content` or `spii` blocks.

Why each line is where it is:

- **Harassment** is off in Mature, where villains threaten and insult, and filters only the
  worst in Teen.
- **Hate speech** filters only the worst in both, because hate aimed at real groups is out in
  every rating (G12) while fictional race feuds (G23) are in.
- **Sexually explicit** filters only the worst in Mature, as a backstop for the fade-out rule
  (F2, Google's prohibited use policy), and from medium in Teen, where romance stops at a kiss.
- **Dangerous content** filters only the worst in both, as a backstop for F3's ban on real-world
  harm instructions.
- **Pictures** stay mild in every rating (M6), so they filter from medium, and sexual content
  from low.
"""

from __future__ import annotations

from collections.abc import Mapping

from graph.llm.types import Rating

HARM_CATEGORIES = ("harassment", "hate_speech", "sexually_explicit", "dangerous_content")
THRESHOLDS = ("off", "block_only_high", "block_medium_and_above", "block_low_and_above")

_TEXT: Mapping[Rating, Mapping[str, str]] = {
    "mature": {
        "harassment": "off",
        "hate_speech": "block_only_high",
        "sexually_explicit": "block_only_high",
        "dangerous_content": "block_only_high",
    },
    "teen": {
        "harassment": "block_only_high",
        "hate_speech": "block_only_high",
        "sexually_explicit": "block_medium_and_above",
        "dangerous_content": "block_only_high",
    },
}

_PICTURES: Mapping[str, str] = {
    "harassment": "block_medium_and_above",
    "hate_speech": "block_medium_and_above",
    "sexually_explicit": "block_low_and_above",
    "dangerous_content": "block_medium_and_above",
}


def safety_settings(rating: Rating, *, picture: bool = False) -> Mapping[str, str]:
    """The threshold per harm category for a call, in our lowercase names."""
    if rating not in _TEXT:
        raise ValueError(f"Unknown rating {rating!r}")
    return dict(_PICTURES if picture else _TEXT[rating])
