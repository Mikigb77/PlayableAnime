"""How factions and people answer a threat, scheduled at in-world times (W4, W5, W10, W11).

A faction's answer depends on its nature and situation, not on a fixed ladder: locals keep clear,
enforcers come to arrest, a harmed faction sends hunters or posts a bounty, a far weaker one
appeases, recruits or worships, one at war with someone else ignores the player or tries to use
them. It answers with what it really has: an elite champion only if it has someone who could be
one, and nobody is conjured to match the player (A9). The answer is a pending event due once the
faction has gathered and travelled (W10). The narrator dresses it in the world's form (G9).

How far an answer goes follows how sure they are who did it (W4, W5, `engine.world.knowledge`).
On talk alone nobody is sent to arrest, hunt or kill: those who keep the law come to look into
it. Someone close to the dead who has only one person's word for it comes to face the doer with
it first (`CONFRONT`), and for revenge only after.
"""

from enum import StrEnum

from engine.resolve.powers import might_with_powers
from engine.state.bible import Law, Zeal
from engine.state.cast import Character, Faction, FactionStatus
from engine.state.records import Deed, Origin, OriginKind, PendingEvent
from engine.state.world import WorldState
from engine.world.geography import faction_seat, is_within, region_of, travel_s
from engine.world.scheduling import Kind, World, by_id, cancel, pending, schedule
from engine.world.telling import account
from engine.world.tuning import ANSWER_GATHER_S, UNKNOWN_TRIP_S, WAR_AT, ZEAL_GATHER_FACTOR


class Answer(StrEnum):
    AVOID = "avoid"  # locals keep clear or flee
    ARREST = "arrest"  # those who keep the law come for the culprit (W11)
    INVESTIGATE = "investigate"  # they look into a crime with no known culprit
    BOUNTY = "bounty"
    HUNTERS = "hunters"
    CONFRONT = "confront"  # someone close to a victim comes to face the one they were told did it
    REVENGE = "revenge"  # one person's own vengeance (W4)
    ARMY = "army"
    ELITE = "elite"  # its strongest, if it has anyone strong enough
    COALITION = "coalition"
    APPEASE = "appease"
    RECRUIT = "recruit"
    WORSHIP = "worship"
    BRIBE = "bribe"
    ASSASSIN = "assassin"
    SEAL = "seal"  # an attempt to seal the player away, where the world has the means
    USE_AGAINST_RIVAL = "use_against_rival"
    IGNORE = "ignore"


# Answers that send people to where the target is; the rest happen off-screen.
ARRIVING = frozenset(
    {
        Answer.ARREST,
        Answer.INVESTIGATE,
        Answer.HUNTERS,
        Answer.CONFRONT,
        Answer.REVENGE,
        Answer.ARMY,
        Answer.ELITE,
        Answer.APPEASE,
        Answer.RECRUIT,
        Answer.WORSHIP,
        Answer.BRIBE,
        Answer.ASSASSIN,
        Answer.SEAL,
        Answer.USE_AGAINST_RIVAL,
    }
)

# Answers that set out to take, hurt or kill the target. Nobody sends one on talk alone (W5).
HOSTILE = frozenset(
    {
        Answer.ARREST,
        Answer.BOUNTY,
        Answer.HUNTERS,
        Answer.ARMY,
        Answer.ELITE,
        Answer.ASSASSIN,
        Answer.SEAL,
    }
)

# In the engine's plain words; the narrator tells it in the world's (G9).
ANSWER_TEXT = {
    Answer.AVOID: "keeps clear of {target}",
    Answer.ARREST: "comes to arrest {target}",
    Answer.INVESTIGATE: "comes to look into what happened",
    Answer.BOUNTY: "puts a price on {target}'s head",
    Answer.HUNTERS: "sends hunters after {target}",
    Answer.CONFRONT: "comes to face {target} over what {target} is said to have done",
    Answer.REVENGE: "comes for revenge on {target}",
    Answer.ARMY: "marches in force against {target}",
    Answer.ELITE: "sends its strongest against {target}",
    Answer.COALITION: "seeks allies against {target}",
    Answer.APPEASE: "sends envoys with gifts to appease {target}",
    Answer.RECRUIT: "comes to recruit {target}",
    Answer.WORSHIP: "comes to venerate {target}",
    Answer.BRIBE: "comes to buy {target} off",
    Answer.ASSASSIN: "sends an assassin after {target}",
    Answer.SEAL: "comes with the means to seal {target} away",
    Answer.USE_AGAINST_RIVAL: "comes to turn {target} against its rivals",
    Answer.IGNORE: "has other concerns than {target}",
}


