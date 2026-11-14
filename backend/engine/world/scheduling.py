"""Pending events the living world schedules, and the moment its code works in (W10, B12).

Everything the world does later is a pending event with an in-world due time, never a number of
turns: a witness reaching the guard post, a rumor reaching the next town, a faction's answer, a
clock's next step, the world tick. Each event carries its own seed, so a rewound world replays it
the same way (W10a), and it rolls the same however the time around it was split into steps.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from engine.context import TurnContext
from engine.rng import SeededRng
from engine.state.records import EventStatus, Origin, PendingEvent
from engine.state.world import WorldState, natural_key


class Kind(StrEnum):
    """The pending events the living world schedules and applies. Events of other kinds belong
    to whoever scheduled them (such as `director.*`, WS11) and are only marked applied here."""

    REPORT = "world.report"  # a witness reaches a faction with what they saw (W11)
    WORD = "world.word"  # whether a witness is free to talk, so word of a deed gets out (W2)
    ANSWER = "world.answer"  # a faction's answer, or a personal revenge, arrives (W4, W5)
    RUMOR = "world.rumor"  # a rumor reaches a place (W2)
    TIDINGS = "world.tidings"  # word of a death reaches the victim's close ties (W4, W11)
    DISCOVERY = "world.discovery"  # a look for what a secret deed left behind (W13)
    CLOCK_STEP = "world.clock_step"  # a clock moves a step with time (E2)
    CLOCK_END = "clock_end"  # a clock's end, also scheduled by the drafter (E2, S1)
    EMERGENCE = "world.emergence"  # a character or faction born of the world state (W15)
    REVIVAL = "world.revival"  # a destroyed faction may rise again (W15a)
    BIRTH = "world.birth"  # a child is born when it is due, if its carrier lives (N6)
    OLD_AGE = "world.old_age"  # the player character's own: its end is close, or here (N6, W6)
    TICK = "world.tick"  # the deterministic world tick (W6)
    RETURN = "world.return"  # someone the world sent somewhere comes back (W6, W4, W11)


@dataclass
class World:
    """The state being changed in place, the turn, the in-world moment the change happens at and
    a random stream for it. World code never reads the clock or rolls any other way."""

    state: WorldState
    ctx: TurnContext
    at_s: int
    rng: SeededRng

    def roll(self, *labels: object) -> SeededRng:
        """A stream for one decision, keyed by what it is about, never by call order."""
        return self.rng.child(*labels)

    def between(self, span: tuple[int, int], *labels: object) -> int:
        low, high = span
        return low if high <= low else self.roll(*labels).randint(low, high)


def schedule(
    w: World,
    kind: Kind | str,
    due_s: int,
    *,
    title: str,
    subject_ids: list[str] | None = None,
    place_id: str | None = None,
    needs_player: bool = False,
    payload: dict[str, Any] | None = None,
    origin: Origin | None = None,
    overdue: bool = False,
) -> PendingEvent:
    """Schedule an event at an in-world time, never before the moment it is scheduled, unless
    it is `overdue`: something that should already have happened by its own time, such as a
    clock's step the world never caught up on, which then applies first, in its time order."""
    event_id = w.state.new_id("event")
    event = PendingEvent(
        id=event_id,
        kind=str(kind),
        title=title,
        due_s=int(due_s) if overdue else max(int(due_s), w.at_s),
        timeline_id=w.state.timeline_id,
        needs_player=needs_player,
        subject_ids=list(dict.fromkeys(subject_ids or [])),
        place_id=place_id,
        origin=origin,
        payload=dict(payload or {}),
        seed=w.rng.child("schedule", event_id).seed,
        created_turn=w.ctx.turn,
        created_s=w.at_s,
    )
    w.state.pending_events[event_id] = event
    return event


def pending(state: WorldState, kind: Kind | str, **payload: Any) -> list[PendingEvent]:
    """Pending events of a kind on this timeline whose payload holds these values, by id."""
    found = [
        e
        for e in state.pending_events.values()
        if e.kind == str(kind)
        and e.status is EventStatus.PENDING
        and e.timeline_id == state.timeline_id
        and all(e.payload.get(k) == v for k, v in payload.items())
    ]
    return sorted(found, key=lambda e: natural_key(e.id))


def cancel(w: World, event: PendingEvent) -> None:
    stored = w.state.pending_events[event.id]
    stored.status = EventStatus.CANCELLED
    stored.applied_turn = w.ctx.turn
    stored.applied_s = w.at_s


def event_rng(event: PendingEvent, rng: SeededRng) -> SeededRng:
    """The event's own stream: its seed when it has one, else one keyed by its id (A3, W10a)."""
    return SeededRng(event.seed) if event.seed else rng.child("event", event.id)


def by_id(records) -> list:
    """Records in a stable order, never the map's (Postgres JSONB reorders keys)."""
    return sorted(records, key=lambda r: natural_key(r.id))


def over(rate: float, years: float) -> float:
    """The chance of something within a stretch of `years`, from its chance in one year: a
    month brings next to nothing and ten years a great deal, with nothing made to happen
    (W6, W10)."""
    return 1 - (1 - min(1.0, max(0.0, rate))) ** max(0.0, years)
