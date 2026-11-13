"""Recording what a finished step did to the world (W1, W2, W7, W8, W11, W12, W13, E2, E5).

`record_consequences` turns each deed resolve proposed into a `Deed`: who did it, where, to whom,
how severe by the world's norms, and who could perceive it. Then the world starts reacting, all
of it in code and on in-world time: witnesses feel about the doer (W4), those of them with
someone to tell set off to tell the factions that hold the place or keep the law (W11), word of
it gets out once a witness is free to talk, or at once before a crowd (W2,
`engine.world.carriers`), a secret deed waits to be discovered from its traces (W13), clocks
that name the deed move (E2), and a conquered place grows restless (W7). The same runs for an
NPC's deed (E5).

A bout both sides agreed to is none of that (W1, `engine.resolve.bouts`). It is one deed however
many blows it had, nobody takes it as an attack, and all it leaves is a little more regard
between those who fought it. A death both accepted is still a death to those close to the dead,
and nothing to the law or to bystanders.
"""

from collections.abc import Sequence

from engine.context import TurnContext
from engine.contracts.resolution import ProposedDeed, Resolution, StepResolution
from engine.rng import SeededRng
from engine.state.records import Deed, TraceKind, Visibility
from engine.state.world import WorldState, natural_key
from engine.world.carriers import leave, schedule_reports, schedule_word, word_out
from engine.world.cast import maybe_resistance
from engine.world.clocks import deed_moves_clocks
from engine.world.discovery import body_trace, schedule_look, ties_trace
from engine.world.geography import characters_at, onlookers, perceives
from engine.world.journeys import GOING
from engine.world.knowledge import character_learns, faction_learns, fought_bout
from engine.world.norms import assess_severity, canonical
from engine.world.scheduling import World

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
    # W11: whoever set off during the step to tell of an earlier deed isn't there to see this.
    leave(new)
    # W2: whoever the step brought on stage or faced is in the scene, and a scene the player
    # character has only just walked into hasn't shown who is around.
    onstage = [*step.strangers, *step.opponent_ids]
    for i, proposed in enumerate(step.deeds):
        if _bout_recorded(new, resolution, proposed):
            continue  # W1: the bout is one deed, however many blows it has
        w = World(state=new, ctx=ctx, at_s=new.world_s, rng=rng.child("deed", i))
        shown = _shown(resolution, step, proposed)
        deed = record_deed(w, resolution, proposed, onstage=onstage, shown=shown)
        react(w, deed)
    return new


def _shown(resolution: Resolution, step: StepResolution, proposed: ProposedDeed) -> bool:
    """W2. Whether a scene has shown who is around where a deed of this step was done. None
    has where the actor got to in this plan: by an earlier step, or by this one for what it
    did where it went. What a step that is the going itself does (`journeys.GOING`) is done
    as they set out, where the scene has them, and resolve gives it no place of its own: the
    scene's people see it, and the rest of the place they leave doesn't (in a live story a
    walk home with someone's wife was seen by her husband at his forge, 2026-11-13)."""
    if any(s.trip is not None and s.trip.arrived for s in resolution.steps if s.index < step.index):
        return False
    trip = step.trip
    if trip is None or not trip.arrived:
        return True
    return step.kind in GOING and proposed.place_id is None


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


def record_deed(
    w: World,
    resolution: Resolution,
    proposed: ProposedDeed,
    *,
    onstage: Sequence[str] = (),
    shown: bool = True,
) -> Deed:
    """W1, W2: the deed with its severity by the world's norms and the witnesses who could
    perceive it. Resolve's witnesses stand when it names them; otherwise everyone there and
    aware saw it, unless it was done in secret or in stopped time (W10a). For what is done by
    or to someone in the player character's scene, there means in the scene
    (`geography.onlookers`): its people, those the deed fell on and whoever the step brought
    on stage (`onstage`), and not everyone the record puts at the place. It is everyone at the
    place when no scene has shown who is around (`shown` false), and when it was done before a
    crowd, which makes it public."""
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
        involved = [actor_id, *victims, *proposed.target_ids, *onstage]
        # Done before a crowd, everyone the record puts there saw it.
        shown = shown and proposed.visibility is not Visibility.PUBLIC
        witnesses = [
            c.id
            for c in onlookers(state, place_id, involved, shown=shown)
            if c.id != actor_id and perceives(c)
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
        wronged_ids=[i for i in dict.fromkeys(proposed.wronged_ids) if i != actor_id],
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
    """The world's first reactions to a deed, at the moment it is done. Those who saw it feel
    about it at once. Everything else it sets going leaves with someone who carries word of it
    (`engine.world.carriers`): the witnesses who set off to tell a faction, and the talk that
    starts at once before a crowd, and otherwise only when a witness is free to talk."""
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
        _leaders_who_saw(w, deed)
        schedule_reports(w, deed)
        if deed.visibility is Visibility.PUBLIC:
            word_out(w, deed)  # nobody stops a crowd
        else:
            schedule_word(w, deed)
    else:
        crowd = [
            c
            for c in characters_at(state, deed.place_id)
            if c.id != deed.actor_id and c.id not in deed.victim_ids
        ]
        schedule_look(w, deed, crowd=bool(crowd))

    deed_moves_clocks(w, deed)
    _conquered(w, deed)


def _leaders_who_saw(w: World, deed: Deed) -> None:
    """A faction whose leader saw it knows at once."""
    state = w.state
    for faction in sorted(state.factions.values(), key=lambda f: natural_key(f.id)):
        if any(leader in deed.witness_ids for leader in faction.leader_ids):
            faction_learns(w, faction.id, deed)


def _conquered(w: World, deed: Deed) -> None:
    """W7: a conquered place loses stability and may grow a resistance."""
    state = w.state
    if canonical(deed.kind) != "conquer":
        return
    # The places it names, or else the place it was done in.
    taken = [t for t in deed.target_ids if t in state.places] or [deed.place_id]
    for place_id in dict.fromkeys(taken):
        place = state.places.get(place_id) if place_id else None
        if place is None:
            continue
        place.stability = max(0, place.stability - CONQUEST_STABILITY_LOSS)
        maybe_resistance(w, deed, place.id)
