"""The wider world moves over the years (W6, W7): wars between factions come to a head.

"If you come back after ten years, two rival kingdoms have already fought a battle: maybe one
of them fell and the other is the one reigning, or both fell" (Miki, 2026-11-13), and "if a
month went by, obviously there is no time for such things". So nothing here is timed in turns
(W10), and nothing is made to happen: a war has a chance in one year of coming to a head,
which gives the chance over the stretch a tick covers.

Two factions are at war while either's stance toward the other is `WAR_AT` or worse. The world
keeps each such pair's time (`WorldState.strife_s`): when it first saw them at war, and then
when they last fought it out. A war comes to a head no sooner than `WAR_PAUSE_S` after that,
and from then on at `WAR_RATE` a year.

How it ends follows the facts before any throw (A2): each side's strength is the strongest
blow it can strike (`answers.faction_might`), a step less while it is weakened or rebuilding.
A side `WAR_SURE` steps above the other wins with no throw, and the other falls. Closer than
that a seeded throw decides (A3), each step worth `WAR_EDGE`, and an even fight may leave both
the weaker and neither the winner. A side that loses is weakened and loses the land nearest
the winner. It falls instead when it was weak already, or when it lost the last round of this
war too: the winner takes what it held. Two sides that wear each other down twice running, or
while both are weak, both fall, and what they held is nobody's until a faction that can reach
it takes it. Land that changes hands is less steady for it and under occupation (W7). A
faction that fell may rise again from its survivors (W15a, `engine.world.cast`), so the years
can bring a fall and a return.

What stays the story's to tell: a faction the player character belongs to or leads is never
fought over by the world's dice, the place the player character is in never changes hands
behind their back, and a faction never falls while they stand on its land. Nobody is killed
off screen: a fallen faction's people live on as its survivors.

What changes is on the records it touches: a faction's status, who holds a place, how steady
it is. The news of it is a `WorldChange`, known at once to the player character when they
live near a place it touched or land of those it came to (`WAR_NEAR_S`), and otherwise news
to them (`unheard`). Word of it travels as a rumor (W2), in the story's language (S10). A
scene in a place it touched or that word of it has reached is handed it (`to_tell`), and they
know of it once a scene told it (`hear`), where a scene has told what its own words bear out
(`borne_out`), so Memory holds only what the story told (C6).
"""

from collections.abc import Iterable

from engine import naming
from engine.base import YEAR
from engine.state.cast import Activity, Faction, FactionStatus, Place, PlaceStatus
from engine.state.records import StatusChange, WorldChange, WorldChangeKind
from engine.state.world import WorldState, natural_key
from engine.world import telling
from engine.world.answers import faction_might, members
from engine.world.geography import ancestors, characters_at, faction_seat, is_within, travel_s
from engine.world.rumors import start_rumor
from engine.world.scheduling import World, by_id, over
from engine.world.tuning import (
    CHANGES_KEPT,
    SEIZE_RATE,
    WAR_AT,
    WAR_EDGE,
    WAR_NEAR_S,
    WAR_NEWS_HOPS,
    WAR_PAUSE_S,
    WAR_RATE,
    WAR_SPENT,
    WAR_SURE,
    WAR_UNREST,
    WAR_WASTE,
)

_WEAK = frozenset({FactionStatus.WEAKENED, FactionStatus.REBUILDING})


def pair_key(a_id: str, b_id: str) -> str:
    """Two factions as one key, whichever way round they are named."""
    return "|".join(sorted((a_id, b_id), key=natural_key))


def at_war(a: Faction, b: Faction) -> bool:
    """Whether two factions are at war: either's stance toward the other is `WAR_AT` or
    worse."""
    return a.relations.get(b.id, 0) <= WAR_AT or b.relations.get(a.id, 0) <= WAR_AT


def strength(state: WorldState, faction: Faction) -> int:
    """What a faction brings to a war (A2, A8): the strongest blow it can strike, a step less
    while it is weakened or rebuilding."""
    return faction_might(state, faction) - (1 if faction.status in _WEAK else 0)


def holdings(state: WorldState, faction_id: str) -> list[Place]:
    return [p for p in by_id(state.places.values()) if p.controller_id == faction_id]


def _storys(state: WorldState, faction: Faction) -> bool:
    """Whether a faction's wars are the story's to tell: the player character belongs to it
    or leads it."""
    you = state.player
    return you.id in faction.leader_ids or you.member_of(faction.id)


