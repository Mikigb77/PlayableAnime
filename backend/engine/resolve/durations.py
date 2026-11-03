"""How long a step takes (W10, W10a).

The interpret step proposes a duration and code bounds it by the kind of action. When how long it
takes is itself uncertain (breaking out of a trap, picking a lock, finding someone in a city), a
seeded roll picks it, spread evenly across orders of magnitude around the proposal and still
within the kind's bounds, so the same trap holds someone minutes or days. Inside a time stop the
world clock stands still and only the actor's own clock runs.
"""

import math
from dataclasses import dataclass

from engine.base import DAY
from engine.contracts.intent import IntentStep
from engine.rng import SeededRng
from engine.timekeeping import DURATION_BOUNDS, bound_duration

# An uncertain duration lands between the proposal divided and multiplied by this.
DURATION_SPREAD = 30
# The longest a chain of cause and effect may add to a step (A9, W10): air running out, a fire
# burning down, poison taking hold.
CHAIN_MAX_S = 30 * DAY


@dataclass(frozen=True)
class Timing:
    duration_s: int  # world seconds
    personal_s: int | None  # the actor's lived seconds, when they differ (W10a)
    rolled_s: int | None = None  # set when a roll picked the time
    rolled_value: float | None = None  # the draw behind it, in [0, 1)


def _spread(step: IntentStep, proposed_s: int, rng: SeededRng) -> tuple[int, float]:
    """A time spread evenly across orders of magnitude around the proposal, and the draw."""
    low, high = DURATION_BOUNDS[step.kind]
    centre = max(1, proposed_s)
    lowest = max(1, low, centre // DURATION_SPREAD)
    highest = max(lowest, min(high, centre * DURATION_SPREAD))
    value = rng.random()
    seconds = math.exp(math.log(lowest) + value * (math.log(highest) - math.log(lowest)))
    return bound_duration(step.kind, round(seconds)), value


def step_timing(step: IntentStep, *, frozen: bool, rolls: bool, rng: SeededRng) -> Timing:
    """The step's world and lived durations. `rolls` says whether an uncertain duration is
    rolled; a step that never got going (ruled out) takes only its proposed time."""
    uncertain = step.duration_uncertain and rolls
    if frozen:
        proposed_lived = step.proposed_personal_s
        if proposed_lived is None:
            proposed_lived = step.proposed_duration_s
        lived = bound_duration(step.kind, proposed_lived)
        if uncertain:
            lived, value = _spread(step, proposed_lived, rng)
            return Timing(duration_s=0, personal_s=lived, rolled_s=lived, rolled_value=value)
        return Timing(duration_s=0, personal_s=lived)

    lived = None
    if step.proposed_personal_s is not None:
        lived = bound_duration(step.kind, step.proposed_personal_s)
    duration = bound_duration(step.kind, step.proposed_duration_s)
    if uncertain:
        duration, value = _spread(step, step.proposed_duration_s, rng)
        return Timing(duration_s=duration, personal_s=lived, rolled_s=duration, rolled_value=value)
    return Timing(duration_s=duration, personal_s=lived)
