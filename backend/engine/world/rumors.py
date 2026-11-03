"""Rumors: word spreading place to place over in-world time, losing accuracy as it goes (W2, W13).

A rumor starts where something happened and moves along the map at the pace news really travels
(W10): with people on foot or by car, faster where the world has phones (G6). Each hop loses some
accuracy; a retelling that strays far enough becomes its own version, which may be wrong. Everyone
at a place hears it when it arrives. Those who believe it react (W4), factions there learn of it
(W3, W5), and the player hears it too if they are there, marked unconfirmed (C6).
"""

from engine.state.records import Deed, EventStatus, PendingEvent, Rumor
from engine.state.world import WorldState
from engine.world.geography import characters_at, news_neighbours, region_of
from engine.world.knowledge import (
    character_learns,
    faction_learns,
    in_faction,
    region_learns,
)
from engine.world.scheduling import Kind, World, by_id, schedule
from engine.world.tuning import (
    ACCURACY_LOSS,
    BELIEVED_FROM,
    CHATTER_S,
    GARBLED_BELOW,
    LOYAL_AFFINITY,
    NEWS_FACTOR,
    NEWS_FACTOR_INSTANT,
    NEWS_MIN_S,
)


def start_rumor(
    w: World,
    *,
    text: str,
    is_true: bool,
    place_id: str | None,
    hops: int,
    deed: Deed | None = None,
    about_ids: list[str] | None = None,
    accuracy: int = 90,
    heard_by: list[str] | None = None,
) -> Rumor:
    """A rumor starts at a place, heard by those given, and sets off to spread (W2)."""
    state = w.state
    rumor = Rumor(
        id=state.new_id("rumor"),
        text=text,
        is_true=is_true,
        accuracy=max(0, min(100, accuracy)),
        deed_id=deed.id if deed else None,
        about_ids=list(dict.fromkeys(about_ids or [])),
        origin_place_id=place_id,
        reached_place_ids=[place_id] if place_id else [],
        started_s=w.at_s,
        timeline_id=state.timeline_id,
    )
    state.rumors[rumor.id] = rumor
    for character_id in dict.fromkeys(heard_by or []):
        news = not heard_before(state, character_id, rumor, deed)
        rumor.heard_at.setdefault(character_id, w.at_s)
        if believes(state, character_id, rumor, rumor.accuracy):
            rumor.believed_by.append(character_id)
            if news and names_actor(rumor, deed):
                character_learns(w, character_id, deed, weight=rumor.accuracy / 100)
    if place_id is not None:
        spread(w, rumor, place_id, hops_left=hops, accuracy=rumor.accuracy, first=True)
    return rumor


def names_actor(rumor: Rumor, deed: Deed | None) -> bool:
    """Whether the rumor rightly says who did the deed."""
    return deed is not None and rumor.is_true and deed.actor_id in rumor.about_ids


def knows_doer(state: WorldState, character_id: str, deed: Deed) -> bool:
    """Whether someone knows who did a deed: they did it, saw it, were told, or heard a rumor
    that rightly names the doer."""
    return character_id in deed.known_by or any(
        character_id in r.heard_at and names_actor(r, deed)
        for r in state.rumors.values()
        if r.deed_id == deed.id
    )


def believes(state: WorldState, character_id: str, rumor: Rumor, accuracy: int) -> bool:
    """A hearer believes a rumor that is accurate enough, unless it accuses someone they are
    devoted to."""
    if accuracy < BELIEVED_FROM:
        return False
    character = state.characters.get(character_id)
    if character is None:
        return False
    for about in rumor.about_ids:
        attitude = character.sheet.disposition.attitudes.get(about)
        if attitude is not None and attitude.affinity >= LOYAL_AFFINITY:
            return False
    return True


def spread(
    w: World, rumor: Rumor, place_id: str, *, hops_left: int, accuracy: int, first: bool = False
) -> None:
    """Send a rumor on from a place to the places next to it it hasn't reached."""
    if hops_left <= 0:
        return
    state = w.state
    factor = NEWS_FACTOR_INSTANT if state.bible.travel.instant_messages else NEWS_FACTOR
    chatter = w.between(CHATTER_S, "chatter", rumor.id, place_id) if first else 0
    on_the_way = {
        e.payload.get("place_id")
        for e in state.pending_events.values()
        if e.kind == Kind.RUMOR
        and e.status is EventStatus.PENDING
        and e.payload.get("rumor_id") == rumor.id
    }
    for next_id, trip_s in news_neighbours(state, place_id):
        if next_id in rumor.reached_place_ids or next_id in on_the_way:
            continue
        loss = w.between(ACCURACY_LOSS, "loss", rumor.id, next_id)
        delay = chatter + max(NEWS_MIN_S, int(trip_s * factor))
        schedule(
            w,
            Kind.RUMOR,
            w.at_s + delay,
            title=f"Word reaches {state.places[next_id].name}: {rumor.text}",
            subject_ids=list(rumor.about_ids),
            place_id=next_id,
            payload={
                "rumor_id": rumor.id,
                "place_id": next_id,
                "hops_left": hops_left - 1,
                "accuracy": max(0, accuracy - loss),
            },
        )


