"""E2, W10, W16: what came due this turn and has to be in the scene.

Pending events fire wherever time passes: at the start of the turn (`catch_up`) and during the
player's steps (`play_out`). Three kinds reach the director:

- **The world's events that need the player** (guards at the door, a summons arriving), applied
  this turn by the living world. The scene in which they arrive must include them (E2).
- **`director.event`**: an event the director rolled inside a long stretch of time, such as month
  four of a year's farming (E7). It needs the player if it needs a decision, so it stopped the
  stretch at its time.
- **`director.plays_out`**: an event nobody took up, playing out with its consequence instead of
  repeating (W16).

The living world's `apply_event` only marks `director.*` events applied, so the director reads
them back here: applied this turn, or still pending but due, when nothing applied them.
"""

from dataclasses import dataclass
from typing import Any

from engine.context import TurnContext
from engine.contracts.direction import EventKind, EventSource, PlannedEvent, Theme
from engine.director.sources import Pick
from engine.state.records import EventStatus, PendingEvent, ThreadKind
from engine.state.world import EventSize, WorldState, natural_key

DIRECTOR_PREFIX = "director."
MONTAGE_KIND = "director.event"
PLAYS_OUT_KIND = "director.plays_out"


def is_director_event(event: PendingEvent) -> bool:
    return event.kind.startswith(DIRECTOR_PREFIX)


def pick_payload(pick: Pick) -> dict[str, Any]:
    return {
        "event": pick.event.model_dump(mode="json"),
        "key": pick.key,
        "window_s": pick.window_s,
        "lingers": pick.lingers,
        "lead": pick.lead,
        "thread_kind": pick.thread_kind.value if pick.thread_kind else None,
        "thread_title": pick.thread_title,
        "involved_ids": list(pick.involved_ids),
    }


def pick_from_payload(payload: dict[str, Any]) -> Pick:
    kind = payload.get("thread_kind")
    return Pick(
        event=PlannedEvent.model_validate(payload["event"]),
        key=str(payload.get("key", "")),
        window_s=int(payload.get("window_s", 0)),
        lingers=bool(payload.get("lingers", False)),
        lead=bool(payload.get("lead", False)),
        thread_kind=ThreadKind(kind) if kind else None,
        thread_title=str(payload.get("thread_title", "")),
        involved_ids=[str(i) for i in payload.get("involved_ids", [])],
    )


def _enum(enum, value, default):
    try:
        return enum(value)
    except ValueError:
        return default


def world_event(event: PendingEvent) -> PlannedEvent:
    """A living-world event that needs the player, as the scene's event. The living world may put
    `{"size", "kind", "brief", "themes"}` under `payload["event"]`; otherwise it is a personal
    arrival told from its title."""
    info = event.payload.get("event")
    info = info if isinstance(info, dict) else {}
    title = event.title or "Something comes due"
    return PlannedEvent(
        size=_enum(EventSize, info.get("size"), EventSize.PERSONAL),
        kind=_enum(EventKind, info.get("kind"), EventKind.ARRIVAL),
        source=EventSource.DUE,
        source_id=event.id,
        title=title,
        brief=str(info.get("brief") or title),
        themes=[t for t in (_enum(Theme, v, None) for v in info.get("themes", [])) if t],
        cast_ids=list(event.subject_ids),
        place_id=event.place_id,
    )


def playout_event(event: PendingEvent) -> PlannedEvent:
    """An ignored event's consequence, as the scene's event or a happening. It needs no
    decision: the player already made one by leaving it (W16)."""
    original = PlannedEvent.model_validate(event.payload["event"])
    return original.model_copy(
        update={
            "source": EventSource.DUE,
            "source_id": event.id,
            "brief": original.consequence or f"{original.title}: it happens without the character.",
            "needs_decision": False,
            "plays_out_s": None,
        }
    )


@dataclass(frozen=True)
class CameDue:
    """Everything that came due for the scene, sorted in time order.

    - `world`: the living world's events that need the player.
    - `rolled`: the director's own events from a long stretch, with their picks.
    - `plays_out`: ignored events whose time came.
    - `pending_ids`: the director's events among them that nothing applied yet.
    """

    world: tuple[PendingEvent, ...] = ()
    rolled: tuple[tuple[PendingEvent, Pick], ...] = ()
    plays_out: tuple[PendingEvent, ...] = ()
    pending_ids: tuple[str, ...] = ()


def came_due(state: WorldState, ctx: TurnContext) -> CameDue:
    timeline = state.timeline_id
    found: list[PendingEvent] = []
    for event in state.pending_events.values():
        if event.timeline_id != timeline:
            continue
        mine = is_director_event(event)
        if event.status is EventStatus.APPLIED and event.applied_turn == ctx.turn:
            if mine or event.needs_player:
                found.append(event)
        elif mine and event.status is EventStatus.PENDING and event.due_s <= state.world_s:
            found.append(event)
    found.sort(key=lambda e: (e.due_s, e.created_turn, e.created_s, natural_key(e.id)))
    world = tuple(e for e in found if not is_director_event(e))
    rolled = tuple(
        (e, pick_from_payload(e.payload["pick"]))
        for e in found
        if e.kind == MONTAGE_KIND and isinstance(e.payload.get("pick"), dict)
    )
    plays_out = tuple(
        e for e in found if e.kind == PLAYS_OUT_KIND and isinstance(e.payload.get("event"), dict)
    )
    pending_ids = tuple(
        e.id for e in found if is_director_event(e) and e.status is EventStatus.PENDING
    )
    return CameDue(world=world, rolled=rolled, plays_out=plays_out, pending_ids=pending_ids)


def open_playouts(state: WorldState) -> list[PendingEvent]:
    """Events still waiting for the player: their play-outs haven't come due."""
    return sorted(
        (
            e
            for e in state.pending_events.values()
            if e.kind == PLAYS_OUT_KIND
            and e.status is EventStatus.PENDING
            and e.timeline_id == state.timeline_id
            and e.due_s > state.world_s
        ),
        key=lambda e: (e.due_s, natural_key(e.id)),
    )


def unreached_rolls(state: WorldState) -> list[PendingEvent]:
    """Events rolled for a time skip that the clock never reached, because something earlier cut
    the stretch short. They belong to time that was never lived, so they never happen (E7)."""
    return sorted(
        (
            e
            for e in state.pending_events.values()
            if e.kind == MONTAGE_KIND
            and e.status is EventStatus.PENDING
            and e.timeline_id == state.timeline_id
            and e.due_s > state.world_s
        ),
        key=lambda e: (e.due_s, natural_key(e.id)),
    )
