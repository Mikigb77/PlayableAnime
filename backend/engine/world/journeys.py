"""Trips (W10, W7): where a step takes someone, how long the way is and where it leaves them.

The interpret step says only where a step goes (`IntentStep.destination`). Code does the rest:

- `heading` reads the trip a step sets out on and what the way takes by the map. Where the
  map's routes cover the way, that is the trip's time, the same every time. Where they don't,
  the step takes the time the interpret step judged.
- `follow` runs as each step plays out: whoever arrived is there, and the player character's
  unfinished trip is kept (`WorldState.journey`), so the rest of the way takes what is left.
- `settle` runs once the narrator's update is applied: the scene ends where the engine has the
  character, and a trip over ground the map didn't cover writes its route, so the same trip
  takes the same time from then on.

A journey that stopped on the way stays the player character's while they stay where it
stopped (`under_way`): through a night at the inn, a fight, a look at the ruin off the road. It
ends when they reach either end of it, and it is given up when they set out somewhere else.
"""

from engine.base import HOUR, MINUTE
from engine.contracts.intent import ActionKind, IntentStep, OutcomeClass
from engine.contracts.resolution import Resolution, StepResolution, Trip
from engine.invariants import ancestry
from engine.state.cast import Character, CharacterStatus, Route
from engine.state.records import StepResult
from engine.state.scene import SceneFrame
from engine.state.world import Journey, WorldState
from engine.world.geography import find_place, has_route, route_s, routes_from

# A trip shorter than this writes no route: crossing a yard or going down to the cellar is a
# move the interpret step times each time, and the map stays a map of journeys.
MIN_ROUTE_S = 10 * MINUTE

# How far aside the player character can step from where a journey stopped and still be on it:
# a look at the ruin off the road, an errand of under an hour. A longer way somewhere else
# gives the journey up.
NEARBY_S = HOUR

# The kinds of step that are the going itself: a place they target is where they go, and the
# way is all the time they take. Any other kind that names a destination goes there to do
# something (sleep at the inn in the village), so the way is only the least it takes.
GOING = (ActionKind.TRAVEL, ActionKind.MOVE)


def start_of(state: WorldState, actor: Character) -> str | None:
    """Where the actor's steps set out from: the scene's place for the player character, which
    is where the models have them, and the place on their own record for anyone else."""
    if actor.id == state.player_id:
        return state.scene.place_id or actor.location_id
    return actor.location_id


def _near(state: WorldState, actor: Character, at_id: str | None) -> list[str]:
    """The places a name the actor gives can mean (C6): the ones they know of, the ones they
    stand in, the ones inside the place they are in, and the ones routes lead to from there."""
    known = [p.id for p in state.places.values() if actor.id in (*p.known_by, *p.visited_by)]
    inside = [p.id for p in state.places.values() if at_id is not None and p.parent_id == at_id]
    return [*known, *ancestry(state.places, at_id), *inside, *routes_from(state, at_id)]


def under_way(state: WorldState, place_id: str | None) -> Journey | None:
    """W10. The player character's unfinished trip, when `place_id` is where it stopped: that
    place, one inside it (a room of the inn on the way) or the one it lies in."""
    journey = state.journey
    if journey is None:
        return None
    if place_id == journey.at_id:
        return journey
    if place_id is None or journey.at_id is None:
        return None
    return journey if _nested(state, place_id, journey.at_id) else None


def heading(
    state: WorldState, actor: Character, step: IntentStep, at_id: str | None
) -> Trip | None:
    """W10. The trip a step sets out on from `at_id`, or None for a step that stays where it is.

    The destination is the place the step names, by its id or by a name the actor could mean.
    A step that names none still goes somewhere when it travels by kind, which carries on the
    trip the player character is partway through, or when it moves and targets one place.
    `route_s` is what the way takes by the map: what is left of a trip the player character is
    partway through, else the routes between the two places, and None when no route covers it.
    """
    named = step.destination.strip()
    to_id = find_place(state.places, named, among=_near(state, actor, at_id)) if named else None
    journey = under_way(state, at_id) if actor.id == state.player_id else None
    if not named:
        aimed = [t for t in dict.fromkeys(step.target_ids) if t in state.places]
        if step.kind in GOING and len(aimed) == 1:
            to_id = aimed[0]
        elif step.kind is not ActionKind.TRAVEL:
            return None
        elif journey is not None:
            to_id = journey.to_id  # "I walk on": the trip they are on goes on
    if to_id is not None and to_id == at_id:
        if journey is None or to_id != journey.from_id:
            return None  # they are there already
        # Turning back to where a trip set out from, which the scene never left on record.
        return Trip(from_id=at_id, to_id=to_id, route_s=max(1, journey.done_s))
    way = None
    if to_id is not None and journey is not None:
        if to_id == journey.to_id:
            way = journey.left_s
        elif to_id == journey.from_id:
            way = max(1, journey.done_s)
    if to_id is not None and way is None:
        way = route_s(state, at_id, to_id)
    return Trip(from_id=at_id, to_id=to_id, to="" if to_id is not None else named, route_s=way)


