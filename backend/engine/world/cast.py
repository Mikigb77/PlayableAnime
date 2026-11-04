"""The world's cast: emerging characters and factions, revivals, and the active set (W15, W15a,
K8).

The world creates new characters and factions on its own, each with a recorded origin in the
world state: an avenger for someone killed, a resistance in a conquered place, a successor to a
destroyed faction. Emergence isn't capped; the active cast is. At most `ACTIVE_NPC_CAP` key NPCs
and `ACTIVE_FACTION_CAP` factions are simulated each tick; the least relevant go dormant, kept in
state and advanced only by their clocks, for the director to call back. A destroyed faction can
rise again only if something survived it, and only through a recorded event (C1).
"""

from engine.state.cast import (
    Activity,
    Character,
    Faction,
    FactionStatus,
    Membership,
    Prominence,
)
from engine.state.records import (
    Cause,
    CauseMechanism,
    CauseRef,
    Deed,
    EventStatus,
    Origin,
    OriginKind,
    PendingEvent,
    StatusChange,
)
from engine.state.sheet import Attitude, Connection, ConnectionKind, Grudge
from engine.state.world import WorldState
from engine.world.answers import schedule_revenge
from engine.world.knowledge import in_faction
from engine.world.scheduling import Kind, World, by_id, pending, schedule
from engine.world.telling import account
from engine.world.tuning import (
    ACTIVE_FACTION_CAP,
    ACTIVE_NPC_CAP,
    AVENGER_DELAY_S,
    AVENGER_ODDS,
    RESISTANCE_DELAY_S,
    REVIVAL_DELAY_S,
    SUCCESSOR_ODDS,
)

AVENGER, RESISTANCE = "avenger", "resistance"


# --- The active cast (K8) -----------------------------------------------------------------


def _involved(state: WorldState, record_id: str) -> int:
    """How much the story is about someone right now: in the scene, owed a grudge by or holding
    one against the player, in an open thread, or the subject of something on its way."""
    score = 0
    if record_id in state.scene.present_ids:
        score += 100
    player = state.player
    character = state.characters.get(record_id)
    if character is not None:
        toward = character.sheet.disposition.attitudes.get(state.player_id)
        if toward is not None and toward.grudges:
            score += 30
        if state.player_id in character.met_by:
            score += 10
    if record_id in player.sheet.disposition.attitudes:
        score += 5
    for thread in state.threads.values():
        if not thread.status.closed and record_id in thread.involved_ids:
            score += 20
    for event in state.pending_events.values():
        if event.status is EventStatus.PENDING and record_id in event.subject_ids:
            score += 15
            break
    faction = state.factions.get(record_id)
    if faction is not None:
        score += 10 * faction.threat
    return score


def enforce_caps(state: WorldState) -> None:
    """Keep the most involved key NPCs and factions active, up to the caps, and the rest
    dormant (W15, K8). A dormant one that the story comes back to (in the scene, in an open
    thread, with something on its way) takes its place on stage again. Ties keep whoever is
    already active, then favour what just emerged."""
    npcs = [c for c in state.npcs() if c.alive and c.prominence is Prominence.KEY]
    factions = [f for f in state.factions.values() if f.status is not FactionStatus.DESTROYED]
    for records, cap in ((npcs, ACTIVE_NPC_CAP), (factions, ACTIVE_FACTION_CAP)):
        ranked = sorted(
            by_id(records),
            key=lambda r: (
                _involved(state, r.id),
                r.activity is Activity.ACTIVE,
                _created(r),
            ),
            reverse=True,
        )
        for i, record in enumerate(ranked):
            record.activity = Activity.ACTIVE if i < cap else Activity.DORMANT


def _created(record) -> int:
    origin = getattr(record, "origin", None)
    return 1 if origin is not None and origin.kind is OriginKind.EMERGENCE else 0


# --- Avengers (W4, W15) --------------------------------------------------------------------


