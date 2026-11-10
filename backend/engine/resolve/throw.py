"""The throw: the dice that decide an open step (A3, A5).

A character throws 20-sided dice and adds them up against a number code works out from what the
step is up against. Nothing here knows about sheets or scenes: `engine.resolve.capability` builds
the hand and the number, and the callers decide what a result does.

- **The hand** is one to five dice by how well they have the move, or the skill or attribute
  the step draws on (`engine.levels`), a green die for each real advantage that holds, two at
  most, and, for a move, its own die thrown last: violet while they are still mastering it,
  where 18 or more is an insight worth three uses (A4), and gold from second nature on, which
  never counts below 10.
- **A 20 throws one more die**, plain, and that one can throw another.
- **The mark.** The total reaching the number passes. Past 20 for each die in the hand as
  well, it is over the top. Short by 5 or less is so close, and short by more is missed.
- **The result** is what the facts allow (A2): so close is a partial success where a half
  result exists, and otherwise a miss with nothing worse attached; a step that can't simply
  fail, such as a blow at someone who can't respond, is partly done on any miss.
- **The world's die** is one grey die for what is nobody's doing, such as whether a place
  holds something it only might: 11 or more for an even chance, 19 or more for a long shot.
  The story's difficulty never moves it, and it never throws another.

Every face comes from the throw's own seeded stream, in the order the dice are kept, so the
recorded seed replays the throw exactly. `shares` works out the exact chances of a hand against
a number by listing every way the dice can fall, which the tests check against the agreed table
and the engine records on the roll.
"""

from dataclasses import dataclass
from functools import cache

from engine import levels
from engine.context import Difficulty
from engine.contracts.intent import OutcomeClass
from engine.rng import SeededRng
from engine.state.records import Die, DieKind, Mark, NumberPart, RollRecord, StepResult, Throw
from engine.state.sheet import Mastery

SIDES = levels.DIE
MAX_GREENS = 2
SO_CLOSE_BY = 5  # a miss by this much or less is so close
INSIGHT_AT = 18  # on the violet die
GOLD_FLOOR = 10  # what a gold die counts for at least (`Die.value`)
# How many dice one die can set off in a row. Six 20s running is one throw in 64 million, so the
# cap changes no figure anyone can see, and it keeps the exact chances a finite sum.
MAX_SPRUNG = 6

LEVEL_POINTS = 10  # what one level adds to a number (`engine.levels.number`)
# A2. A throw that passes less often than this is a long shot, in the words of the class.
LONG_SHOT_BELOW = 0.15

WORLD_EVEN = 11
WORLD_LONG_SHOT = 19

ALL_RESULTS = [StepResult.SUCCESS, StepResult.PARTIAL, StepResult.FAILURE]
HARM_DONE = [StepResult.SUCCESS, StepResult.PARTIAL]  # A2: never bounces off harmlessly
# G15: what only the actor's own nature stands in the way of is done, cleanly or with the strain
# showing; the dice never take the choice from the player.
OWN_CHOICE = [StepResult.SUCCESS, StepResult.PARTIAL]
YES_OR_NO = [StepResult.SUCCESS, StepResult.FAILURE]


@dataclass(frozen=True)
class Hand:
    """What a character throws for a step, before any advantage: `dice` in all, the move's own
    die among them when `last` says which kind it is, and why, in words."""

    dice: int
    why: str = ""
    last: DieKind | None = None

    def __post_init__(self) -> None:
        if self.dice < 1:
            raise ValueError("a hand holds at least one die")
        if self.last not in (None, DieKind.VIOLET, DieKind.GOLD):
            raise ValueError("a move's own die is violet or gold")


@dataclass(frozen=True)
class Number:
    """What a throw has to reach, and what it is made of: the level first, then each thing that
    moves it. `level` is the level it started from, which decides whether there is anything to
    throw for at all (`open_against`)."""

    level: int
    parts: tuple[NumberPart, ...] = ()

    @property
    def value(self) -> int:
        return max(0, sum(part.points for part in self.parts))

    def plus(self, text: str, points: int) -> "Number":
        if not points:
            return self
        return Number(self.level, (*self.parts, NumberPart(text=text, points=points)))

    def raised(self, by: int, text: str) -> "Number":
        """G18. Raised by whole levels, or lowered when `by` is negative: ten for each, and the
        level it is weighed at moves with it."""
        if not by:
            return self
        part = NumberPart(text=text, points=LEVEL_POINTS * by)
        return Number(self.level + by, (*self.parts, part))


