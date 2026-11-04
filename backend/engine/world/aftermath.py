"""What follows once it is known who did a deed (W4, W11, W15).

Victims, families and witnesses react as people (W11). When a death or a grave harm is
attributed, word reaches the victims' family and friends wherever they are, at the pace news
travels, and they keep a grudge and may come for revenge (W4). It reaches the victims' factions
too, and the factions those sit in: a kingdom learns who wiped out its army even where nobody
lived to report it (W5, W13). Someone killed who mattered, with nobody close left, may still find
an avenger the world hadn't shown yet (W15). A hunted beast's pack hears who killed it (G24).
"""

from engine.base import DAY
from engine.state.cast import FactionStatus, Prominence
from engine.state.records import Deed, PendingEvent
from engine.state.world import WorldState
from engine.world.cast import maybe_avenger
from engine.world.geography import faction_seat, travel_s
from engine.world.knowledge import COMRADE, FRIEND, character_learns, faction_learns, ties_of
from engine.world.norms import Nature, deed_nature, is_beast
from engine.world.rumors import knows_doer
from engine.world.scheduling import Kind, World, pending, schedule
from engine.world.telling import listing, struck_names
from engine.world.tuning import NEWS_FACTOR, NEWS_FACTOR_INSTANT, NEWS_MIN_S

# When nothing on the map connects the victim's kin to the place, word still gets there.
FAR_NEWS_S = 7 * DAY


def _news_s(state: WorldState, from_id: str | None, to_id: str | None) -> int:
    factor = NEWS_FACTOR_INSTANT if state.bible.travel.instant_messages else NEWS_FACTOR
    trip = travel_s(state, from_id, to_id)
    return FAR_NEWS_S if trip is None else max(NEWS_MIN_S, int(trip * factor))


def victims_factions(state: WorldState, deed: Deed) -> list[str]:
    """The factions a deed's victims belong to, and the factions those sit in (G10), with any
    host it struck, such as an army, and the faction that host sits in. In a stable order."""
    found: list[str] = []
    starts: list[str] = [t for t in deed.target_ids if t in state.factions]
    for victim_id in deed.victim_ids:
        victim = state.characters.get(victim_id)
        if victim is not None:
            starts.extend(m.faction_id for m in victim.memberships)
    for faction_id in starts:
        current, seen = faction_id, set()
        while current in state.factions and current not in seen:
            seen.add(current)
            found.append(current)
            current = state.factions[current].parent_id
    return list(dict.fromkeys(found))


def on_attributed(w: World, deed: Deed) -> None:
    """The doer of a harmful deed is known: send word to the victims' close ties and their
    factions, and look for an avenger where none is left."""
    state = w.state
    kind = deed_nature(state, deed)
    hunt = kind is Nature.HUNT
    if not hunt and (kind is not Nature.HARM or deed.severity < 3):
        return
    for victim_id in deed.victim_ids:
        victim = state.characters.get(victim_id)
        if victim is None:
            continue
        least = COMRADE if hunt else FRIEND  # a beast's pack is its kin
        # Word of a person's death is talk, which beasts don't follow (G24); a pack learns of
        # its own.
        close = [
            (cid, tie)
            for cid, tie in ties_of(state, victim_id, least=least)
            if cid != deed.actor_id and (hunt or not is_beast(state, cid))
        ]
        for character_id, _ in close:
            if knows_doer(state, character_id, deed) or character_id == state.player_id:
                continue
            if pending(state, Kind.TIDINGS, deed_id=deed.id, character_id=character_id):
                continue
            where = state.characters[character_id].location_id
            delay = _news_s(state, deed.place_id, where)
            schedule(
                w,
                Kind.TIDINGS,
                w.at_s + delay,
                title=f"Word of what happened to {victim.name} reaches someone close to them",
                subject_ids=[character_id, victim_id, deed.actor_id],
                place_id=where,
                payload={"deed_id": deed.id, "character_id": character_id},
            )
        fell = not victim.alive
        if (
            not hunt
            and fell
            and victim.prominence is Prominence.KEY
            and not [c for c in close if c[1] >= FRIEND]
        ):
            maybe_avenger(w, deed, victim)
    _tell_factions(w, deed)


def _tell_factions(w: World, deed: Deed) -> None:
    """W5, W11, W13: word of who did it reaches the victims' factions at the pace news travels
    to where each acts from, unless they already know."""
    state = w.state
    hosts = [t for t in deed.target_ids if t in state.factions]
    whom = listing(struck_names(state, [*deed.victim_ids, *hosts]))
    what = f"what happened to {whom}" if whom else "what happened"
    for faction_id in victims_factions(state, deed):
        faction = state.factions[faction_id]
        if faction.status is FactionStatus.DESTROYED or faction_id in deed.known_by_factions:
            continue
        if deed.actor_id in faction.leader_ids:
            continue
        if pending(state, Kind.TIDINGS, deed_id=deed.id, faction_id=faction_id):
            continue
        seat = faction_seat(state, faction)
        schedule(
            w,
            Kind.TIDINGS,
            w.at_s + _news_s(state, deed.place_id, seat),
            title=f"Word of {what} reaches {faction.name}",
            subject_ids=[faction_id, *deed.victim_ids, deed.actor_id],
            place_id=seat,
            payload={"deed_id": deed.id, "faction_id": faction_id},
        )


def on_tidings(w: World, event: PendingEvent) -> None:
    """Word of a death or a grave harm reaches someone close to the victim (W4), or one of the
    victims' factions (W5)."""
    deed = w.state.deeds.get(str(event.payload.get("deed_id")))
    if deed is None:
        return
    faction_id = event.payload.get("faction_id")
    if faction_id is not None:
        faction_learns(w, str(faction_id), deed)
        return
    character_id = str(event.payload.get("character_id"))
    if knows_doer(w.state, character_id, deed):
        return
    deed.known_by.append(character_id)
    character_learns(w, character_id, deed, weight=1.0)
