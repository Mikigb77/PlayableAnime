"""Where things are and how long it takes to get between them (W7, W10).

Places record rough travel times to their neighbours (`Place.routes`). A place inside another (a
bar in a city) is `LOCAL_LINK_S` from it when no route says otherwise, so two buildings in one
city are a short walk apart. A region of its own (a city, a village, a kingdom) has no such link
to the place it sits in: two cities in one kingdom are as far apart as their routes say, however
close each is to "the kingdom". A route between two places is what the trip between them takes.
"""

import heapq
import re
import unicodedata
from collections.abc import Iterable

from engine.invariants import ancestry
from engine.state.cast import Character, Faction, Place
from engine.state.world import WorldState, natural_key
from engine.world.scheduling import by_id
from engine.world.tuning import LOCAL_LINK_S, REGION_KINDS


def ancestors(state: WorldState, place_id: str | None) -> list[str]:
    """The place and the places it sits in, nearest first."""
    return ancestry(state.places, place_id)


def is_within(state: WorldState, place_id: str | None, area_id: str | None) -> bool:
    """Whether `place_id` is `area_id` or somewhere inside it."""
    return area_id is not None and area_id in ancestors(state, place_id)


# Latin accents, which `_slug` drops, unlike other scripts' marks (a kana's dakuten makes another
# letter). `engine.limits.normalize` keeps only ASCII, which would drop non-Latin names whole.
_ACCENTS = re.compile("[\u0300-\u036f]")


def _slug(text: str) -> str:
    """A place's id or name without case, accents or the marks between words, so "Templo
    Subterráneo", "templo-subterraneo" and "templo_subterraneo" read the same."""
    bare = unicodedata.normalize("NFC", _ACCENTS.sub("", unicodedata.normalize("NFKD", text)))
    return re.sub(r"[\W_]+", "_", bare.casefold()).strip("_")


def find_place(
    places: dict[str, Place], ref: str | None, among: Iterable[str] | None = None
) -> str | None:
    """R8. The id of the one place `ref` names: by its exact id, or else by its id or its name
    however it is spelled, among the places `among` lists (all of them by default), so a name
    never reaches a place the story hasn't brought near. None when it names none, or more than
    one."""
    ref = (ref or "").strip()
    if not ref:
        return None
    if ref in places:
        return ref
    wanted = _slug(ref)
    if not wanted:
        return None
    pool = [places[i] for i in dict.fromkeys(among) if i in places] if among is not None else None
    for key in (lambda p: p.id, lambda p: p.name):
        found = [
            p.id for p in (places.values() if pool is None else pool) if _slug(key(p)) == wanted
        ]
        if found:
            return found[0] if len(found) == 1 else None
    return None


def region_of(state: WorldState, place_id: str | None) -> str | None:
    """The region whose people carry the player's reputation for what happens here (W3)."""
    chain = ancestors(state, place_id)
    for pid in chain:
        if state.places[pid].kind.strip().casefold() in REGION_KINDS:
            return pid
    return chain[-1] if chain else None


def _is_region(state: WorldState, place_id: str) -> bool:
    return state.places[place_id].kind.strip().casefold() in REGION_KINDS


def _route_graph(state: WorldState) -> dict[str, dict[str, int]]:
    """Explicit routes, both ways: a route from A to B is also one from B to A unless B lists
    its own time back."""
    graph: dict[str, dict[str, int]] = {pid: {} for pid in state.places}
    for place in by_id(state.places.values()):
        for route in place.routes:
            if route.to_id not in state.places:
                continue
            graph[place.id][route.to_id] = min(
                route.travel_s, graph[place.id].get(route.to_id, route.travel_s)
            )
    for place in by_id(state.places.values()):
        for route in place.routes:
            if route.to_id in graph and place.id not in graph[route.to_id]:
                graph[route.to_id][place.id] = route.travel_s
    return graph