# W17. Someone a move in a romance wronged comes to whoever made it, and what a partner whose
# heart is gone by then has come to say instead (`arrivals.on_answer`).
HAVE_IT_OUT = "comes to have it out with {target}"
ENDS_IT = "comes to tell {target} it is over between them"


def _might(state: WorldState, character: Character) -> int:
    """The might the world can measure them by (A8, W5): a light-speed time stop once the world
    could know of it, hidden strength as what it shows (G20), less any weakening."""
    return max(0, might_with_powers(state, character) - character.sheet.condition.weakened_tiers)


def members(state: WorldState, faction_id: str) -> list[Character]:
    """Living leaders and members of a faction, by id."""
    faction = state.factions.get(faction_id)
    leaders = set(faction.leader_ids) if faction else set()
    return [
        c
        for c in by_id(state.characters.values())
        if c.alive and (c.id in leaders or c.member_of(faction_id))
    ]


def faction_might(state: WorldState, faction: Faction, *, excluding: str | None = None) -> int:
    """The strongest blow it can really strike (A8): its mightiest living leader or member,
    leaving out the one it would strike at. A faction with nobody on record counts as ordinary
    people."""
    return max(
        (_might(state, c) for c in members(state, faction.id) if c.id != excluding),
        default=1,
    )


def actor_might(state: WorldState, character_id: str) -> int:
    character = state.characters.get(character_id)
    return _might(state, character) if character is not None else 1


def enforced_law(state: WorldState, faction_id: str) -> Law | None:
    """The law this faction enforces most zealously, if it keeps any (W11)."""
    order = {Zeal.HIGH: 0, Zeal.MEDIUM: 1, Zeal.LOW: 2}
    laws = [
        law
        for law in state.bible.laws
        if law.enforcer_faction_id == faction_id and law.zeal is not Zeal.NONE
    ]
    return min(laws, key=lambda law: (order[law.zeal], law.id)) if laws else None


def law_at(state: WorldState, faction_id: str, place_id: str | None) -> Law | None:
    """The law a faction keeps where something was done (W11): the one it enforces most
    zealously, if the place is within its reach, the region its seat sits in. Where the map
    doesn't place the faction, its law holds wherever the story is."""
    law = enforced_law(state, faction_id)
    faction = state.factions.get(faction_id)
    if law is None or faction is None or place_id is None:
        return law
    seat = faction_seat(state, faction)
    if seat is None or is_within(state, place_id, region_of(state, seat)):
        return law
    return None


def rival_at_war(state: WorldState, faction: Faction) -> str | None:
    """Another faction it is at war with, if any (relations of `WAR_AT` or worse)."""
    enemies = [
        fid
        for fid, stance in sorted(faction.relations.items())
        if stance <= WAR_AT
        and fid in state.factions
        and state.factions[fid].status is not FactionStatus.DESTROYED
    ]
    return enemies[0] if enemies else None