def _stands_on(state: WorldState, place: Place) -> bool:
    """Whether the player character is in a place, or in one that lies within it."""
    return is_within(state, state.player.location_id, place.id)


def wars(state: WorldState) -> list[tuple[Faction, Faction]]:
    """The wars the world may bring to a head, each pair once, in a stable order: two
    factions at war, neither destroyed, at least one of them active, and neither the player
    character's own."""
    factions = [
        f for f in by_id(state.factions.values()) if f.status is not FactionStatus.DESTROYED
    ]
    found = []
    for n, a in enumerate(factions):
        for b in factions[n + 1 :]:
            if not at_war(a, b) or _storys(state, a) or _storys(state, b):
                continue
            if Activity.ACTIVE in (a.activity, b.activity):
                found.append((a, b))
    return found


def strive(w: World, since_s: int) -> None:
    """The world's part in its wars and its empty lands, for the stretch from `since_s` to
    now: each war that has had its time may come to a head, once, and a place nobody holds
    may be taken."""
    state = w.state
    if w.at_s <= since_s:
        return
    current = set()
    for a, b in wars(state):
        if FactionStatus.DESTROYED in (a.status, b.status):
            continue  # it fell to another of its wars in this same stretch
        key = pair_key(a.id, b.id)
        current.add(key)
        # A war the world sees for the first time started no earlier than this stretch.
        marked = state.strife_s.setdefault(key, since_s)
        years = (w.at_s - max(since_s, marked + WAR_PAUSE_S)) / YEAR
        if years > 0 and w.roll("war", key).chance(over(WAR_RATE, years)):
            _campaign(w, a, b)
            state.strife_s[key] = w.at_s
    # A pair no longer at war keeps no time: a new war between them starts its own.
    for key in [k for k in state.strife_s if k not in current]:
        del state.strife_s[key]
    years = (w.at_s - since_s) / YEAR
    for place in by_id(state.places.values()):
        if place.controller_id is not None or _stands_on(state, place):
            continue
        if _lost_in_war(state, place) and w.roll("seize", place.id).chance(over(SEIZE_RATE, years)):
            _seize(w, place)
    _prune(state)


# --- a war comes to a head ---------------------------------------------------------------------


def _campaign(w: World, a: Faction, b: Faction) -> None:
    """Two factions fight it out. The facts decide first (A2): a side `WAR_SURE` steps
    stronger wins, and the other falls. Closer than that a throw decides, and an even fight
    may leave both the weaker. Whoever loses while weak, or for the second time running,
    falls."""
    state = w.state
    key = pair_key(a.id, b.id)
    gap = strength(state, a) - strength(state, b)
    stream = w.roll("campaign", key, state.strife_s.get(key, 0))
    last = _last_round(state, a, b)
    if abs(gap) >= WAR_SURE:
        winner, loser = (a, b) if gap > 0 else (b, a)
    else:
        if gap == 0 and stream.chance(WAR_SPENT):
            _spent(w, a, b, again=last is not None and last.kind is WorldChangeKind.SPENT)
            return
        a_wins = stream.chance(0.5 + WAR_EDGE * gap)
        winner, loser = (a, b) if a_wins else (b, a)
    lost_before = (
        last is not None
        and last.kind in (WorldChangeKind.BEATEN, WorldChangeKind.FELL)
        and last.faction_ids == [winner.id, loser.id]
    )
    falls = abs(gap) >= WAR_SURE or loser.status in _WEAK or lost_before
    held = holdings(state, loser.id)
    if falls and not any(_stands_on(state, p) for p in held):
        _fall(w, loser, f"Fell to {winner.name}.")
        for place in held:
            _change_hands(w, place, winner.id)
        _record(w, WorldChangeKind.FELL, [winner, loser], held)
        return
    lost = _nearest_land(state, loser, winner)
    _weaken(w, loser, f"Beaten by {winner.name}.")
    for place in lost:
        _change_hands(w, place, winner.id)
    _record(w, WorldChangeKind.BEATEN, [winner, loser], lost)