def _travel_graph(state: WorldState, routes: dict[str, dict[str, int]]) -> dict:
    """Routes, plus the short walk between a place and the one it sits in, unless the place is
    a region of its own."""
    graph = {pid: dict(links) for pid, links in routes.items()}
    for place in by_id(state.places.values()):
        if place.parent_id in graph and not _is_region(state, place.id):
            graph[place.id].setdefault(place.parent_id, LOCAL_LINK_S)
            graph[place.parent_id].setdefault(place.id, LOCAL_LINK_S)
    return graph


def _ways(state: WorldState, from_id: str) -> dict[str, tuple[int, bool]]:
    """The quickest way from one place to every place the map connects it to: the seconds it
    takes, and whether it runs over a route the map records, rather than only the short walks
    between a place and the one it sits in. A route straight between two places is what the
    trip takes, whatever else connects them."""
    routes = _route_graph(state)
    graph = _travel_graph(state, routes)
    # Each way is weighed by its time, then by whether a route covers it, so of two ways that
    # take the same time the one over a route stands.
    best: dict[str, tuple[int, int]] = {from_id: (0, 1)}
    frontier: list[tuple[int, int, str]] = [(0, 1, from_id)]
    while frontier:
        cost, unrouted, pid = heapq.heappop(frontier)
        if (cost, unrouted) > best.get(pid, (cost, unrouted)):
            continue
        for nxt, step in sorted(graph[pid].items()):
            way = (cost + step, 0 if nxt in routes[pid] else unrouted)
            if nxt not in best or way < best[nxt]:
                best[nxt] = way
                heapq.heappush(frontier, (*way, nxt))
    ways = {pid: (cost, not unrouted) for pid, (cost, unrouted) in best.items()}
    for to_id, direct in routes[from_id].items():
        ways[to_id] = (direct, True)
    return ways


def travel_s(state: WorldState, from_id: str | None, to_id: str | None) -> int | None:
    """Rough travel time between two places, or None when nothing on the map connects them
    (W10). A route between the two is what it takes; otherwise the quickest way over routes and
    the short walks between a place and the one it sits in."""
    if from_id is None or to_id is None or from_id not in state.places or to_id not in state.places:
        return None
    if from_id == to_id:
        return 0
    way = _ways(state, from_id).get(to_id)
    return way[0] if way is not None else None


def ways_from(state: WorldState, from_id: str | None) -> dict[str, int]:
    """W10. Rough travel time from a place to every place the map connects it to, itself at
    0: `travel_s` for them all at once."""
    if from_id is None or from_id not in state.places:
        return {}
    return {to_id: cost for to_id, (cost, _) in _ways(state, from_id).items()} | {from_id: 0}


def route_s(state: WorldState, from_id: str | None, to_id: str | None) -> int | None:
    """W10. What a trip between two places takes by the map's own routes, or None when no route
    covers the way: the two aren't connected, or only by the short walks between a place and
    the one it sits in, which are too rough to time someone's steps by (a room next door isn't
    a quarter of an hour away)."""
    if from_id is None or to_id is None or from_id == to_id:
        return None
    return routes_from(state, from_id).get(to_id)


def has_route(state: WorldState, a: str | None, b: str | None) -> bool:
    """Whether the map records a route straight between two places, either way."""
    if a not in state.places or b not in state.places:
        return False
    return any(r.to_id == b for r in state.places[a].routes) or any(
        r.to_id == a for r in state.places[b].routes
    )


def routes_from(state: WorldState, from_id: str | None) -> dict[str, int]:
    """W10. Every place the map's routes reach from `from_id`, with what the trip takes."""
    if from_id is None or from_id not in state.places:
        return {}
    return {
        to_id: max(1, cost)
        for to_id, (cost, routed) in _ways(state, from_id).items()
        if routed and to_id != from_id
    }


