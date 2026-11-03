"""`direct`: the director's decisions for one turn (W16, E4, E6, N1, N2, S2, M1, M2).

It runs after the player's steps played out (B5 step 3) and decides, in code, from the state:

1. What came due and has to be in the scene: the world's events that need the player, events
   rolled inside a time skip, and ignored events playing out (E2, E7, W16).
2. Whether something new comes in, from stall pressure, in W16's order of sources. Nothing
   unrelated comes in during an encounter (W10) or on the opening scene (N5).
3. What the player took up, so a taken-up event stops waiting to play out (W16).
4. Thread changes, callbacks, the suggestions' shape and the picture.
5. The director's memory for next turn, goals the player stated and leads that expired (N2).

It never changes the state: `record` writes the plan's `updates` back. The director decides that
something happens and what it is, never how it ends (W16).
"""

from engine.context import TurnContext
from engine.contracts.direction import (
    DirectorPlan,
    DirectorUpdates,
    EventSource,
    PlannedEvent,
    ThreadChange,
)
from engine.contracts.intent import Intent
from engine.contracts.resolution import Resolution
from engine.director import rules
from engine.director.due import PLAYS_OUT_KIND, came_due, open_playouts, playout_event, world_event
from engine.director.goals import expired_leads, player_goals
from engine.director.ids import IdProbe
from engine.director.pictures import decide_picture
from engine.director.pressure import in_control, measure, next_drift
from engine.director.sources import Pick, pick_event
from engine.director.suggestions import plan_suggestions
from engine.director.themes import allowed_themes
from engine.director.threads import callbacks, current_thread, lifecycle
from engine.director.turn import TurnFacts, player_deeds, read_turn
from engine.rng import SeededRng
from engine.state.records import (
    Lead,
    Origin,
    OriginKind,
    PendingEvent,
    Thread,
    ThreadStatus,
)
from engine.state.world import EventSize, WorldState


def _taken_up(event: PendingEvent, facts: TurnFacts) -> bool:
    """Whether the player took up a waiting event: they named its thread, or their deeds or the
    current encounter involve its people."""
    thread_id = event.payload.get("thread_id")
    if thread_id and thread_id in facts.responded_threads:
        return True
    return bool(facts.touched.intersection(event.subject_ids))


def _open_event(
    state: WorldState,
    ctx: TurnContext,
    pick: Pick,
    ids: IdProbe,
    updates: DirectorUpdates,
) -> PlannedEvent:
    """Record what a new event that needs a decision brings: its thread (a new one, or the one it
    continues), its play-out if nobody takes it up, and a lead for an offer (N1, N2, W16)."""
    event = pick.event
    thread_id = event.thread_id
    if thread_id is None and pick.thread_kind is not None:
        thread_id = ids.new("thread")
        updates.new_threads.append(
            Thread(
                id=thread_id,
                title=pick.thread_title or event.title,
                kind=pick.thread_kind,
                stakes=event.brief,
                involved_ids=list(dict.fromkeys([*pick.involved_ids, *event.cast_ids])),
                origin=Origin(
                    kind=OriginKind.AGENDA
                    if event.source is EventSource.AGENDA
                    else OriginKind.EMERGENCE
                    if event.source is EventSource.EMERGENCE
                    else OriginKind.EVENT,
                    ref_id=event.source_id or event.card_id,
                    text=event.title,
                ),
                opened_turn=ctx.turn,
                last_active_turn=ctx.turn,
                known_by=[state.player_id],
            )
        )
    plays_out_s = state.world_s + max(1, pick.window_s)
    event = event.model_copy(update={"thread_id": thread_id, "plays_out_s": plays_out_s})
    updates.schedule.append(
        PendingEvent(
            id=ids.new("director-event"),
            kind=PLAYS_OUT_KIND,
            title=f"{event.title}: left alone",
            due_s=plays_out_s,
            timeline_id=state.timeline_id,
            needs_player=False,
            subject_ids=list(event.cast_ids),
            place_id=event.place_id,
            origin=Origin(kind=OriginKind.EVENT, ref_id=thread_id, text=event.title),
            payload={
                "event": event.model_dump(mode="json"),
                "thread_id": thread_id,
                "lingers": pick.lingers,
            },
            created_turn=ctx.turn,
            created_s=state.world_s,
        )
    )
    if pick.lead:
        updates.new_leads.append(
            Lead(
                id=ids.new("lead"),
                text=event.title,
                kind=event.kind.value,
                place_id=event.place_id,
                offered_turn=ctx.turn,
                offered_s=state.world_s,
                expires_s=plays_out_s,
                thread_id=thread_id,
            )
        )
    return event


