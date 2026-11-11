"""Recording what a finished step did to the world (W1, W2, W7, W8, W11, W12, W13, E2, E5).

`record_consequences` turns each deed resolve proposed into a `Deed`: who did it, where, to whom,
how severe by the world's norms, and who could perceive it. Then the world starts reacting, all
of it in code and on in-world time: witnesses feel about the doer (W4), word starts to spread
(W2), witnesses set off to tell the factions that hold the place or keep the law (W11), close
ties hear of a death (W4), a secret deed waits to be discovered from its traces (W13), clocks that
name the deed move (E2), and a conquered place grows restless (W7). The same runs for an NPC's
deed (E5).

A bout both sides agreed to is none of that (W1, `engine.resolve.bouts`). It is one deed however
many blows it had, nobody takes it as an attack, and all it leaves is a little more regard
between those who fought it. A death both accepted is still a death to those close to the dead,
and nothing to the law or to bystanders.
"""

from engine.context import TurnContext
from engine.contracts.resolution import ProposedDeed, Resolution, StepResolution
from engine.rng import SeededRng
from engine.state.cast import Character
from engine.state.records import Deed, TraceKind, Visibility
from engine.state.world import WorldState, natural_key
from engine.world.aftermath import on_attributed
from engine.world.answers import law_at
from engine.world.cast import maybe_resistance
from engine.world.clocks import deed_moves_clocks
from engine.world.discovery import attributed, body_trace, schedule_look, ties_trace
from engine.world.geography import (
    ancestors,
    characters_at,
    faction_seat,
    perceives,
    region_of,
    travel_s,
)
from engine.world.knowledge import (
    FRIEND,
    character_learns,
    closeness,
    faction_learns,
    fought_bout,
    region_learns,
)
from engine.world.norms import (
    Nature,
    assess_severity,
    canonical,
    deed_nature,
    is_beast,
    is_crime,
)
from engine.world.rumors import start_rumor
from engine.world.scheduling import Kind, World, schedule
from engine.world.telling import account
from engine.world.tuning import (
    CALL_S,
    FLEE_S,
    LOYAL_AFFINITY,
    RUMOR_HOPS,
    RUMOR_MIN_SEVERITY,
    SILENT_FEAR,
    UNKNOWN_TRIP_S,
)

CONQUEST_STABILITY_LOSS = 30


def record_consequences(
    state: WorldState,
    resolution: Resolution,
    step: StepResolution,
    ctx: TurnContext,
    rng: SeededRng,
) -> WorldState:
    """Record each deed of a finished step at its end time and set the world's reactions going.
    The step's own effects (a death, say) are already applied, so a victim is already dead."""
    if not step.deeds:
        return state
    new = state.model_copy(deep=True)
    for i, proposed in enumerate(step.deeds):
        if _bout_recorded(new, resolution, proposed):
            continue  # W1: the bout is one deed, however many blows it has
        w = World(state=new, ctx=ctx, at_s=new.world_s, rng=rng.child("deed", i))
        deed = record_deed(w, resolution, proposed)
        react(w, deed)
    return new


def _bout_recorded(state: WorldState, resolution: Resolution, proposed: ProposedDeed) -> bool:
    """W1. Whether a blow inside the terms of a bout belongs to a bout already on record: the
    one the scene's encounter is, which someone of this blow fought in since it began."""
    encounter = state.scene.encounter
    if proposed.terms is None or proposed.victim_ids:
        return False
    if encounter is None or encounter.bout is None:
        return False
    actor_id = proposed.actor_id or resolution.actor_id or state.player_id
    fighters = {actor_id, *proposed.target_ids}
    return any(
        deed.is_bout
        and deed.world_s >= encounter.started_s
        and deed.timeline_id == state.timeline_id
        and fighters & {deed.actor_id, *deed.target_ids}
        for deed in state.deeds.values()
    )


