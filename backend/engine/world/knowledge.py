"""What learning of a deed does to people and factions (W2, W3, W4, W5, W9, W11, E5).

People react only to what they could know (W2): a witness at once, others when a rumor they
believe reaches them, close ties when word of a death arrives. How hard they take it follows the
deed's severity, steeply at the monstrous end (W12): a brawl barely moves a bystander, but
whoever lived through a massacre turns against the one who did it and remembers (W4, W8). The
same loop runs for every actor (E5): an NPC who murders a rival gets grudges and avengers just as
the player would. Only the player has a reputation with factions and regions (W3), and it changes
slowly both ways (W9).

How far anyone goes against the doer follows how they know (`Grounds`, W4, W5): hostility grows
in stages, and each needs its own evidence.

- **Suspicion**: they heard it said, and it rests on one person's word or on none. What they
  think of the doer moves by how much of the talk they believe, and that is all: nobody keeps
  a grudge, comes for revenge or sends anyone to take or hurt the doer on talk. Those who keep
  the law come to look into it. The deed records who has only heard it (`Deed.heard_by`), and
  the narrator is told so of the people in the scene.
- **Accusation**: someone who knows told them, a witness or whoever tied what it left behind to
  the doer. They hold it against the doer. A faction acts on it, and someone close to the dead
  comes to face the doer with it.
- **Open enmity**: they saw it, or it is beyond one person's word (`proven`: done before a
  crowd, or two who saw it are alive and would say so), which even talk of it carries, or they
  put it to the doer's face and nothing changed their mind. Then they come for revenge.

What both sides of a fight agreed to is no attack (W1, `engine.resolve.bouts`). A bout leaves a
little more regard between those who fought it (`fought_bout`). A death both accepted is a loss
to those close to the dead, who may still hold it against the one who killed them, and nothing
to bystanders, factions or the law. A blow that went beyond the terms is an attack, and costs
more trust than an open one.
"""

from enum import IntEnum

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
from engine.state.records import Deed, Visibility
from engine.state.sheet import Attitude, ConnectionKind, Grudge
from engine.state.world import WorldState, natural_key
from engine.world.answers import (
    actor_might,
    answer_threat,
    faction_might,
    law_at,
    look_into,
    schedule_confrontation,
    schedule_revenge,
)
from engine.world.geography import is_within
from engine.world.norms import CHILD_AGE, Nature, deed_nature, is_beast, is_crime
from engine.world.scheduling import World
from engine.world.telling import account
from engine.world.tuning import (
    BOUT_REGARD,
    BOUT_REGARD_MAX,
    BROKEN_TERMS_TRUST,
    BYSTANDER_FEAR,
    BYSTANDER_HOSTILITY,
    INSIDE_ANSWER_SEVERITY,
    KIN_HOSTILITY,
    LOYAL_AFFINITY,
    PROOF_WITNESSES,
    REPUTATION_STEP_MAX,
    SILENT_FEAR,
    TIE_HOSTILITY,
)


def _clamp(value: float, low: int, high: int) -> int:
    return max(low, min(high, round(value)))


# --- How they know ----------------------------------------------------------------------------


class Grounds(IntEnum):
    """How someone knows who did a deed, from the weakest (W2, W4)."""

    HEARD = 1  # talk: a rumor that names the doer reached them
    TOLD = 2  # the word of someone who knows: a witness's report, word sent to those close
    SAW = 3  # they saw it done, or it was done to them


def proven(state: WorldState, deed: Deed) -> bool:
    """Whether who did a deed is beyond one person's word: it was done before a crowd, or
    enough of those who saw it are alive and would say so (W4). Whoever is dead, devoted to
    the doer or too afraid of them is nobody's second voice."""
    if deed.visibility is Visibility.PUBLIC:
        return True
    voices = [
        state.characters[i]
        for i in deed.witness_ids
        if i != deed.actor_id and i in state.characters
    ]
    return sum(would_talk(state, witness, deed) for witness in voices) >= PROOF_WITNESSES


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


def protects(state: WorldState, witness: Character, deed: Deed) -> bool:
    """Devoted to the doer, or close to them: they keep it to themselves."""
    toward = witness.sheet.disposition.attitudes.get(deed.actor_id)
    if toward is not None and toward.affinity >= LOYAL_AFFINITY:
        return True
    return closeness(state, witness, deed.actor_id) >= FRIEND