def on_the_road(state: WorldState, actor_id: str, step: StepResolution) -> bool:
    """W16. Whether a step is a trip of the player character's that got going, so the road may
    bring something on the way (`engine.director.schedule_road`). A night at the inn they
    walked to is no time on the road."""
    if step.trip is None or step.kind not in GOING or actor_id != state.player_id:
        return False
    return (
        step.outcome_class is not OutcomeClass.RULED_OUT and step.result is not StepResult.FAILURE
    )


def cut_short(step: StepResolution, elapsed_s: int) -> bool:
    """W10. Whether an event that cut a step after `elapsed_s` stopped its trip on the way. It
    did when the step was the going itself. A step that went somewhere to do something there
    was stopped on the way only while the map's time for the way was still running."""
    trip = step.trip
    if trip is None or not trip.arrived:
        return False
    if step.kind in GOING:
        return True
    return trip.takes_s is not None and elapsed_s < trip.takes_s


def first_visit(state: WorldState, step: StepResolution) -> bool:
    """W2. Whether a trip of the player character's that arrived took them somewhere they had
    never been: a place on record they haven't visited, or one the record doesn't hold yet at
    the end of a real trip. A few steps to the counter are no arrival, and neither is going
    somewhere to do something else there."""
    trip = step.trip
    if trip is None or not trip.arrived or step.kind not in GOING:
        return False
    if trip.to_id is None:
        return step.duration_s >= MIN_ROUTE_S
    place = state.places.get(trip.to_id)
    return place is not None and state.player_id not in place.visited_by


def follow(state: WorldState, actor_id: str, step: StepResolution, *, planned_s: int) -> None:
    """W10. As a step ends in `play_out`, in place: someone whose trip arrived is at the place
    it went to, so what they do next happens there and is seen there (W1, W2). A trip of the
    player character's that stopped on the way is kept as their journey, and one that reached
    either end of their journey ends it. A step aside (to a room, to the stream) leaves the
    journey as it is, and so does a step that never got going.

    `planned_s` is what the step was settled to take, before anything cut it short.
    """
    trip = step.trip
    if trip is None:
        return
    if step.outcome_class is OutcomeClass.RULED_OUT or step.result is StepResult.FAILURE:
        return
    actor = state.characters.get(actor_id)
    player = actor_id == state.player_id
    if trip.arrived:
        if actor is not None and trip.to_id in state.places:
            actor.location_id = trip.to_id
        if player:
            _arrive(state, trip)
        return
    if player:
        if step.interrupted:
            state.director.road_stops += 1  # W16: the rest of the way is quieter
        kept = _on_the_way(under_way(state, trip.from_id), trip, step.duration_s, planned_s)
        if kept is not None:
            state.journey = kept


def _arrive(state: WorldState, trip: Trip) -> None:
    """The player character's trip arrived. At either end of their journey the journey is
    over and the road starts afresh, and a journey over ground the map didn't cover leaves its
    route (W7), the time judged for the whole way when it set out. Anywhere else was a step
    aside: `settle` says whether they are still on their way."""
    journey = state.journey
    if journey is not None and trip.to_id not in (journey.to_id, journey.from_id):
        return
    on_it = under_way(state, trip.from_id) is not None
    state.journey = None
    state.director.road_stops = 0
    if journey is None or journey.mapped or not on_it or trip.to_id != journey.to_id:
        return
    if _route_worthy(state, state, journey.from_id, journey.to_id, journey.total_s):
        _write_route(state, journey.from_id, journey.to_id, journey.total_s)


