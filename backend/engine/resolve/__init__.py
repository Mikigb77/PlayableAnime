"""Resolve (B5 step 3): logic first, then dice (A2, A3, A5 to A8, R2, R6, G8, G14, G18, G25, A9).

`resolve_intent(state, intent, ctx, rng) -> Resolution` is what `engine.pipeline.resolve` calls.
It settles each step of the interpret step's `Intent` in code: the world's rules, the sheet, the
beats, who stands in the way and whether they can respond at all, then the class, and a seeded roll
only where the facts leave the outcome open. See `engine.resolve.core` for the order of checks.

- `core`: the plan, step by step, and where a chained plan stops (R6).
- `checks`: the world's rules (G8), the sheet (G14) and the beats (R2).
- `power`: the A8 axes, the ladder gap (G18), condition and who can't respond.
- `odds`: bands, odds, difficulty (A5) and the roll (A3).
- `capability`: what the character brings to a rolled step against the challenge the interpret
  step judged, and the lift a run of misses gives the next roll (A2, A3, G14).
- `chain`: chains of cause and effect, link by link (A9).
- `durations`: how long a step takes, rolled when uncertain (W10).
- `effects`: the aim's outcome, the proposed deed and the costs (F4, W1, A1).
- `words`: matching plain words against the state, and reasons in the world's words (A8).

Powers that bend time, player theories and growth (WS9b) live in `engine.resolve.powers`.
"""

from engine.resolve.core import resolve_intent

__all__ = ["resolve_intent"]
