"""What learning of a deed does to people and factions (W2, W3, W4, W5, W9, W11, E5).

People react only to what they could know (W2): a witness at once, others when a rumor they
believe reaches them, close ties when word of a death arrives. How hard they take it follows the
deed's severity, steeply at the monstrous end (W12): a brawl barely moves a bystander, but
whoever lived through a massacre turns against the one who did it and remembers (W4, W8). The
same loop runs for every actor (E5): an NPC who murders a rival gets grudges and avengers just as
the player would. Only the player has a reputation with factions and regions (W3), and it changes
slowly both ways (W9).
"""

from engine.base import (
    AFFINITY_MAX,
    AFFINITY_MIN,
    ESTEEM_MAX,
    ESTEEM_MIN,
    FEAR_MAX,
    FEAR_MIN,
    THREAT_MAX,
    TRUST_MAX,
    TRUST_MIN,
)
from engine.kin import related
from engine.state.cast import Character, Faction, FactionStatus, Prominence, Reputation
from engine.state.records import Deed
from engine.state.sheet import Attitude, ConnectionKind, Grudge
from engine.state.world import WorldState, natural_key
from engine.world.answers import (
    actor_might,
    answer_threat,
    faction_might,
    law_at,
    schedule_revenge,
)
from engine.world.geography import is_within
from engine.world.norms import CHILD_AGE, Nature, deed_nature, is_crime
from engine.world.scheduling import World
from engine.world.telling import account
from engine.world.tuning import (
    BYSTANDER_FEAR,
    BYSTANDER_HOSTILITY,
    INSIDE_ANSWER_SEVERITY,
    KIN_HOSTILITY,
    REPUTATION_STEP_MAX,
    TIE_HOSTILITY,
)


def _clamp(value: float, low: int, high: int) -> int:
    return max(low, min(high, round(value)))


# --- Ties -----------------------------------------------------------------------------------

FAMILY, FRIEND, COMRADE = 3, 2, 1


def closeness(state: WorldState, character: Character, other_id: str) -> int:
    """How close a character is to someone: family 3 (a parent or child, or a family
    connection), friend or ally 2, comrade in a faction 1, stranger 0. Either side's records
    count."""
    other = state.characters.get(other_id)
    if related(state, character.id, other_id):  # N6: parent and child
        return FAMILY
    best = 0
    for a, b in ((character, other_id), (other, character.id)):
        if a is None:
            continue
        for connection in a.sheet.resources.connections:
            if connection.character_id != b:
                continue
            if connection.kind is ConnectionKind.FAMILY:
                return FAMILY
            if connection.kind in (ConnectionKind.ALLY, ConnectionKind.TRUSTS_THEM):
                best = max(best, FRIEND)
        if a.sheet.disposition.attitudes.get(b, Attitude()).affinity >= 50:
            best = max(best, FRIEND)
    if other is not None and best == 0:
        shared = {m.faction_id for m in character.memberships} & {
            m.faction_id for m in other.memberships
        }
        if shared:
            best = COMRADE
    return best


def ties_of(state: WorldState, person_id: str, *, least: int = FRIEND) -> list[tuple[str, int]]:
    """Living characters at least this close to someone, closest first, then by id. A young child
    is family, but too young to carry word on, look into a death or avenge it."""
    found = []
    for character in state.characters.values():
        if character.id == person_id or not character.alive:
            continue
        if character.age is not None and character.age < CHILD_AGE:
            continue
        tie = closeness(state, character, person_id)
        if tie >= least:
            found.append((character.id, tie))
    return sorted(found, key=lambda item: (-item[1], natural_key(item[0])))


# --- People ---------------------------------------------------------------------------------


def shift_attitude(
    character: Character,
    toward_id: str,
    *,
    affinity: float = 0,
    fear: float = 0,
    trust: float = 0,
    grudge: Grudge | None = None,
) -> bool:
    """Move how a character feels about someone, within bounds. True if a new grudge was kept."""
    attitudes = character.sheet.disposition.attitudes
    attitude = attitudes.setdefault(toward_id, Attitude())
    attitude.affinity = _clamp(attitude.affinity + affinity, AFFINITY_MIN, AFFINITY_MAX)
    attitude.fear = _clamp(attitude.fear + fear, FEAR_MIN, FEAR_MAX)
    attitude.trust = _clamp(attitude.trust + trust, TRUST_MIN, TRUST_MAX)
    if attitude.apparent_affinity is not None:
        attitude.apparent_affinity = _clamp(
            attitude.apparent_affinity + affinity, AFFINITY_MIN, AFFINITY_MAX
        )
    if grudge is None:
        return False
    if any(g.deed_id == grudge.deed_id and g.deed_id is not None for g in attitude.grudges):
        return False
    attitude.grudges.append(grudge)
    return True


