"""W16, E6: stall pressure, computed in code.

Pressure is turns since the last decision with stakes, plus repeats of the same low-stakes action,
plus clocks close to their end. Turns inside an encounter don't count as quiet: the encounter is
the stakes (W10). When pressure reaches the story's threshold (10, 5 or 3 turns for calm, normal
and dramatic) an event comes in; from 60% of it, one may come early. Drift moves the threshold a
little within the chosen setting, never past it: it rises while the player is comfortably in
control and falls after a big event (E6).
"""

import re
from dataclasses import dataclass

from engine.context import EventFrequency, TurnContext
from engine.contracts.intent import Intent
from engine.contracts.resolution import Resolution
from engine.director import rules
from engine.director.turn import TurnFacts, player_deeds
from engine.state.records import ClockStatus, StepResult
from engine.state.sheet import Health
from engine.state.world import WorldState

_FILLER = {"a", "an", "the", "my", "our", "his", "her", "their", "i", "again", "some", "to"}


@dataclass(frozen=True)
class Pressure:
    value: float
    threshold: float
    stakes: bool
    encounter: bool
    turns_without_stakes: int
    low_stakes_streak: int
    action_key: str | None

    @property
    def reached(self) -> bool:
        return self.value >= self.threshold

    @property
    def early_chance(self) -> float:
        """The chance of an event before the threshold: none below EARLY_FROM of it, rising to
        EARLY_CHANCE just below it."""
        if self.reached:
            return 1.0
        start = rules.EARLY_FROM * self.threshold
        if self.value <= 0 or self.value < start:
            return 0.0
        return rules.EARLY_CHANCE * (self.value - start) / (self.threshold - start)

    @property
    def building(self) -> bool:
        """Pressure is high enough that the scene should nudge (S2's wild choice)."""
        return self.value >= rules.EARLY_FROM * self.threshold


def threshold(frequency: EventFrequency, drift: float) -> float:
    """W16 with E6's drift: rising drift brings events sooner, falling drift later."""
    return rules.THRESHOLDS[frequency] * (1 - rules.DRIFT_SPAN * drift)


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[^\W\d_]+", text.casefold()) if w not in _FILLER]


def action_key(resolution: Resolution, intent: Intent | None) -> str | None:
    """A rough signature of what the player did, so a repeated low-stakes action can be spotted:
    the standing action, or the steps' verbs (the first two words of each step's text without the
    intent)."""
    if intent is not None:
        if intent.standing is not None and not intent.steps:
            return f"standing:{intent.standing.value}"
        verbs = sorted({" ".join(_words(step.verb)[:2]) for step in intent.steps} - {""})
        if verbs:
            return "|".join(verbs)
    texts = sorted({" ".join(_words(step.text)[:2]) for step in resolution.steps} - {""})
    return "|".join(texts) or None


def clock_pressure(state: WorldState) -> float:
    """Running clocks one step or less from their end, whose next step isn't far off."""
    total = 0.0
    for clock in state.clocks.values():
        if clock.status is not ClockStatus.RUNNING or clock.remaining > 1:
            continue
        if clock.next_step_s is not None and clock.next_step_s - state.world_s > rules.CLOCK_NEAR_S:
            continue
        total += rules.CLOCK_WEIGHT
    return min(rules.CLOCK_CAP, total)


def had_stakes(state: WorldState, resolution: Resolution, facts: TurnFacts) -> bool:
    """A decision with stakes: resolve says the turn held real stakes, the player took up an open
    thread or lead, or the player did something that matters (a deed of severity 2 or more)."""
    if resolution.stakes or facts.player_responded:
        return True
    return any(deed.severity >= 2 for deed in player_deeds(state, facts))


def measure(
    state: WorldState,
    resolution: Resolution,
    ctx: TurnContext,
    intent: Intent | None,
    facts: TurnFacts,
) -> Pressure:
    memory = state.director
    encounter = state.scene.encounter is not None
    stakes = had_stakes(state, resolution, facts)
    limit = threshold(ctx.settings.event_frequency, memory.frequency_drift)
    key = action_key(resolution, intent)
    if ctx.turn <= 1 or encounter or stakes:
        # The opening plays the premise's own situation (N5); an encounter and a decision with
        # stakes are the opposite of a stall.
        quiet, streak, key = 0, 0, None
    else:
        quiet = memory.turns_without_stakes + 1
        repeat = key is not None and key == memory.last_action_key
        streak = memory.low_stakes_streak + 1 if repeat else 1
    value = 0.0
    if ctx.turn > 1 and not encounter:
        value = quiet + rules.REPEAT_WEIGHT * max(0, streak - 1) + clock_pressure(state)
    return Pressure(
        value=round(value, 3),
        threshold=round(limit, 3),
        stakes=stakes,
        encounter=encounter,
        turns_without_stakes=quiet,
        low_stakes_streak=streak,
        action_key=key,
    )


def in_control(state: WorldState, resolution: Resolution, pressure: Pressure) -> bool:
    """E6: comfortably in control: every step a clean success, no encounter, and the player
    character no worse than hurt."""
    if pressure.encounter or not resolution.steps:
        return False
    if any(step.result is not StepResult.SUCCESS or step.interrupted for step in resolution.steps):
        return False
    return state.player.sheet.condition.health in (Health.UNHURT, Health.HURT)


def next_drift(drift: float, *, big: bool, comfortable: bool) -> float:
    if big:
        drift += rules.DRIFT_AFTER_BIG_EVENT
    elif comfortable:
        drift += rules.DRIFT_IN_CONTROL
    elif drift > 0:
        drift = max(0.0, drift - rules.DRIFT_SETTLE)
    elif drift < 0:
        drift = min(0.0, drift + rules.DRIFT_SETTLE)
    return round(max(-1.0, min(1.0, drift)), 3)
