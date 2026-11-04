"""Discovery without witnesses (W13): a secret deed is secret, not forgotten.

Each secret deed keeps what it left behind (`Deed.traces`): bodies, wounds only a power like the
doer's makes, damage visible from the road, a hidden survivor, records, and how connected the
victims were. The world looks at in-world times set by those traces and rolls with odds they set.
What is found starts rumors that may be wrong: the true culprit, nobody known, an accident, or a
rival faction (which can start a war). A body left where it fell is a trace when anyone is near
enough to come across it, so a hunted beast's pack finds its dead. A hermit with no ties who
leaves no trace can vanish without anyone noticing.

Done in stopped time, a body or a blast shows nobody near it (W10a). Where the world knows the
doer can stop time, though, death with nobody near is that power's signature, and it points at
them as a wound only their power makes would.
"""

import math

from engine.resolve.powers.time_stop import stops_time
from engine.state.records import Deed, PendingEvent, Trace, TraceKind, Visibility
from engine.state.world import WorldState
from engine.world.aftermath import on_attributed
from engine.world.answers import Answer, law_at, open_answer, schedule_answer
from engine.world.geography import characters_at, region_of
from engine.world.knowledge import COMRADE, faction_learns, region_learns, ties_of
from engine.world.norms import Nature, deed_nature, is_crime
from engine.world.rumors import blame, names_actor, start_rumor
from engine.world.scheduling import Kind, World, by_id, pending, schedule
from engine.world.telling import account, cap, found, listing, where
from engine.world.tuning import (
    BODY_NEARBY_STRENGTH,
    CROWD_DELAY_S,
    DISCOVERY_ATTEMPTS,
    DISCOVERY_FADE,
    DISCOVERY_GAP_FACTOR,
    REGION_KINDS,
    RUMOR_HOPS,
    RUMOR_MIN_SEVERITY,
    TIES_STRENGTH_MAX,
    TIES_STRENGTH_PER_TIE,
    TRACE_ATTRIBUTION,
    TRACE_DELAY_S,
)

# Traces anyone nearby notices at once when people are around.
_PLAIN_SIGHT = (TraceKind.BODY, TraceKind.NOISE, TraceKind.DAMAGE)


def hops(severity: int) -> int:
    """How far word of a find travels: a trifle stays with those who found it (W2)."""
    return RUMOR_HOPS[severity] if severity >= RUMOR_MIN_SEVERITY else 0


def ties_trace(state: WorldState, deed: Deed) -> Trace | None:
    """W13: how connected the victims were, worked out from the state: family, friends and
    comrades who will miss them, or a beast's pack (G24). None for a hermit with no ties."""
    if deed_nature(state, deed) not in (Nature.HARM, Nature.HUNT):
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


def body_trace(state: WorldState, deed: Deed) -> Trace | None:
    """W13, G24: the dead left where they fell, when anyone is near enough to come across them:
    anyone at the place finds them within moments, anyone close by (inside it, or in the spot
    it is part of, short of a whole region) in time. None if a trace already tells of a body,
    or nobody is near: a hermit's body in a cave nobody visits lies unfound."""
    if any(t.kind is TraceKind.BODY for t in deed.traces):
        return None
    place = state.places.get(deed.place_id) if deed.place_id else None
    dead = [v for v in deed.victim_ids if v in state.characters and not state.characters[v].alive]
    if place is None or not dead:
        return None

    def anyone(area: str | None, *, within: bool) -> bool:
        return any(c.id != deed.actor_id for c in characters_at(state, area, within=within))

    area = place.parent_id
    if area in state.places and state.places[area].kind.strip().casefold() in REGION_KINDS:
        area = None
    if anyone(place.id, within=False):
        strength = 100
    elif anyone(place.id, within=True) or anyone(area, within=True):
        strength = BODY_NEARBY_STRENGTH
    else:
        return None
    names = [state.characters[v].name for v in dead]
    verb = "lie" if len(names) > 1 else "lies"
    return Trace(
        kind=TraceKind.BODY,
        text=f"{cap(listing(names))} {verb} dead{where(state, place.id)}.",
        strength=strength,
    )