def character_learns(w: World, character_id: str, deed: Deed, *, weight: float = 1.0) -> None:
    """Someone learns of a deed and who did it, and feels about the doer accordingly (W4).

    `weight` is how much they take it in: 1 for a witness or close tidings, a rumor's accuracy
    for hearsay. Victims and their close ties keep a grudge, and family or friends of someone
    killed can come for revenge later. The player's own feelings are the player's to choose
    (G15), so the player character never reacts here.
    """
    state = w.state
    character = state.characters.get(character_id)
    if (
        character is None
        or not character.alive
        or character.id == deed.actor_id
        or character.id == state.player_id
    ):
        return
    kind = deed_nature(state, deed)
    sev = deed.severity
    harmful = kind in (Nature.HARM, Nature.HUNT)
    affected = [*deed.victim_ids, *deed.target_ids] if harmful else deed.target_ids
    tie = max((closeness(state, character, v) for v in affected if v != character.id), default=0)
    affinity = fear = trust = 0.0
    keeps_grudge = False
    struck = character.id in deed.victim_ids or character.id in deed.target_ids
    if harmful and struck:
        # A hunted beast that lives remembers the hunt as any victim would (G24).
        hurt = max(sev, 2) if kind is Nature.HUNT else sev
        if character.id in deed.victim_ids:
            affinity, fear, trust = -10 * hurt, 6 * hurt, -8 * hurt
        else:
            # Aimed at, or in the way, and unharmed: they noticed the swing (A8).
            affinity, fear, trust = -8 * hurt, 4 * hurt, -6 * hurt
        if kind is Nature.HARM:
            # Nobody who lived through a monstrous deed takes it more lightly than a bystander.
            affinity = min(affinity, -BYSTANDER_HOSTILITY[sev])
            fear = max(fear, BYSTANDER_FEAR[sev])
        keeps_grudge = hurt >= 2
    elif kind is Nature.HARM:
        affinity = -(BYSTANDER_HOSTILITY[sev] + TIE_HOSTILITY * sev * tie)
        fear, trust = BYSTANDER_FEAR[sev], affinity / 2
        keeps_grudge = (tie >= FRIEND and sev >= 3) or (tie and sev >= 4) or sev >= 5
    elif kind is Nature.HUNT:
        if tie:
            # The beast's own kin, its pack or its mate, remember the hunter (W4, G24).
            affinity = -KIN_HOSTILITY * (1 + tie)
            fear, trust = 3 * sev, affinity / 2
            keeps_grudge = True
        elif sev >= 2:
            fear = 3 * sev  # a show of strength to everyone else
    elif kind is Nature.HELP:
        if character.id in deed.target_ids:
            affinity, trust = 8 * sev, 6 * sev
        elif tie:
            affinity, trust = 3 * sev * tie, 2 * sev * tie
        else:
            affinity = 2 * sev
    elif kind is Nature.DISPLAY:
        fear = 3 * sev
    elif sev >= 3:
        fear = sev
    grudge = (
        Grudge(reason=account(state, deed), deed_id=deed.id, since_turn=w.ctx.turn)
        if keeps_grudge
        else None
    )
    new_grudge = shift_attitude(
        character,
        deed.actor_id,
        affinity=affinity * weight,
        fear=fear * weight,
        trust=trust * weight,
        grudge=grudge,
    )
    if not new_grudge:
        return
    victim_fell = any(
        not state.characters[v].alive for v in deed.victim_ids if v in state.characters
    )
    attacked = character.id in deed.victim_ids or character.id in deed.target_ids
    if tie >= FRIEND and victim_fell:
        schedule_revenge(w, character, deed)
    elif attacked and sev >= 3 and character.prominence is Prominence.KEY:
        schedule_revenge(w, character, deed)


# --- Factions and regions ---------------------------------------------------------------------


def _toward(current: int, delta: float, low: int, high: int) -> int:
    """W9: one deed moves reputation by a bounded step, and less the further it already is from
    neutral in that direction."""
    step = max(-REPUTATION_STEP_MAX, min(REPUTATION_STEP_MAX, delta))
    if step > 0 and current > 0:
        step *= 1 - current / (high * 1.5)
    elif step < 0 and current < 0 and low < 0:
        step *= 1 - current / (low * 1.5)
    return _clamp(current + step, low, high)


def adjust_reputation(reputation: Reputation, *, esteem: float = 0, fear: float = 0) -> None:
    reputation.esteem = _toward(reputation.esteem, esteem, ESTEEM_MIN, ESTEEM_MAX)
    reputation.fear = _toward(reputation.fear, fear, FEAR_MIN, FEAR_MAX)


def reputation_shift(
    state: WorldState, deed: Deed, *, harmed: bool, helped: bool
) -> tuple[float, float]:
    """W3: how a deed moves esteem and fear with those who learn of it. A hunt is harm only to
    those whose beast it was; to anyone else it shows strength (G24)."""
    kind = deed_nature(state, deed)
    sev = deed.severity
    if kind in (Nature.HARM, Nature.HUNT) and harmed:
        return -4 * sev, 3 * sev
    if kind is Nature.HUNT:
        return 0, (2 * sev if sev >= 2 else 0)
    if kind is Nature.HARM:
        return (-sev if sev >= 3 else 0), (2 * sev if sev >= 2 else 0)
    if kind is Nature.HELP:
        return (4 * sev if helped else sev), 0
    if kind is Nature.DISPLAY:
        return 0, 3 * sev
    return 0, 0


