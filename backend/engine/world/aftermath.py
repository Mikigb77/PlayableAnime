"""What follows once it is known who did a deed (W4, W11, W15).

Victims, families and witnesses react as people (W11). When a death or a grave harm is
attributed, word reaches the victims' family and friends wherever they are, at the pace news
travels, from someone who knows (`knowledge.Grounds.TOLD`), also where talk of it got there
first. They keep a grudge, and come to face the doer with it, or for revenge where it is beyond
one person's word (W4). It reaches the victims' factions
too, and the factions those sit in: a kingdom learns who wiped out its army even where nobody
lived to report it (W5, W13). Someone killed who mattered, with nobody close left, may still find
an avenger the world hadn't shown yet (W15). A hunted beast's pack hears who killed it (G24).

A move in a romance that wrongs someone (W17) sends word to whoever it wronged, and to nobody
else: from an affair up, and only where someone could bring it, because it was done within a
day's travel of them (`HOME_NEWS_S`) or someone who saw it is tied to them. What is done far
from home, among strangers, reaches them only as talk, if it travels that far.
"""

from engine import bonds
from engine.base import DAY
from engine.state.cast import FactionStatus, Prominence
from engine.state.records import Deed, PendingEvent
from engine.state.world import WorldState
from engine.world.cast import maybe_avenger
from engine.world.geography import faction_seat, travel_s
from engine.world.knowledge import (
    COMRADE,
    FRIEND,
    Grounds,
    character_learns,
    closeness,
    faction_learns,
    ties_of,
    would_talk,
)
from engine.world.norms import Nature, deed_nature, is_beast, killed
from engine.world.scheduling import Kind, World, pending, schedule
from engine.world.telling import listing, struck_names
from engine.world.tuning import HOME_NEWS_S, NEWS_FACTOR, NEWS_FACTOR_INSTANT, NEWS_MIN_S

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
    if kind is Nature.ROMANCE:
        _tell_wronged(w, deed)
        return
    hunt = kind is Nature.HUNT
    if not hunt and (kind is not Nature.HARM or deed.severity < 3):
        return
    if deed.agreed and not killed(state, deed.victim_ids):
        return  # W1: inside terms both accepted, only a death is news to those close to them
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
            # Whoever has only heard talk of it is still owed word from someone who knows.
            if character_id in deed.known_by or character_id == state.player_id:
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
            and not deed.agreed  # W1: a death both accepted calls up no avenger of its own
            and victim.prominence is Prominence.KEY
            and not [c for c in close if c[1] >= FRIEND]
        ):
            maybe_avenger(w, deed, victim)
    _tell_factions(w, deed)


def _tell_wronged(w: World, deed: Deed) -> None:
    """W17. Word of a move in a romance sets out to whoever it wronged and doesn't know yet,
    from an affair up (`bonds.FACED_FROM`): a flirt that went nowhere is nobody's errand.
    Someone has to be able to bring it: it was done within `HOME_NEWS_S` of travel from them,
    where people know them, or someone who saw it and would talk is tied to them. They learn
    it from someone who knows (`Grounds.TOLD`), at the pace news travels (W10)."""
    state = w.state
    actor = state.characters.get(deed.actor_id)
    if actor is None or deed.severity < bonds.FACED_FROM:
        return
    voices = [
        state.characters[i]
        for i in deed.witness_ids
        if i in state.characters and would_talk(state, state.characters[i], deed)
    ]
    for wronged_id in deed.wronged_ids:
        person = state.characters.get(wronged_id)
        if person is None or not person.alive or wronged_id == state.player_id:
            continue
        if wronged_id in deed.known_by:
            continue
        if pending(state, Kind.TIDINGS, deed_id=deed.id, character_id=wronged_id):
            continue
        where = person.location_id
        trip = travel_s(state, deed.place_id, where)
        near = trip is not None and trip <= HOME_NEWS_S
        if not near and not any(closeness(state, v, wronged_id) >= COMRADE for v in voices):
            continue
        schedule(
            w,
            Kind.TIDINGS,
            w.at_s + _news_s(state, deed.place_id, where),
            title=f"Word of what {actor.name} did reaches {person.name}",
            subject_ids=[wronged_id, deed.actor_id],
            place_id=where,
            payload={"deed_id": deed.id, "character_id": wronged_id},
        )


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
    victims' factions (W5). Or word of a move in a romance reaches someone it wronged (W17)."""
    deed = w.state.deeds.get(str(event.payload.get("deed_id")))
    if deed is None:
        return
    faction_id = event.payload.get("faction_id")
    if faction_id is not None:
        faction_learns(w, str(faction_id), deed)
        return
    character_id = str(event.payload.get("character_id"))
    if character_id in deed.known_by:
        return
    deed.known_by.append(character_id)
    character_learns(w, character_id, deed, weight=1.0, grounds=Grounds.TOLD)
