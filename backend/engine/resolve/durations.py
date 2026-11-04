"""How long a step takes (W10, W10a).

The interpret step proposes a duration and code bounds it by the kind of action. When how long it
takes is itself uncertain (breaking out of a trap, picking a lock, finding someone in a city), a
seeded roll picks it, spread evenly across orders of magnitude around the proposal and still
within the kind's bounds, so the same trap holds someone minutes or days. Inside a time stop the
world clock stands still and only the actor's own clock runs. A step that lasts until a time of
day takes the seconds to it on the world's clock, counted here rather than by the model.
"""

import math
from dataclasses import dataclass

from engine.base import DAY
from engine.contracts.intent import IntentStep
from engine.rng import SeededRng
from engine.state.bible import Calendar
from engine.timekeeping import DURATION_BOUNDS, bound_duration, parse_clock, seconds_until

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


def until_time(step: IntentStep, calendar: Calendar, start_s: int) -> Timing | None:
    """W10. A step that lasts until a time of day ("until nightfall", "sleep till dawn") takes
    the seconds from `start_s` to the next time the world's clock shows it, never rolled. The
    player named the time, so it holds whatever the kind's longest (a watch until dusk can
    outlast an hour), and it is under a day; the kind's shortest still holds. None for a step
    without one, or with one that isn't a time of day."""
    time_of_day = parse_clock(step.until)
    if time_of_day is None:
        return None
    shortest, _ = DURATION_BOUNDS[step.kind]
    return Timing(
        duration_s=max(shortest, seconds_until(calendar, start_s, time_of_day)), personal_s=None
    )


def lived_estimate(step: IntentStep) -> int:
    """The actor's lived time for the step as proposed, within its kind's bounds."""
    proposed = step.proposed_personal_s
    return bound_duration(step.kind, step.proposed_duration_s if proposed is None else proposed)


def step_timing(
    step: IntentStep,
    *,
    frozen: bool,
    rolls: bool,
    rng: SeededRng,
    stop_left_s: int | None = None,
    outlasts: bool | None = None,
    rate: float | None = None,
    rate_left_s: int | None = None,
) -> Timing:
    """The step's world and lived durations. `rolls` says whether an uncertain duration is
    rolled; a step that never got going (ruled out) takes only its proposed time.

    In a time stop with `stop_left_s` lived seconds left, a step that outlasts it lives out the
    stop and then takes world time for the rest (W10a). `outlasts` is what the step was settled
    as, so a rolled time keeps to it: a step settled as done inside the stop finishes by the
    stop's end, and one settled as outlasting it runs past. With a haste or slow, `rate` is the
    actor's lived seconds per world second, for `rate_left_s` more lived seconds if it runs out.
    """
    uncertain = step.duration_uncertain and rolls
    if frozen:
        proposed_lived = step.proposed_personal_s
        if proposed_lived is None:
            proposed_lived = step.proposed_duration_s
        lived = bound_duration(step.kind, proposed_lived)
        rolled_value = None
        if uncertain:
            lived, rolled_value = _spread(step, proposed_lived, rng)
        if stop_left_s is not None and outlasts is not None:
            edge = max(0, stop_left_s)
            lived = max(lived, edge + 1) if outlasts else min(lived, edge)
        world = 0
        if stop_left_s is not None and lived > stop_left_s:
            world = lived - max(0, stop_left_s)
        rolled = lived if rolled_value is not None else None
        return Timing(
            duration_s=world, personal_s=lived, rolled_s=rolled, rolled_value=rolled_value
        )

    if rate is not None and rate > 0 and rate != 1:
        lived = lived_estimate(step)
        rolled_value = None
        if uncertain:
            proposed = step.proposed_personal_s or step.proposed_duration_s
            lived, rolled_value = _spread(step, proposed, rng)
        sped = lived if rate_left_s is None else min(lived, max(0, rate_left_s))
        world = max(0, round(sped / rate + (lived - sped)))
        rolled = lived if rolled_value is not None else None
        return Timing(
            duration_s=world, personal_s=lived, rolled_s=rolled, rolled_value=rolled_value
        )

    lived = None
    if step.proposed_personal_s is not None:
        lived = bound_duration(step.kind, step.proposed_personal_s)
    duration = bound_duration(step.kind, step.proposed_duration_s)
    if uncertain:
        duration, value = _spread(step, step.proposed_duration_s, rng)
        return Timing(duration_s=duration, personal_s=lived, rolled_s=duration, rolled_value=value)
    return Timing(duration_s=duration, personal_s=lived)
