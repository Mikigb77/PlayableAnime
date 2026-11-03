"""E7, W16, K8: events inside a long stretch of time, such as "I farm here for a year".

Before the clock moves through a stretch of a day or more, the director rolls for events along it
in at most `MONTAGE_MAX_STEPS` steps, so a thousand-year skip costs no more than a season's. Each
step has a chance of an event from the story's frequency setting. Rolled events are scheduled as
`director.event` pending events at seeded times inside their step; the first that needs a decision
is marked `needs_player`, so the clock stops at it and the scene starts there ("the river rises
in month four"). Rolling stops at that event, because nothing after it has happened yet. Small good
things that need no decision simply happen on the way and colour the montage.
"""

import math

from engine.base import DAY
from engine.context import TurnContext
from engine.director import rules
from engine.director.due import MONTAGE_KIND, pick_payload
from engine.director.sources import pick_event
from engine.director.themes import allowed_themes
from engine.rng import SeededRng
from engine.state.records import Origin, OriginKind, PendingEvent
from engine.state.world import WorldState


def montage_steps(start_s: int, end_s: int) -> list[tuple[int, int]]:
    """The stretch split into at most MONTAGE_MAX_STEPS equal steps of at least a day."""
    length = end_s - start_s
    count = max(1, min(rules.MONTAGE_MAX_STEPS, length // DAY))
    bounds = [start_s + length * i // count for i in range(count + 1)]
    return list(zip(bounds[:-1], bounds[1:], strict=True))


def schedule_stretch(
    state: WorldState, start_s: int, end_s: int, ctx: TurnContext, rng: SeededRng
) -> WorldState:
    """Schedule the W16 events of a long stretch from `start_s` to `end_s` (E7).

    Call it with the clock at the stretch's start, before the clock moves. Returns the state with
    the events scheduled, or the same state when the stretch is shorter than a day, an encounter
    is on (W10: nothing unrelated interrupts it) or nothing was rolled.
    """
    if end_s - start_s < rules.MONTAGE_MIN_S or state.scene.encounter is not None:
        return state
    gap = rules.MONTAGE_MEAN_GAP_S[ctx.settings.event_frequency]
    allowed = allowed_themes(state, ctx)
    recent = list(state.director.recent_sources)
    new: WorldState | None = None
    for index, (low, high) in enumerate(montage_steps(start_s, end_s)):
        step_rng = rng.child("step", index)
        if not step_rng.chance(1 - math.exp(-(high - low) / gap)):
            continue
        pick = pick_event(
            new or state, ctx, step_rng.child("pick"), allowed, recent=recent, decision_only=False
        )
        if pick is None:
            continue
        new = new or state.model_copy(deep=True)
        due_s = low + 1 + step_rng.child("when").below(high - low)
        event_id = new.new_id("director-event")
        needs_decision = pick.event.needs_decision
        new.pending_events[event_id] = PendingEvent(
            id=event_id,
            kind=MONTAGE_KIND,
            title=pick.event.title,
            due_s=due_s,
            timeline_id=new.timeline_id,
            needs_player=needs_decision,
            place_id=pick.event.place_id,
            subject_ids=list(pick.event.cast_ids),
            origin=Origin(kind=OriginKind.ENGINE, text="W16 roll inside a time skip (E7)"),
            payload={"pick": pick_payload(pick)},
            seed=step_rng.seed,
            created_turn=ctx.turn,
            created_s=start_s,
        )
        recent = [*recent, pick.key][-rules.RECENT_SOURCES :]
        if needs_decision:
            break
    return new or state