def record_deed(w: World, resolution: Resolution, proposed: ProposedDeed) -> Deed:
    """W1, W2: the deed with its severity by the world's norms and the witnesses who could
    perceive it. Resolve's witnesses stand when it names them; otherwise everyone present and
    aware saw it, unless it was done in secret or in stopped time (W10a)."""
    state = w.state
    actor_id = proposed.actor_id or resolution.actor_id or state.player_id
    actor = state.characters.get(actor_id)
    place_id = proposed.place_id or (actor.location_id if actor else None)
    victims = list(dict.fromkeys(proposed.victim_ids))
    explicit = [
        c for c in dict.fromkeys(proposed.witness_ids) if c != actor_id and c in state.characters
    ]
    if explicit or proposed.in_stopped_time or proposed.visibility is Visibility.SECRET:
        witnesses = explicit
    else:
        witnesses = [
            c.id for c in characters_at(state, place_id) if c.id != actor_id and perceives(c)
        ]
    visibility = proposed.visibility or (Visibility.WITNESSED if witnesses else Visibility.SECRET)
    if proposed.in_stopped_time:
        # The user sees a frozen world; whoever was immune goes unnoticed (W10a).
        unnoticed = list(witnesses)
    else:
        unnoticed = [c for c in proposed.unnoticed_witness_ids if c in witnesses]
    deed = Deed(
        id=state.new_id("deed"),
        actor_id=actor_id,
        kind=proposed.kind,
        text=proposed.text,
        turn=w.ctx.turn,
        world_s=w.at_s,
        timeline_id=state.timeline_id,
        place_id=place_id,
        victim_ids=victims,
        target_ids=list(dict.fromkeys(proposed.target_ids)),
        severity=assess_severity(
            state, proposed.kind, proposed.severity, victims, proposed.target_ids
        ),
        visibility=visibility,
        witness_ids=witnesses,
        unnoticed_witness_ids=unnoticed,
        traces=list(proposed.traces),
        in_stopped_time=proposed.in_stopped_time,
        known_by=list(dict.fromkeys([actor_id, *witnesses])),
        terms=proposed.terms,
        broke_terms=proposed.broke_terms,
    )
    if visibility is Visibility.SECRET and not deed.is_bout:
        body = body_trace(state, deed)
        if body is not None:
            deed.traces.append(body)
        ties = (
            None if any(t.kind is TraceKind.TIES for t in deed.traces) else ties_trace(state, deed)
        )
        if ties is not None:
            deed.traces.append(ties)
    state.deeds[deed.id] = deed
    return deed


def react(w: World, deed: Deed) -> None:
    """The world's first reactions to a deed, at the moment it is done."""
    state = w.state
    if deed.is_bout:
        # W1. Nobody takes a bout both sides agreed to as an attack: no word of one goes round,
        # nobody reports it and nothing is left to find out.
        fought_bout(w, deed)
        deed_moves_clocks(w, deed)
        return
    for witness_id in sorted(deed.witness_ids, key=natural_key):
        character_learns(w, witness_id, deed)

    if deed.visibility is not Visibility.SECRET:
        public = deed.visibility is Visibility.PUBLIC
        if deed.severity >= RUMOR_MIN_SEVERITY or public:
            start_rumor(
                w,
                text=account(state, deed),
                is_true=True,
                place_id=deed.place_id,
                hops=RUMOR_HOPS[deed.severity] + (1 if public else 0),
                deed=deed,
                about_ids=[deed.actor_id, *deed.victim_ids, *deed.target_ids],
                accuracy=100 if public else 90,
                heard_by=deed.witness_ids,
            )
        region_learns(w, region_of(state, deed.place_id), deed)
        _leaders_who_saw(w, deed)
        schedule_reports(w, deed)
        if attributed(state, deed):
            on_attributed(w, deed)
    else:
        crowd = [
            c
            for c in characters_at(state, deed.place_id)
            if c.id != deed.actor_id and c.id not in deed.victim_ids
        ]
        schedule_look(w, deed, crowd=bool(crowd))

    deed_moves_clocks(w, deed)
    _mark_places(w, deed)


def _leaders_who_saw(w: World, deed: Deed) -> None:
    """A faction whose leader saw it knows at once."""
    state = w.state
    for faction in sorted(state.factions.values(), key=lambda f: natural_key(f.id)):
        if any(leader in deed.witness_ids for leader in faction.leader_ids):
            faction_learns(w, faction.id, deed)


def _report_targets(state: WorldState, deed: Deed) -> list[str]:
    """Factions a witness would tell (W11): whoever holds the place, those who keep the law
    there against a crime, and the witnesses' own factions when it is serious. Nobody reports a
    hunt too small to be news (G24)."""
    targets: list[str] = []
    if deed.agreed:
        return targets  # W1: what both sides agreed to is nobody's to report
    if deed_nature(state, deed) is Nature.HUNT and deed.severity < RUMOR_MIN_SEVERITY:
        return targets
    for place_id in ancestors(state, deed.place_id):
        holder = state.places[place_id].controller_id
        if holder in state.factions:
            targets.append(holder)
            break
    if is_crime(state, deed):
        targets.extend(f for f in sorted(state.factions) if law_at(state, f, deed.place_id))
    if deed.severity >= 2:
        for witness_id in deed.witness_ids:
            witness = state.characters.get(witness_id)
            if witness is not None:
                targets.extend(m.faction_id for m in witness.memberships)
    return [f for f in dict.fromkeys(targets) if f in state.factions]