def choose_answer(
    w: World,
    faction: Faction,
    target_id: str,
    tier: int,
    *,
    enforcing: bool,
    harmed: bool,
    hostile: bool = True,
) -> Answer:
    """W5: weigh the answers that fit this faction's nature and situation, then draw one. With
    `hostile` false it has only heard talk, and none of the answers that take, hurt or kill is
    among them."""
    state = w.state
    if enforcing and hostile:
        return Answer.ARREST
    target_might = actor_might(state, target_id)
    gap = target_might - faction_might(state, faction, excluding=target_id)
    reputation = faction.player_reputation if target_id == state.player_id else None
    esteem = reputation.esteem if reputation else 0
    fear = reputation.fear if reputation else 0
    has_champion = any(
        _might(state, c) >= target_might - 1
        for c in members(state, faction.id)
        if c.id != target_id
    )
    extraordinary = not state.bible.grounded
    at_war = rival_at_war(state, faction) is not None

    weights: dict[Answer, float] = {}

    def add(answer: Answer, weight: float) -> None:
        weights[answer] = weights.get(answer, 0.0) + weight

    if tier <= 1:
        add(Answer.IGNORE, 3)
        add(Answer.AVOID, 2)
    if harmed:
        add(Answer.HUNTERS, 3 if gap <= 1 else 1)
        add(Answer.BOUNTY, 2)
        if gap >= 1:
            add(Answer.ASSASSIN, 2)
    if gap <= 0:
        add(Answer.HUNTERS, 2)
        add(Answer.BRIBE, 0.5)
    elif gap <= 2:
        add(Answer.BOUNTY, 2)
        add(Answer.ASSASSIN, 1)
        add(Answer.BRIBE, 1)
        if has_champion:
            add(Answer.ELITE, 3)
        if tier >= 4:
            add(Answer.ARMY, 2)
    else:
        add(Answer.APPEASE, 3)
        add(Answer.AVOID, 2)
        add(Answer.RECRUIT, 2)
        if tier >= 4:
            add(Answer.COALITION, 3)
        if extraordinary and tier >= 4:
            add(Answer.SEAL, 2)
        if fear >= 80 and esteem >= 0:
            add(Answer.WORSHIP, 2 if extraordinary else 0.5)
    if esteem >= 40:
        add(Answer.RECRUIT, 3)
        add(Answer.APPEASE, 1)
    if at_war:
        add(Answer.IGNORE, 2)
        add(Answer.USE_AGAINST_RIVAL, 2)
    if not hostile:
        weights = {answer: weight for answer, weight in weights.items() if answer not in HOSTILE}
    if not weights:
        add(Answer.AVOID, 1)
    options = sorted(weights, key=lambda a: a.value)
    return w.roll("answer", faction.id, target_id).weighted(options, [weights[a] for a in options])


def gather_s(w: World, answer: Answer, *labels: object, law: Law | None = None) -> int:
    seconds = w.between(ANSWER_GATHER_S[answer.value], "gather", *labels)
    if law is not None and answer in (Answer.ARREST, Answer.INVESTIGATE):
        seconds = int(seconds * ZEAL_GATHER_FACTOR[law.zeal.value])
    return seconds


def open_answer(
    state: WorldState,
    *,
    target_id: str,
    faction_id: str | None = None,
    avenger_id: str | None = None,
) -> PendingEvent | None:
    """The answer already on its way to this target from this faction or avenger, if any."""
    found = pending(
        state, Kind.ANSWER, target_id=target_id, faction_id=faction_id, avenger_id=avenger_id
    )
    return found[0] if found else None


def schedule_answer(
    w: World,
    answer: Answer,
    *,
    target_id: str,
    destination_id: str | None,
    tier: int,
    deed: Deed | None = None,
    faction: Faction | None = None,
    avenger: Character | None = None,
    attempt: int = 0,
    law: Law | None = None,
) -> PendingEvent:
    """Schedule an answer at the time it can really arrive: gathering, then travel from where the
    faction (or the avenger) is to where they believe the target to be (W10)."""
    state = w.state
    source_id = avenger.id if avenger else faction.id if faction else "world"
    origin_place = (
        avenger.location_id if avenger else faction_seat(state, faction) if faction else None
    )
    trip = travel_s(state, origin_place, destination_id) if answer in ARRIVING else 0
    if trip is None:
        # The map doesn't place them, or nothing on it joins the two: still not at once.
        trip = UNKNOWN_TRIP_S
    gather = gather_s(w, answer, source_id, target_id, attempt, law=law)
    target = state.characters.get(target_id)
    who = avenger.name if avenger else faction.name if faction else "someone"
    text = ANSWER_TEXT[answer].format(target=target.name if target else "them")
    if answer is Answer.CONFRONT and deed is not None:
        # The narrator has only the title to go by: what it is over, and that it is no attack.
        if deed.wronged_ids:
            text = HAVE_IT_OUT.format(target=target.name if target else "them")  # W17
        text = f"{text}, to hear it answered and not to attack: {account(state, deed)}"
    return schedule(
        w,
        Kind.ANSWER,
        w.at_s + gather + trip,
        title=f"{who} {text}",
        subject_ids=[i for i in (source_id, target_id) if i != "world"],
        place_id=destination_id if answer in ARRIVING else None,
        needs_player=answer in ARRIVING and target_id == state.player_id,
        payload={
            "answer": answer.value,
            "faction_id": faction.id if faction else None,
            "avenger_id": avenger.id if avenger else None,
            "target_id": target_id,
            "deed_id": deed.id if deed else None,
            "tier": tier,
            "attempt": attempt,
        },
        origin=Origin(kind=OriginKind.DEED, ref_id=deed.id) if deed else None,
    )


