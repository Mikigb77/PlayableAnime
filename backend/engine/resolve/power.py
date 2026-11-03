"""Power on the A8 axes, the ladder gap (G18) and whether someone can respond at all (A2).

Every character carries a tier on each axis, worked out from their whole sheet (G13, G14). Where
the world has a ladder on that axis, the gap is measured in its rungs, so "one realm up" means
what the world says it means; elsewhere one step is two tiers. Condition counts: a badly wounded or
weakened character stands lower than their sheet (A8).
"""

import re
from dataclasses import dataclass
from statistics import median

from engine.resolve.words import stems
from engine.state.bible import PowerLadder
from engine.state.cast import Character
from engine.state.sheet import Health, PowerAxis
from engine.state.world import WorldState

# One step of power where the world has no ladder on the axis, in tiers.
NO_LADDER_STEP = 2.0

# How far a condition pulls someone down, in steps (rungs where there is a ladder).
HEALTH_PENALTY = {
    Health.UNHURT: 0.0,
    Health.HURT: 0.0,
    Health.WOUNDED: 0.5,
    Health.BADLY_WOUNDED: 1.0,
    Health.DYING: 2.0,
}
HEALTH_WORDS = {
    Health.WOUNDED: "wounded",
    Health.BADLY_WOUNDED: "badly wounded",
    Health.DYING: "dying",
}
FATIGUE_PENALTY = {3: 0.25, 4: 0.5}
DRY_RESERVE_PENALTY = 0.5

# Passing states that leave someone unable to respond at all (A2, A8), matched on whole words of
# the state's name, so "sleepless" or "bound by an oath" doesn't count. "Bound" counts only alone.
HELPLESS_WORDS = frozenset(
    """asleep sleeping unconscious paralysed paralyzed petrified stunned subdued helpless
    shackled chained""".split()
)
HELPLESS_PHRASES = ("knocked out", "tied up", "bound hand and foot", "bound and gagged")
HELPLESS_NAMES = frozenset({"bound"})
# Words that turn a helpless state into its opposite or less: "half asleep", "no longer bound".
NOT_HELPLESS = frozenset("not no never half barely nearly almost longer".split())
SUBDUED_STATE = "subdued"


@dataclass(frozen=True)
class Scale:
    """How many tiers make one step of power on an axis, and the ladder that names them."""

    step: float
    ladder: PowerLadder | None = None


def scale(state: WorldState, axis: PowerAxis, *characters: Character) -> Scale:
    """The ladder for this axis that the characters stand on (G18), or the default step."""
    ladders = [lad for lad in state.bible.ladders if lad.axis is axis]
    if not ladders:
        return Scale(NO_LADDER_STEP)

    def on(ladder: PowerLadder, character: Character) -> bool:
        return any(p.ladder_id == ladder.id for p in character.sheet.ladders)

    ladder = (
        next((lad for lad in ladders if all(on(lad, c) for c in characters)), None)
        or next((lad for lad in ladders if any(on(lad, c) for c in characters)), None)
        or ladders[0]
    )
    steps = [b.tier - a.tier for a, b in zip(ladder.rungs, ladder.rungs[1:], strict=False)]
    steps = [s for s in steps if s > 0]
    return Scale(float(median(steps)) if steps else 1.0, ladder)


def rung(state: WorldState, character: Character, axis: PowerAxis) -> tuple[str, int] | None:
    """The rung's name in the world's words and its tier, where the character stands on a ladder
    for this axis."""
    best: tuple[str, int] | None = None
    for position in character.sheet.ladders:
        ladder = state.bible.ladder(position.ladder_id)
        if ladder is None or ladder.axis is not axis:
            continue
        if 0 <= position.rung < len(ladder.rungs):
            found = ladder.rungs[position.rung]
            if best is None or found.tier > best[1]:
                best = (found.name, found.tier)
    return best


def base_tier(state: WorldState, character: Character, axis: PowerAxis) -> int:
    """The sheet's tier on the axis, raised to the ladder rung where one says more (G18)."""
    tier = character.sheet.axes.on(axis)
    on_ladder = rung(state, character, axis)
    return max(tier, on_ladder[1]) if on_ladder else tier


@dataclass(frozen=True)
class Standing:
    """Where a character stands on an axis right now, and what pulls them down."""

    character: Character
    tier: float
    rung: str | None
    notes: tuple[str, ...]


def standing(state: WorldState, character: Character, axis: PowerAxis, measure: Scale) -> Standing:
    """A8. The tier on the axis after condition: wounds, fatigue, an empty reserve and any
    weakening the sheet records."""
    condition = character.sheet.condition
    penalty_steps = HEALTH_PENALTY[condition.health]
    notes: list[str] = []
    if condition.health in HEALTH_WORDS:
        notes.append(HEALTH_WORDS[condition.health])
    if condition.fatigue in FATIGUE_PENALTY:
        penalty_steps += FATIGUE_PENALTY[condition.fatigue]
        notes.append("exhausted")
    dry = [r.name for r in condition.reserves if r.level == 0]
    if dry:
        penalty_steps += DRY_RESERVE_PENALTY
        notes.append(f"drained of {dry[0]}")
    if condition.weakened_tiers:
        notes.append("weakened")
    penalty = penalty_steps * measure.step + condition.weakened_tiers
    on_ladder = rung(state, character, axis)
    return Standing(
        character=character,
        tier=max(0.0, base_tier(state, character, axis) - penalty),
        rung=on_ladder[0] if on_ladder else None,
        notes=tuple(notes),
    )


def helpless_state(character: Character) -> str | None:
    """A passing state on the sheet that leaves them unable to respond: asleep, bound, stunned."""
    if character.sheet.condition.health is Health.DYING:
        return "dying"
    for state in character.sheet.condition.states:
        if _helpless(state.name):
            return state.name
    return None


def _helpless(state_name: str) -> bool:
    words = re.findall(r"[a-z]+", state_name.casefold())
    if not words or NOT_HELPLESS.intersection(words):
        return False
    text = " ".join(words)
    if text in HELPLESS_NAMES:
        return True
    return bool(HELPLESS_WORDS.intersection(words)) or any(
        re.search(rf"\b{phrase}\b", text) for phrase in HELPLESS_PHRASES
    )


_TIME = stems("time")
_STOPPED = stems("stop stopped frozen froze freeze halted paused")


def claims_frozen_in_time(why_not: str) -> bool:
    """Whether a proposed reason for not responding is a time stop, which the state can check:
    it speaks of time and of time stopping or freezing."""
    said = stems(why_not)
    return bool(_TIME & said) and bool(_STOPPED & said)
