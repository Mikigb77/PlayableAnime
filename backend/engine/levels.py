"""One scale of levels for moves, skills, bodies and things (A3, A4, G14, G18).

A level is a number of 20-sided dice on one side, and a number to beat on the other: someone at
level 3 throws three dice, and whoever goes against something at level 3 has to reach 27 on a
Balanced story (`number`). Everything a step can be weighed with sits on this one scale, so any
two can be compared:

- **A move** throws by its mastery: one die while they are learning it, two practiced, three
  skilled, four at second nature, and a fifth for a move made their own.
- **A step with no named move** throws by the skill it draws on: untrained or novice one die,
  fair two, skilled three, expert four, master five.
- **A raw feat** with no skill behind it, such as lifting, enduring or resisting, throws by the
  attribute it tests: two dice for an average adult, and one more for each level above.
- **A thing** in the way has the level of the six words the interpret step judges it by:
  trivial is nothing to beat, easy is level 1, and extreme is level 5.
- **A rung** of a world's ladder counts as one level where a move meets that power head-on, or
  two where the world says so (`PowerLadder.rung_levels`).

Mastery grows with use (A4): six uses take a move from learning to practiced, fifteen more to
skilled and thirty more to second nature, about fifty in all. A use that nothing resisted counts
once, and one a roll decided counts twice. No count of uses reaches a move made their own. A new
move starts two steps under the skill it belongs to, so a master's new move starts at skilled.
Talent sets the pace: someone who learns four times as fast needs a quarter of the uses (two,
four and eight, fourteen in all), a slow learner twice as many, and a gifted character's new
move starts at practiced.

The story's difficulty is what comes off every number (A5): 6 on Story, 3 on Balanced and
nothing on Brutal, so at their own level a character passes about four times in five, seven in
ten or six in ten.

Nothing here rolls. `engine.resolve.capability` builds the hand and the number of a step from
this scale, and `engine.resolve.throw` throws the dice.
"""

import math

from engine.context import Difficulty
from engine.contracts.intent import Challenge
from engine.state.sheet import Mastery, SkillLevel

DIE = 20

MASTERY_DICE = {
    Mastery.LEARNING: 1,
    Mastery.PRACTICED: 2,
    Mastery.SKILLED: 3,
    Mastery.SECOND_NATURE: 4,
    Mastery.OWN: 5,
}
SKILL_DICE = {
    SkillLevel.UNTRAINED: 1,
    SkillLevel.NOVICE: 1,
    SkillLevel.FAIR: 2,
    SkillLevel.SKILLED: 3,
    SkillLevel.EXPERT: 4,
    SkillLevel.MASTER: 5,
}
# An average adult's attribute (`Attributes`) and the dice it throws.
AVERAGE_ATTRIBUTE = 3
AVERAGE_DICE = 2
CHALLENGE_LEVEL = {
    Challenge.TRIVIAL: 0,
    Challenge.EASY: 1,
    Challenge.MODERATE: 2,
    Challenge.HARD: 3,
    Challenge.VERY_HARD: 4,
    Challenge.EXTREME: 5,
}

# A5. What the story's difficulty takes off every number a level sets.
EASE = {Difficulty.STORY: 6, Difficulty.BALANCED: 3, Difficulty.BRUTAL: 0}
# A3. One step of what moves a number besides the level: a wound, a hindrance, a gift that fits.
STEP = 5
# A2. Something this many levels under the hand is nothing to throw for.
NO_CONTEST_BELOW = 2

# A4. Uses that take a move to the next mastery, at an ordinary pace.
USES_TO_NEXT = {Mastery.LEARNING: 6, Mastery.PRACTICED: 15, Mastery.SKILLED: 30}
PLAIN_USE = 1  # used, with nothing resisting
RESISTED_USE = 2  # used where a throw decided it
INSIGHT_USE = 3  # used where the move's own die showed an insight
# How far under the skill it belongs to a new move starts, in steps of the scale.
NEW_MOVE_BELOW_SKILL = 2
# Where a new move starts for someone with a gift for learning, whatever their skill.
GIFTED_START = Mastery.PRACTICED

_BY_DICE = {dice: mastery for mastery, dice in MASTERY_DICE.items()}


def attribute_dice(level: int) -> int:
    """The dice a raw feat throws from the attribute it tests: two for an average adult, one
    more for each level above, and never fewer than one."""
    return max(1, AVERAGE_DICE + level - AVERAGE_ATTRIBUTE)


def number(level: int, difficulty: Difficulty = Difficulty.BALANCED) -> int:
    """What a throw has to reach against something at this level: ten for each level, less what
    the story's difficulty takes off (`EASE`), so 7, 17, 27, 37 and 47 on Balanced. Level 0 is
    nothing to beat."""
    if level <= 0:
        return 0
    return max(0, 10 * level - EASE[difficulty])


def uses_to_next(mastery: Mastery, pace: float = 1.0) -> int | None:
    """How many uses take a move from this mastery to the next, or None where use alone takes
    it no further: at second nature, and for a move made their own. `pace` is how fast they
    learn, 1 for an ordinary character: at 4 the six, fifteen and thirty become two, four and
    eight, and at a half they double."""
    need = USES_TO_NEXT.get(mastery)
    if need is None:
        return None
    return max(1, math.ceil(need / pace))


def grown(mastery: Mastery, uses: int, gained: int, pace: float = 1.0) -> tuple[Mastery, int]:
    """A4. A move's mastery and count after `gained` more uses, at their `pace` of learning.
    Uses past what a step up takes carry on toward the next, so a long stretch of practice can
    climb more than one. From second nature on the count only adds up."""
    uses += max(0, gained)
    need = uses_to_next(mastery, pace)
    while need is not None and uses >= need:
        uses -= need
        mastery = list(Mastery)[mastery.rank + 1]
        need = uses_to_next(mastery, pace)
    return mastery, uses


def starting_mastery(skill: SkillLevel | None, gifted: bool = False) -> Mastery:
    """A4. Where a new move starts: two steps under the skill it belongs to, and at learning
    with no such skill or a lesser one. An expert's new move starts at practiced and a master's
    at skilled, so a master with a new cut is still a master. Someone `gifted` at learning
    starts at practiced, or where their skill puts them if that is higher."""
    dice = SKILL_DICE[skill] - NEW_MOVE_BELOW_SKILL if skill is not None else 0
    if gifted:
        dice = max(dice, MASTERY_DICE[GIFTED_START])
    return _BY_DICE[max(MASTERY_DICE[Mastery.LEARNING], dice)]