def own_die(mastery: Mastery) -> DieKind:
    """A4. A move's own die: violet while they are still mastering it, gold from second nature."""
    return DieKind.GOLD if mastery.rank >= Mastery.SECOND_NATURE.rank else DieKind.VIOLET


def level_number(level: int, why: str, difficulty: Difficulty) -> Number:
    """The number a level sets on this story's difficulty, as the first part of a `Number`."""
    points = levels.number(level, difficulty)
    return Number(level, (NumberPart(text=why, points=points),))


def open_against(hand: Hand, level: int) -> bool:
    """A2. Whether there is anything to throw for: nothing at level 0 is, and nothing two
    levels or more under the hand."""
    return level > 0 and level > hand.dice - levels.NO_CONTEST_BELOW


def class_of(odds: float) -> OutcomeClass:
    """A2. The class of a step a throw decides, from its exact chance."""
    return OutcomeClass.LONG_SHOT if odds < LONG_SHOT_BELOW else OutcomeClass.CONTESTED


def mark_of(total: int, number: int, hand_size: int) -> Mark:
    if total >= number:
        return Mark.OVER_THE_TOP if total > SIDES * hand_size else Mark.PASSED
    return Mark.SO_CLOSE if number - total <= SO_CLOSE_BY else Mark.MISSED


def result_of(mark: Mark, allowed: list[StepResult]) -> StepResult:
    """A2. What a mark means among the results the facts allow."""
    if mark.passed:
        return StepResult.SUCCESS
    if StepResult.FAILURE not in allowed:
        return StepResult.PARTIAL
    if mark is Mark.SO_CLOSE and StepResult.PARTIAL in allowed:
        return StepResult.PARTIAL
    return StepResult.FAILURE


MARK_WORDS = {
    Mark.OVER_THE_TOP: "over the top",
    Mark.PASSED: "passed",
    Mark.SO_CLOSE: "so close",
    Mark.MISSED: "missed",
}


def told(roll: RollRecord) -> str:
    """A8. A throw in words, for a step's reason: the hand and why, each green die's reason,
    what the number is made of, the total against it and the mark. "Aura blade (skilled), 3
    dice, and a green die for coming from behind, against the guard's swordplay (skilled),
    level 3; you are wounded (+5): 31 against 32, so close"."""
    thrown = roll.throw
    if thrown is None:
        return roll.odds_label
    hand = thrown.hand_why or f"{thrown.hand} dice"
    greens = "".join(f", and a green die for {g[:1].lower()}{g[1:]}" for g in thrown.greens)
    parts = parts_told(thrown.made_of)
    return f"{hand}{greens}, against {parts}: {thrown.line}, {MARK_WORDS[thrown.mark]}"


def parts_told(parts: list[NumberPart] | tuple[NumberPart, ...]) -> str:
    """What a number is made of, in words: the level it starts from, then each thing that moves
    it with its points, such as "a good lock, a hard task, level 3; you are wounded (+5)"."""
    told = [
        part.text if i == 0 else f"{part.text} ({part.points:+d})" for i, part in enumerate(parts)
    ]
    return "; ".join(told)


def throw(
    rng: SeededRng,
    hand: Hand,
    number: Number,
    *,
    label: str,
    allowed: list[StepResult],
    difficulty: Difficulty,
    greens: list[str] | tuple[str, ...] = (),
    against: str = "",
    deadly: bool = False,
    miss_costs: str = "",
) -> RollRecord:
    """Throw `hand` with a green die for each of `greens` (two at most count) against `number`,
    and record it. The plain dice fall first, then the green ones, then the move's own."""
    reasons = [g for g in greens if g][:MAX_GREENS]
    kinds = [DieKind.PLAIN] * (hand.dice - (1 if hand.last else 0))
    kinds += [DieKind.GREEN] * len(reasons)
    if hand.last is not None:
        kinds.append(hand.last)
    dice: list[Die] = []
    for kind in kinds:
        dice.extend(_fall(rng, kind))
    total = sum(die.value for die in dice)
    size = len(kinds)
    target = number.value
    mark = mark_of(total, target, size)
    own = next((d for d in dice if d.kind is DieKind.VIOLET), None)
    thrown = Throw(
        dice=dice,
        hand=size,
        hand_why=hand.why,
        greens=reasons,
        number=target,
        made_of=list(number.parts),
        total=total,
        most=SIDES * size,
        mark=mark,
        against=against,
        deadly=deadly,
        miss_costs=miss_costs if deadly else "",
        insight=own is not None and own.face >= INSIGHT_AT,
    )
    return RollRecord(
        seed=rng.seed,
        label=label,
        odds=round(chance(hand, len(reasons), target), 4),
        odds_label=thrown.line,
        result=result_of(mark, allowed),
        allowed=list(allowed),
        difficulty=difficulty,
        throw=thrown,
    )