def _garbled(w: World, rumor: Rumor, deed: Deed | None, accuracy: int) -> Rumor:
    """The version a retelling turns into once it strays far from what happened (W2): it no
    longer names the doer, so it is no longer true. One per rumor, reused as it spreads."""
    state = w.state
    text = f"A garbled account goes round: {rumor.text}"
    about = [i for i in rumor.about_ids if deed is None or i != deed.actor_id]
    for other in by_id(state.rumors.values()):
        if other.deed_id == rumor.deed_id and other.text == text and other.id != rumor.id:
            return other
    variant = Rumor(
        id=state.new_id("rumor"),
        text=text,
        is_true=False,
        accuracy=accuracy,
        deed_id=rumor.deed_id,
        about_ids=about,
        origin_place_id=rumor.origin_place_id,
        reached_place_ids=list(rumor.reached_place_ids),
        started_s=w.at_s,
        timeline_id=state.timeline_id,
    )
    state.rumors[variant.id] = variant
    return variant


def heard_before(state: WorldState, character_id: str, rumor: Rumor, deed: Deed | None) -> bool:
    """Whether the rumor is old news to them: they heard it, or it names a doer they already
    know, or it tells no more than another rumor about the same deed they heard."""
    if character_id in rumor.heard_at:
        return True
    if names_actor(rumor, deed):
        return knows_doer(state, character_id, deed)
    return rumor.deed_id is not None and any(
        character_id in other.heard_at
        for other in state.rumors.values()
        if other.deed_id == rumor.deed_id and other.id != rumor.id
    )


def on_rumor(w: World, event: PendingEvent) -> None:
    """A rumor reaches a place: everyone there hears it, believers react, the factions that hold
    the place learn of it, and it travels on."""
    state = w.state
    rumor = state.rumors.get(str(event.payload.get("rumor_id")))
    place_id = event.payload.get("place_id")
    if rumor is None or place_id not in state.places or place_id in rumor.reached_place_ids:
        return
    deed = state.deeds.get(rumor.deed_id) if rumor.deed_id else None
    accuracy = int(event.payload.get("accuracy", rumor.accuracy))
    if accuracy < GARBLED_BELOW <= rumor.accuracy and names_actor(rumor, deed):
        rumor = _garbled(w, rumor, deed, accuracy)
        if place_id in rumor.reached_place_ids:
            return
    reached_regions = {region_of(state, p) for p in rumor.reached_place_ids}
    reached_holders = {
        state.places[p].controller_id for p in rumor.reached_place_ids if p in state.places
    }
    rumor.reached_place_ids.append(place_id)
    weight = accuracy / 100
    attributed = names_actor(rumor, deed)

    for character in characters_at(state, place_id):
        if heard_before(state, character.id, rumor, deed):
            continue
        rumor.heard_at[character.id] = w.at_s
        if not believes(state, character.id, rumor, accuracy):
            continue
        rumor.believed_by.append(character.id)
        if attributed:
            character_learns(w, character.id, deed, weight=weight)

    if attributed and accuracy >= BELIEVED_FROM:
        holder = state.places[place_id].controller_id
        if holder is not None:
            faction_learns(w, holder, deed, weight=weight)
        region = region_of(state, place_id)
        if region not in reached_regions:
            region_learns(w, region, deed, weight=weight)
    elif not rumor.is_true and accuracy >= BELIEVED_FROM:
        if state.places[place_id].controller_id not in reached_holders:
            blame(w, rumor, deed, place_id)

    spread(w, rumor, place_id, hops_left=int(event.payload.get("hops_left", 0)), accuracy=accuracy)


def blame(w: World, rumor: Rumor, deed: Deed | None, place_id: str | None) -> None:
    """W13: a wrong rumor that blames a faction turns the victims' factions against it, which
    can start a war between factions. It counts once per rumor, at the first place it reaches
    that the victims' faction holds."""
    state = w.state
    place = state.places.get(place_id) if place_id else None
    holder = place.controller_id if place else None
    if deed is None or holder is None:
        return
    blamed = [i for i in rumor.about_ids if i in state.factions and i != holder]
    harmed = any(in_faction(state, v, holder) for v in deed.victim_ids)
    if not blamed or not harmed:
        return
    faction = state.factions[holder]
    for other in blamed:
        faction.relations[other] = max(-100, faction.relations.get(other, 0) - 10 * deed.severity)
