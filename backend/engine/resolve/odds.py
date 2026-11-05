"""The odds of a rolled step and the roll itself (A2, A3, A5).

Only contested and long-shot steps, close calls and uncertain finds are rolled. Each class has a
band its odds stay inside whatever shifts them, so a clever approach or the story's difficulty
moves the odds of a long shot without ever making it a sure thing, and nothing here can turn a
certain or ruled-out step into a roll (A2, A5).

Odds are worked in log-odds, so shifts add up smoothly: a gap of one step of power (a realm, where
the world has a ladder) moves the odds by `GAP_SLOPE`.
"""

import math

from engine.context import Difficulty
from engine.contracts.intent import OutcomeClass
from engine.resolve.words import odds_label
from engine.rng import SeededRng
from engine.state.records import RollRecord, StepResult

# G18: one step up (a realm) is a long shot at best, two or more is ruled out in a straight fight,
# and two below can't push back at all. Gaps are opposition minus actor, in steps of power.
LONG_SHOT_AT = 1.0
RULED_OUT_AT = 2.0
CERTAIN_AT = -2.0
GAP_SLOPE = 1.4
# A long shot's odds before shifts: from one step up to just under two. They start inside the band
# so a clever approach or an easier story can still raise them.
LONG_SHOT_ODDS = (0.10, 0.03)

CONTESTED_BAND = (0.05, 0.95)
LONG_SHOT_BAND = (0.02, 0.15)
CLOSE_CALL_BAND = (0.2, 0.8)
FIND_BAND = (0.2, 0.8)
BANDS = {OutcomeClass.CONTESTED: CONTESTED_BAND, OutcomeClass.LONG_SHOT: LONG_SHOT_BAND}

# The default odds when the opposition can't be measured on an axis.
UNMEASURED_ODDS = {OutcomeClass.CONTESTED: 0.5, OutcomeClass.LONG_SHOT: 0.1}

# A5. Shifts the odds of rolled steps only.
DIFFICULTY_SHIFT = {Difficulty.STORY: 0.8, Difficulty.BALANCED: 0.0, Difficulty.BRUTAL: -0.6}

# How much of the miss side of a contested roll is a partial success (A2: it can fail, partly
# succeed or cost something).
PARTIAL_SHARE = 0.25

ALL_RESULTS = [StepResult.SUCCESS, StepResult.PARTIAL, StepResult.FAILURE]
HARM_DONE = [StepResult.SUCCESS, StepResult.PARTIAL]  # A2: never bounces off harmlessly
# G15: what only the actor's own nature stands in the way of is done, cleanly or with the strain
# showing; the roll never takes the choice from the player.
OWN_CHOICE = [StepResult.SUCCESS, StepResult.PARTIAL]
YES_OR_NO = [StepResult.SUCCESS, StepResult.FAILURE]


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def gap_logit(gap: float) -> float:
    """The log-odds of beating opposition `gap` steps of power above the actor. Within a step the
    odds slide smoothly; a whole step up drops them to a long shot, because the gaps between rungs
    are large and felt (G18)."""
    if gap < LONG_SHOT_AT:
        return -GAP_SLOPE * gap
    share = min(1.0, (gap - LONG_SHOT_AT) / (RULED_OUT_AT - LONG_SHOT_AT))
    top, bottom = (logit(p) for p in LONG_SHOT_ODDS)
    return top + share * (bottom - top)


def settle(
    base_logit: float,
    shift: float,
    band: tuple[float, float],
    difficulty: Difficulty,
    *,
    against_player: bool = False,
):
    """The final odds: the base and the shifts, held inside the class's band, then the
    difficulty, held inside the band again so it never changes the class (A5). The difficulty
    works for the player: it eases their rolls, and hardens those `against_player`, such as a foe
    striking back (N6)."""
    low, high = band
    odds = min(high, max(low, sigmoid(base_logit + shift)))
    eased = DIFFICULTY_SHIFT[difficulty]
    odds = min(high, max(low, sigmoid(logit(odds) + (-eased if against_player else eased))))
    return round(odds, 4)


def roll(
    rng: SeededRng,
    odds: float,
    *,
    label: str,
    allowed: list[StepResult],
    difficulty: Difficulty,
) -> RollRecord:
    """One seeded roll (A3). The value comes first from the stream, so `SeededRng(seed).random()`
    replays it. Below the odds is a success; above, a partial success where the facts allow one,
    otherwise a failure."""
    value = rng.random()
    if value < odds:
        result = StepResult.SUCCESS
    elif StepResult.FAILURE not in allowed:
        result = StepResult.PARTIAL
    elif StepResult.PARTIAL in allowed and value < odds + PARTIAL_SHARE * (1 - odds):
        result = StepResult.PARTIAL
    else:
        result = StepResult.FAILURE
    return RollRecord(
        seed=rng.seed,
        label=label,
        odds=odds,
        odds_label=odds_label(odds),
        value=value,
        result=result,
        allowed=list(allowed),
        difficulty=difficulty,
    )