def world_die(
    rng: SeededRng, *, label: str, difficulty: Difficulty, long_shot: bool = False
) -> RollRecord:
    """A3. The world's die, for what is not the character's doing: one grey die, 11 or more for
    an even chance and 19 or more for a long shot. The difficulty is recorded and never moves
    it."""
    number = WORLD_LONG_SHOT if long_shot else WORLD_EVEN
    die = Die(kind=DieKind.GREY, face=rng.randint(1, SIDES))
    mark = Mark.PASSED if die.face >= number else Mark.MISSED
    why = "a long shot" if long_shot else "an even chance"
    thrown = Throw(
        dice=[die],
        hand=1,
        hand_why="The world's die",
        number=number,
        made_of=[NumberPart(text=why, points=number)],
        total=die.face,
        most=SIDES,
        mark=mark,
    )
    return RollRecord(
        seed=rng.seed,
        label=label,
        odds=(SIDES + 1 - number) / SIDES,
        odds_label=thrown.line,
        result=StepResult.SUCCESS if mark.passed else StepResult.FAILURE,
        allowed=list(YES_OR_NO),
        difficulty=difficulty,
        throw=thrown,
    )


def _fall(rng: SeededRng, kind: DieKind) -> list[Die]:
    """One die of the hand, and every die its 20s set off after it."""
    fallen = [Die(kind=kind, face=rng.randint(1, SIDES))]
    while fallen[-1].face == SIDES and len(fallen) <= MAX_SPRUNG:
        fallen.append(Die(kind=DieKind.PLAIN, face=rng.randint(1, SIDES), sprung=True))
    return fallen


# --- the exact chances ------------------------------------------------------------------------


@cache
def _one(floor: int, sprung_left: int) -> tuple[tuple[int, float], ...]:
    """What one die adds, with every die its 20s set off, as (total, chance) pairs."""
    found: dict[int, float] = {}
    each = 1 / SIDES
    for face in range(1, SIDES + 1):
        value = max(face, floor)
        if face == SIDES and sprung_left > 0:
            for more, p in _one(1, sprung_left - 1):
                found[value + more] = found.get(value + more, 0.0) + each * p
        else:
            found[value] = found.get(value, 0.0) + each
    return tuple(sorted(found.items()))


@cache
def _totals(plain: int, gold: int) -> tuple[tuple[int, float], ...]:
    """Every total `plain` dice and `gold` gold dice can make, with its chance."""
    totals: dict[int, float] = {0: 1.0}
    for floor in [1] * plain + [GOLD_FLOOR] * gold:
        nxt: dict[int, float] = {}
        for total, p in totals.items():
            for add, q in _one(floor, MAX_SPRUNG):
                nxt[total + add] = nxt.get(total + add, 0.0) + p * q
        totals = nxt
    return tuple(sorted(totals.items()))


@dataclass(frozen=True)
class Shares:
    """The exact chances of a hand against a number. The first three add up to one; a throw over
    the top is a pass too, so `over_the_top` is a part of `passed`."""

    passed: float
    so_close: float
    missed: float
    over_the_top: float


def shares(hand: Hand, greens: int, number: int) -> Shares:
    """A3. The exact chances of each mark, from every way the dice can fall. A green die and a
    violet one fall like a plain die; only a gold one counts differently."""
    size = hand.dice + min(MAX_GREENS, max(0, greens))
    gold = 1 if hand.last is DieKind.GOLD else 0
    passed = close = missed = over = 0.0
    for total, p in _totals(size - gold, gold):
        mark = mark_of(total, number, size)
        if mark.passed:
            passed += p
            if mark is Mark.OVER_THE_TOP:
                over += p
        elif mark is Mark.SO_CLOSE:
            close += p
        else:
            missed += p
    return Shares(passed, close, missed, over)


def chance(hand: Hand, greens: int, number: int) -> float:
    """The exact chance the hand reaches the number."""
    return min(1.0, max(0.0, shares(hand, greens, number).passed))