def maybe_avenger(w: World, deed: Deed, victim: Character) -> None:
    """Someone killed who mattered, with nobody close left to avenge them, may still have an
    avenger the world hadn't shown yet: kin, a sworn friend, an heir."""
    if pending(w.state, Kind.EMERGENCE, what=AVENGER, deed_id=deed.id, victim_id=victim.id):
        return
    if not w.roll("avenger", deed.id, victim.id).chance(AVENGER_ODDS):
        return
    schedule(
        w,
        Kind.EMERGENCE,
        w.at_s + w.between(AVENGER_DELAY_S, "avenger-delay", deed.id, victim.id),
        title=f"Someone rises to avenge {victim.name}",
        subject_ids=[victim.id, deed.actor_id],
        place_id=deed.place_id,
        payload={"what": AVENGER, "deed_id": deed.id, "victim_id": victim.id},
        origin=Origin(kind=OriginKind.DEED, ref_id=deed.id),
    )


def _emerge_avenger(w: World, event: PendingEvent) -> None:
    state = w.state
    deed = state.deeds.get(str(event.payload.get("deed_id")))
    victim = state.characters.get(str(event.payload.get("victim_id")))
    if deed is None or victim is None:
        return
    target = state.characters.get(deed.actor_id)
    if target is None or not target.alive:
        return
    location = victim.location_id if victim.location_id in state.places else deed.place_id
    avenger = Character(
        id=state.new_id("npc"),
        name=f"{victim.name}'s avenger",
        prominence=Prominence.KEY,
        description=f"Someone close to {victim.name}, sworn to make {target.name} pay.",
        location_id=location if location in state.places else None,
        memberships=[
            Membership(faction_id=m.faction_id, rank="", loyalty=60)
            for m in victim.memberships
            if m.faction_id in state.factions
            and state.factions[m.faction_id].status is not FactionStatus.DESTROYED
        ],
        origin=Origin(
            kind=OriginKind.EMERGENCE,
            ref_id=deed.id,
            text=f"Rose to avenge {victim.name}, killed by {target.name}.",
        ),
    )
    avenger.sheet.resources.connections.append(
        Connection(name=victim.name, kind=ConnectionKind.FAMILY, character_id=victim.id)
    )
    avenger.sheet.disposition.attitudes[target.id] = Attitude(
        affinity=-80,
        trust=-60,
        grudges=[Grudge(reason=account(state, deed), deed_id=deed.id, since_turn=w.ctx.turn)],
    )
    state.characters[avenger.id] = avenger
    schedule_revenge(w, avenger, deed)
    enforce_caps(state)


# --- Resistance after a conquest (W7, W15) ---------------------------------------------------


def maybe_resistance(w: World, deed: Deed, place_id: str) -> None:
    if pending(w.state, Kind.EMERGENCE, what=RESISTANCE, place_id=place_id):
        return
    place = w.state.places[place_id]
    schedule(
        w,
        Kind.EMERGENCE,
        w.at_s + w.between(RESISTANCE_DELAY_S, "resistance-delay", deed.id, place_id),
        title=f"A resistance forms in {place.name}",
        subject_ids=[place_id, deed.actor_id],
        place_id=place_id,
        payload={"what": RESISTANCE, "deed_id": deed.id, "place_id": place_id},
        origin=Origin(kind=OriginKind.DEED, ref_id=deed.id),
    )


def _emerge_resistance(w: World, event: PendingEvent) -> None:
    state = w.state
    deed = state.deeds.get(str(event.payload.get("deed_id")))
    place = state.places.get(str(event.payload.get("place_id")))
    if deed is None or place is None:
        return
    holder = place.controller_id
    if holder is None or not (holder == deed.actor_id or in_faction(state, deed.actor_id, holder)):
        return  # the conquest didn't hold; there is nothing to resist
    resistance = Faction(
        id=state.new_id("faction"),
        name=f"the resistance in {place.name}",
        kind="resistance",
        description=f"People of {place.name} who never accepted the conquest.",
        goal=f"Free {place.name}.",
        origin=Origin(
            kind=OriginKind.EMERGENCE,
            ref_id=deed.id,
            text=f"Formed after {place.name} was conquered.",
        ),
        threat=2 if deed.actor_id == state.player_id else 0,
    )
    if holder in state.factions:
        resistance.relations[holder] = -80
    if deed.actor_id == state.player_id:
        resistance.player_reputation.esteem = -40
        resistance.player_reputation.fear = 20
    state.factions[resistance.id] = resistance
    enforce_caps(state)


