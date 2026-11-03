"""What follows once it is known who did a deed (W4, W11, W15).

Victims, families and witnesses react as people (W11). When a death or a grave harm is
attributed, word reaches the victims' family and friends wherever they are, at the pace news
travels, and they keep a grudge and may come for revenge (W4). Someone killed who mattered, with
nobody close left, may still find an avenger the world hadn't shown yet (W15).
"""

from engine.base import DAY
from engine.state.cast import Prominence
from engine.state.records import Deed, PendingEvent
from engine.world.cast import maybe_avenger
from engine.world.geography import travel_s
from engine.world.knowledge import FRIEND, character_learns, ties_of
from engine.world.norms import Nature, deed_nature
from engine.world.rumors import knows_doer
from engine.world.scheduling import Kind, World, pending, schedule
from engine.world.tuning import NEWS_FACTOR, NEWS_FACTOR_INSTANT, NEWS_MIN_S

# When nothing on the map connects the victim's kin to the place, word still gets there.
FAR_NEWS_S = 7 * DAY


def on_attributed(w: World, deed: Deed) -> None:
    """The doer of a harmful deed is known: send word to the victims' close ties, and look for
    an avenger where none is left."""
    state = w.state
    if deed_nature(deed) is not Nature.HARM or deed.severity < 3:
        return
    factor = NEWS_FACTOR_INSTANT if state.bible.travel.instant_messages else NEWS_FACTOR
    for victim_id in deed.victim_ids:
        victim = state.characters.get(victim_id)
        if victim is None:
            continue
        close = [(cid, tie) for cid, tie in ties_of(state, victim_id) if cid != deed.actor_id]
        for character_id, _ in close:
            if knows_doer(state, character_id, deed) or character_id == state.player_id:
                continue
            if pending(state, Kind.TIDINGS, deed_id=deed.id, character_id=character_id):
                continue
            where = state.characters[character_id].location_id
            trip = travel_s(state, deed.place_id, where)
            delay = FAR_NEWS_S if trip is None else max(NEWS_MIN_S, int(trip * factor))
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
            fell
            and victim.prominence is Prominence.KEY
            and not [c for c in close if c[1] >= FRIEND]
        ):
            maybe_avenger(w, deed, victim)


def on_tidings(w: World, event: PendingEvent) -> None:
    """Word of a death or a grave harm reaches someone close to the victim (W4)."""
    deed = w.state.deeds.get(str(event.payload.get("deed_id")))
    character_id = str(event.payload.get("character_id"))
    if deed is None or knows_doer(w.state, character_id, deed):
        return
    deed.known_by.append(character_id)
    character_learns(w, character_id, deed, weight=1.0)
