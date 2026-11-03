"""Discovery without witnesses (W13): a secret deed is secret, not forgotten.

Each secret deed keeps what it left behind (`Deed.traces`): bodies, wounds only a power like the
doer's makes, damage visible from the road, a hidden survivor, records, and how connected the
victims were. The world looks at in-world times set by those traces and rolls with odds they set.
What is found starts rumors that may be wrong: the true culprit, nobody known, an accident, or a
rival faction (which can start a war). A hermit with no ties who leaves no trace can vanish without
anyone noticing.
"""

import math

from engine.state.records import Deed, PendingEvent, Trace, TraceKind, Visibility
from engine.state.world import WorldState
from engine.world.aftermath import on_attributed
from engine.world.answers import Answer, law_at, open_answer, schedule_answer
from engine.world.geography import characters_at, region_of
from engine.world.knowledge import COMRADE, faction_learns, region_learns, ties_of
from engine.world.norms import Nature, deed_nature, is_crime, killed
from engine.world.rumors import blame, names_actor, start_rumor
from engine.world.scheduling import Kind, World, by_id, pending, schedule
from engine.world.tuning import (
    CROWD_DELAY_S,
    DISCOVERY_ATTEMPTS,
    DISCOVERY_FADE,
    DISCOVERY_GAP_FACTOR,
    RUMOR_HOPS,
    TIES_STRENGTH_MAX,
    TIES_STRENGTH_PER_TIE,
    TRACE_ATTRIBUTION,
    TRACE_DELAY_S,
)

# Traces anyone nearby notices at once when people are around.
_PLAIN_SIGHT = (TraceKind.BODY, TraceKind.NOISE, TraceKind.DAMAGE)


def ties_trace(state: WorldState, deed: Deed) -> Trace | None:
    """W13: how connected the victims were, worked out from the state: family, friends and
    comrades who will miss them. None for a hermit with no ties."""
    if deed_nature(deed) is not Nature.HARM:
        return None
    count = sum(
        len([t for t in ties_of(state, v, least=COMRADE) if t[0] != deed.actor_id])
        for v in deed.victim_ids
    )
    if count == 0:
        return None
    return Trace(
        kind=TraceKind.TIES,
        text="People who will miss the victims.",
        strength=min(TIES_STRENGTH_MAX, TIES_STRENGTH_PER_TIE * count),
    )


def find_odds(traces: list[Trace], attempt: int) -> float:
    """The chance a look finds something: any trace can give it away, and each later look finds
    less as the traces fade."""
    missed = math.prod(1 - t.strength / 100 for t in traces)
    return (1 - missed) * DISCOVERY_FADE**attempt


def attribution_odds(traces: list[Trace], attempt: int, *, stopped: bool = False) -> float:
    """Once found, the chance the traces point at the doer. Done in stopped time, a body, a
    noise or a ruin shows nobody near it, so only traces such as a wound only the doer's power
    makes can point at them (W10a)."""
    pointing = [t for t in traces if not (stopped and t.kind in _PLAIN_SIGHT)]
    best = max((TRACE_ATTRIBUTION[t.kind.value] for t in pointing), default=0.0)
    return best * DISCOVERY_FADE**attempt


def attributed(state: WorldState, deed: Deed) -> bool:
    """Whether anyone but the doer knows who did it: a witness, or a true rumor naming them."""
    if any(k != deed.actor_id for k in deed.known_by):
        return True
    return any(names_actor(r, deed) for r in state.rumors.values() if r.deed_id == deed.id)


def schedule_look(w: World, deed: Deed, *, attempt: int = 0, crowd: bool = False) -> None:
    """Schedule the world's next look at a secret deed's traces, at a time the traces set."""
    if deed.visibility is not Visibility.SECRET or not deed.traces:
        return
    if attempt >= DISCOVERY_ATTEMPTS or pending(w.state, Kind.DISCOVERY, deed_id=deed.id):
        return
    delays = []
    for trace in deed.traces:
        span = (
            CROWD_DELAY_S
            if crowd and trace.kind in _PLAIN_SIGHT
            else TRACE_DELAY_S[trace.kind.value]
        )
        delays.append(w.between(span, "look", deed.id, attempt, trace.kind.value))
    delay = min(delays) * DISCOVERY_GAP_FACTOR**attempt
    schedule(
        w,
        Kind.DISCOVERY,
        w.at_s + delay,
        title=f"Someone may notice: {deed.text}",
        subject_ids=[*deed.victim_ids, *deed.target_ids],
        place_id=deed.place_id,
        payload={"deed_id": deed.id, "attempt": attempt},
    )


