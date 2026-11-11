"""E7, W16, K8: events inside a long stretch of time, such as "I farm here for a year".

Before the clock moves through a stretch of a day or more, the director rolls for events along it
in at most `MONTAGE_MAX_STEPS` steps, so a thousand-year skip costs no more than a season's. Each
step has a chance of an event from the story's frequency setting. Rolled events are scheduled as
`director.event` pending events at seeded times inside their step; the first that needs a decision
is marked `needs_player`, so the clock stops at it and the scene starts there ("the river rises
in month four"). Rolling stops at that event, because nothing after it has happened yet. Small good
things that need no decision simply happen on the way and colour the montage.

A trip is rolled the same way from its own table, at the road's own, much higher rate, so a
journey meets things on the way (W10, `schedule_road`).
"""

import math
from collections.abc import Callable
from dataclasses import replace

from engine.base import DAY
from engine.context import TurnContext
from engine.director import deck, rules
from engine.director.due import MONTAGE_KIND, pick_payload
from engine.director.sources import Pick, from_card, pick_event
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

    def pick(current: WorldState, pick_rng: SeededRng, recent: list[str]) -> Pick | None:
        return pick_event(current, ctx, pick_rng, allowed, recent=recent, decision_only=False)

    return _schedule(
        state,
        montage_steps(start_s, end_s),
        gap,
        pick,
        ctx,
        rng,
        origin="W16 roll inside a time skip (E7)",
    )


def road_steps(start_s: int, end_s: int) -> list[tuple[int, int]]:
    """A trip split into at most MONTAGE_MAX_STEPS equal legs of at least ROAD_MIN_S."""
    length = end_s - start_s
    count = max(1, min(rules.MONTAGE_MAX_STEPS, length // rules.ROAD_MIN_S))
    bounds = [start_s + length * i // count for i in range(count + 1)]
    return list(zip(bounds[:-1], bounds[1:], strict=True))


def schedule_road(
    state: WorldState, start_s: int, end_s: int, ctx: TurnContext, rng: SeededRng
) -> WorldState:
    """W10, W16: schedule what the road brings on a trip of the player character's from
    `start_s` to `end_s`, so that a journey is not always one scene: someone on the way, a way
    that is blocked, trouble, a place to stop (`deck.ROAD`).

    The longer the way, the likelier it meets something (`rules.ROAD_MEAN_GAP_S`), and each
    stop since they last arrived somewhere makes the rest of the way quieter. The first event
    that needs a decision stops the clock there, on the way, and the scene starts from it; the
    small good things simply happen and colour the telling. Call it as `schedule_stretch` is
    called, in its place. Nothing is rolled for a trip under `rules.ROAD_MIN_S` or while an
    encounter is on.
    """
    if end_s - start_s < rules.ROAD_MIN_S or state.scene.encounter is not None:
        return state
    quieter = min(rules.ROAD_MAX_QUIETER, state.director.road_stops)
    gap = rules.ROAD_MEAN_GAP_S[ctx.settings.event_frequency] * 2**quieter
    allowed = allowed_themes(state, ctx)

    def pick(current: WorldState, pick_rng: SeededRng, recent: list[str]) -> Pick | None:
        card = deck.draw_road(ctx, pick_rng, allowed, recent=recent)
        if card is None:
            return None
        drawn = from_card(current, card, pick_rng.child("cast"))
        # It happens on the way, not in the place the trip left.
        return replace(drawn, event=drawn.event.model_copy(update={"place_id": None}))

    return _schedule(
        state, road_steps(start_s, end_s), gap, pick, ctx, rng, origin="W16 roll on the way (W10)"
    )


def _schedule(
    state: WorldState,
    steps: list[tuple[int, int]],
    gap: int,
    pick_for: Callable[[WorldState, SeededRng, list[str]], Pick | None],
    ctx: TurnContext,
    rng: SeededRng,
    *,
    origin: str,
) -> WorldState:
    """Roll each step for an event, with a chance from its length and the mean `gap` between
    events, and schedule what `pick_for` draws at a seeded time inside the step. Rolling stops
    at the first event that needs a decision: nothing after it has happened yet."""
    recent = list(state.director.recent_sources)
    start_s = steps[0][0]
    new: WorldState | None = None
    for index, (low, high) in enumerate(steps):
        step_rng = rng.child("step", index)
        if not step_rng.chance(1 - math.exp(-(high - low) / gap)):
            continue
        pick = pick_for(new or state, step_rng.child("pick"), recent)
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
            origin=Origin(kind=OriginKind.ENGINE, text=origin),
            payload={"pick": pick_payload(pick)},
            seed=step_rng.seed,
            created_turn=ctx.turn,
            created_s=start_s,
        )
        recent = [*recent, pick.key][-rules.RECENT_SOURCES :]
        if needs_decision:
            break
    return new or state
