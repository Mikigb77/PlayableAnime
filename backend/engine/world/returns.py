"""Whoever the world sends somewhere comes back (W6, W4, W11).

Nobody on record has a home: people are where the story put them. So when the world itself
moves someone, on an outing of their own (the tick, W6), to bring a faction what they saw
(W11) or to face someone (W4), it is a round trip. `left` notes where they set out from, as one
pending event for each person (`Kind.RETURN`), and `on_return` puts them back there once their
stay and the way back have passed (W10).

They stay where they went while something holds them there: the player character's scene has
them, they are in no state to travel, or an errand of theirs is still to come (an answer they
are bringing, a report they carry). And nothing brings back someone the story has since taken
elsewhere, such as a companion who left with the player character: they are where the story
has them now.
"""

from engine.resolve.power import helpless_state
from engine.state.cast import Character
from engine.state.records import Fact, FactKind, Origin, OriginKind, PendingEvent
from engine.state.world import WorldState
from engine.world.geography import scene_ids, travel_s
from engine.world.scheduling import Kind, World, cancel, pending, schedule
from engine.world.tuning import HELD_MAX_S, HELD_S


def trip_of(state: WorldState, character_id: str) -> PendingEvent | None:
    """The round trip someone is on: their pending return, whose place is where they set out
    from and whose `at_id` is where the world last took them."""
    found = pending(state, Kind.RETURN, character_id=character_id)
    return found[0] if found else None


def left(
    w: World, who: Character, from_id: str | None, stay: tuple[int, int]
) -> PendingEvent | None:
    """The world has just moved `who` from `from_id` to where they are now: they come back
    once they have stayed (`stay`, a span to draw from) and made the way back. Someone already
    on a round trip keeps the place they first set out from, and comes back from wherever they
    are now, even from the room next door: a step out of the house is where the next step
    further would start. Returns their pending return, or None when they are back where they
    set out from or the map holds no such place."""
    state = w.state
    if who.id == state.player_id:
        return None
    trip = trip_of(state, who.id)
    base = trip.place_id if trip is not None else from_id
    at = who.location_id
    if base not in state.places or at not in state.places or at == base:
        if trip is not None:
            cancel(w, trip)  # this move brought them back, or took them off the map
        return None
    due_s = w.at_s + w.between(stay, "stay", who.id, at) + (travel_s(state, at, base) or 0)
    if trip is not None:
        trip.payload["at_id"] = at
        trip.due_s = max(trip.due_s, due_s)
        return trip
    return _schedule(w, who, base, due_s)


def _schedule(
    w: World, who: Character, base: str, due_s: int, held_s: int | None = None
) -> PendingEvent:
    payload = {"character_id": who.id, "at_id": who.location_id}
    if held_s is not None:
        payload["held_s"] = held_s  # since when something has kept them from setting out
    return schedule(
        w,
        Kind.RETURN,
        due_s,
        title=f"{who.name} comes back to {w.state.places[base].name}",
        subject_ids=[who.id],
        place_id=base,
        payload=payload,
    )


def on_return(w: World, event: PendingEvent) -> None:
    """A return comes due. They are back where they set out from, unless the story has taken
    them elsewhere since, which ends the round trip, or something still holds them where they
    went, which puts it off. A return that brought nobody back came to nothing, so no scene
    at the place they set out from is told they came (`engine.director.due.noticed`)."""
    state = w.state
    who = state.characters.get(str(event.payload.get("character_id")))
    base = event.place_id
    if who is None or not who.alive or base not in state.places:
        cancel(w, event)
        return
    if who.location_id != event.payload.get("at_id"):
        cancel(w, event)  # the story moved them: they are where it has them
        return
    held_s = int(event.payload.get("held_s", w.at_s))
    until_s = _held_until(w, who, held_s)
    if until_s is not None:
        cancel(w, event)
        way_s = travel_s(state, who.location_id, base) or 0
        _schedule(w, who, base, until_s + way_s, held_s)
        return
    who.location_id = base
    fact = Fact(
        id=state.new_id("fact"),
        text=f"{who.name} comes back to {state.places[base].name}.",
        kind=FactKind.OBSERVATION,
        importance=1,
        subject_ids=[who.id],
        known_by=[who.id],
        turn=w.ctx.turn,
        world_s=w.at_s,
        timeline_id=state.timeline_id,
        origin=Origin(kind=OriginKind.AGENDA, ref_id=who.id),
    )
    state.facts[fact.id] = fact


def errands_of(state: WorldState, character_id: str) -> list[PendingEvent]:
    """The errands of the world's making someone is on, still to come: an answer they are
    bringing to someone (W4), a report they carry to their faction (W11)."""
    return [
        *pending(state, Kind.ANSWER, avenger_id=character_id),
        *pending(state, Kind.REPORT, witness_id=character_id),
    ]


def _held_until(w: World, who: Character, held_s: int) -> int | None:
    """When someone due back can set out, or None when nothing holds them. An errand of theirs
    that is still to come holds them until a day after it has. The player character's scene,
    or a state that leaves them helpless, holds them a day at first and then as long again as
    it has held them since `held_s`, up to a week (W10, K8: a year in a cell asks weekly)."""
    state = w.state
    errands = errands_of(state, who.id)
    if errands:
        return max(e.due_s for e in errands) + HELD_S
    if who.id in scene_ids(state) or helpless_state(who) is not None:
        return w.at_s + min(max(HELD_S, w.at_s - held_s), HELD_MAX_S)
    return None
