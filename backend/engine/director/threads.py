"""N1: thread lifecycle and callbacks.

Threads open from events, premises, deeds and agendas. The director keeps their status honest:

- An open thread nobody touched for `DORMANT_AFTER_TURNS` turns goes dormant (attention, not world
  time: its clock, if it has one, keeps running on in-world time, E2).
- A dormant thread wakes when the player takes it up or an event brings it back.
- A thread closes when what it was about is over: its mystery is solved, its clock ran out (the
  exam happened), or everyone it pitted the player against is dead. It is resolved if the player
  took it up at some point, and resolved without the player otherwise. An ignored event's thread
  closes without the player when it plays out, unless the matter lingers, in which case it goes
  dormant and can return later.

Each scene, one or two dormant threads the player knows are pulled into context for callbacks
(C4), preferring those whose people or places are in the scene.
"""

from engine.context import TurnContext
from engine.contracts.direction import ThreadChange
from engine.director import rules
from engine.director.sources import thread_themes
from engine.director.themes import fits
from engine.director.turn import TurnFacts
from engine.rng import SeededRng
from engine.state.cast import CharacterStatus
from engine.state.records import ClockStatus, Thread, ThreadKind, ThreadStatus
from engine.state.world import WorldState, natural_key

# Threads that end when everyone they pit the player against is dead.
OPPOSED = (ThreadKind.THREAT, ThreadKind.RIVALRY)


def _closed_by_world(state: WorldState, thread: Thread) -> str | None:
    """Why the world has closed this thread, if it has."""
    mysteries = [m for m in state.bible.mysteries if m.thread_id == thread.id]
    if any(m.solved for m in mysteries):
        return "its mystery was solved"
    clock = state.clocks.get(thread.clock_id) if thread.clock_id else None
    if (
        clock is not None
        and clock.status is ClockStatus.ENDED
        and thread.kind is not ThreadKind.MYSTERY
        and not mysteries
    ):
        # A mystery outlives its clock: the council can name a boss and the killer stay unknown.
        return f"its clock ran out: {clock.steps[-1]}"
    if thread.kind in OPPOSED:
        others = [
            state.characters[i]
            for i in thread.involved_ids
            if i != state.player_id and i in state.characters
        ]
        if others and all(c.status is CharacterStatus.DEAD for c in others):
            return "everyone it pitted the player against is dead"
    return None


def lifecycle(
    state: WorldState,
    ctx: TurnContext,
    facts: TurnFacts,
    *,
    woken: set[str],
    settled: dict[str, ThreadStatus],
) -> list[ThreadChange]:
    """The thread changes for this turn.

    `woken` are threads an event brings in this turn; `settled` are threads an ignored event's
    play-out decides (dormant or resolved without the player). The player taking a thread up
    (`facts.responded_threads`) or acting on its people (`facts.touched`) keeps it active.
    """
    changes: list[ThreadChange] = []
    for thread in sorted(state.threads.values(), key=lambda t: natural_key(t.id)):
        if thread.status.closed:
            continue
        taken_up = thread.id in facts.responded_threads
        touched = taken_up or bool(facts.touched.intersection(thread.involved_ids))
        if thread.id in settled:
            # An ignored event played out; a thread the player took up this very turn stays theirs.
            if not taken_up:
                changes.append(
                    ThreadChange(
                        thread_id=thread.id,
                        status=settled[thread.id],
                        active=True,  # it moved on, without the player
                        reason="the event nobody took up played out",
                    )
                )
                continue
        why = _closed_by_world(state, thread)
        if why is not None:
            player_in = taken_up or thread.taken_up_turn is not None
            status = ThreadStatus.RESOLVED if player_in else ThreadStatus.RESOLVED_WITHOUT_PLAYER
            changes.append(ThreadChange(thread_id=thread.id, status=status, reason=why))
            continue
        if thread.id in woken or touched:
            changes.append(
                ThreadChange(
                    thread_id=thread.id,
                    status=ThreadStatus.OPEN if thread.status is ThreadStatus.DORMANT else None,
                    active=True,
                    taken_up=taken_up,
                    reason="taken up" if taken_up else "back in the scene",
                )
            )
            continue
        idle = ctx.turn - thread.last_active_turn
        if thread.status is ThreadStatus.OPEN and idle >= rules.DORMANT_AFTER_TURNS:
            changes.append(
                ThreadChange(
                    thread_id=thread.id,
                    status=ThreadStatus.DORMANT,
                    reason=f"untouched for {idle} turns",
                )
            )
    return changes


def callbacks(
    state: WorldState,
    rng: SeededRng,
    allowed,
    *,
    exclude: set[str],
    changes: list[ThreadChange],
    limit: int = rules.MAX_CALLBACKS,
) -> list[str]:
    """N1, C4: one or two dormant threads the player knows, for the narrator to call back to.
    Threads whose people or places are in the scene come first; the rest are a seeded pick."""
    after = {c.thread_id: c.status for c in changes if c.status is not None}
    present = set(state.scene.present_ids) - {state.player_id}  # the player is in every thread
    if state.scene.place_id:
        present.add(state.scene.place_id)
    candidates: list[Thread] = []
    weights: list[float] = []
    for thread in sorted(state.threads.values(), key=lambda t: natural_key(t.id)):
        status = after.get(thread.id, thread.status)
        if status is not ThreadStatus.DORMANT or thread.id in exclude:
            continue
        if state.player_id not in thread.known_by or not fits(thread_themes(thread), allowed):
            continue
        candidates.append(thread)
        weights.append(4.0 if present.intersection(thread.involved_ids) else 1.0)
    chosen: list[str] = []
    while candidates and len(chosen) < limit:
        pick = rng.child("callback", len(chosen)).weighted(candidates, weights)
        index = candidates.index(pick)
        chosen.append(pick.id)
        del candidates[index], weights[index]
    return chosen


def current_thread(
    state: WorldState, changes: list[ThreadChange], event_thread_id: str | None
) -> str | None:
    """S2: the thread the scene is about, for `thread` choices: the event's, else the open thread
    the player knows that was active most recently."""
    if event_thread_id is not None:
        return event_thread_id
    after = {c.thread_id: c for c in changes}
    best: tuple | None = None
    chosen = None
    for thread in state.threads.values():
        change = after.get(thread.id)
        status = change.status if change and change.status else thread.status
        if status is not ThreadStatus.OPEN or state.player_id not in thread.known_by:
            continue
        active = (1 if change and change.active else 0, thread.last_active_turn)
        rank = (active, natural_key(thread.id))
        if best is None or rank > best:
            best, chosen = rank, thread.id
    return chosen
