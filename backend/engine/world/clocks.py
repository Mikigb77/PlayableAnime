"""Clocks: threats, ambitions and scheduled events that move whether or not the player is there
(E2, N5).

A clock steps on in-world time (`interval_s`, from `next_step_s`) and with deeds that match its
`advances_on` and `reverses_on`. Each entry matches a deed by kind ("kill"), or by kind and the
id of a victim, target or place ("kill:carmine", "burn:mill"). A clock that fills becomes a
pending `clock_end` event at its time (unless one is already set), and when that event arrives
the clock ends. If the player isn't there, it happens without them: the exam takes place, and a
thread of ambition, quest, threat or debt tied to it is resolved without the player. Mysteries,
rivalries and romances stay open, since the people in them remain.

Where it ends is where its event says, else where its owner is. A clock nobody owns, with no
place on record, is the story's own countdown ("the commander arrives at your door", "winter
closes the pass"): when the player character knows of it, or its thread involves them, its end
comes to them wherever they are, with the people its thread involves (`comes_to_player`). The
first plays on the real models (2026-11-14) had thirteen clocks of sixteen drafted that way,
and every one that ran out did so in silence, a search of the player's own house among them.
"""

from engine.state.records import (
    Clock,
    ClockStatus,
    Deed,
    EventStatus,
    Fact,
    FactKind,
    Origin,
    OriginKind,
    PendingEvent,
    Thread,
    ThreadKind,
    ThreadStatus,
)
from engine.state.world import WorldState
from engine.world.geography import characters_at, faction_seat, is_within
from engine.world.norms import canonical
from engine.world.rumors import start_rumor
from engine.world.scheduling import Kind, World, by_id, cancel, pending, schedule

ENDS_WITHOUT_PLAYER = frozenset(
    {ThreadKind.AMBITION, ThreadKind.QUEST, ThreadKind.THREAT, ThreadKind.DEBT}
)
NEWS_HOPS = 3


def _ends(event: PendingEvent, clock_id: str) -> bool:
    """Whether an event is the end of this clock."""
    return event.payload.get("clock_id") == clock_id or (
        event.origin is not None
        and event.origin.kind is OriginKind.CLOCK
        and event.origin.ref_id == clock_id
    )


def _end_events(w: World, clock: Clock) -> list[PendingEvent]:
    return [e for e in pending(w.state, Kind.CLOCK_END) if _ends(e, clock.id)]


def ensure_clock_events(w: World) -> None:
    """Every running clock that steps with time has its next step pending, and every full one
    its end. Run at the start of each catch-up and each tick, so clocks the drafter or the
    narrator added start moving."""
    for clock in by_id(w.state.clocks.values()):
        if clock.status is not ClockStatus.RUNNING:
            continue
        if clock.remaining == 0:
            _ensure_end(w, clock)
        elif clock.interval_s is not None and not pending(
            w.state, Kind.CLOCK_STEP, clock_id=clock.id
        ):
            if clock.next_step_s is None:
                clock.next_step_s = w.at_s + clock.interval_s
            schedule(
                w,
                Kind.CLOCK_STEP,
                clock.next_step_s,
                title=f"{clock.name}: {clock.steps[clock.filled]}",
                subject_ids=[clock.owner_id] if clock.owner_id else [],
                payload={"clock_id": clock.id},
                origin=Origin(kind=OriginKind.CLOCK, ref_id=clock.id),
                overdue=True,
            )


def _ensure_end(w: World, clock: Clock) -> None:
    if _end_events(w, clock):
        return
    schedule(
        w,
        Kind.CLOCK_END,
        w.at_s,
        title=clock.steps[-1],
        subject_ids=[clock.owner_id] if clock.owner_id else [],
        payload={"clock_id": clock.id},
        origin=Origin(kind=OriginKind.CLOCK, ref_id=clock.id),
    )


def _record_step(w: World, clock: Clock, index: int) -> None:
    """Who knows the clock knows it moved (C6)."""
    state = w.state
    known_by = list(clock.known_by)
    if clock.owner_id in state.characters and clock.owner_id not in known_by:
        known_by.append(clock.owner_id)
    fact = Fact(
        id=state.new_id("fact"),
        text=f"{clock.name}: {clock.steps[index]}",
        kind=FactKind.OBSERVATION,
        importance=3,
        subject_ids=[clock.owner_id] if clock.owner_id else [],
        known_by=known_by,
        turn=w.ctx.turn,
        world_s=w.at_s,
        timeline_id=state.timeline_id,
        origin=Origin(kind=OriginKind.CLOCK, ref_id=clock.id),
    )
    state.facts[fact.id] = fact


def advance(w: World, clock: Clock, steps: int = 1) -> None:
    """Move a running clock forward; a full clock gets its end (E2)."""
    if clock.status is not ClockStatus.RUNNING:
        return
    for _ in range(max(0, steps)):
        if clock.remaining == 0:
            break
        _record_step(w, clock, clock.filled)
        clock.filled += 1
    if clock.remaining == 0:
        _ensure_end(w, clock)


def reverse(w: World, clock: Clock) -> None:
    """Set a running clock back a step. A clock that was full no longer ends: the end the world
    scheduled when it filled is called off (an end the drafter set at a date still stands)."""
    if clock.status is not ClockStatus.RUNNING or clock.filled == 0:
        return
    if clock.remaining == 0:
        for event in _end_events(w, clock):
            if event.payload.get("clock_id") == clock.id:
                cancel(w, event)
    clock.filled -= 1