def on_discovery(w: World, event: PendingEvent) -> None:
    """A look at a secret deed's traces: something may be found, and the culprit may be named."""
    state = w.state
    deed = state.deeds.get(str(event.payload.get("deed_id")))
    if deed is None or attributed(state, deed):
        return
    attempt = int(event.payload.get("attempt", 0))
    stream = w.roll("discovery", deed.id, attempt)
    if not deed.discovered:
        if not stream.chance(find_odds(deed.traces, attempt)):
            schedule_look(w, deed, attempt=attempt + 1)
            return
        deed.discovered = True
        if stream.chance(attribution_odds(deed.traces, attempt, stopped=deed.in_stopped_time)):
            name_the_doer(w, deed)
            return
        _unexplained(w, deed, stream)
        schedule_look(w, deed, attempt=attempt + 1)
        return
    if stream.chance(attribution_odds(deed.traces, attempt, stopped=deed.in_stopped_time)):
        name_the_doer(w, deed)
    else:
        schedule_look(w, deed, attempt=attempt + 1)


def name_the_doer(w: World, deed: Deed) -> None:
    """The truth comes out: a rumor naming the doer starts where it happened, among the people
    and the faction there, and in the region (W3, W13)."""
    state = w.state
    actor = state.characters.get(deed.actor_id)
    who = actor.name if actor else "someone"
    rumor = start_rumor(
        w,
        text=f"{who} did it: {deed.text}",
        is_true=True,
        place_id=deed.place_id,
        hops=RUMOR_HOPS[deed.severity],
        deed=deed,
        about_ids=[deed.actor_id, *deed.victim_ids],
        accuracy=80,
        heard_by=[c.id for c in characters_at(state, deed.place_id) if c.id != deed.actor_id],
    )
    weight = rumor.accuracy / 100
    place = state.places.get(deed.place_id) if deed.place_id else None
    if place is not None and place.controller_id is not None:
        faction_learns(w, place.controller_id, deed, weight=weight)
    region_learns(w, region_of(state, deed.place_id), deed, weight=weight)
    on_attributed(w, deed)


def _unexplained(w: World, deed: Deed, stream) -> None:
    """Found, but not who did it: the rumor says nobody knows, blames an accident, or blames a
    faction the victims' side already distrusts, which may be wrong (W13). Those who keep the
    law look into a crime."""
    state = w.state
    victims = [state.characters[v] for v in deed.victim_ids if v in state.characters]
    names = ", ".join(v.name for v in victims) or "someone"
    what = "was found dead" if killed(state, deed.victim_ids) else "came to harm"
    suspects = _suspects(state, deed)
    choices = ["unknown", "accident"] + (["rival"] if suspects else [])
    pick = stream.choice(choices)
    if pick == "rival":
        blamed = state.factions[suspects[0]]
        text = f"{blamed.name} did it, people say: {names} {what}."
        is_true, about = False, [blamed.id, *deed.victim_ids]
    elif pick == "accident":
        text = f"{names} {what}; an accident, people say."
        is_true, about = False, list(deed.victim_ids)
    else:
        text = f"{names} {what}, and nobody knows who did it."
        is_true, about = True, list(deed.victim_ids)
    rumor = start_rumor(
        w,
        text=text,
        is_true=is_true,
        place_id=deed.place_id,
        hops=RUMOR_HOPS[deed.severity],
        deed=deed,
        about_ids=about,
        accuracy=70,
        heard_by=[c.id for c in characters_at(state, deed.place_id) if c.id != deed.actor_id],
    )
    if not is_true:
        blame(w, rumor, deed, deed.place_id)
    if is_crime(deed):
        _investigate(w, deed)


def _suspects(state: WorldState, deed: Deed) -> list[str]:
    """Factions the victims' factions already distrust (relations below zero), worst first,
    leaving out the doer's own, which would make the rumor nearly true."""
    actor = state.characters.get(deed.actor_id)
    actor_factions = {m.faction_id for m in actor.memberships} if actor else set()
    stances: dict[str, int] = {}
    for victim_id in deed.victim_ids:
        victim = state.characters.get(victim_id)
        if victim is None:
            continue
        for membership in victim.memberships:
            faction = state.factions.get(membership.faction_id)
            if faction is None:
                continue
            for other, stance in faction.relations.items():
                if stance < 0 and other in state.factions and other not in actor_factions:
                    stances[other] = min(stance, stances.get(other, 0))
    return [fid for fid, _ in sorted(stances.items(), key=lambda item: (item[1], item[0]))]


def _investigate(w: World, deed: Deed) -> None:
    """W11: those who keep the law look into a crime nobody is named for. Their arrival at the
    scene is another chance to name the doer."""
    state = w.state
    for faction in by_id(state.factions.values()):
        law = law_at(state, faction.id, deed.place_id)
        if law is None or open_answer(state, target_id=deed.actor_id, faction_id=faction.id):
            continue
        schedule_answer(
            w,
            Answer.INVESTIGATE,
            target_id=deed.actor_id,
            destination_id=deed.place_id,
            tier=0,
            deed=deed,
            faction=faction,
            law=law,
        )
