"""Romance on record (W17).

A romance between two people is a `Bond` in the state, and it moves in stages: interest,
courting, together, promised, married, over. Each stage needs something to have happened in the
story, and code decides it: the interpret step proposes a move (`RomanceMove`), and
`engine.resolve.romance` rules on it from what the record holds.

The other person has a heart of their own: `Attitude.attraction`, how drawn they are to someone
as a lover, from 0 to 100. Only the engine moves it, by what happened between the two, and it
takes its own time: after it moves it rests, for as long as that person's pace says (`pace`),
before anything moves it again. So a romance is won over days of the story, never in one
scene of sweet words. The player character's own feelings are the player's (G15), so nobody's
record holds them.

What a stage needs:

- **Interest** opens with the first romantic step someone makes toward another.
- **Courting**: an advance was answered, and their heart is past `COURTING_AT`.
- **Together**: they were asked and said yes. Their heart decides it: at `DECLARE_SURE` or more
  the answer is yes with nothing thrown, under `DECLARE_NO` it is no, and between the two the
  ask is thrown for like any step of words.
- **Promised**: the same, asked of a partner, with `PROPOSE_SURE` and `PROPOSE_NO`.
- **Married**: the two were promised and wed.
- **Over**: one of them ended it, which is always theirs to do, or one of them died. A bond
  that is over stays over, and a romance that starts again is a new bond. Being left costs the
  one who was left some of what they felt, so getting back together has to be won again.

Nothing here assumes a genre (G5): a stage is a fact between two people, and what a wedding or
a betrothal looks like is the world's.
"""

from __future__ import annotations

import zlib
from enum import StrEnum

from engine.base import DAY, HOUR
from engine.kin import ancestors
from engine.state.cast import Character
from engine.state.records import Bond, BondStage
from engine.state.world import WorldState, natural_key

# How far one answered advance moves a heart, and what more it moves one that already likes
# and trusts whoever made it, once a step.
NOTCH = 10
WARM_BONUS = 5
# Liking and trust, averaged, from which someone is warm toward another, and against them.
WARM_AT = 40
# The fear from which nothing is freely given: the fear that keeps a witness silent
# (`engine.world.tuning.SILENT_FEAR`).
AFRAID_AT = 70
# A step that lasts days is more than one moment between two people: it counts for as many
# notches as the heart had time to rest and move again, up to this many, so a season of
# courting brings someone a long way and the last of it is still played.
MOST_NOTCHES = 6

COURTING_AT = 30
DECLARE_NO, DECLARE_SURE = 40, 70
PROPOSE_NO, PROPOSE_SURE = 60, 85
# A kiss or an embrace is sure with a partner whose heart is still in it.
TENDER_SURE = 40
# Beyond a kiss: sure with a partner whose heart is in it or with anyone this drawn, and not
# open at all with someone barely drawn who is no partner.
INTIMATE_NO, INTIMATE_PARTNER, INTIMATE_SURE = 30, 50, 70
# From here someone is drawn enough to another that it helps a romantic step of words.
DRAWN_AT = 40
# What ending it costs in how the other likes and trusts whoever ended it, by how far the two
# had come, and what it takes from their heart.
PARTED_COUPLE, PARTED_COURTING = 15, 5
PARTED_HEART_COUPLE, PARTED_HEART_COURTING = 30, 10
# What an ask that was thrown for and turned down takes from their heart: asked too soon,
# it sets things back, so asking again and again only digs the hole.
TURNED_DOWN = 5

FORWARD = {
    BondStage.INTEREST: (BondStage.COURTING, BondStage.TOGETHER),
    BondStage.COURTING: (BondStage.TOGETHER,),
    BondStage.TOGETHER: (BondStage.PROMISED,),
    BondStage.PROMISED: (BondStage.MARRIED,),
    BondStage.MARRIED: (),
    BondStage.OVER: (),
}


# The stages in the order a romance comes to them, its end last.
ORDER = tuple(FORWARD)


class Pace(StrEnum):
    """How long someone's heart rests after it moves."""

    SLOW = "slow"
    STEADY = "steady"
    QUICK = "quick"


REST_S = {Pace.SLOW: 3 * DAY, Pace.STEADY: DAY, Pace.QUICK: 8 * HOUR}
_PACES = (Pace.SLOW, Pace.STEADY, Pace.STEADY, Pace.QUICK)


def pace(character_id: str) -> Pace:
    """Someone's own pace, which is theirs for the whole story: it follows from who they are
    (their id), never from a throw, so no telling of the story changes it."""
    return _PACES[zlib.crc32(character_id.encode()) % len(_PACES)]


def can_move(bond: Bond, stage: BondStage) -> bool:
    """Whether a bond may come to a stage: forward, a step at a time save that an ask answered
    with a yes makes a couple of two who were only interested, and to its end from anywhere.
    Never back, and never on from its end."""
    if not bond.stage.live:
        return False
    return stage is BondStage.OVER or stage in FORWARD[bond.stage]