def on_clock_step(w: World, event: PendingEvent) -> None:
    clock = w.state.clocks.get(str(event.payload.get("clock_id")))
    if clock is None or clock.status is not ClockStatus.RUNNING or clock.remaining == 0:
        return
    advance(w, clock)
    if clock.interval_s is not None:
        clock.next_step_s = max(clock.next_step_s or w.at_s, event.due_s) + clock.interval_s
    if clock.remaining > 0:
        ensure_clock_events(w)


def matches(entry: str, deed: Deed) -> bool:
    kind, _, subject = entry.partition(":")
    if canonical(kind) != canonical(deed.kind):
        return False
    return not subject or subject.strip() in {*deed.subject_ids, deed.place_id}


def deed_moves_clocks(w: World, deed: Deed) -> None:
    """E2: deeds advance or set back the clocks that name them, whether or not anyone knows yet:
    killing the heir moves the succession whoever saw it."""
    for clock in by_id(w.state.clocks.values()):
        if any(matches(entry, deed) for entry in clock.advances_on):
            advance(w, clock)
        elif any(matches(entry, deed) for entry in clock.reverses_on):
            reverse(w, clock)


def where_it_ends(w: World, event: PendingEvent, clock: Clock) -> str | None:
    """Where a clock's end happens: where its event says, else where its owner is."""
    state = w.state
    if event.place_id is not None:
        return event.place_id
    owner = state.factions.get(clock.owner_id) if clock.owner_id else None
    if owner is not None:
        return faction_seat(state, owner)
    character = state.characters.get(clock.owner_id) if clock.owner_id else None
    return character.location_id if character is not None else None


def player_there(w: World, place_id: str | None) -> bool:
    return place_id is not None and is_within(w.state, w.state.player.location_id, place_id)


def thread_of(state: WorldState, clock: Clock) -> Thread | None:
    """The thread a clock belongs to: the one it names, else the one that names it."""
    if clock.thread_id and clock.thread_id in state.threads:
        return state.threads[clock.thread_id]
    return next((t for t in by_id(state.threads.values()) if t.clock_id == clock.id), None)


def comes_to_player(state: WorldState, event: PendingEvent, clock: Clock) -> bool:
    """E2: whether a clock's end comes to the player character wherever they are. It does when
    the record gives it nowhere else to happen (its event names no place, and nobody on record
    owns it) and it is theirs: they know of the clock, or its thread involves them. A clock
    with an owner ends where the owner is, with the player only if they are there, and one
    that is neither known to them nor about them is the world's own business (C6)."""
    if event.place_id is not None:
        return False
    if clock.owner_id in state.factions or clock.owner_id in state.characters:
        return False
    thread = thread_of(state, clock)
    return state.player_id in clock.known_by or (
        thread is not None and state.player_id in thread.involved_ids
    )


def ended_with_player(state: WorldState, clock_id: str) -> PendingEvent | None:
    """The end of this clock as it happened, when it happened with the player character: the
    applied event, which says on which turn. None when it has yet to end, or ended without
    them."""
    for event in state.pending_events.values():
        if (
            event.kind == Kind.CLOCK_END
            and event.status is EventStatus.APPLIED
            and event.needs_player
            and event.timeline_id == state.timeline_id
            and _ends(event, clock_id)
        ):
            return event
    return None


def on_clock_end(w: World, event: PendingEvent) -> bool:
    """A clock's end arrives: it happens, with the player if they are there or it comes to them
    (`comes_to_player`), else without them. Returns whether it needs the player."""
    state = w.state
    clock_id = event.payload.get("clock_id") or (event.origin.ref_id if event.origin else None)
    clock = state.clocks.get(str(clock_id)) if clock_id else None
    if clock is None:
        return event.needs_player
    if clock.status is not ClockStatus.RUNNING:
        return False
    for index in range(clock.filled, len(clock.steps)):
        _record_step(w, clock, index)
    clock.filled = len(clock.steps)
    clock.status = ClockStatus.ENDED
    where = where_it_ends(w, event, clock)
    thread = thread_of(state, clock)
    if where is None and comes_to_player(state, event, clock):
        # It happens where they are, and the people its thread involves come with it: they are
        # the event's own, so the scene has them (W10, `director.due.brings`).
        where = state.player.location_id
        event.needs_player = True
        coming = [
            i
            for i in (thread.involved_ids if thread is not None else [])
            if i != state.player_id and i in state.characters and state.characters[i].alive
        ]
        event.subject_ids = list(dict.fromkeys([*event.subject_ids, *coming]))
        # The scene's event says which countdown ran out, as well as how (`due.world_event`).
        event.payload.setdefault("event", {"brief": f"{clock.name}: {clock.steps[-1]}"})
    with_player = event.needs_player or player_there(w, where)
    if not with_player:
        if thread is not None and not thread.status.closed and thread.kind in ENDS_WITHOUT_PLAYER:
            thread.status = ThreadStatus.RESOLVED_WITHOUT_PLAYER
            thread.closed_turn = w.ctx.turn
    # Those there see it happen, and so does the player whenever it happens with them: for them it
    # is no rumor but what they saw (C6).
    present = [c.id for c in characters_at(state, where)]
    if with_player and state.player_id not in present:
        present.append(state.player_id)
    start_rumor(
        w,
        text=f"{clock.name}: {clock.steps[-1]}",
        is_true=True,
        place_id=where,
        hops=NEWS_HOPS,
        about_ids=[clock.owner_id] if clock.owner_id else [],
        accuracy=95,
        heard_by=present,
        seen_by=present,
    )
    return with_player