def would_report(state: WorldState, witness: Character, faction_id: str, deed: Deed) -> bool:
    """Whether a witness tells this faction (W11): not if they are devoted to the doer, too
    afraid of them (unless it is their own faction), or of a faction at odds with it, such as a
    crime family's people with the police. The player's character never reports by itself, and
    a beast tells nobody but its own pack (G24)."""
    if witness.id == state.player_id or not witness.alive:
        return False
    if is_beast(state, witness.id) and not witness.member_of(faction_id):
        return False
    toward = witness.sheet.disposition.attitudes.get(deed.actor_id)
    if toward is not None and toward.affinity >= LOYAL_AFFINITY:
        return False
    if closeness(state, witness, deed.actor_id) >= FRIEND:
        return False
    if witness.member_of(faction_id):
        return True
    if toward is not None and toward.fear >= SILENT_FEAR:
        return False
    for membership in witness.memberships:
        own = state.factions.get(membership.faction_id)
        if own is not None and own.relations.get(faction_id, 0) <= -30:
            return False
    return True


def schedule_reports(w: World, deed: Deed) -> None:
    """Each faction to tell gets one report, from the witness who can reach it soonest: at once
    if the faction is right there, after a call where the world has phones, else after the
    witness has got there on foot or by whatever people use, and about an hour where the map
    doesn't say where the faction is (W10, G6)."""
    state = w.state
    instant = state.bible.travel.instant_messages
    for faction_id in _report_targets(state, deed):
        if deed.actor_id in state.factions[faction_id].leader_ids:
            continue
        seat = faction_seat(state, state.factions[faction_id])
        trip = travel_s(state, deed.place_id, seat)
        best: tuple[int, str, bool] | None = None
        for witness_id in sorted(deed.witness_ids, key=natural_key):
            witness = state.characters.get(witness_id)
            if witness is None or not would_report(state, witness, faction_id, deed):
                continue
            labels = ("report", deed.id, faction_id, witness_id)
            if trip == 0:
                delay, moves = w.between(CALL_S, *labels), False
            elif instant:
                delay = w.between(FLEE_S, *labels, "flee") + w.between(CALL_S, *labels)
                moves = False
            else:
                way = UNKNOWN_TRIP_S if trip is None else trip
                delay, moves = w.between(FLEE_S, *labels, "flee") + way, trip is not None
            if best is None or delay < best[0]:
                best = (delay, witness_id, moves)
        if best is None:
            continue
        delay, witness_id, moves = best
        schedule(
            w,
            Kind.REPORT,
            w.at_s + delay,
            title=f"{state.characters[witness_id].name} tells {state.factions[faction_id].name}",
            subject_ids=[witness_id, faction_id, deed.actor_id],
            place_id=seat if moves else None,
            payload={
                "deed_id": deed.id,
                "faction_id": faction_id,
                "witness_id": witness_id,
                "moves": moves,
            },
        )


def _mark_places(w: World, deed: Deed) -> None:
    """W7, W8: a conquered place loses stability and may grow a resistance; a place that saw
    something terrible remembers it in its mood."""
    state = w.state
    if canonical(deed.kind) == "conquer":
        # The places it names, or else the place it was done in.
        taken = [t for t in deed.target_ids if t in state.places] or [deed.place_id]
        for place_id in dict.fromkeys(taken):
            place = state.places.get(place_id) if place_id else None
            if place is None:
                continue
            place.stability = max(0, place.stability - CONQUEST_STABILITY_LOSS)
            maybe_resistance(w, deed, place.id)
    elif (
        deed.visibility is not Visibility.SECRET
        and deed.severity >= 4
        and deed_nature(state, deed) is Nature.HARM
        and not deed.agreed  # W1: a death both accepted leaves no place shaken
        and deed.place_id in state.places
    ):
        actor = state.characters.get(deed.actor_id)
        who = actor.name if actor else "someone"
        state.places[deed.place_id].mood = f"shaken; people remember what {who} did here"
