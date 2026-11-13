"""Answers arriving (W4, W5, W10, W11).

An answer that sends people arrives where they believe the target to be: if the target is there,
it needs them and the scene starts there (the guards kick in the door at 3 a.m.); if not, they
search, and may track the target down later. Someone who comes on their own account is at that
place once they get there, on record, and goes back to where they came from afterwards
(`engine.world.returns`). Answers that don't send anyone (a bounty, a coalition, keeping clear)
change the world off-screen, and the player runs into them in later scenes. What sets an answer
going is a faction learning of a deed, which a witness's report brings
(`engine.world.carriers`).

Two answers are steps on the way to knowing (W4, W11, `engine.world.knowledge`). Those who came
to look into a crime ask whoever saw it and is still there to tell, then read what it left
behind, and come to arrest only once that gives them the doer. Someone who came to face the doer
with what they were told comes for revenge after, unless by then they are too afraid of the
doer or no longer think ill of them.

Someone a move in a romance wronged comes to have it out with whoever made it (W17), whatever
they still feel for them: only fear keeps them away. A partner whose heart is gone by then
(`bonds.LEAVES_UNDER`) has come to end it, and the romance is over on record from that moment,
by their doing. Nobody comes for revenge on their own partner. A rival does, after, for a
betrayal, unless they let it rest.
"""

from engine import bonds
from engine.state.cast import Character, Faction, FactionStatus
from engine.state.records import Deed, Fact, FactKind, Origin, OriginKind, PendingEvent
from engine.state.world import natural_key
from engine.world.answers import (
    ANSWER_TEXT,
    ARRIVING,
    ENDS_IT,
    HAVE_IT_OUT,
    Answer,
    members,
    schedule_answer,
    schedule_revenge,
)
from engine.world.carriers import carries
from engine.world.discovery import attribution_odds, name_the_doer, out
from engine.world.geography import characters_at, faction_seat, is_within
from engine.world.knowledge import faction_learns, partner_of, shift_attitude
from engine.world.returns import left
from engine.world.rumors import start_rumor
from engine.world.scheduling import World, by_id, cancel
from engine.world.telling import account, bounty
from engine.world.tuning import (
    ERRAND_STAY_S,
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
    # W17. Someone a move in a romance wronged, come to have it out with whoever made it.
    affair = avenger is not None and deed is not None and bool(deed.wronged_ids)
    if avenger is not None and _lets_it_rest(
        avenger, target, answer, faced=payload.get("faced"), affair=affair
    ):
        cancel(w, event)
        return False
    text = ANSWER_TEXT[answer].format(target=target.name)
    if affair and answer is Answer.CONFRONT:
        text = HAVE_IT_OUT.format(target=target.name)

    if answer not in ARRIVING:
        _off_screen(w, event, answer, faction, target, insiders, f"{source_name} {text}.")
        return False

    destination = event.place_id
    if (
        avenger is not None
        and avenger.location_id in state.places
        and target.location_id == avenger.location_id
        and not is_within(state, target.location_id, destination)
    ):
        # Whoever is already at the very place the one they are after is has found them,
        # wherever they had meant to look (A2).
        destination = event.place_id = avenger.location_id
    if avenger is not None and destination in state.places:
        # Whoever comes is there now, on record, whether or not they find who they came for:
        # the scene that meets them has them at its place (W4, W10). And they go back to
        # where they came from once they are done there (`engine.world.returns`).
        came_from, avenger.location_id = avenger.location_id, destination
        left(w, avenger, came_from, ERRAND_STAY_S)
    if destination is not None and is_within(state, target.location_id, destination):
        here = [c.id for c in characters_at(state, destination, within=True)]
        if affair and answer is Answer.CONFRONT:
            text, deed = _has_it_out(w, event, avenger, target, deed)
        _fact(w, f"{source_name} {text}.", [*insiders, *here], [target.id], event.id)
        if answer is Answer.INVESTIGATE and deed is not None:
            _look_closer(w, deed, faction)
        if answer is Answer.CONFRONT and avenger is not None and deed is not None:
            # They have put it to the doer's face. What they do about it comes after (W4):
            # over a romance, nothing from their own partner, and from a rival only for a
            # betrayal.
            rival = affair and not partner_of(state, avenger.id, target.id)
            if not affair or (rival and deed.severity >= bonds.BETRAYAL):
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
    avenger: Character,
    target: Character,
    answer: Answer,
    *,
    faced: object = None,
    affair: bool = False,
) -> bool:
    """W4. Whether someone who was coming to face the doer, or for revenge after they had,
    comes no more: by now they are too afraid of the doer, or no longer think ill of them.
    Revenge for what they saw, or for what is beyond one person's word, isn't called off.
    Someone a move in a romance wronged (`affair`, W17) comes to have it out however much they
    still like whoever made it: only fear keeps them away."""
    if answer is not Answer.CONFRONT and not (answer is Answer.REVENGE and faced):
        return False
    toward = avenger.attitude_toward(target.id)
    if affair and answer is Answer.CONFRONT:
        return toward.fear >= SILENT_FEAR
    return toward.fear >= SILENT_FEAR or toward.affinity >= FORGIVEN_AFFINITY


def _has_it_out(
    w: World, event: PendingEvent, partner: Character, target: Character, deed: Deed
) -> tuple[str, Deed]:
    """W17. Someone a move in a romance wronged has found whoever made it. Their own partner
    whose heart is under `bonds.LEAVES_UNDER` by now has come to end it: the romance is over
    on record, by their doing, and the event's title says so for the scene that tells it.
    Anyone else has it out with them and no more, and so does a wife or a husband where a
    marriage is for life (`bonds.for_life`): they stay married, with what is left of it.
    Returns what they came to do, and the deed it is over: the gravest of it they know by
    now."""
    state = w.state
    # What they have it out over is the gravest of it they know by now, the latest first.
    known = [
        d
        for d in state.deeds.values()
        if d.actor_id == deed.actor_id
        and d.timeline_id == deed.timeline_id
        and partner.id in d.wronged_ids
        and partner.id in d.known_by
    ]
    worst = max(known, key=lambda d: (d.severity, d.world_s, natural_key(d.id)), default=deed)
    told = account(state, worst)
    bond = bonds.live(state, partner.id, target.id)
    text = HAVE_IT_OUT.format(target=target.name)
    title = f"{partner.name} {text}, to hear it answered and not to attack: {told}"
    heart = partner.attitude_toward(target.id).attraction
    stays = bonds.for_life(state, partner.id, target.id)  # nobody leaves such a marriage
    if bond is not None and bond.stage.couple and heart < bonds.LEAVES_UNDER and not stays:
        bonds.end(
            bond,
            by_id=partner.id,
            how=f"{partner.name} ended it: {told}",
            turn=w.ctx.turn,
            world_s=w.at_s,
        )
        text = ENDS_IT.format(target=target.name)
        title = f"{partner.name} {text}: {told}"
    event.title = title
    # Memory files who came under the deed they came over (C6).
    event.payload["deed_id"] = worst.id
    return text, worst


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
        # It is set off screen: nobody shows it to the player character, even where they stand.
        # For them it is the talk of the place, heard once a scene tells it (W2, C6).
        present = [c.id for c in characters_at(state, where) if c.id != state.player_id]
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