def _on_the_way(
    journey: Journey | None, trip: Trip, elapsed_s: int, planned_s: int
) -> Journey | None:
    """The player character's journey after a trip that stopped short, where `journey` is the
    one under way where the trip set out: the way behind them grows by what this step
    covered, counted in the map's time whatever carried them.

    Where no route says how long the way is, the time judged for the trip stands in for it, so
    the rest still takes what is left. None when nothing says how long the whole way is: the
    record doesn't hold the destination, the player set the time, or something of their own
    carried them.
    """
    if trip.from_id is None or trip.to_id is None:
        return None
    total, takes = trip.route_s, trip.takes_s
    mapped = True
    if total is None:
        if trip.arrived is None or trip.by_own_means or planned_s < 1:
            return None
        total = takes = planned_s
        mapped = False
    if takes is None:
        return None
    covered = min(total, round(total * elapsed_s / takes))
    if journey is not None:
        if trip.to_id == journey.to_id:
            done = min(journey.total_s, journey.done_s + covered)
            return journey.model_copy(update={"done_s": done})
        if trip.to_id == journey.from_id:
            return journey.model_copy(update={"done_s": max(0, journey.done_s - covered)})
    return Journey(
        from_id=trip.from_id,
        to_id=trip.to_id,
        total_s=total,
        done_s=covered,
        at_id=trip.from_id,
        mapped=mapped,
    )


def _nested(state: WorldState, a: str, b: str) -> bool:
    """Whether one place lies within the other, as a room in its house does."""
    return a in ancestry(state.places, b) or b in ancestry(state.places, a)


def _route_worthy(
    played: WorldState, state: WorldState, from_id: str | None, to_id: str | None, travel_s: int
) -> bool:
    """W7. Whether a trip that took `travel_s` between two places belongs on the map: both are
    on record, they aren't one inside the other, the way is a real trip and not a few minutes'
    walk, and no route ran straight between them before the turn (`played`)."""
    if from_id is None or to_id is None or from_id == to_id:
        return False
    if from_id not in state.places or to_id not in state.places:
        return False
    if travel_s < MIN_ROUTE_S or _nested(state, from_id, to_id):
        return False
    return not has_route(played, from_id, to_id)


def _new_routes(
    played: WorldState, state: WorldState, trips: list[StepResolution], ended_at: str | None
) -> list[tuple[str, str, int]]:
    """W7, W10. The routes this turn's trips write: each trip that arrived over ground the map
    didn't cover, on the road's own terms (nothing of the actor's own carried them), between
    two places that aren't one inside the other and had no route straight between them. A trip
    whose destination the record didn't hold yet ends where the scene did."""
    routes: list[tuple[str, str, int]] = []
    for index, step in enumerate(trips):
        trip = step.trip
        assert trip is not None
        if trip.route_s is not None or not trip.arrived or trip.by_own_means:
            continue
        to_id = trip.to_id
        if to_id is None and index == len(trips) - 1:
            to_id = ended_at
        if _route_worthy(played, state, trip.from_id, to_id, step.duration_s):
            routes.append((trip.from_id, to_id, step.duration_s))
    return routes


def settle(
    played: WorldState, state: WorldState, resolution: Resolution, *, told: bool
) -> tuple[WorldState, list[str]]:
    """W10, R8. The turn's trips, once the narrator's update is applied to `state` (`played`
    is the state the steps left, before it). `told` says whether the narrator said where its
    scene ends. Returns the state, a new one if anything had to change, and what was put right,
    for the turn's log.

    - A trip that arrived ends the scene there. A scene that still ends where the trip set out
      from, or that nobody ended anywhere, is put where the trip went, with those who were
      with the player character.
    - A trip that didn't arrive never ends the scene at its destination: it is put back where
      the trip set out from. One the player timed over ground no route covers is the
      narrator's to place.
    - A trip over ground the map didn't cover writes its route (`_new_routes`).
    - The player character's journey goes with them to the place the scene stopped in on the
      way and through a step aside, and it is dropped once they have set out somewhere else
      or the scene stands at either end of it (`_goes_on`).
    """
    if resolution.actor_id not in (None, state.player_id):
        return state, []
    trips = [s for s in resolution.steps if s.trip is not None]
    place = state.scene.place_id
    last = trips[-1].trip if trips else None
    start = played.scene.place_id
    move_to: str | None = None
    notes: list[str] = []
    if last is None:
        pass
    elif last.arrived:
        there = last.to_id
        behind = not told or _still_at(state, place, start, there)
        if there in state.places and there != place and behind:
            move_to = there
            if told:
                notes.append(f"the scene ended in {place!r}, where the trip left: now {there!r}")
    elif last.arrived is False and told and start in state.places:
        if place != start and _still_at(state, place, last.to_id, start):
            move_to = start
            notes.append(
                f"the scene ended in {place!r}, which the trip didn't reach: now {start!r}"
            )
    ended_at = move_to or place
    routes = _new_routes(played, state, trips, ended_at)
    astray = state.journey is not None and under_way(state, ended_at) is None
    if move_to is None and not routes and not astray:
        return state, notes
    new = state.model_copy(deep=True)
    if move_to is not None and last is not None:
        # A scene nobody ended says nothing of who went along, so nobody does.
        with_them = _travellers(played, new, start, arrived=bool(last.arrived)) if told else set()
        _end_scene_at(new, move_to, with_them, told)
    for from_id, to_id, travel_s in routes:
        _write_route(new, from_id, to_id, travel_s)
    if astray and new.journey is not None:
        if _goes_on(new, new.journey, trips, ended_at):
            new.journey.at_id = ended_at  # the place the scene stopped in is on the way
        else:
            new.journey = None
            new.director.road_stops = 0  # W16: another way starts afresh
    return new, notes


