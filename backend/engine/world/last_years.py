"""The player character's own old age (N6, W6, W10): nothing when it begins, a stop when the end
is close, then a real end.

Miki, 2026-11-13: "Your character can die of old age, but you shouldn't give a warning", "when
you're getting close to die, if it's a time skip, you should stop it and talk with the user.
Like, give the user the turn back, and he says, no, okay, let's move forward", "you shouldn't
be able to see the exact years that you have left", and of that scene: "you listen to your
heart and it starts slowing down", "you can sort of foresee that your end is close", "how can
I extend my life? Or maybe the user can choose to face death peacefully".

Old age takes everyone else under the tick's dice (`engine.world.lives`). The player
character's is theirs to live. Its day is drawn once, by the odds everyone's old age follows
(`old_age.taken_at`), and kept where nobody reads it: no scene, no screen and no brief ever
holds the day or how long is left. Nothing announces that old age has begun.

**The years stop when the end is close.** Some way before the day, a part of their span drawn
with it (`LAST_YEARS`, so the distance tells nobody the day), an event that needs them stops
the stretch of time they are in, once. The scene it opens lets them feel that the end is close,
with no number, and the turn is theirs again. `Character.old_age_span` then holds the span
they were told for. Someone already that close when the world first looks, a story that starts
with a dying character or a span that just changed, is told a day in.

**Going on, it takes them** on the day, never within a season of the stop. The day is on
record from the first, so the years find it however they are cut, and a rewound story finds
the same day (W10a). It ends their story like any death (N6): the record has them dead of old
age, and their romances ended by it (W17).

**A longer life is another span.** A rung that lengthens life (G19), a people that lives
longer (G23), a span the story gave them: when how long they live changes, what was pending
for the old span is cancelled, and a new day is drawn for the new one, with a stop of its own.

Where the record can't say, nothing happens (A2), as for anyone: no age on record, a ladder
whose rung carries no lifespan, a people old age never takes, a beast. And nothing is guessed
for them. Someone the world first finds already older than their kind lives has outlived it by
means the record doesn't give: anyone else is taken to have half as long again
(`old_age.own_span`), a guess the dice can live with, but no ground to end the player's story
on, so on record old age doesn't take such a player character. Where their span is only the
human one the world assumes (`old_age.on_record`), a world drafted before peoples said how long
they live, old age still comes, but neither the Character screen nor the narrator is given the
span before the stop has told it (`shown`), and the scene of the stop may answer that the story
has them living far longer (`_UNSAID`): the narrator's update then puts it on record.
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
from engine.world.tuning import AGELESS_YEARS, LAST_YEARS, LIFE_QUIET_S, OLD_AGE_FROM

NEAR, TAKES = "near", "takes"
# What the player reads over the scene of each (`PlannedEvent.title`), said in the story's
# language from the director's book (`engine.director.titles`).
NEAR_TITLE = "Your years run short"
TAKES_TITLE = "Your years run out"
# What the stop adds where the span is the world's assumption, not the record's word.
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
    def told(self) -> bool:
        """Whether a scene has told them the end is close, for the span they have now."""
        return self.you.old_age_span == self.span

    @property
    def old(self) -> bool:
        """Whether they have reached the age from which the years take people."""
        return self.age >= OLD_AGE_FROM * self.span


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
    """The player character's years as the Character screen and the narrator are given them:
    where the record itself says how long they live, or once a scene has told them the end is
    close. A span the world only assumes is not theirs to read before that. It is how long
    someone like them lives, never the day: nothing shows how long they have left."""
    found = years_of(state, at_s)
    if found is None or not (found.told or old_age.on_record(state, found.you)):
        return None
    return found


def ensure_old_age(w: World) -> None:
    """The player character's old age is pending as the record now has it: the stop before its
    day, or the day itself once a scene has told them the end is close. Whatever was pending
    for someone else, for another span or for a stage already behind them is cancelled. The
    first time the world counts their years it settles whether they have a span of their own:
    none within the span of someone like them, and as good as for ever for someone it finds
    already past that, since how long they live is then a guess (A2)."""
    state = w.state
    you = state.characters.get(state.player_id)
    if you is not None and you.lifespan_years is None:
        age = old_age.age_at(state, you, w.at_s)
        if age is not None:
            past = old_age.own_span(state, you, age) > 0
            you.lifespan_years = AGELESS_YEARS if past else 0
    found = years_of(state, w.at_s)
    stage = None if found is None else TAKES if found.told else NEAR
    kept = False
    for event in pending(state, Kind.OLD_AGE):
        if not kept and found is not None and _is_for(event, found, stage):
            kept = True
        else:
            cancel(w, event)
    if found is None or kept:
        return
    day_s, share = _draw(w, found)
    if found.told:
        # They were told for this span and its day is gone, a span that changed and changed
        # back: a day again, and no second stop.
        _schedule(w, found, TAKES, TAKES_TITLE, max(day_s, w.at_s + LIFE_QUIET_S))
        return
    lead = max(LIFE_QUIET_S, math.ceil(found.span * share * YEAR))
    stop_s = max(w.at_s + DAY, day_s - lead)
    _schedule(w, found, NEAR, NEAR_TITLE, stop_s, day_s=max(day_s, stop_s + LIFE_QUIET_S))


def on_old_age(w: World, event: PendingEvent) -> bool:
    """The end of the player character's life is close, or old age takes them. Either needs
    them: it is their own scene. One that no longer holds, for someone who is no longer the
    player character or for a span they no longer have, is cancelled, so nobody is told."""
    found = years_of(w.state, w.at_s)
    stage = event.payload.get("phase")
    if found is None or not _is_for(event, found, stage) or found.told != (stage == TAKES):
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
        f"{you.name} is {you.age}, of the about {found.span} years someone like them lives, "
        "and the end of their life is close. The years stop here. Tell it from inside, as "
        "they sense it in their own body, such as a heart that slows or strength that doesn't "
        "come back, and let them foresee that going on as they are, old age takes them soon. "
        "Nobody knows the day: give no number of years or days left. What they do with the "
        "time is theirs: look for a way to lengthen their life, where the world has one, or "
        f"meet the end in peace.{unsaid}"
    )
    day_s = int(event.payload.get("day_s", 0))
    _schedule(w, found, TAKES, TAKES_TITLE, max(day_s, w.at_s + LIFE_QUIET_S))
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


def _draw(w: World, found: Years) -> tuple[int, float]:
    """The day old age takes them, drawn for this span from the age they have reached, and
    the part of their span before it at which the years stop (`LAST_YEARS`). Both come from
    one stream keyed by who they are and the span, so nothing else moves them."""
    roll = w.roll("old age", found.you.id, found.span)
    at = old_age.taken_at(found.span, found.age, roll.random())
    return w.at_s + math.ceil((at - found.age) * YEAR), roll.uniform(*LAST_YEARS)


def _schedule(w: World, found: Years, stage: str, title: str, due_s: int, **more: int) -> None:
    schedule(
        w,
        Kind.OLD_AGE,
        due_s,
        title=title,
        subject_ids=[found.you.id],
        needs_player=True,
        payload={"phase": stage, "who": found.you.id, "span": found.span, **more},
    )