def on_emergence(w: World, event: PendingEvent) -> None:
    what = event.payload.get("what")
    if what == AVENGER:
        _emerge_avenger(w, event)
    elif what == RESISTANCE:
        _emerge_resistance(w, event)


# --- Revivals (W15a) ------------------------------------------------------------------------


def survivors(state: WorldState, faction: Faction) -> list[str]:
    """What could carry a destroyed faction on: recorded survivors, or living members."""
    return list(faction.survivors) or [
        c.id for c in by_id(state.characters.values()) if c.alive and c.member_of(faction.id)
    ]


def schedule_revivals(w: World, since_s: int, until_s: int) -> None:
    """Every faction destroyed in [since_s, until_s) gets one look, later, at whether it rises
    again. Each destruction falls in exactly one tick's window, so it is looked at once."""
    for faction in by_id(w.state.factions.values()):
        if faction.status is not FactionStatus.DESTROYED:
            continue
        destroyed = [
            h
            for h in faction.status_history
            if h.status == FactionStatus.DESTROYED.value
            and h.timeline_id == w.state.timeline_id
            and since_s <= h.world_s < until_s
        ]
        if not destroyed or pending(w.state, Kind.REVIVAL, faction_id=faction.id):
            continue
        schedule(
            w,
            Kind.REVIVAL,
            destroyed[-1].world_s + w.between(REVIVAL_DELAY_S, "revival", faction.id),
            title=f"What is left of {faction.name} may rise again",
            subject_ids=[faction.id],
            payload={"faction_id": faction.id},
        )


def on_revival(w: World, event: PendingEvent) -> None:
    """A destroyed faction rises again if anyone survived it: the same faction, rebuilding with
    its old grudges, or a successor with its own name (W15a). Nobody left, no return."""
    state = w.state
    faction = state.factions.get(str(event.payload.get("faction_id")))
    if faction is None or faction.status is not FactionStatus.DESTROYED:
        return
    left = survivors(state, faction)
    if not left:
        return
    if w.roll("successor", faction.id).chance(SUCCESSOR_ODDS):
        heir = Faction(
            id=state.new_id("faction"),
            name=f"the heirs of {faction.name}",
            kind=faction.kind,
            description=f"Risen from the ruin of {faction.name}.",
            parent_id=faction.parent_id,
            status=FactionStatus.WEAKENED,
            goal=faction.goal,
            methods=faction.methods,
            relations=dict(faction.relations),
            player_reputation=faction.player_reputation.model_copy(),
            survivors=[],
            origin=Origin(
                kind=OriginKind.SUCCESSOR,
                ref_id=faction.id,
                text=f"Successor to {faction.name}, founded by its survivors.",
            ),
        )
        state.factions[heir.id] = heir
        for character in by_id(state.characters.values()):
            if character.alive and character.member_of(faction.id):
                character.memberships.append(Membership(faction_id=heir.id, loyalty=70))
    else:
        faction.status = FactionStatus.REBUILDING
        faction.activity = Activity.ACTIVE
        cause = Cause(
            mechanism=CauseMechanism.REVIVAL,
            ref_kind=CauseRef.EVENT,
            ref_id=event.id,
            text=f"Survivors carried {faction.name} on.",
        )
        faction.status_history.append(
            StatusChange(
                status=FactionStatus.REBUILDING.value,
                turn=w.ctx.turn,
                world_s=w.at_s,
                timeline_id=state.timeline_id,
                cause=cause,
                from_status=FactionStatus.DESTROYED.value,
                note="Revived by its survivors, weak, with its old grudges.",
            )
        )
    enforce_caps(state)
