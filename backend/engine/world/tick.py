"""The deterministic world tick (W6, P0): the world moves on in in-world time with no model call.

The tick is a pending event that runs at most once a day of in-world time, and at most
`MAX_TICKS_PER_PASSAGE` times in one stretch however long, so a year's time skip costs a fixed
number of steps (E7, K8). Each tick covers the in-world time since the last one. It looks at
factions destroyed in that window for a later revival (W15a), keeps clocks moving (E2), keeps the
active cast within its caps (W15), and lets each active faction and key NPC make a move of their
own: mend or sour a relation, consolidate what they hold, recover, travel, heal, or pursue their
goal, which advances a clock of theirs that moves only by effort. Each move is recorded as a fact
with an agenda origin, for the director to draw on (W16) and for the model part of the tick (W6,
P1) to tell as what they actually did. Dormant characters and factions don't move.
"""

import math

from engine.state.cast import Activity, Character, Faction, FactionStatus, Prominence
from engine.state.records import (
    ClockStatus,
    Fact,
    FactKind,
    Origin,
    OriginKind,
    PendingEvent,
    StatusChange,
)
from engine.state.sheet import Health
from engine.state.world import natural_key
from engine.world.answers import members
from engine.world.cast import enforce_caps, schedule_revivals
from engine.world.clocks import advance, ensure_clock_events
from engine.world.geography import news_neighbours
from engine.world.knowledge import shift_attitude
from engine.world.scheduling import Kind, World, by_id, pending, schedule
from engine.world.tuning import (
    AGENDA_FACTS_KEPT,
    FACTION_MOVE_MEAN_S,
    MAX_TICKS_PER_PASSAGE,
    NPC_MOVE_MEAN_S,
    TICK_INTERVAL_S,
)

_HEALING = [Health.DYING, Health.BADLY_WOUNDED, Health.WOUNDED, Health.HURT, Health.UNHURT]


def plan_ticks(w: World, until_s: int) -> None:
    """Make sure the tick is pending, spaced so the stretch up to `until_s` holds at most
    `MAX_TICKS_PER_PASSAGE` of them."""
    ticks = pending(w.state, Kind.TICK)
    if ticks:
        tick = ticks[0]
        last_s = int(tick.payload.get("last_s", w.at_s))
    else:
        last_s = w.at_s
        tick = schedule(
            w,
            Kind.TICK,
            w.at_s + TICK_INTERVAL_S,
            title="The world moves on",
            payload={"last_s": last_s, "stride_s": TICK_INTERVAL_S},
        )
    span = max(0, until_s - last_s)
    stride = max(TICK_INTERVAL_S, math.ceil(span / MAX_TICKS_PER_PASSAGE))
    tick.payload["stride_s"] = stride
    tick.due_s = last_s + stride


def on_tick(w: World, event: PendingEvent) -> None:
    state = w.state
    last_s = int(event.payload.get("last_s", event.due_s))
    stride = int(event.payload.get("stride_s", TICK_INTERVAL_S))
    span = max(0, event.due_s - last_s)
    schedule_revivals(w, last_s, event.due_s)
    ensure_clock_events(w)
    enforce_caps(state)
    for faction in by_id(state.factions.values()):
        if faction.activity is Activity.ACTIVE and faction.status is not FactionStatus.DESTROYED:
            if w.roll("moves", faction.id).chance(_odds(span, FACTION_MOVE_MEAN_S)):
                _faction_move(w, faction)
    for npc in by_id(state.npcs()):
        if npc.alive and npc.prominence is Prominence.KEY and npc.activity is Activity.ACTIVE:
            if w.roll("moves", npc.id).chance(_odds(span, NPC_MOVE_MEAN_S)):
                _npc_move(w, npc)
    _prune_agenda_facts(w)
    schedule(
        w,
        Kind.TICK,
        event.due_s + stride,
        title="The world moves on",
        payload={"last_s": event.due_s, "stride_s": stride},
    )


def _odds(span_s: int, mean_s: int) -> float:
    """The chance of at least one move in a span, for moves that come every `mean_s` on
    average."""
    return 1 - math.exp(-span_s / mean_s)


def _record(w: World, subject_id: str, text: str, known_by: list[str], *others: str) -> None:
    state = w.state
    fact = Fact(
        id=state.new_id("fact"),
        text=text,
        kind=FactKind.OBSERVATION,
        importance=1,
        subject_ids=[subject_id, *others],
        known_by=list(dict.fromkeys(known_by)),
        turn=w.ctx.turn,
        world_s=w.at_s,
        timeline_id=state.timeline_id,
        origin=Origin(kind=OriginKind.AGENDA, ref_id=subject_id),
    )
    state.facts[fact.id] = fact


def _own_clock(w: World, owner_id: str):
    """A running clock of theirs that moves only by effort, not by time."""
    clocks = [
        c
        for c in by_id(w.state.clocks.values())
        if c.owner_id == owner_id
        and c.status is ClockStatus.RUNNING
        and c.interval_s is None
        and c.remaining > 0
    ]
    return clocks[0] if clocks else None