def news_neighbours(state: WorldState, place_id: str) -> list[tuple[str, int]]:
    """Where word goes next from a place, with the travel time: along routes, into the places
    inside it, and out to the place it sits in while that is still within its region (W2)."""
    if place_id not in state.places:
        return []
    found: dict[str, int] = dict(_route_graph(state)[place_id])
    place = state.places[place_id]
    region = region_of(state, place_id)
    if place.parent_id in state.places and region != place_id:
        found.setdefault(place.parent_id, LOCAL_LINK_S)
    for child in by_id(state.places.values()):
        if child.parent_id == place_id:
            found.setdefault(child.id, LOCAL_LINK_S)
    return sorted(found.items(), key=lambda item: (item[1], item[0]))


# Passing states in which someone perceives nothing around them.
_UNAWARE = ("asleep", "sleeping", "unconscious", "knocked out", "senseless", "comatose")


def perceives(character: Character) -> bool:
    """Whether they take in what happens around them: not asleep or knocked out (W2)."""
    states = " ".join(s.name.casefold() for s in character.sheet.condition.states)
    return not any(word in states for word in _UNAWARE)


def characters_at(
    state: WorldState, place_id: str | None, *, within: bool = False
) -> list[Character]:
    """Living characters at a place (or anywhere inside it), by id."""
    if place_id is None:
        return []
    return [
        c
        for c in by_id(state.characters.values())
        if c.alive
        and c.location_id is not None
        and (c.location_id == place_id or (within and is_within(state, c.location_id, place_id)))
    ]


def together(state: WorldState, a: str | None, b: str | None) -> bool:
    """Whether two places are one spot to the people of a scene: the same place, or one inside
    the other (the well and the courtyard it stands in). A place the state doesn't name counts."""
    return a is None or b is None or is_within(state, a, b) or is_within(state, b, a)


def scene_ids(state: WorldState) -> list[str]:
    """W2. Who is in the player character's scene: the player character, those the scene shows
    (`SceneFrame.present_ids`) and those in its fight, chase or talks, who are there whatever
    the last scene's end listed."""
    encounter = state.scene.encounter
    facing = encounter.opponent_ids if encounter is not None else []
    return list(dict.fromkeys([state.player_id, *state.scene.present_ids, *facing]))


def onlookers(
    state: WorldState, place_id: str | None, involved: Iterable[str] = (), *, shown: bool = True
) -> list[Character]:
    """W2. The living characters who are there when something is done at a place, by id.
    `involved` are its doer, those it fell on or was aimed at, and whoever it brought on stage.

    A place can be a forest or a whole city, and being somewhere in it is not seeing what
    happens in one corner of it. So where the player character is, what is done by or to
    someone in their scene (`scene_ids`) is seen by the people in the scene and by those
    involved who are at the place: someone struck from afar isn't there. Nobody else the
    record puts at the place saw it, however many. What others do there outside the scene is
    seen by everyone at the place but the scene's people, who were in the scene. Everyone at
    the place is there when it is somewhere else, and where no scene has shown who is around
    (`shown` false: the player character has only just arrived, or it was done before a crowd).
    """
    there = characters_at(state, place_id)
    if not shown or not together(state, place_id, state.player.location_id or state.scene.place_id):
        return there
    cast = scene_ids(state)
    involved = list(dict.fromkeys(involved))
    if not any(i in cast for i in involved):
        return [c for c in there if c.id not in cast]
    people = [state.characters.get(i) for i in dict.fromkeys([*cast, *involved])]
    return by_id(
        c for c in people if c is not None and c.alive and together(state, c.location_id, place_id)
    )


def faction_seat(state: WorldState, faction: Faction) -> str | None:
    """Where a faction acts from: the outermost place it controls (then by id), else where its
    first living leader is, else its parent faction's seat."""
    seen: set[str] = set()
    current: Faction | None = faction
    while current is not None and current.id not in seen:
        seen.add(current.id)
        held = [p for p in by_id(state.places.values()) if p.controller_id == current.id]
        if held:
            return min(held, key=lambda p: (len(ancestors(state, p.id)), natural_key(p.id))).id
        for leader_id in current.leader_ids:
            leader = state.characters.get(leader_id)
            if leader is not None and leader.alive and leader.location_id in state.places:
                return leader.location_id
        current = state.factions.get(current.parent_id) if current.parent_id else None
    return None