def in_faction(state: WorldState, character_id: str, faction_id: str) -> bool:
    """Whether someone belongs to a faction or to one inside it (G10), or leads it."""
    character = state.characters.get(character_id)
    faction = state.factions.get(faction_id)
    if character is None or faction is None:
        return False
    if character_id in faction.leader_ids:
        return True
    for membership in character.memberships:
        current, seen = membership.faction_id, set()
        while current is not None and current not in seen:
            if current == faction_id:
                return True
            seen.add(current)
            parent = state.factions.get(current)
            current = parent.parent_id if parent else None
    return False


def faction_learns(w: World, faction_id: str, deed: Deed, *, weight: float = 1.0) -> None:
    """A faction learns of a deed and who did it (W3, W5, W11, E5). Each deed counts once.

    Those who keep a law come for whoever broke it. With the player as the doer, esteem and fear
    move, and so does the threat the faction sees; crossing a threat tier sets its own answer in
    motion (W5). With an NPC as the doer, a harmed faction turns against the doer's factions and
    may hunt the doer (E5).
    """
    state = w.state
    faction = state.factions.get(faction_id)
    if faction is None or faction.status is FactionStatus.DESTROYED:
        return
    stored = state.deeds.get(deed.id)
    if stored is None or faction_id in stored.known_by_factions:
        return
    stored.known_by_factions.append(faction_id)
    actor = state.characters.get(deed.actor_id)
    if actor is None or deed.actor_id in faction.leader_ids:
        return  # nobody answers their own leader
    kind = deed_nature(state, deed)
    struck = [*deed.victim_ids, *deed.target_ids] if kind in (Nature.HARM, Nature.HUNT) else []
    harmed = any(in_faction(state, v, faction_id) for v in struck)
    if (
        in_faction(state, deed.actor_id, faction_id)
        and deed.severity < 4
        and not (harmed and deed.severity >= INSIDE_ANSWER_SEVERITY)
    ):
        # A faction shrugs off most of what its own people do: only the worst turns it on them,
        # or a serious attempt on one of its own, such as one member trying to murder another.
        return
    helped = kind is Nature.HELP and any(in_faction(state, t, faction_id) for t in deed.target_ids)
    law = law_at(state, faction_id, deed.place_id)
    enforcing = law is not None and is_crime(state, deed)

    if deed.actor_id == state.player_id:
        esteem, fear = reputation_shift(state, deed, harmed=harmed, helped=helped)
        adjust_reputation(faction.player_reputation, esteem=esteem * weight, fear=fear * weight)
        before = faction.threat
        faction.threat = threat_tier(state, faction, deed, harmed=harmed)
        crossed = faction.threat > before
    else:
        if harmed:
            for membership in sorted(actor.memberships, key=lambda m: m.faction_id):
                other = membership.faction_id
                if other == faction_id or other not in state.factions:
                    continue
                stance = faction.relations.get(other, 0) - 10 * deed.severity * weight
                faction.relations[other] = _clamp(stance, AFFINITY_MIN, AFFINITY_MAX)
        crossed = harmed and deed.severity >= 3
    if not actor.alive or not (enforcing or crossed):
        return
    tier = faction.threat if deed.actor_id == state.player_id else deed.severity - 1
    answer_threat(w, faction, stored, tier, enforcing=enforcing, harmed=harmed)


def threat_tier(state: WorldState, faction: Faction, deed: Deed, *, harmed: bool) -> int:
    """W5: how much of a threat a faction now sees in the player, 0 to 5. It rises with the
    worst it has learned the player did, more when done to its own, with its fear, and with a
    power gap it can't match. It doesn't fall on its own."""
    sev = deed.severity
    harmful = deed_nature(state, deed) in (Nature.HARM, Nature.HUNT, Nature.DISPLAY)
    base = (sev - 1 if harmed else max(0, sev - 2)) if harmful else 0
    from_fear = faction.player_reputation.fear // 20
    gap = actor_might(state, deed.actor_id) - faction_might(state, faction, excluding=deed.actor_id)
    bonus = 1 if harmful and gap >= 3 else 0
    return min(THREAT_MAX, max(faction.threat, max(base, from_fear) + bonus))


def region_learns(w: World, region_id: str | None, deed: Deed, *, weight: float = 1.0) -> None:
    """W3: the people of a region hear what the player did. Harm done among them weighs as harm
    to them."""
    state = w.state
    region = state.places.get(region_id) if region_id else None
    if region is None or deed.actor_id != state.player_id:
        return
    local = is_within(state, deed.place_id, region.id)
    # A hunt among them harms nobody of theirs (G24).
    harmed = local and deed_nature(state, deed) is not Nature.HUNT
    esteem, fear = reputation_shift(state, deed, harmed=harmed, helped=local)
    adjust_reputation(region.player_reputation, esteem=esteem * weight, fear=fear * weight)