def live(state: WorldState, a: str, b: str) -> Bond | None:
    """The romance between two people that isn't over, if there is one."""
    return next(
        (
            bond
            for bond in _sorted(state)
            if bond.stage.live and bond.holds(a) and bond.holds(b) and a != b
        ),
        None,
    )


def last_over(state: WorldState, a: str, b: str) -> Bond | None:
    """The latest romance between two people that ended, if one did."""
    over = [
        bond
        for bond in _sorted(state)
        if not bond.stage.live and bond.holds(a) and bond.holds(b) and a != b
    ]
    return max(over, key=lambda bond: bond.since_s, default=None)


def partners(state: WorldState, character_id: str) -> list[str]:
    """Whom someone is a couple with: together, promised or married, by id."""
    return [
        bond.other(character_id)
        for bond in _sorted(state)
        if bond.stage.couple and bond.holds(character_id)
    ]


def _sorted(state: WorldState) -> list[Bond]:
    # Never by the map's own order, which Postgres doesn't keep.
    return sorted(state.bonds.values(), key=lambda bond: natural_key(bond.id))


def kin(characters: dict[str, Character], a: str, b: str) -> bool:
    """Whether two people are close family by blood, as far as the record has it: one descends
    from the other, or they share a parent."""
    first, second = characters.get(a), characters.get(b)
    if first is None or second is None:
        return False
    if a in ancestors(characters, b) or b in ancestors(characters, a):
        return True
    return bool(set(first.parent_ids) & set(second.parent_ids))


class Closed(StrEnum):
    """Why someone's heart is closed to another."""

    FAMILY = "family"
    AVERSE = "averse"  # they want nothing to do with them
    AFRAID = "afraid"  # too afraid of them for anything to be freely given


def closed_to(state: WorldState, other: Character, suitor_id: str) -> Closed | None:
    """Why someone's heart is closed to another, or None when it is open: they are family,
    they want nothing to do with them, or they are too afraid of them for anything to be
    freely given."""
    if kin(state.characters, other.id, suitor_id):
        return Closed.FAMILY
    attitude = other.attitude_toward(suitor_id)
    if attitude.affinity <= -WARM_AT:
        return Closed.AVERSE
    if attitude.fear >= AFRAID_AT:
        return Closed.AFRAID
    return None


def gain(
    other: Character,
    suitor_id: str,
    *,
    whole: bool,
    over_the_top: bool,
    now_s: int,
    lasted_s: int,
    moved_s: int | None = None,
    cut: bool = False,
) -> int:
    """How far an advance that was answered moves someone's heart: a notch, or half of one when
    it only half came off (`whole` false). Their heart rests after it moves, so nothing moves
    it again until it has, and nothing moves the heart of someone who neither likes nor trusts
    whoever made the advance. A step that goes on past the rest counts from there, and one
    that lasted long enough for their heart to rest and move again counts for each time it
    could, up to `MOST_NOTCHES`. Two things add to that once, however long the step: a little
    more for someone who already likes and trusts them, and one notch more for a throw over
    the top, which is one moment that went better than anyone hoped. `moved_s` is when their
    heart last moved, where this plan already moved it. A step an event cut short (`cut`)
    counts only the times their heart had rested while it ran: nothing, when it was stopped
    sooner than that."""
    attitude = other.attitude_toward(suitor_id)
    last = attitude.heart_moved_s if moved_s is None else moved_s
    rest = REST_S[pace(other.id)]
    resting_s = 0 if last is None else max(0, rest - (now_s - last))
    free_s = max(0, lasted_s) - resting_s  # of the step, once their heart had rested
    if free_s < 0:
        return 0
    warmth = (attitude.affinity + attitude.trust) / 2
    if warmth <= -WARM_AT:
        return 0
    notch = NOTCH if whole else NOTCH // 2
    times = min(MOST_NOTCHES, (0 if cut else 1) + free_s // rest)
    if times == 0:
        return 0
    more = notch * times
    if over_the_top:
        more += notch
    if warmth >= WARM_AT:
        more += WARM_BONUS
    return more


def heart_words(attraction: int, whom: str = "them") -> str:
    """Someone's heart toward another, in words a narrator can tell from."""
    if attraction >= PROPOSE_SURE:
        return f"deeply in love with {whom}"
    if attraction >= DECLARE_SURE:
        return f"in love with {whom}"
    if attraction >= DRAWN_AT:
        return f"drawn to {whom}"
    if attraction >= COURTING_AT:
        return f"starting to be drawn to {whom}"
    if attraction > 0:
        return f"curious about {whom}, and no more than that yet"
    return f"not drawn to {whom}"
