"""Climbing over the years (W6, G19): how fast someone who isn't the player character climbs
one of the world's ladders, and what their attempt at the next rung comes to.

Nobody is lifted (Miki, 2026-11-13: "I would feel cheated out of 100 years of training" if
"even the most secondary character that was no one" were raised to the character's level, and
"to all power-ups there should be a reason"). Nothing here reads the player character's sheet.
Whoever stands on a ladder goes on climbing it at the pace their own record shows, by the rule
the player character climbs by (`engine.resolve.powers.growth`): a rank fills with effort,
each rung taking twice the last, and at its peak the climb is thrown for.

How fast someone climbs is read off how far they have come for their age: the effort behind
them, every rung up to theirs and what their stage adds, over the years they have been at it,
counted from the age people take a climb up (`CLIMB_FROM` of their people's span). So the
next rung takes them about as long again as they have been climbing. Whoever reached a high
rung young keeps rising, an elder on a low rung dies on it, and nobody catches up with anyone
by the world's doing. On the lowest rung nothing shows yet how fast someone climbs, so there
their talent sets it against the ordinary pace (`engine.talent`): twice as fast for a knack,
four times for a genius, eight for someone one of a kind, half under a weakness. Above it
their record already shows what their talent was worth. The world reads the pace once for
each climb and keeps it (`LadderPosition.yearly_s`), by the age they had when it first counted
them, or the odds would turn on how the years were cut (W10).

Where the record can't say, nobody climbs (A2): someone with no age on record stays where
they are, and nobody steps onto a ladder they don't stand on.
"""

from engine import levels
from engine import talent as talent_mod
from engine.context import Difficulty
from engine.resolve import throw as dice
from engine.resolve.powers import growth
from engine.state.bible import PowerLadder
from engine.state.cast import Character
from engine.state.sheet import LadderPosition
from engine.state.world import WorldState
from engine.world import old_age
from engine.world.tuning import CLIMB_FROM, CLIMB_LEAST


def behind_s(person: Character, ladder: PowerLadder, position: LadderPosition) -> float:
    """The effort behind someone where they stand on a ladder, in seconds: every rung up to
    theirs, and what they have toward the next (their stage, or the work their sheet holds)."""
    done = sum(growth.rung_need_s(index) for index in range(position.rung + 1))
    rank = growth.rank_of(person, ladder)
    return done + (rank.effort_s if rank is not None else 0.0)


def years_at_it(state: WorldState, person: Character, age: float) -> float:
    """How long someone of an age has been climbing: since the age their people take it up,
    and never less than `CLIMB_LEAST` of their people's span, so a child found on a rung is
    a quick climber and not an endlessly quick one."""
    lives = old_age.peoples_span(state, person)
    return max(age - CLIMB_FROM * lives, CLIMB_LEAST * lives)


def yearly_s(
    state: WorldState, person: Character, ladder: PowerLadder, position: LadderPosition, age: float
) -> int:
    """The effort a year someone puts into a climb, in seconds, as their record shows it at
    an age: what is behind them over the years they have been at it. On the lowest rung
    their talent for the climb sets it against that."""
    pace = behind_s(person, ladder, position) / years_at_it(state, person, age)
    if position.rung == 0:
        pace *= talent_mod.standing(person, talent_mod.ladder_key(ladder.id)).pace
    return max(1, round(pace))


def odds(person: Character, ladder: PowerLadder) -> dice.Shares:
    """G19, A3. The chances of someone's attempt at the next rung, by the throw the player
    character makes: three dice against a level of 3, a green die for a talent that covers
    the climb and a second for one of a kind, a die fewer under a weakness. The world's own
    throws are made at the balanced number, whatever the story's difficulty: that setting is
    the player's."""
    stands = talent_mod.standing(person, talent_mod.ladder_key(ladder.id))
    if stands.steps >= talent_mod.ONE_OF_A_KIND_STEPS:
        greens = 2
    else:
        greens = 1 if stands.steps > 0 else 0
    count = growth.BREAKTHROUGH_DICE - (1 if stands.steps < 0 else 0)
    number = levels.number(growth.BREAKTHROUGH_LEVEL, Difficulty.BALANCED)
    return dice.shares(dice.Hand(count), greens, number)