def would_talk(state: WorldState, witness: Character, deed: Deed) -> bool:
    """Whether a witness tells the people around them what they saw (W2): not if they are
    devoted to the doer or too afraid of them. The player's character keeps their own counsel,
    and beasts don't talk (G24)."""
    if witness.id == state.player_id or not witness.alive or is_beast(state, witness.id):
        return False
    if protects(state, witness, deed):
        return False
    toward = witness.sheet.disposition.attitudes.get(deed.actor_id)
    return toward is None or toward.fear < SILENT_FEAR


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


def character_learns(
    w: World,
    character_id: str,
    deed: Deed,
    *,
    weight: float = 1.0,
    grounds: Grounds = Grounds.SAW,
) -> None:
    """Someone learns of a deed and who did it, and feels about the doer accordingly (W4).

    `weight` is how much they take it in: 1 for a witness or close tidings, a rumor's accuracy
    for hearsay. `grounds` is how they know, and sets how far they go. On talk alone they feel
    it, and the deed records that they heard it and how much of it they believed
    (`Deed.heard_by`). Told by someone who knows, they take in the rest, victims' close ties
    keep the grudge, and family or friends of someone killed come to face the doer with it.
    Having seen it, or where it is beyond one person's word (`proven`, when even talk of it
    counts as knowing), they come for revenge later. The player's own feelings are the player's
    to choose (G15), so the player character never reacts here.
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
    # W1. Whoever stood in a fight both sides agreed to wasn't attacked in it.
    struck = not deed.agreed and (
        character.id in deed.victim_ids or character.id in deed.target_ids
    )
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
        # W1. A blow beyond the terms of a bout is remembered, however light it was.
        keeps_grudge = hurt >= 2 or deed.broke_terms
    elif kind is Nature.HARM:
        # W1. A death both accepted turns no bystander against the one who dealt it: only those
        # close to the dead take it as a loss.
        seen = 0 if deed.agreed else BYSTANDER_HOSTILITY[sev]
        affinity = -(seen + TIE_HOSTILITY * sev * tie)
        fear, trust = BYSTANDER_FEAR[sev], affinity / 2
        keeps_grudge = tie >= FRIEND and sev >= 3
        if not deed.agreed:
            keeps_grudge = keeps_grudge or bool(tie and sev >= 4) or sev >= 5
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
    if deed.broke_terms:
        trust *= BROKEN_TERMS_TRUST  # it came under cover of a friendly fight
    stored = state.deeds.get(deed.id, deed)
    heard = stored.heard_by.get(character.id)
    # Talk of what is beyond one person's word is no mere talk: everyone knows it.
    sure = proven(state, stored)
    if grounds is Grounds.HEARD and not sure:
        if heard is not None or character.id in stored.known_by:
            return  # the same talk again, or talk of what they know for themselves
        stored.heard_by[character.id] = max(0.0, min(1.0, weight))
        shift_attitude(
            character,
            deed.actor_id,
            affinity=affinity * weight,
            fear=fear * weight,
            trust=trust * weight,
        )
        return
    if heard is not None:
        # What they had only heard, they now know: they take in the rest of it.
        del stored.heard_by[character.id]
        weight = max(0.0, weight - heard)
    if grounds is Grounds.HEARD and character.id not in stored.known_by:
        stored.known_by.append(character.id)  # nobody has to come and tell them
    told = account(state, deed)
    grudge = Grudge(reason=told, deed_id=deed.id, since_turn=w.ctx.turn) if keeps_grudge else None
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
    comes = (tie >= FRIEND and victim_fell) or (
        struck and sev >= 3 and character.prominence is Prominence.KEY
    )
    if not comes:
        return
    if grounds is Grounds.SAW or sure:
        schedule_revenge(w, character, deed)
    else:
        # One person's word, or a finding nobody saw: they put it to the doer's face first.
        schedule_confrontation(w, character, deed)


def fought_bout(w: World, deed: Deed) -> None:
    """W1, W4. A bout both sides agreed to: those who fought it think a little better of each
    other for it, up to `BOUT_REGARD_MAX`, and that is all. Nobody was attacked, so nobody is
    afraid, keeps a grudge or comes for revenge, however many blows it had. The player
    character's own feelings are the player's (G15)."""
    state = w.state
    fighters = [i for i in dict.fromkeys([deed.actor_id, *deed.target_ids])]
    for fighter_id in sorted(fighters, key=natural_key):
        fighter = state.characters.get(fighter_id)
        if fighter is None or not fighter.alive or fighter_id == state.player_id:
            continue
        for other_id in fighters:
            if other_id == fighter_id or other_id not in state.characters:
                continue
            attitude = fighter.sheet.disposition.attitudes.get(other_id, Attitude())
            shift_attitude(
                fighter,
                other_id,
                affinity=max(0, min(BOUT_REGARD, BOUT_REGARD_MAX - attitude.affinity)),
                trust=max(0, min(BOUT_REGARD, BOUT_REGARD_MAX - attitude.trust)),
            )


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


def faction_learns(
    w: World,
    faction_id: str,
    deed: Deed,
    *,
    weight: float = 1.0,
    grounds: Grounds = Grounds.TOLD,
) -> None:
    """A faction learns of a deed and who did it (W3, W5, W11, E5). Each deed counts once.

    Those who keep a law come for whoever broke it. With the player as the doer, esteem and fear
    move, and so does the threat the faction sees; crossing a threat tier sets its own answer in
    motion (W5). With an NPC as the doer, a harmed faction turns against the doer's factions and
    may hunt the doer (E5).

    `grounds` is how it knows. On talk alone (`Grounds.HEARD`, of a deed that isn't beyond one
    person's word) what it thinks moves by how much of the talk it believes, and it sends
    nobody to take, hurt or kill: those who keep the law come to look into it, one whose own
    were struck waits for word from someone who knows, and any other answers the threat it now
    sees with what isn't hostile. Once someone who knows tells it, the rest counts: the law
    comes to arrest, and one whose own were struck sees the threat and answers it.
    """
    state = w.state
    faction = state.factions.get(faction_id)
    if faction is None or faction.status is FactionStatus.DESTROYED:
        return
    stored = state.deeds.get(deed.id)
    if stored is None or faction_id in stored.known_by_factions:
        return
    heard = stored.heard_by_factions.get(faction_id)
    # Talk of what is beyond one person's word is no mere talk: everyone knows it.
    talk = grounds is Grounds.HEARD and not proven(state, stored)
    if talk:
        if heard is not None:
            return  # the same talk again
        stored.heard_by_factions[faction_id] = max(0.0, min(1.0, weight))
    else:
        stored.heard_by_factions.pop(faction_id, None)
        stored.known_by_factions.append(faction_id)
        if heard is not None:
            weight = max(0.0, weight - heard)  # what it had only heard already counted
    actor = state.characters.get(deed.actor_id)
    if actor is None or deed.actor_id in faction.leader_ids:
        return  # nobody answers their own leader
    if deed.agreed:
        # W1. A fight both sides agreed to is no attack on anyone's faction: there is nothing
        # to answer. A death in it still shows what the player can do, and the dead one's own
        # think a little less of them for it.
        if deed.actor_id == state.player_id and deed.victim_ids:
            theirs = any(in_faction(state, v, faction_id) for v in deed.victim_ids)
            esteem = -deed.severity if theirs else 0
            adjust_reputation(
                faction.player_reputation, esteem=esteem * weight, fear=2 * deed.severity * weight
            )
        return
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

    # Its own were struck and it has only talk to go by: it waits for word from someone who
    # knows before it sees a threat to answer.
    waits = talk and harmed
    if deed.actor_id == state.player_id:
        esteem, fear = reputation_shift(state, deed, harmed=harmed, helped=helped)
        adjust_reputation(faction.player_reputation, esteem=esteem * weight, fear=fear * weight)
        before = faction.threat
        if not waits:
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
        crossed = harmed and deed.severity >= 3 and not waits
    if not actor.alive:
        return
    tier = faction.threat if deed.actor_id == state.player_id else deed.severity - 1
    if talk:
        if enforcing:
            look_into(w, faction, stored, law)
        elif crossed:
            answer_threat(w, faction, stored, tier, enforcing=False, harmed=harmed, hostile=False)
        return
    if enforcing or crossed:
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
    if deed.agreed:
        # W1. What both sides agreed to harms nobody there: a death in it only shows strength.
        if deed.victim_ids:
            adjust_reputation(region.player_reputation, fear=2 * deed.severity * weight)
        return
    local = is_within(state, deed.place_id, region.id)
    # A hunt among them harms nobody of theirs (G24).
    harmed = local and deed_nature(state, deed) is not Nature.HUNT
    esteem, fear = reputation_shift(state, deed, harmed=harmed, helped=local)
    adjust_reputation(region.player_reputation, esteem=esteem * weight, fear=fear * weight)
