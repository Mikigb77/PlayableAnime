"""The player character's own old age (N6, W6, W10): a warning first, then a real end.

Old age takes everyone else under the tick's dice (`engine.world.lives`). The player
character's is theirs to live, so it never comes as a throw they couldn't see coming: it is
two pending events of their own, at in-world times.

**It sets in** the moment they reach the age from which the years take people
(`OLD_AGE_FROM` of how long they live, `old_age.span`), or a day on for someone who is
already past it when the world first looks: a story that starts with an old character, or a
span that just changed. The event needs them, so it stops the stretch of time they are in,
once, and the scene it opens tells them their years are short. `Character.old_age_span` then
holds the span they were told for.

**It takes them** on a date drawn at that moment, by the odds everyone's old age follows
(`old_age.taken_at`), given the age they have reached, and never within a season of the
warning. The date is a pending event with a seed of its own, so a rewound story finds the
same day (W10a). Going on past it ends their story like any death (N6): the record has them
dead of old age, and their romances ended by it (W17).

**A longer life is another span.** A rung that lengthens life (G19), a people that lives
longer (G23), a span the story gave them: when how long they live changes, what was pending
for the old span is cancelled, and old age sets in at the new span's own age, with a warning
of its own.

Where the record can't say, nothing happens (A2), as for anyone: no age on record, a ladder
whose rung carries no lifespan, a people old age never takes, a beast. And nothing is guessed
for them. Someone the world first finds already older than their kind lives has outlived it by
means the record doesn't give: anyone else is taken to have half as long again
(`old_age.own_span`), a guess the dice can live with, but no ground to end the player's story
on, so on record old age doesn't take such a player character. Where their span is only the
human one the world assumes (`old_age.on_record`), a world drafted before peoples said how long
they live, old age still comes, but the Character screen doesn't claim the span before a scene
has told it (`shown`), and the scene that tells it may answer that the story has them living
far longer (`_UNSAID`): the narrator's update then puts it on record.
"""

import math
from dataclasses import dataclass

from engine.base import DAY, YEAR
from engine.state.cast import Character
from engine.state.records import EventStatus, PendingEvent
from engine.state.world import EventSize, WorldState
from engine.world import lives, old_age
from engine.world.norms import is_beast
from engine.world.scheduling import Kind, World, cancel, pending, schedule
from engine.world.tuning import AGELESS_YEARS, LIFE_QUIET_S, OLD_AGE_FROM

SETS_IN, TAKES = "sets_in", "takes"
# What the player reads over the scene of each (`PlannedEvent.title`), said in the story's
# language from the director's book (`engine.director.titles`).
SETS_IN_TITLE = "Old age sets in"
TAKES_TITLE = "Your years run out"
# How much longer than their span next to nobody lives (`old_age.worn`), for the narrator.
_AT_MOST = 1.2
# What the warning adds where the span is the world's assumption, not the record's word.
_UNSAID = (
    " The record doesn't say how long they live, and takes it for a human life. If the story "
    "has made them someone who lives far longer, or whom old age never takes, show no old age "
    "and say how long they live in the update (lifespan_years, 1000000 for never)."
)


@dataclass(frozen=True)
class Years:
    """The player character where old age can come to them: their age now, to the day, and
    how long they live."""

    you: Character
    age: float
    span: int

    @property
    def set_in(self) -> bool:
        """Whether a scene has told them old age set in, for the span they have now."""
        return self.you.old_age_span == self.span


def years_of(state: WorldState, at_s: int) -> Years | None:
    """The player character's years at a moment, or None where old age never comes to them
    or the record can't say (A2): dead, a beast, no age on record, a ladder whose rung
    carries no lifespan, a people old age never takes."""
    you = state.characters.get(state.player_id)
    if you is None or not you.alive or is_beast(state, you.id):
        return None
    age = old_age.age_at(state, you, at_s)
    if age is None or old_age.open_ended(state, you):
        return None
    span = old_age.span(state, you)
    return Years(you, age, span) if span < AGELESS_YEARS else None


def shown(state: WorldState, at_s: int) -> Years | None:
    """The player character's years as the Character screen gives them (S10): where the
    record itself says how long they live, or once a scene has told them old age set in. A
    span the world only assumes is not theirs to read before that."""
    found = years_of(state, at_s)
    if found is None or not (found.set_in or old_age.on_record(state, found.you)):
        return None
    return found


