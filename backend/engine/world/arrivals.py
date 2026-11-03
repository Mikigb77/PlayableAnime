"""Reports reaching factions, and answers arriving (W4, W5, W10, W11).

A witness's report reaches a faction when the witness could really have got there, or called
(W10). Then the faction learns of the deed (W3, W5, W11). An answer that sends people arrives
where they believe the target to be: if the target is there, it needs them and the scene starts
there (the guards kick in the door at 3 a.m.); if not, they search, and may track the target
down later. Answers that don't send anyone (a bounty, a coalition, keeping clear) change the
world off-screen, and the player runs into them in later scenes.
"""

from engine.state.cast import FactionStatus
from engine.state.records import Fact, FactKind, Origin, OriginKind, PendingEvent
from engine.world.answers import ANSWER_TEXT, ARRIVING, Answer, members, schedule_answer
from engine.world.discovery import attributed, attribution_odds, name_the_doer
from engine.world.geography import characters_at, faction_seat, is_within
from engine.world.knowledge import faction_learns, shift_attitude
from engine.world.rumors import start_rumor
from engine.world.scheduling import World, by_id
from engine.world.tuning import FIND_ODDS, HUNT_ATTEMPTS, SEARCH_S

COALITION_BOOST = 20
AVOID_FEAR = 10


def on_report(w: World, event: PendingEvent) -> None:
    """A witness reaches a faction with what they saw (W11)."""
    state = w.state
    deed = state.deeds.get(str(event.payload.get("deed_id")))
    faction_id = str(event.payload.get("faction_id"))
    witness = state.characters.get(str(event.payload.get("witness_id")))
    if deed is None or faction_id not in state.factions:
        return
    if witness is not None and witness.alive and event.payload.get("moves") and event.place_id:
        witness.location_id = event.place_id
    faction_learns(w, faction_id, deed)


def _fact(w: World, text: str, known_by: list[str], subject_ids: list[str], ref: str) -> None:
    state = w.state
    fact = Fact(
        id=state.new_id("fact"),
        text=text,
        kind=FactKind.OBSERVATION,
        importance=3,
        subject_ids=list(dict.fromkeys(subject_ids)),
        known_by=list(dict.fromkeys(known_by)),
        turn=w.ctx.turn,
        world_s=w.at_s,
        timeline_id=state.timeline_id,
        origin=Origin(kind=OriginKind.EVENT, ref_id=ref),
    )
    state.facts[fact.id] = fact


def on_answer(w: World, event: PendingEvent) -> bool:
    """An answer comes due. Returns whether it needs the player: people came for the player
    and found them where they came."""
    state = w.state
    payload = event.payload
    answer = Answer(str(payload.get("answer")))
    faction = state.factions.get(str(payload.get("faction_id")))
    avenger = state.characters.get(str(payload.get("avenger_id")))
    target = state.characters.get(str(payload.get("target_id")))
    deed = state.deeds.get(str(payload.get("deed_id")))
    source_name = faction.name if faction else avenger.name if avenger else "someone"
    insiders = [c.id for c in members(state, faction.id)] if faction else []
    if avenger is not None:
        insiders.append(avenger.id)
    gone = (faction is not None and faction.status is FactionStatus.DESTROYED) or (
        avenger is not None and not avenger.alive
    )
    if target is None or not target.alive or gone:
        return False
    text = ANSWER_TEXT[answer].format(target=target.name)

    if answer not in ARRIVING:
        _off_screen(w, event, answer, faction, target, insiders, f"{source_name} {text}.")
        return False

    destination = event.place_id
    if destination is not None and is_within(state, target.location_id, destination):
        here = [c.id for c in characters_at(state, destination, within=True)]
        _fact(w, f"{source_name} {text}.", [*insiders, *here], [target.id], event.id)
        if answer is Answer.INVESTIGATE and deed is not None:
            _look_closer(w, deed)
        return target.id == state.player_id

    # They came and the target wasn't there.
    place = state.places.get(destination) if destination else None
    where = f" at {place.name}" if place else ""
    _fact(
        w,
        f"{source_name} came looking for {target.name}{where} and found them gone.",
        [*insiders, *(c.id for c in characters_at(state, destination))],
        [target.id],
        event.id,
    )
    if answer is Answer.INVESTIGATE:
        if deed is not None:
            _look_closer(w, deed)
        return False
    attempt = int(payload.get("attempt", 0)) + 1
    if attempt >= HUNT_ATTEMPTS or target.location_id is None:
        return False
    found = w.roll("hunt", event.id).chance(FIND_ODDS * 0.75 ** (attempt - 1))
    next_place = target.location_id if found else destination
    follow = schedule_answer(
        w,
        answer,
        target_id=target.id,
        destination_id=next_place,
        tier=int(payload.get("tier", 0)),
        deed=deed,
        faction=faction,
        avenger=avenger,
        attempt=attempt,
    )
    # Searching takes time on top of the trip.
    follow.due_s += w.between(SEARCH_S, "search", event.id)
    return False


def _look_closer(w: World, deed) -> None:
    """Investigators at the scene are another chance to name the doer (W13)."""
    if attributed(w.state, deed) or not deed.traces:
        return
    if w.roll("investigation", deed.id).chance(attribution_odds(deed.traces, 0)):
        name_the_doer(w, deed)


def _off_screen(w: World, event, answer, faction, target, insiders, text) -> None:
    state = w.state
    if answer is Answer.BOUNTY and faction is not None:
        where = faction_seat(state, faction) or target.location_id
        start_rumor(
            w,
            text=text,
            is_true=True,
            place_id=where,
            hops=4,
            about_ids=[target.id, faction.id],
            accuracy=90,
            heard_by=[c.id for c in characters_at(state, where)],
        )
    elif answer is Answer.COALITION and faction is not None:
        for other in by_id(state.factions.values()):
            if other.id == faction.id or other.status is FactionStatus.DESTROYED:
                continue
            if other.threat >= 2 or other.player_reputation.fear >= 40:
                for a, b in ((faction, other), (other, faction)):
                    a.relations[b.id] = min(100, a.relations.get(b.id, 0) + COALITION_BOOST)
    elif answer is Answer.AVOID and faction is not None:
        held = [p.id for p in by_id(state.places.values()) if p.controller_id == faction.id]
        for place_id in held:
            state.places[place_id].mood = f"wary; people keep clear of {target.name}"
        for member_id in insiders:
            if member_id in state.characters:
                shift_attitude(state.characters[member_id], target.id, fear=AVOID_FEAR)
    _fact(w, text, insiders, [target.id], event.id)
