"""Clocks: threats, ambitions and scheduled events that move whether or not the player is there
(E2, N5).

A clock steps on in-world time (`interval_s`, from `next_step_s`) and with deeds that match its
`advances_on` and `reverses_on`. Each entry matches a deed by kind ("kill"), or by kind and the
id of a victim, target or place ("kill:carmine", "burn:mill"). A clock that fills becomes a
pending `clock_end` event at its time (unless one is already set), and when that event arrives
the clock ends. If the player isn't there, it happens without them: the exam takes place, and a
thread of ambition, quest, threat or debt tied to it is resolved without the player. Mysteries,
rivalries and romances stay open, since the people in them remain.
"""

from engine.state.records import (
    Clock,
    ClockStatus,
    Deed,
    Fact,
    FactKind,
    Origin,
    OriginKind,
    PendingEvent,
    ThreadKind,
    ThreadStatus,
)
from engine.world.geography import characters_at, faction_seat, is_within
from engine.world.norms import canonical
from engine.world.rumors import start_rumor
from engine.world.scheduling import Kind, World, by_id, pending, schedule

ENDS_WITHOUT_PLAYER = frozenset(
    {ThreadKind.AMBITION, ThreadKind.QUEST, ThreadKind.THREAT, ThreadKind.DEBT}
)
NEWS_HOPS = 3


def _end_events(w: World, clock: Clock) -> list[PendingEvent]:
    return [
        e
        for e in pending(w.state, Kind.CLOCK_END)
        if e.payload.get("clock_id") == clock.id
        or (
            e.origin is not None
            and e.origin.kind is OriginKind.CLOCK
            and e.origin.ref_id == clock.id
        )
    ]


def ensure_clock_events(w: World) -> None:
    """Every running clock that steps with time has its next step pending, and every full one
    its end. Run at the start of each catch-up and each tick, so clocks the drafter or the
    narrator added start moving."""
    for clock in by_id(w.state.clocks.values()):
        if clock.status is not ClockStatus.RUNNING:
            continue
        if clock.remaining == 0:
            _ensure_end(w, clock)
        elif (
            clock.interval_s is not None
            and clock.next_step_s is not None
            and not pending(w.state, Kind.CLOCK_STEP, clock_id=clock.id)
        ):
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


def reverse(clock: Clock) -> None:
    if clock.status is ClockStatus.RUNNING and clock.filled > 0:
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
            reverse(clock)


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


def on_clock_end(w: World, event: PendingEvent) -> bool:
    """A clock's end arrives: it happens, with the player if they are there, else without them.
    Returns whether it needs the player."""
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
    with_player = event.needs_player or player_there(w, where)
    if not with_player:
        thread = state.threads.get(clock.thread_id) if clock.thread_id else None
        if thread is not None and not thread.status.closed and thread.kind in ENDS_WITHOUT_PLAYER:
            thread.status = ThreadStatus.RESOLVED_WITHOUT_PLAYER
            thread.closed_turn = w.ctx.turn
    start_rumor(
        w,
        text=f"{clock.name}: {clock.steps[-1]}",
        is_true=True,
        place_id=where,
        hops=NEWS_HOPS,
        about_ids=[clock.owner_id] if clock.owner_id else [],
        accuracy=95,
        heard_by=[c.id for c in characters_at(state, where)],
    )
    return with_player