def answer_threat(
    w: World,
    faction: Faction,
    deed: Deed,
    tier: int,
    *,
    enforcing: bool,
    harmed: bool,
    hostile: bool = True,
) -> PendingEvent | None:
    """A faction answers a deed or a crossed threat tier, unless an answer of the same weight is
    already on its way. A much bigger threat replaces a smaller answer still under way, and
    knowing who did it ends a look into it. With `hostile` false it has only heard talk, and
    sends nobody to take, hurt or kill (W5)."""
    if faction.status is FactionStatus.DESTROYED:
        return None
    target_id = deed.actor_id
    existing = open_answer(w.state, target_id=target_id, faction_id=faction.id)
    if existing is not None:
        looking = existing.payload.get("answer") == Answer.INVESTIGATE.value
        if not (looking and hostile) and tier < int(existing.payload.get("tier", 0)) + 2:
            return None
        cancel(w, existing)
    answer = choose_answer(
        w, faction, target_id, tier, enforcing=enforcing, harmed=harmed, hostile=hostile
    )
    law = law_at(w.state, faction.id, deed.place_id) if enforcing else None
    return schedule_answer(
        w,
        answer,
        target_id=target_id,
        destination_id=deed.place_id,
        tier=tier,
        deed=deed,
        faction=faction,
        law=law,
    )


def look_into(w: World, faction: Faction, deed: Deed, law: Law | None) -> PendingEvent | None:
    """W11: those who keep the law come to look into a crime they can't yet lay at anyone's
    door: one found with nobody named for it, or one they have only heard talk of. Nothing
    when they already have an answer on its way to the doer."""
    if open_answer(w.state, target_id=deed.actor_id, faction_id=faction.id) is not None:
        return None
    return schedule_answer(
        w,
        Answer.INVESTIGATE,
        target_id=deed.actor_id,
        destination_id=deed.place_id,
        tier=0,
        deed=deed,
        faction=faction,
        law=law,
    )


def schedule_revenge(
    w: World, avenger: Character, deed: Deed, *, faced: bool = False
) -> PendingEvent | None:
    """W4: someone close to a victim comes for the one they are sure did it, later. With
    `faced`, they have put it to the doer's face first (`schedule_confrontation`)."""
    return _comes_for(w, Answer.REVENGE, avenger, deed, faced=faced)


def schedule_confrontation(w: World, accuser: Character, deed: Deed) -> PendingEvent | None:
    """W4: someone close to a victim who has one person's word for who did it comes to face them
    with it. What follows is theirs to decide once they have (`arrivals.on_answer`)."""
    return _comes_for(w, Answer.CONFRONT, accuser, deed)


def _comes_for(
    w: World, answer: Answer, avenger: Character, deed: Deed, *, faced: bool = False
) -> PendingEvent | None:
    target_id = deed.actor_id
    if avenger.id == target_id or not avenger.alive:
        return None
    if open_answer(w.state, target_id=target_id, avenger_id=avenger.id) is not None:
        return None
    target = w.state.characters.get(target_id)
    destination = target.location_id if target is not None else deed.place_id
    event = schedule_answer(
        w,
        answer,
        target_id=target_id,
        destination_id=destination or deed.place_id,
        tier=deed.severity,
        deed=deed,
        avenger=avenger,
    )
    if faced:
        event.payload["faced"] = True
    return event