def _spent(w: World, a: Faction, b: Faction, *, again: bool) -> None:
    """Neither wins, and each is the weaker for it. Two that wore each other down the last
    time too (`again`), or that were both weak already, both fall, and what they held is
    nobody's."""
    state = w.state
    held = [*holdings(state, a.id), *holdings(state, b.id)]
    both_weak = a.status in _WEAK and b.status in _WEAK
    if (again or both_weak) and not any(_stands_on(state, p) for p in held):
        _fall(w, a, f"Destroyed in its war with {b.name}.")
        _fall(w, b, f"Destroyed in its war with {a.name}.")
        for place in held:
            _change_hands(w, place, None)
        _record(w, WorldChangeKind.BOTH_FELL, [a, b], held)
        return
    _weaken(w, a, f"Worn down by its war with {b.name}.")
    _weaken(w, b, f"Worn down by its war with {a.name}.")
    _record(w, WorldChangeKind.SPENT, [a, b], [])


def _last_round(state: WorldState, a: Faction, b: Faction) -> WorldChange | None:
    """How the two last fought it out on this timeline, if the record still holds it."""
    both = {a.id, b.id}
    rounds = [
        c
        for c in state.changes.values()
        if c.timeline_id == state.timeline_id and set(c.faction_ids) == both
    ]
    return max(rounds, key=lambda c: (c.world_s, natural_key(c.id)), default=None)


def _nearest_land(state: WorldState, loser: Faction, winner: Faction) -> list[Place]:
    """What a beaten side loses: of the land it holds beyond its seat, the place nearest the
    winner's seat by the map, with whatever of its own lies within it. Never where the player
    character stands, and nothing when its seat is all it has."""
    seat = faction_seat(state, loser)
    held = holdings(state, loser.id)
    open_to = [
        p
        for p in held
        if p.id != seat and not is_within(state, seat, p.id) and not _stands_on(state, p)
    ]
    if not open_to:
        return []
    front = faction_seat(state, winner)

    def away(place: Place) -> tuple[int, int, list]:
        far = travel_s(state, front, place.id)
        return (far is None, far or 0, natural_key(place.id))

    first = min(open_to, key=away)
    return [p for p in held if p.id == first.id or is_within(state, p.id, first.id)]


def _status(w: World, faction: Faction, status: FactionStatus, note: str) -> None:
    state = w.state
    before = faction.status
    faction.status = status
    faction.status_history.append(
        StatusChange(
            status=status.value,
            from_status=before.value,
            turn=w.ctx.turn,
            world_s=w.at_s,
            timeline_id=state.timeline_id,
            note=note,
        )
    )


def _weaken(w: World, faction: Faction, note: str) -> None:
    if faction.status is FactionStatus.INTACT:
        _status(w, faction, FactionStatus.WEAKENED, note)


def _fall(w: World, faction: Faction, note: str) -> None:
    """A faction is destroyed. Its people live on, as what could carry it on (W15a)."""
    left = [c.id for c in members(w.state, faction.id)]
    faction.survivors = list(dict.fromkeys([*faction.survivors, *left]))
    _status(w, faction, FactionStatus.DESTROYED, note)


def _change_hands(w: World, place: Place, holder_id: str | None) -> None:
    """A place has a new holder, or none (W7): it is less steady for it, and under occupation
    where someone took it. A ruined place stays ruined (C1)."""
    state = w.state
    place.controller_id = holder_id
    place.stability = max(0, place.stability - (WAR_WASTE if holder_id is None else WAR_UNREST))
    status = PlaceStatus.DAMAGED if holder_id is None else PlaceStatus.OCCUPIED
    if place.status in (PlaceStatus.RUINED, status):
        return
    before = place.status
    place.status = status
    place.status_history.append(
        StatusChange(
            status=status.value,
            from_status=before.value,
            turn=w.ctx.turn,
            world_s=w.at_s,
            timeline_id=state.timeline_id,
            note="Taken in a war." if holder_id else "Left to nobody by a war.",
        )
    )


# --- land nobody holds -------------------------------------------------------------------------


def _lost_in_war(state: WorldState, place: Place) -> bool:
    """Whether the last thing the world's wars did to a place was to leave it to nobody."""
    touched = [
        c
        for c in state.changes.values()
        if c.timeline_id == state.timeline_id and place.id in c.place_ids
    ]
    last = max(touched, key=lambda c: (c.world_s, natural_key(c.id)), default=None)
    return last is not None and last.kind is WorldChangeKind.BOTH_FELL


