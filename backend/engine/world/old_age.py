"""Old age (W6, W10, G23): how long someone lives, and the chance that a stretch of years takes
them.

Nobody is made to die. From 85% of their span on (`OLD_AGE_FROM`) the years may take someone,
the likelier the older: half of those who get that far are gone at the full span, and next to
nobody sees a fifth more than it. The chance over a stretch follows from the ages it runs
between and from nothing else, so a month takes next to nobody, a hundred years take every
mortal, and the odds are the same however the world's ticks cut the years (W10).

How long someone lives is the longest of three things on record. Their people's lifespan
(G23), a human one where the world doesn't say, and as good as for ever for a people old age
never takes, which the record gives a lifespan of 0 (`ageless`): the undead, spirits,
machines. Their rung's, where climbing the world's
ladder lengthens life (`Rung.lifespan_years`, G19): whoever breaks through outlives those who
never did (Miki, 2026-11-13: "if they are training for 100 years, either they are dead of old
age or some of them might actually successfully improved"). And a span of their own
(`Character.lifespan_years`) for someone the world first finds older than the other two
allow, an elder of three hundred among people who live eighty: they have outlived their span
by means the record doesn't give, and are taken to have half as long again past it as they
have had (`OWN_SPAN`), so they neither drop dead the day the world first counts their years
nor live for ever. The world settles that once for each person, by the age they had when it
first counted them, and never again: whoever grows past their span under the dice has only
been lucky, and gets no more years for it, or the odds would turn on how the years were cut.

Where the record can't say, the dice take nobody (A2). A ladder drafted before rungs carried
a lifespan says nothing of how long its rungs live, so whoever stands on it is left alone
(`open_ended`): better a cultivator who lives too long than one dead at eighty by a rule
their world never had. Someone with no age on record is left alone too, and so are beasts,
whose kinds have no lifespan on record.
"""

import math

from engine.base import YEAR
from engine.state.cast import Character
from engine.state.world import WorldState
from engine.world.tuning import AGELESS_YEARS, LIFESPAN_YEARS, OLD_AGE_FROM, OWN_SPAN


def _lifespan(state: WorldState, person: Character) -> int | None:
    """Their people's lifespan as the record has it: None where it doesn't say, or where they
    are of no people on record."""
    people = next((p for p in state.bible.peoples if p.id == person.people_id), None)
    return people.lifespan_years if people is not None else None


def ageless(state: WorldState, person: Character) -> bool:
    """Whether old age never takes someone's people (G23): the record gives it a lifespan of
    0, which a new world's draft says of the undead, of spirits, of machines."""
    return _lifespan(state, person) == 0


def peoples_span(state: WorldState, person: Character) -> int:
    """How long the people of someone's kind take over a life (G23), for what is measured
    against it, such as the age a climb is taken up at: their people's lifespan, or a human
    span where the world doesn't say and for a people old age never takes."""
    return _lifespan(state, person) or LIFESPAN_YEARS


def _rungs(state: WorldState, person: Character) -> list[list[int | None]]:
    """For each of the world's ladders someone stands on, the lifespans of its rungs up to
    theirs, lowest first."""
    found = []
    for position in person.sheet.ladders:
        ladder = state.bible.ladder(position.ladder_id)
        if ladder is None or not ladder.rungs:
            continue
        rung = min(position.rung, len(ladder.rungs) - 1)
        found.append([r.lifespan_years for r in ladder.rungs[: rung + 1]])
    return found


def open_ended(state: WorldState, person: Character) -> bool:
    """Whether the record can't say how long someone lives: they stand on a ladder whose
    rung, where they are, carries no lifespan. The dice take no such person (A2)."""
    return any(spans[-1] is None for spans in _rungs(state, person))


def natural_span(state: WorldState, person: Character) -> int:
    """How long someone like them lives, in years: the longer of their people's span and
    their rung's (a higher rung never shortens a life, so it is the longest up to theirs),
    and as good as for ever for one of a people old age never takes."""
    if ageless(state, person):
        return AGELESS_YEARS
    rungs = [years for spans in _rungs(state, person) for years in spans if years]
    return max([peoples_span(state, person), *rungs])


def on_record(state: WorldState, person: Character) -> bool:
    """Whether the record itself says how long someone lives, with nothing assumed: their
    people has a lifespan on record, a rung up to theirs carries one, or they have a span of
    their own. Where none does, `span` is the human one the world assumes."""
    if person.lifespan_years or _lifespan(state, person) is not None:
        return True
    return any(years for spans in _rungs(state, person) for years in spans)


def span(state: WorldState, person: Character) -> int:
    """How long someone lives, in years: as long as someone like them does (`natural_span`),
    or their own span where the world gave them one."""
    return max(natural_span(state, person), person.lifespan_years or 0)


def own_span(state: WorldState, person: Character, age: float) -> int:
    """The span of their own for someone the world first counts at an age: for whoever is
    older than someone like them lives, as long again past that as `OWN_SPAN` of what they
    have outlived it by. 0 for anyone within the span of someone like them: they have none
    of their own."""
    lives = natural_span(state, person)
    if age <= lives:
        return 0
    return math.ceil(age + (age - lives) * OWN_SPAN)


def age_at(state: WorldState, person: Character, at_s: int) -> float | None:
    """Someone's age at a moment, to the day: the whole years on record (`Character.age`, as
    of the world's last count, `WorldState.aged_s`) and the part of a year since, or the time
    since their birth for someone born in the story. None with no age on record."""
    if person.age is None:
        return None
    if person.born_s is not None:
        return max(0, at_s - person.born_s) / YEAR
    counted = state.aged_s if state.aged_s is not None else at_s
    return person.age + (at_s - counted) / YEAR


def worn(age: float, lives: float) -> float:
    """How much of the chance of dying of old age someone has behind them at an age, as a
    cumulative hazard: nothing before `OLD_AGE_FROM` of their span, ln 2 at the full span
    (half of those who got that far are gone), and rising with the cube of how far past the
    start of old age they are."""
    if lives <= 0:
        return 0.0
    past = age / lives - OLD_AGE_FROM
    return math.log(2) * (past / (1 - OLD_AGE_FROM)) ** 3 if past > 0 else 0.0


def chance(lives: float, from_age: float, to_age: float) -> float:
    """The chance that old age takes someone between two ages, given they reached the first.
    Two stretches end to end take as many as the one stretch they make up."""
    if to_age <= from_age:
        return 0.0
    return 1 - math.exp(worn(from_age, lives) - worn(to_age, lives))


def taken_at(lives: float, from_age: float, luck: float) -> float:
    """The age at which old age takes someone who has reached `from_age`, for a `luck` drawn
    evenly from 0 to 1: the same odds as `chance`, turned round, so the chance of being taken
    before any age is the chance `chance` gives the stretch up to it. Never before the start
    of old age, and never before `from_age`."""
    luck = min(max(luck, 0.0), 1 - 1e-12)
    behind = worn(from_age, lives) - math.log(1 - luck)
    at = lives * (OLD_AGE_FROM + (1 - OLD_AGE_FROM) * (behind / math.log(2)) ** (1 / 3))
    return max(at, from_age)