def ensure_old_age(w: World) -> None:
    """The player character's old age is pending as the record now has it: its setting in, at
    the age it does or a day from now for someone already past it, or the day it takes them
    once a scene has told them. Whatever was pending for someone else, for another span or
    for a stage already behind them is cancelled. The first time the world counts their years
    it settles whether they have a span of their own: none within the span of someone like
    them, and as good as for ever for someone it finds already past that, since how long they
    live is then a guess (A2)."""
    state = w.state
    you = state.characters.get(state.player_id)
    if you is not None and you.lifespan_years is None:
        age = old_age.age_at(state, you, w.at_s)
        if age is not None:
            past = old_age.own_span(state, you, age) > 0
            you.lifespan_years = AGELESS_YEARS if past else 0
    found = years_of(state, w.at_s)
    stage = None if found is None else TAKES if found.set_in else SETS_IN
    kept = False
    for event in pending(state, Kind.OLD_AGE):
        if not kept and found is not None and _is_for(event, found, stage):
            kept = True
        else:
            cancel(w, event)
    if found is None or kept:
        return
    if found.set_in:
        _draw(w, found)
        return
    wait = math.ceil((found.span * OLD_AGE_FROM - found.age) * YEAR)
    _schedule(w, found, SETS_IN, SETS_IN_TITLE, max(DAY, wait))


def on_old_age(w: World, event: PendingEvent) -> bool:
    """Old age sets in for the player character, or takes them. Either needs them: it is
    their own scene. One that no longer holds, for someone who is no longer the player
    character or for a span they no longer have, is cancelled, so nobody is told of it."""
    found = years_of(w.state, w.at_s)
    stage = event.payload.get("phase")
    if found is None or not _is_for(event, found, stage) or found.set_in != (stage == TAKES):
        event.status = EventStatus.CANCELLED
        return False
    you = found.you
    if w.state.aged_s is not None:
        # The scene reads everyone's age off the record, which the tick last counted up to
        # years ago in a long stretch: it is counted up to this day.
        lives.grow_older(w.state, w.at_s)
    if stage == TAKES:
        event.payload["event"] = _told(f"Old age takes {you.name}, at {you.age}.")
        lives.taken(w, you, known=True)
        return True
    you.old_age_span = found.span
    unsaid = "" if old_age.on_record(w.state, you) else _UNSAID
    event.payload["event"] = _told(
        f"{you.name} has grown old: {you.age}, of the about {found.span} years someone like them "
        "lives. Show it in their own body in this scene, and let them understand what it "
        f"means: their years are running out. Half of those who reach this age are gone by "
        f"{found.span}, and next to nobody sees {round(found.span * _AT_MOST)}. Only "
        "something that lengthens their life, where the world has such a thing, puts it off."
        f"{unsaid}"
    )
    _draw(w, found)
    return True


def _is_for(event: PendingEvent, found: Years, stage: object) -> bool:
    told = event.payload
    return (told.get("who"), told.get("span"), told.get("phase")) == (
        found.you.id,
        found.span,
        stage,
    )


def _told(brief: str) -> dict[str, str]:
    """The scene's event as the director reads it (`engine.director.due.world_event`): a
    personal one, a loss, told from this brief."""
    return {"size": EventSize.PERSONAL.value, "kind": "loss", "brief": brief}


def _draw(w: World, found: Years) -> None:
    """The day old age takes them, drawn once for this span from the age they have reached,
    and never within a season of now: those days are the story's to tell."""
    luck = w.roll("old age", found.you.id, found.span).random()
    at = old_age.taken_at(found.span, found.age, luck)
    wait = math.ceil((at - found.age) * YEAR)
    _schedule(w, found, TAKES, TAKES_TITLE, max(LIFE_QUIET_S, wait))


def _schedule(w: World, found: Years, stage: str, title: str, wait_s: int) -> None:
    schedule(
        w,
        Kind.OLD_AGE,
        w.at_s + wait_s,
        title=title,
        subject_ids=[found.you.id],
        needs_player=True,
        payload={"phase": stage, "who": found.you.id, "span": found.span},
    )