def _seize(w: World, place: Place) -> None:
    """A faction that can reach an empty place takes it: the active one whose seat is nearest
    by the map, never the player character's own."""
    state = w.state
    reach = []
    for faction in by_id(state.factions.values()):
        if faction.status is FactionStatus.DESTROYED or faction.activity is not Activity.ACTIVE:
            continue
        if _storys(state, faction):
            continue
        far = travel_s(state, faction_seat(state, faction), place.id)
        if far is not None:
            reach.append((far, natural_key(faction.id), faction))
    if not reach:
        return
    taker = min(reach, key=lambda r: r[:2])[2]
    _change_hands(w, place, taker.id)
    _record(w, WorldChangeKind.SEIZED, [taker], [place])


# --- the news of it (C6, W2) -------------------------------------------------------------------


def _record(
    w: World, kind: WorldChangeKind, factions: list[Faction], places: list[Place]
) -> WorldChange:
    """The news of a change: known at once to the player character when they live near a
    place it touched or land of those it came to, and news to them otherwise. Word of it
    starts where it happened and travels as a rumor (W2), in the story's language (S10)."""
    state = w.state
    you = state.player
    touched = [p.id for p in places]
    seats = [seat for f in factions if (seat := faction_seat(state, f)) is not None]
    origin = next(iter([*touched, *seats]), None)
    lands = [p.id for f in factions for p in holdings(state, f.id)]
    near = any(_near(state, you.location_id, i) for i in dict.fromkeys([*touched, *seats, *lands]))
    change = WorldChange(
        id=state.new_id("change"),
        kind=kind,
        faction_ids=[f.id for f in factions],
        place_ids=touched,
        origin_place_id=origin,
        turn=w.ctx.turn,
        world_s=w.at_s,
        timeline_id=state.timeline_id,
        known_by=[you.id] if near else [],
    )
    state.changes[change.id] = change
    if near:
        learn(state, change)
    if origin is not None:
        there = [c.id for c in characters_at(state, origin) if c.id != you.id]
        rumor = start_rumor(
            w,
            text=telling.world_change(state, change, w.ctx.settings.language),
            is_true=True,
            place_id=origin,
            hops=WAR_NEWS_HOPS,
            about_ids=[*change.faction_ids, *touched],
            accuracy=95,
            heard_by=there,
            seen_by=there,
        )
        change.rumor_id = rumor.id
    return change


def _near(state: WorldState, from_id: str | None, place_id: str) -> bool:
    if from_id is None:
        return False
    if is_within(state, from_id, place_id) or is_within(state, place_id, from_id):
        return True
    far = travel_s(state, from_id, place_id)
    return far is not None and far <= WAR_NEAR_S


def learn(state: WorldState, change: WorldChange) -> None:
    """The player character knows of a change: the turns of status it brought are known to
    them too, so Memory shows a fallen faction as fallen (C6, `visibility.believed_status`).
    Mutates `state`."""
    you = state.player_id
    if you not in change.known_by:
        change.known_by.append(you)
    records = [state.factions.get(i) for i in change.faction_ids]
    records += [state.places.get(i) for i in change.place_ids]
    for record in records:
        if record is None:
            continue
        for entry in record.status_history:
            if entry.world_s == change.world_s and entry.timeline_id == change.timeline_id:
                if you not in entry.known_by:
                    entry.known_by.append(you)
        if you not in record.known_by:
            record.known_by.append(you)


def hand_over(state: WorldState) -> None:
    """Someone else is the player character now (N6, `engine.succession.carry_on`). They grew
    up in this world: what came to a faction or a place they know of, they know. What the one
    before them had heard is nothing to them, and the rest is news to them as to anyone.
    Mutates `state`."""
    you = state.player_id
    for change in by_id(state.changes.values()):
        if change.timeline_id != state.timeline_id or you in change.known_by:
            continue
        records = [state.factions.get(i) for i in change.faction_ids]
        records += [state.places.get(i) for i in change.place_ids]
        if any(record is not None and you in record.known_by for record in records):
            learn(state, change)


def of(state: WorldState, record_id: str) -> list[WorldChange]:
    """The changes on this timeline that came to a faction or a place, oldest first."""
    found = [
        c
        for c in state.changes.values()
        if c.timeline_id == state.timeline_id and record_id in (*c.faction_ids, *c.place_ids)
    ]
    return sorted(found, key=lambda c: (c.world_s, natural_key(c.id)))