def find_odds(traces: list[Trace], attempt: int) -> float:
    """The chance a look finds something: any trace can give it away, and each later look finds
    less as the traces fade."""
    missed = math.prod(1 - t.strength / 100 for t in traces)
    return (1 - missed) * DISCOVERY_FADE**attempt


def attribution_odds(state: WorldState, deed: Deed, attempt: int) -> float:
    """Once found, the chance the traces point at the doer. Done in stopped time, a body, a
    noise or a ruin shows nobody near it, so only traces such as a wound only the doer's power
    makes can point at them (W10a), unless the world knows the doer stops time: then death or
    ruin with nobody near is that power's signature."""
    stopped = deed.in_stopped_time
    pointing = [t for t in deed.traces if not (stopped and t.kind in _PLAIN_SIGHT)]
    best = max((TRACE_ATTRIBUTION[t.kind.value] for t in pointing), default=0.0)
    if stopped and known_time_stopper(state, deed) and len(pointing) < len(deed.traces):
        best = max(best, TRACE_ATTRIBUTION[TraceKind.WOUND.value])
    return best * DISCOVERY_FADE**attempt


def known_time_stopper(state: WorldState, deed: Deed) -> bool:
    """Whether the world could know the doer stops time: the power isn't secret, or another deed
    they did in stopped time has already been laid at their door (W10a, G20)."""
    actor = state.characters.get(deed.actor_id)
    if actor is None or not any(stops_time(p) for p in actor.sheet.powers):
        return False
    if any(stops_time(p) and not p.secret for p in actor.sheet.powers):
        return True
    return any(
        other.id != deed.id
        and other.actor_id == deed.actor_id
        and other.in_stopped_time
        and attributed(state, other)
        for other in state.deeds.values()
    )


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
        title=f"What happened{where(w.state, deed.place_id)} may come to light",
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
        if stream.chance(attribution_odds(state, deed, attempt)):
            name_the_doer(w, deed)
            return
        _unexplained(w, deed, stream)
        schedule_look(w, deed, attempt=attempt + 1)
        return
    if stream.chance(attribution_odds(state, deed, attempt)):
        name_the_doer(w, deed)
    else:
        schedule_look(w, deed, attempt=attempt + 1)


def name_the_doer(w: World, deed: Deed) -> None:
    """The truth comes out: a rumor naming the doer starts where it happened, among the people
    and the faction there, and in the region (W3, W13)."""
    state = w.state
    rumor = start_rumor(
        w,
        text=account(state, deed),
        is_true=True,
        place_id=deed.place_id,
        hops=hops(deed.severity),
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
    what = found(state, deed)
    suspects = _suspects(state, deed)
    choices = ["unknown", "accident"] + (["rival"] if suspects else [])
    pick = stream.choice(choices)
    if pick == "rival":
        blamed = state.factions[suspects[0]]
        text = f"{what}. {cap(blamed.name)} did it, people say."
        is_true, about = False, [blamed.id, *deed.victim_ids]
    elif pick == "accident":
        text = f"{what}: an accident, people say."
        is_true, about = False, list(deed.victim_ids)
    else:
        text = f"{what}, and nobody knows who did it."
        is_true, about = True, list(deed.victim_ids)
    rumor = start_rumor(
        w,
        text=text,
        is_true=is_true,
        place_id=deed.place_id,
        hops=hops(deed.severity),
        deed=deed,
        about_ids=about,
        accuracy=70,
        heard_by=[c.id for c in characters_at(state, deed.place_id) if c.id != deed.actor_id],
    )
    if not is_true:
        blame(w, rumor, deed, deed.place_id)
    if is_crime(state, deed):
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