def direct(
    state: WorldState,
    resolution: Resolution,
    ctx: TurnContext,
    rng: SeededRng,
    intent: Intent | None = None,
) -> DirectorPlan:
    rng = rng.child("director")
    facts = read_turn(state, resolution, ctx, intent)
    allowed = allowed_themes(state, ctx)
    ids = IdProbe(state)
    memory = state.director.model_copy(deep=True)
    updates = DirectorUpdates()
    pressure = measure(state, resolution, ctx, intent, facts)

    # 1. What came due.
    due = came_due(state, ctx)
    updates.applied_ids.extend(due.pending_ids)
    event: PlannedEvent | None = None
    happenings: list[PlannedEvent] = []
    settled: dict[str, ThreadStatus] = {}
    recent = list(memory.recent_sources)
    for pending in due.world:
        planned = world_event(pending)
        if event is None:
            event = planned
        else:
            happenings.append(planned)
    for _pending, pick in due.rolled:
        if pick.event.needs_decision and event is None:
            event = _open_event(state, ctx, pick, ids, updates)
            recent.append(pick.key)
        else:
            happenings.append(pick.event)
    for pending in due.plays_out:
        if _taken_up(pending, facts):
            # Taken up by the very action it would have played out during: it never happens.
            updates.cancel_ids.append(pending.id)
            continue
        thread_id = pending.payload.get("thread_id")
        if thread_id:
            lingers = bool(pending.payload.get("lingers"))
            settled[thread_id] = (
                ThreadStatus.DORMANT if lingers else ThreadStatus.RESOLVED_WITHOUT_PLAYER
            )
        planned = playout_event(pending)
        if event is None:
            event = planned
        else:
            happenings.append(planned)

    # 2. Events still waiting for the player that they took up this turn stop waiting.
    for pending in open_playouts(state):
        if _taken_up(pending, facts):
            updates.cancel_ids.append(pending.id)
    updates.applied_ids = [i for i in updates.applied_ids if i not in updates.cancel_ids]

    # 3. Something new, if it's time (W16). Never during an encounter or on the opening scene.
    if event is None and not pressure.encounter and ctx.turn > 1:
        if rng.child("pressure").chance(pressure.early_chance):
            pick = pick_event(state, ctx, rng.child("source"), allowed, recent=recent)
            if pick is not None:
                event = _open_event(state, ctx, pick, ids, updates)
                recent.append(pick.key)
                if pick.event.source is EventSource.DECK:
                    memory.deck_draws += 1

    # 4. Threads, callbacks and suggestions.
    woken = {event.thread_id} if event is not None and event.thread_id else set()
    changes = lifecycle(state, ctx, facts, woken=woken, settled=settled)
    known_new = {t.id for t in updates.new_threads}
    changes += [ThreadChange(thread_id=i, active=True) for i in sorted(known_new)]
    closed = [
        c.thread_id
        for c in changes
        if c.status is not None
        and c.status.closed
        and c.thread_id not in settled
        and _matters(state, c.thread_id, facts)
    ]
    updates.thread_changes = changes
    calls = callbacks(
        state,
        rng.child("callbacks"),
        allowed,
        exclude=woken | known_new,
        changes=changes,
        limit=1 if event is not None else rules.MAX_CALLBACKS,
    )
    deciding = event.thread_id if event is not None and event.needs_decision else None
    thread_id = current_thread(state, changes, deciding)
    suggestions = plan_suggestions(ctx, pressure=pressure, event=event, thread_id=thread_id)

    # 5. The picture.
    picture = decide_picture(state, ctx, facts, memory, event=event, closed_threads=closed)

    # 6. The director's memory for next turn.
    decision = event is not None and event.needs_decision
    memory.turns_without_stakes = 0 if decision else pressure.turns_without_stakes
    memory.low_stakes_streak = 0 if event is not None else pressure.low_stakes_streak
    memory.last_action_key = None if event is not None else pressure.action_key
    if event is not None:
        memory.last_event_turn = ctx.turn
        memory.last_event_size = event.size
    big = (event is not None and event.size is not EventSize.PERSONAL) or any(
        d.severity >= rules.BIG_DEED for d in player_deeds(state, facts)
    )
    memory.frequency_drift = next_drift(
        memory.frequency_drift,
        big=big,
        comfortable=in_control(state, resolution, pressure),
    )
    memory.recent_sources = recent[-rules.RECENT_SOURCES :]
    updates.memory = memory

    # 7. Goals and leads (N2).
    updates.new_goals, updates.taken_lead_ids = player_goals(state, ctx, intent, facts, ids)
    updates.expired_lead_ids = expired_leads(state, updates.taken_lead_ids)

    return DirectorPlan(
        event=event,
        happenings=happenings,
        callbacks=calls,
        picture=picture,
        suggestions=suggestions,
        stall_pressure=max(0.0, pressure.value),
        updates=updates,
    )


def _matters(state: WorldState, thread_id: str, facts: TurnFacts) -> bool:
    """An arc worth a picture when it ends (M1): a premise thread, a clocked one or one the
    player took up."""
    thread = state.threads.get(thread_id)
    if thread is None:
        return False
    return (
        thread.origin.kind is OriginKind.PREMISE
        or thread.clock_id is not None
        or thread.taken_up_turn is not None
        or thread_id in facts.responded_threads
    )
