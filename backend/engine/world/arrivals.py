"""Answers arriving (W4, W5, W10, W11).

An answer that sends people arrives where they believe the target to be: if the target is there,
it needs them and the scene starts there (the guards kick in the door at 3 a.m.); if not, they
search, and may track the target down later. Someone who comes on their own account is at that
place from then on, on record. Answers that don't send anyone (a bounty, a
coalition, keeping clear) change the world off-screen, and the player runs into them in later
scenes. What sets an answer going is a faction learning of a deed, which a witness's report
brings (`engine.world.carriers`).

Two answers are steps on the way to knowing (W4, W11, `engine.world.knowledge`). Those who came
to look into a crime ask whoever saw it and is still there to tell, then read what it left
behind, and come to arrest only once that gives them the doer. Someone who came to face the doer
with what they were told comes for revenge after, unless by then they are too afraid of the
doer or no longer think ill of them.
"""

from engine.state.cast import Character, Faction, FactionStatus
from engine.state.records import Deed, Fact, FactKind, Origin, OriginKind, PendingEvent
from engine.state.world import natural_key
from engine.world.answers import (
    ANSWER_TEXT,
    ARRIVING,
    Answer,
    members,
    schedule_answer,
    schedule_revenge,
)
from engine.world.carriers import carries
from engine.world.discovery import attribution_odds, name_the_doer, out
from engine.world.geography import characters_at, faction_seat, is_within
from engine.world.knowledge import faction_learns, shift_attitude
from engine.world.rumors import start_rumor
from engine.world.scheduling import World, by_id, cancel
from engine.world.telling import bounty
from engine.world.tuning import (
    FIND_ODDS,
    FORGIVEN_AFFINITY,
    HUNT_ATTEMPTS,
    SEARCH_S,
    SILENT_FEAR,
    TRACE_FINDING_WEIGHT,
)

COALITION_BOOST = 20
AVOID_FEAR = 10


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
    if avenger is not None and _lets_it_rest(avenger, target, answer, faced=payload.get("faced")):
        cancel(w, event)
        return False
    text = ANSWER_TEXT[answer].format(target=target.name)

    if answer not in ARRIVING:
        _off_screen(w, event, answer, faction, target, insiders, f"{source_name} {text}.")
        return False

    destination = event.place_id
    if avenger is not None and destination in state.places:
        # Whoever comes is there now, on record, whether or not they find who they came for:
        # the scene that meets them has them at its place (W4, W10).
        avenger.location_id = destination
    if destination is not None and is_within(state, target.location_id, destination):
        here = [c.id for c in characters_at(state, destination, within=True)]
        _fact(w, f"{source_name} {text}.", [*insiders, *here], [target.id], event.id)
        if answer is Answer.INVESTIGATE and deed is not None:
            _look_closer(w, deed, faction)
        if answer is Answer.CONFRONT and avenger is not None and deed is not None:
            # They have put it to the doer's face. What they do about it comes after (W4).
            schedule_revenge(w, avenger, deed, faced=True)
        return target.id == state.player_id

    # They came and the target wasn't there.
    place = state.places.get(destination) if destination else None
    where = f" at {place.name}" if place else ""
    there = [c.id for c in characters_at(state, destination)]
    if answer is Answer.INVESTIGATE:
        # They came for what happened, not for anyone: they have nobody to look for yet.
        _fact(w, f"{source_name} {text}{where}.", [*insiders, *there], [], event.id)
        if deed is not None:
            _look_closer(w, deed, faction)
        return False
    _fact(
        w,
        f"{source_name} came looking for {target.name}{where} and found them gone.",
        [*insiders, *there],
        [target.id],
        event.id,
    )
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
    if payload.get("faced"):
        follow.payload["faced"] = True
    # Searching takes time on top of the trip.
    follow.due_s += w.between(SEARCH_S, "search", event.id)
    return False


def _lets_it_rest(
    avenger: Character, target: Character, answer: Answer, *, faced: object = None
) -> bool:
    """W4. Whether someone who was coming to face the doer, or for revenge after they had,
    comes no more: by now they are too afraid of the doer, or no longer think ill of them.
    Revenge for what they saw, or for what is beyond one person's word, isn't called off."""
    if answer is not Answer.CONFRONT and not (answer is Answer.REVENGE and faced):
        return False
    toward = avenger.attitude_toward(target.id)
    return toward.fear >= SILENT_FEAR or toward.affinity >= FORGIVEN_AFFINITY


def _look_closer(w: World, deed: Deed, faction: Faction | None) -> None:
    """Those who came to look into it find out who did it, or don't (W11, W13). They ask
    whoever saw it and is still there, able and willing to tell them: a witness's word. Failing
    that they read what it left behind, which may name the doer, to them and, where nobody has
    been named yet, to everyone."""
    state = w.state
    if faction is not None and faction.id in deed.known_by_factions:
        return
    if faction is not None:
        for witness_id in sorted(deed.witness_ids, key=natural_key):
            witness = state.characters.get(witness_id)
            there = witness is not None and is_within(state, witness.location_id, deed.place_id)
            if there and carries(state, witness, faction.id, deed):
                faction_learns(w, faction.id, deed)
                return
    if not deed.traces:
        return
    if not w.roll("investigation", deed.id).chance(attribution_odds(state, deed, 0)):
        return
    if not out(state, deed):
        name_the_doer(w, deed)
    if faction is not None:
        faction_learns(w, faction.id, deed, weight=TRACE_FINDING_WEIGHT)


def _off_screen(w: World, event, answer, faction, target, insiders, text) -> None:
    state = w.state
    if answer is Answer.BOUNTY and faction is not None:
        seat = faction_seat(state, faction)
        where = seat or target.location_id
        present = [c.id for c in characters_at(state, where)]
        start_rumor(
            w,
            # S10: a rumor is kept as it is told, so it is told in the story's language.
            text=bounty(faction.name, target.name, w.ctx.settings.language),
            is_true=True,
            place_id=where,
            hops=4,
            about_ids=[target.id, faction.id],
            accuracy=90,
            heard_by=present,
            # Those at the seat when the price is set know it is so (C6); elsewhere it is talk.
            seen_by=present if seat else [],
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