def unheard(state: WorldState) -> list[WorldChange]:
    """The changes on this timeline the player character hasn't heard of, oldest first."""
    found = [
        c
        for c in state.changes.values()
        if c.timeline_id == state.timeline_id and state.player_id not in c.known_by
    ]
    return sorted(found, key=lambda c: (c.world_s, natural_key(c.id)))


def touched(state: WorldState, change: WorldChange, place_id: str | None) -> bool:
    """Whether a change touched a place: one of its places is this one, lies within it or
    holds it."""
    return place_id is not None and any(
        is_within(state, place_id, p) or is_within(state, p, place_id) for p in change.place_ids
    )


def to_tell(state: WorldState, place_id: str | None) -> list[WorldChange]:
    """What a scene at a place can show or tell the player character of what they haven't
    heard: the changes that touched the place, and those word of which has reached it or a
    place it lies in, oldest first."""
    around = set(ancestors(state, place_id))
    if not around:
        return []
    found = []
    for change in unheard(state):
        rumor = state.rumors.get(change.rumor_id or "")
        reached = rumor is not None and around.intersection(rumor.reached_place_ids)
        if reached or touched(state, change, place_id):
            found.append(change)
    return found


def heard_in(state: WorldState, turn: int) -> list[WorldChange]:
    """What turn `turn` brought the wider world that the player character knows of already,
    living near it: oldest first."""
    found = [
        c
        for c in state.changes.values()
        if c.turn == turn and c.timeline_id == state.timeline_id and state.player_id in c.known_by
    ]
    return sorted(found, key=lambda c: (c.world_s, natural_key(c.id)))


def hear(state: WorldState, told: Iterable[str]) -> tuple[WorldState, list[str]]:
    """A scene told the player character of changes, by id, or they heard the rumor of one
    (`by_rumor`): they know of them now. Returns the state, a new one when anything changed,
    and the ids of the changes now known."""
    ids = [
        key
        for key in dict.fromkeys(told)
        if (c := state.changes.get(key)) is not None
        and c.timeline_id == state.timeline_id
        and state.player_id not in c.known_by
    ]
    if not ids:
        return state, []
    after = state.model_copy(deep=True)
    for key in ids:
        learn(after, after.changes[key])
    return after, ids


def borne_out(
    state: WorldState, told: Iterable[str], scene: str, place_id: str | None = None
) -> list[str]:
    """Of the changes a scene says it told, by id, what its words bear out (C6): a change is
    told where the scene names a faction or a place it came to (`naming.spoken_of`). The
    place the scene is in doesn't count, nor a place it lies in, and neither does whoever
    holds it, unless the change touched it: their names are there every day. So in the
    winner's city the fall of its enemy is told by naming the enemy or the land it lost, and
    in a town that changed hands by naming whoever holds it now. A word that could also mean
    something else, such as a third faction or the place the scene is in, names nothing.

    The narrator's list alone tells nothing: in the second live story of a homecoming
    (2026-11-13) it listed all the news of people's lives it was handed under a scene that
    said none of it (`lives.borne_out`)."""
    spot = place_id or state.player.location_id or state.scene.place_id
    around = ancestors(state, spot)
    holder = next(
        (h for p in around if p in state.places and (h := state.places[p].controller_id)), None
    )
    records: dict[str, list[str]] = {f.id: [f.name] for f in state.factions.values()}
    records |= {p.id: [p.name] for p in state.places.values()}
    spoken = naming.spoken_of(records, [scene])
    found = []
    for key in dict.fromkeys(told):
        change = state.changes.get(key)
        if change is None:
            continue
        everyday = {*around} if touched(state, change, spot) else {*around, holder}
        theirs = {*change.faction_ids, *change.place_ids} - everyday
        if any(whose <= theirs for whose in spoken):
            found.append(key)
    return found


def by_rumor(state: WorldState, rumor_id: str | None) -> list[str]:
    """The changes a rumor carries word of, by id."""
    if rumor_id is None:
        return []
    return [c.id for c in by_id(state.changes.values()) if c.rumor_id == rumor_id]


def _prune(state: WorldState) -> None:
    """Keep the latest `CHANGES_KEPT` changes: the record of what they did is on the factions
    and places themselves."""
    if len(state.changes) <= CHANGES_KEPT:
        return
    kept = sorted(state.changes.values(), key=lambda c: (c.world_s, natural_key(c.id)))
    for change in kept[: len(kept) - CHANGES_KEPT]:
        del state.changes[change.id]