def _goes_on(
    state: WorldState, journey: Journey, trips: list[StepResolution], ended_at: str | None
) -> bool:
    """Whether a journey goes on from `ended_at`, a place apart from where it stopped. It does
    when the stretch of it travelled this turn stopped there, and when the player character
    only stepped aside: a spot the scene moved to, or a way of under an hour in all
    (`NEARBY_S`), counted in the map's time. It doesn't once the scene stands at either end of
    it, or once they went further than that some other way."""
    ends = (journey.to_id, journey.from_id)
    if any(end in ancestry(state.places, ended_at) for end in ends):
        return False
    aside = 0
    for step in trips:
        trip = step.trip
        assert trip is not None
        if step.outcome_class is OutcomeClass.RULED_OUT or step.result is StepResult.FAILURE:
            continue
        if trip.to_id in ends:
            continue  # a stretch of the journey itself
        if trip.by_own_means:
            return False  # nobody can say how far that carried them
        aside += step.duration_s if trip.route_s is None else trip.route_s
    return aside < NEARBY_S


def _still_at(state: WorldState, place: str | None, a: str | None, b: str | None) -> bool:
    """Whether a scene that ends in `place` is still at `a` and not at `b`: in `a` itself, or
    somewhere inside it that isn't inside `b` as well (a kitchen of the farm the trip left,
    never a corner of the cellar it went down to)."""
    if place is None or a is None:
        return False
    if place == a:
        return True
    within = ancestry(state.places, place)
    return a in within and (b is None or b not in within)


def _travellers(
    played: WorldState, state: WorldState, start: str | None, *, arrived: bool
) -> set[str]:
    """C2. Those of the scene who go where the player character goes when code moves its end:
    whoever the scene ends with that is with them. For a scene put where a trip arrived, that
    is where the scene stood; for one put back where the trip set out from, where they were
    before the telling moved anyone. Someone the telling names from elsewhere doesn't move."""
    record = state if arrived else played
    left = state.scene.place_id if arrived else start
    with_them = set()
    for character_id in state.scene.present_ids:
        character = record.characters.get(character_id)
        if character is None:
            continue
        where = character.location_id
        if where is None or (left is not None and left in ancestry(record.places, where)):
            with_them.add(character_id)
    return with_them


def _end_scene_at(state: WorldState, place_id: str, travellers: set[str], told: bool) -> None:
    """R8. The scene ends at `place_id`, in place, with the player character there and
    `travellers` with them. The rest of the scene's people stay in it only if that is where
    they are. A scene nobody ended (`told` false) still holds the positions and the things of
    the place the trip left, so those go."""
    places, frame = state.places, state.scene
    player = state.player
    present: list[str] = []
    for character_id in frame.present_ids:
        character = state.characters.get(character_id)
        if character is None:
            continue
        if character_id == player.id:
            present.append(character_id)
        elif character_id in travellers and character.status is CharacterStatus.ALIVE:
            character.location_id = place_id
            present.append(character_id)
        elif place_id in ancestry(places, character.location_id):
            present.append(character_id)
    if told:
        frame.place_id = place_id
        frame.present_ids = present
    else:
        state.scene = SceneFrame(
            place_id=place_id,
            present_ids=present,
            ended_on=frame.ended_on,
            encounter=frame.encounter,
        )
    player.location_id = place_id
    for known in (places[place_id].visited_by, places[place_id].known_by):
        if player.id not in known:
            known.append(player.id)


def _write_route(state: WorldState, from_id: str, to_id: str, travel_s: int) -> None:
    """One route between two places, whichever way it is travelled: the time the trip took."""
    origin, end = state.places[from_id], state.places[to_id]
    origin.routes = [r for r in origin.routes if r.to_id != to_id]
    end.routes = [r for r in end.routes if r.to_id != from_id]
    origin.routes.append(Route(to_id=to_id, travel_s=max(1, travel_s)))
