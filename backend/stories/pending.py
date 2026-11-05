"""Pending events between the world state and the `stories_pendingevent` table (B12, W10).

The engine keeps a story's pending events in `WorldState.pending_events`, and the table keeps
them for staff and for anything off-screen that schedules one without touching the story row. A
turn reads the table's rows on the story's timeline into the state before it plays (`load`), and
writes back each event the turn scheduled, applied or cancelled (`write_back`), in the
transaction that saves the turn.

A row's id is derived from the story and the engine's event id, so writing an event back twice
updates one row. `payload` holds the engine's `PendingEvent` as JSON; the columns hold what staff
see and may change, and they win over the payload when a row is read. A row written outside a
turn needs only its columns, with the event's own payload under `payload.payload`; its event
takes the row's id as its own. Every read and write is scoped to the story, so no event of one
story can touch another's rows.
"""

from __future__ import annotations

import logging
import uuid

from django.db.models import Q
from pydantic import ValidationError

from engine.state.records import EventStatus
from engine.state.records import PendingEvent as Event
from engine.state.world import WorldState
from stories.models import PendingEvent as Row
from stories.models import PendingEventStatus, Story

logger = logging.getLogger("stories")

# Fixed forever: row ids are derived from it.
_NAMESPACE = uuid.UUID("8f0c7d0e-5b1a-4a59-9a8e-3f3c0d6c2b7e")
_COLUMNS = ("timeline_id", "due_world_s", "kind", "payload", "status", "created_turn")


def row_id(story_id: uuid.UUID | str, event_id: str) -> uuid.UUID:
    """The row derived from the story and the engine's event `event_id`."""
    return uuid.uuid5(_NAMESPACE, f"{story_id}:{event_id}")


def _own_row(event_id: str) -> uuid.UUID | None:
    """The row an event read from a row written outside a turn came from: its id is the row's."""
    try:
        return uuid.UUID(event_id)
    except ValueError:
        return None


def _row_ids(story: Story, event_ids) -> dict[str, uuid.UUID]:
    """Each event's row: the one it came from, if that is this story's, else its derived one."""
    ids = {event_id: row_id(story.pk, event_id) for event_id in event_ids}
    own = {event_id: pk for event_id in ids if (pk := _own_row(event_id)) is not None}
    if own:
        mine = set(
            Row.objects.filter(story=story, pk__in=list(own.values())).values_list("pk", flat=True)
        )
        ids.update({event_id: pk for event_id, pk in own.items() if pk in mine})
    return ids


def load(story: Story, state: WorldState) -> WorldState:
    """`state` with the story's pending rows on its timeline added, and with each row's columns
    (status, due time, kind) over the matching event's, so staff changes count."""
    waiting: dict[uuid.UUID, str] = {}
    for event in state.pending_events.values():
        if event.status is EventStatus.PENDING:
            waiting[row_id(story.pk, event.id)] = event.id
            if (pk := _own_row(event.id)) is not None:
                waiting[pk] = event.id
    rows = list(
        Row.objects.filter(story=story).filter(
            Q(status=PendingEventStatus.PENDING, timeline_id=state.timeline_id)
            | Q(pk__in=list(waiting))
        )
    )
    if not rows:
        return state
    events = dict(state.pending_events)
    for row in rows:
        event = _event(story, row, waiting.get(row.pk))
        if event is not None:
            events[event.id] = event
    return state.model_copy(update={"pending_events": events})


def write_back(story: Story, before: WorldState, after: WorldState) -> int:
    """Saves the events the turn changed or added, as rows. Call it in the turn's transaction.
    Returns how many rows it wrote."""
    ids = _row_ids(story, list(after.pending_events))
    # An event saved with the state but never as a row, such as one in a new story's state.
    saved = set(
        Row.objects.filter(story=story, pk__in=list(ids.values())).values_list("pk", flat=True)
    )
    changed = [
        event
        for event in after.pending_events.values()
        if before.pending_events.get(event.id) != event or ids[event.id] not in saved
    ]
    rows = [
        Row(
            id=ids[event.id],
            story=story,
            timeline_id=event.timeline_id,
            due_world_s=event.due_s,
            kind=event.kind,
            payload=event.model_dump(mode="json"),
            status=event.status.value,
            created_turn=event.created_turn,
            applied_turn=event.applied_turn,
        )
        for event in changed
    ]
    if rows:
        Row.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["id"],
            update_fields=[*_COLUMNS, "applied_turn"],
        )
    # An event the engine dropped from the state never fires, so its row shouldn't either.
    gone = before.pending_events.keys() - after.pending_events.keys()
    if gone:
        dropped = list(_row_ids(story, gone).values())
        Row.objects.filter(story=story, pk__in=dropped, status=PendingEventStatus.PENDING).update(
            status=PendingEventStatus.CANCELLED
        )
    return len(rows)


def cancel_after(story: Story, turn: int) -> int:
    """C8: cancels every row a turn after `turn` scheduled, as when a rewind takes those turns
    back: the world it went back to never scheduled them, whether or not they had fired. Call it
    in the rewind's transaction, after `write_back`. Returns how many rows it cancelled."""
    return (
        Row.objects.filter(story=story, created_turn__gt=turn)
        .exclude(status=PendingEventStatus.CANCELLED)
        .update(status=PendingEventStatus.CANCELLED)
    )


def _event(story: Story, row: Row, event_id: str | None) -> Event | None:
    data = dict(row.payload) if isinstance(row.payload, dict) else {}
    if event_id is None:
        own = data.get("id")
        # The payload's id names this row only if it maps back to it.
        event_id = own if isinstance(own, str) and row_id(story.pk, own) == row.pk else str(row.pk)
    data.update(
        id=event_id,
        kind=row.kind,
        due_s=row.due_world_s,
        timeline_id=row.timeline_id,
        status=row.status,
        created_turn=row.created_turn,
        applied_turn=row.applied_turn,
    )
    try:
        return Event.model_validate(data)
    except ValidationError:
        # One bad row mustn't stop the story. Ids and kind only, never the payload (T6).
        logger.warning(
            "A pending event row couldn't be read, so it was left out",
            extra={"pending_event": {"id": str(row.pk), "kind": row.kind}},
        )
        return None