def _settled_before(w: World, faction: Faction) -> bool:
    """Whether its last change of status came in an earlier turn. A faction revived this turn
    stays rebuilding until the next, so each turn's change from destroyed is a revival (C1)."""
    history = faction.status_history
    return not history or history[-1].turn < w.ctx.turn


def _faction_move(w: World, faction: Faction) -> None:
    state = w.state
    insiders = [c.id for c in members(state, faction.id)]
    moves = []
    if faction.status is FactionStatus.WEAKENED or (
        faction.status is FactionStatus.REBUILDING and _settled_before(w, faction)
    ):
        moves.append("recover")
    others = [
        f
        for f in by_id(state.factions.values())
        if f.id != faction.id and f.status is not FactionStatus.DESTROYED
    ]
    if others:
        moves.append("relations")
    held = [p for p in by_id(state.places.values()) if p.controller_id == faction.id]
    if any(p.stability < 100 for p in held):
        moves.append("consolidate")
    moves.append("pursue")
    stream = w.roll("move", faction.id)
    move = stream.choice(moves)
    if move == "recover":
        before = faction.status
        faction.status = (
            FactionStatus.WEAKENED if before is FactionStatus.REBUILDING else FactionStatus.INTACT
        )
        faction.status_history.append(
            StatusChange(
                status=faction.status.value,
                from_status=before.value,
                turn=w.ctx.turn,
                world_s=w.at_s,
                timeline_id=state.timeline_id,
                note="Recovered its strength.",
            )
        )
        _record(w, faction.id, f"{faction.name} recovers its strength.", insiders)
    elif move == "relations":
        other = stream.choice(others)
        stance = faction.relations.get(other.id, 0)
        direction = (1 if stance >= 0 else -1) if stream.chance(0.6) else stream.choice([1, -1])
        change = direction * stream.randint(5, 15)
        faction.relations[other.id] = max(-100, min(100, stance + change))
        verb = "draws closer to" if change > 0 else "grows hostile to"
        _record(w, faction.id, f"{faction.name} {verb} {other.name}.", insiders, other.id)
    elif move == "consolidate":
        place = stream.choice([p for p in held if p.stability < 100])
        place.stability = min(100, place.stability + stream.randint(5, 10))
        _record(w, faction.id, f"{faction.name} tightens its hold on {place.name}.", insiders)
    else:
        clock = _own_clock(w, faction.id)
        if clock is not None:
            advance(w, clock)
        goal = faction.goal or "its own ends"
        _record(w, faction.id, f"{faction.name} works toward {goal}", insiders)


def _npc_move(w: World, npc: Character) -> None:
    state = w.state
    moves = []
    if npc.sheet.condition.health is not Health.UNHURT:
        moves.append("heal")
    if npc.id not in state.scene.present_ids and npc.location_id in state.places:
        if news_neighbours(state, npc.location_id):
            moves.append("travel")
    peers = [
        c
        for c in by_id(state.npcs())
        if c.id != npc.id and c.alive and c.prominence is Prominence.KEY
    ]
    if peers:
        moves.append("bond")
    moves.append("pursue")
    stream = w.roll("move", npc.id)
    move = stream.choice(moves)
    if move == "heal":
        health = npc.sheet.condition.health
        npc.sheet.condition.health = _HEALING[_HEALING.index(health) + 1]
        _record(w, npc.id, f"{npc.name}'s wounds mend.", [npc.id])
    elif move == "travel":
        place_id, _ = stream.choice(news_neighbours(state, npc.location_id))
        npc.location_id = place_id
        _record(w, npc.id, f"{npc.name} goes to {state.places[place_id].name}.", [npc.id])
    elif move == "bond":
        other = stream.choice(peers)
        change = stream.choice([1, -1]) * stream.randint(5, 15)
        shift_attitude(npc, other.id, affinity=change)
        verb = "warms to" if change > 0 else "cools toward"
        _record(w, npc.id, f"{npc.name} {verb} {other.name}.", [npc.id], other.id)
    else:
        clock = _own_clock(w, npc.id)
        if clock is not None:
            advance(w, clock)
        goal = npc.agenda.goal if npc.agenda else "their own affairs"
        _record(w, npc.id, f"{npc.name} works toward {goal}", [npc.id])


def _prune_agenda_facts(w: World) -> None:
    """Keep only the latest few agenda moves per subject, so a long story's state stays flat
    (K8). Facts aren't the kind of record C1 keeps forever; deeds, people and places are."""
    by_subject: dict[str, list[Fact]] = {}
    for fact in w.state.facts.values():
        if (
            fact.origin is not None
            and fact.origin.kind is OriginKind.AGENDA
            and fact.importance == 1
        ):
            by_subject.setdefault(fact.origin.ref_id or "", []).append(fact)
    for facts in by_subject.values():
        facts.sort(key=lambda f: (f.world_s, natural_key(f.id)))
        for old in facts[:-AGENDA_FACTS_KEPT]:
            del w.state.facts[old.id]
