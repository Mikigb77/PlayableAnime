"""Applying one pending event that fell due (W2, W5, W6, W10, W13, W15, E2, N6).

`apply_in_place` is the handler the clock runs for every due event, in time order. It leaves the
event applied, never moves the clock or the timeline, and records on the applied event whether it
needed the player at the moment it happened: guards arriving where the player still is do, and
guards arriving where the player has left don't. Events this package doesn't own (such as the
director's `director.*` events, or a drafter's custom kinds) are only marked applied, keeping the
flag they were scheduled with.
"""

from engine.context import TurnContext
from engine.rng import SeededRng
from engine.state.records import EventStatus, PendingEvent
from engine.state.world import WorldState
from engine.world.aftermath import on_tidings
from engine.world.arrivals import on_answer, on_report
from engine.world.births import on_birth
from engine.world.cast import on_emergence, on_revival
from engine.world.clocks import on_clock_end, on_clock_step
from engine.world.discovery import on_discovery
from engine.world.rumors import on_rumor
from engine.world.scheduling import Kind, World, event_rng
from engine.world.tick import on_tick

_QUIET = {
    Kind.REPORT: on_report,
    Kind.RUMOR: on_rumor,
    Kind.TIDINGS: on_tidings,
    Kind.DISCOVERY: on_discovery,
    Kind.CLOCK_STEP: on_clock_step,
    Kind.EMERGENCE: on_emergence,
    Kind.REVIVAL: on_revival,
    Kind.TICK: on_tick,
}
_MAY_NEED_PLAYER = {
    Kind.ANSWER: on_answer,
    Kind.CLOCK_END: on_clock_end,
    Kind.BIRTH: on_birth,
}


def apply_in_place(
    state: WorldState, event: PendingEvent, ctx: TurnContext, rng: SeededRng
) -> WorldState:
    """Apply a due event to `state` itself, at the clock's current time, and return it.

    `rng` is the turn's stream; the event rolls from its own seed (or a stream keyed by its id),
    so it rolls the same however the time around it was split into steps.
    """
    stored = state.pending_events.get(event.id)
    if stored is None or stored.status is not EventStatus.PENDING:
        raise ValueError(f"event {event.id!r} is not a pending event of this state")
    w = World(state=state, ctx=ctx, at_s=state.world_s, rng=event_rng(stored, rng))
    # Settle it first, so anything it schedules or caps sees it as happened (C1 causes).
    stored.status = EventStatus.APPLIED
    stored.applied_turn = ctx.turn
    stored.applied_s = state.world_s
    try:
        kind = Kind(stored.kind)
    except ValueError:
        return state  # not ours: marked applied, its flag as scheduled
    if kind in _QUIET:
        _QUIET[kind](w, stored)
        stored.needs_player = False
    else:
        stored.needs_player = bool(_MAY_NEED_PLAYER[kind](w, stored))
    return state


def needs_player(state: WorldState, event: PendingEvent) -> bool:
    """Whether an applied event stops the clock for the player: read from the event as applied,
    since applying it settled that from the state at the time."""
    stored = state.pending_events.get(event.id, event)
    return stored.needs_player
