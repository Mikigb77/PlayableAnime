"""Where things are and how long it takes to get between them (W7, W10).

Places record rough travel times to their neighbours (`Place.routes`). A place inside another (a
bar in a city) is `LOCAL_LINK_S` from it when no route says otherwise, so two buildings in one
city are a short walk apart. A region of its own (a city, a village, a kingdom) has no such link
to the place it sits in: two cities in one kingdom are as far apart as their routes say, however
close each is to "the kingdom". A route between two places is what the trip between them takes.
"""

import heapq

from engine.invariants import ancestry
from engine.state.cast import Character, Faction
from engine.state.world import WorldState, natural_key
from engine.world.scheduling import by_id
from engine.world.tuning import LOCAL_LINK_S, REGION_KINDS


def ancestors(state: WorldState, place_id: str | None) -> list[str]:
    """The place and the places it sits in, nearest first."""
    return ancestry(state.places, place_id)


def is_within(state: WorldState, place_id: str | None, area_id: str | None) -> bool:
    """Whether `place_id` is `area_id` or somewhere inside it."""
    return area_id is not None and area_id in ancestors(state, place_id)


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


def travel_s(state: WorldState, from_id: str | None, to_id: str | None) -> int | None:
    """Rough travel time between two places, or None when nothing on the map connects them
    (W10). A route between the two is what it takes; otherwise the quickest way over routes and
    the short walks between a place and the one it sits in."""
    if from_id is None or to_id is None or from_id not in state.places or to_id not in state.places:
        return None
    if from_id == to_id:
        return 0
    routes = _route_graph(state)
    if to_id in routes[from_id]:
        return routes[from_id][to_id]
    graph = _travel_graph(state, routes)
    best: dict[str, int] = {from_id: 0}
    frontier: list[tuple[int, str]] = [(0, from_id)]
    while frontier:
        cost, pid = heapq.heappop(frontier)
        if pid == to_id:
            return cost
        if cost > best.get(pid, cost):
            continue
        for nxt, step in sorted(graph[pid].items()):
            total = cost + step
            if total < best.get(nxt, total + 1):
                best[nxt] = total
                heapq.heappush(frontier, (total, nxt))
    return None


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
