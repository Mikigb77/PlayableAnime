"""The world's words for what happened (G16, C6): how people tell a deed, a death or a find.

A deed's own text is the step as resolve settled it, in the player's words and with its outcome
("cut down every villager in the square (it worked)"). People don't talk like that, so the world
never repeats it. It tells a deed from what it records: who did it, what kind of act, to whom and
where, as in "Lin Feng killed Han Jie at the outer-court well". Rumors, grudges and the titles of
the world's events are written here. Nothing here assumes a genre (G5).

Whoever tells a deed tells it by what they know (C6): a `Teller` gives the name they know each
person, place or faction by, and whether they believe a victim died of the deed. The world tells
by the truth; the player's Memory screen tells by what the player character knows, as "you".
"""

import re
from typing import Protocol

from engine.state.cast import Character, Faction, Place
from engine.state.records import Deed
from engine.state.scene import Terms
from engine.state.world import WorldState
from engine.world.norms import Nature, canonical, creature_of, deed_nature, killed
from engine.world.tuning import REGION_KINDS


class Teller(Protocol):
    """What whoever tells a deed knows of it (C6)."""

    def name(self, record: Character | Place | Faction) -> str | None:
        """The name they know a character, place or faction by, or None if they don't."""
        ...

    def believes_dead(self, victim_id: str, deed: Deed) -> bool:
        """Whether they believe the victim died of the deed."""
        ...


class Truth:
    """The world telling its own deeds, as they happen: every name, and who really died."""

    def __init__(self, state: WorldState) -> None:
        self.state = state

    def name(self, record: Character | Place | Faction) -> str | None:
        return record.name

    def believes_dead(self, victim_id: str, deed: Deed) -> bool:
        return bool(killed(self.state, [victim_id]))


# What each kind of deed did, in the past tense, before whoever it fell on.
_DONE = {
    "kill": "killed",
    "massacre": "massacred",
    "rape": "raped",
    "torture": "tortured",
    "enslave": "enslaved",
    "raze": "razed",
    "wound": "wounded",
    "kidnap": "kidnapped",
    "poison": "poisoned",
    "conquer": "conquered",
    "betray": "betrayed",
    "assault": "attacked",
    "burn": "burned",
    "destroy": "destroyed",
    "extort": "extorted",
    "blackmail": "blackmailed",
    "frame": "framed",
    "curse": "cursed",
    "steal": "robbed",
    "threaten": "threatened",
    "insult": "insulted",
    "humiliate": "humiliated",
    "save": "saved",
    "heal": "healed",
    "protect": "protected",
    "defend": "defended",
    "free": "freed",
    "feed": "fed",
    "give": "gave gifts to",
    "help": "helped",
    "spare": "spared",
    "pardon": "pardoned",
}
# Kinds whose attempt reads differently when it harmed nobody: "tried to kill Zhao".
_TRIED = {
    "kill": "tried to kill",
    "massacre": "tried to kill",
    "rape": "tried to rape",
    "torture": "tried to torture",
    "enslave": "tried to enslave",
    "wound": "tried to hurt",
    "kidnap": "tried to kidnap",
    "poison": "tried to poison",
    "conquer": "tried to conquer",
    "steal": "tried to rob",
}
_NUMBERS = (
    "no",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)
# Kinds done to places, told by the places when nobody was harmed: "burned the granary".
_ON_PLACES = frozenset({"raze", "burn", "destroy", "conquer"})
# Kinds that say less than a death: an attack that killed is told as a killing.
_DEADLY = frozenset({"assault", "wound"})
_KILLING = frozenset({"kill", "massacre"})
# W1. A bout both sides agreed to, told by its terms, before whom it was fought with.
_BOUT = {
    Terms.NO_HARM: "sparred with",
    Terms.WOUNDS: "fought a duel with",
    Terms.DEATH: "fought a duel to the death with",
}
# Resolve's outcome note at the end of a step's text: "(it worked)", "(it partly worked)".
_OUTCOME = re.compile(r"\s*\((?:it worked|it partly worked|it failed)\)\s*$")


def cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def number(count: int) -> str:
    return _NUMBERS[count] if 0 <= count < len(_NUMBERS) else str(count)


def listing(names: list[str], *, most: int = 3, more: int = 0) -> str:
    """Names as people say them: "A", "A and B", "A, B and C", or "A, B and four others".
    `more` counts those without a name: "A and one other", "someone", "three people"."""
    names = list(dict.fromkeys(n for n in names if n))
    if not names:
        return "" if more <= 0 else "someone" if more == 1 else f"{number(more)} people"
    if len(names) + (1 if more > 0 else 0) > most:
        shown, rest = names[: most - 1], len(names) - (most - 1) + max(0, more)
        return f"{', '.join(shown)} and {number(rest)} others"
    if more > 0:
        names.append(f"{number(more)} {'other' if more == 1 else 'others'}")
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def where(state: WorldState, place_id: str | None, teller: Teller | None = None) -> str:
    """ " in Willow Ford" for a region of its own, " at the outer-court well" for a spot, or
    nothing where the place isn't known."""
    place = state.places.get(place_id) if place_id else None
    named = (teller or Truth(state)).name(place) if place is not None else None
    if not named:
        return ""
    word = "in" if place.kind.strip().casefold() in REGION_KINDS else "at"
    return f" {word} {named}"


def plain_text(deed: Deed) -> str:
    """The deed's own text without resolve's outcome note."""
    return _OUTCOME.sub("", deed.text).strip().rstrip(".")


def struck_names(state: WorldState, ids: list[str]) -> list[str]:
    """Who a deed fell on, by name: a host such as an army stands for the members of it who fell
    with it, and places and nameless victims are left out."""
    return _struck(state, ids, Truth(state))[0]


def _struck(
    state: WorldState,
    ids: list[str],
    teller: Teller,
    *,
    doer_id: str | None = None,
    self_word: str = "themselves",
) -> tuple[list[str], int]:
    """Who a deed fell on, as the teller knows them, and how many more they can't name: a host
    such as an army stands for its members who fell with it, a beast they don't know is "an ash
    wolf", the doer is `self_word`, and nameless victims (the villagers of a massacre) are
    counted. Places are left out. A name already given counts as one more."""
    names: list[str] = []
    unnamed = 0
    hosts = []
    for faction_id in dict.fromkeys(i for i in ids if i in state.factions):
        named = teller.name(state.factions[faction_id])
        if named:
            hosts.append(faction_id)
            names.append(named)
    for being_id in dict.fromkeys(ids):
        if being_id in state.places or being_id in state.factions:
            continue
        character = state.characters.get(being_id)
        if character is None:
            unnamed += 1
            continue
        if any(character.member_of(h) for h in hosts):
            continue
        creature = creature_of(state, being_id)
        named = teller.name(character)
        if being_id == doer_id:
            named = self_word
        elif not named and creature is not None:
            named = f"{_article(creature.name)} {creature.name}"
        if named and named not in names:
            names.append(named)
        else:
            unnamed += 1
    return names, unnamed


def account(
    state: WorldState, deed: Deed, *, doer: str | None = None, teller: Teller | None = None
) -> str:
    """One sentence telling a deed as people would: "Lin Feng killed Han Jie at the well." The
    doer is named unless `doer` gives the word to use instead ("Someone")."""
    told = tell(state, deed, doer=doer, teller=teller)
    if told is not None:
        return told
    subject = _subject(state, deed, doer, teller or Truth(state))
    text = plain_text(deed)
    place = where(state, deed.place_id, teller)
    if not text:
        return f"{cap(subject)} did something{place}."
    return f"{cap(subject)}: {text[:1].lower()}{text[1:]}."


def tell(
    state: WorldState, deed: Deed, *, doer: str | None = None, teller: Teller | None = None
) -> str | None:
    """The deed told from what it records, or None where only its own text could tell it (a
    kind the world has no words for, done to nobody it can name)."""
    teller = teller or Truth(state)
    subject = _subject(state, deed, doer, teller)
    word = canonical(deed.kind)
    place = where(state, deed.place_id, teller)
    what = deed_nature(state, deed)
    if word in ("breakthrough", "reveal", "display"):
        return f"{cap(_display(subject, word, deed))}{place}."
    themselves = "yourself" if subject.casefold() == "you" else "themselves"

    def whom(ids: list[str]) -> tuple[list[str], int]:
        return _struck(state, ids, teller, doer_id=deed.actor_id, self_word=themselves)

    if deed.is_bout:
        # W1. A fight both sides agreed to is told as one, never as an attack.
        partners, others = whom(deed.target_ids)
        return f"{cap(subject)} {_BOUT[deed.terms]} {listing(partners, more=others)}{place}."
    harmful = what in (Nature.HARM, Nature.HUNT)
    hosts = [t for t in deed.target_ids if t in state.factions]
    on, unnamed = whom([*deed.victim_ids, *hosts] if harmful else deed.target_ids)
    if harmful and not on and not unnamed and word not in _ON_PLACES:
        # Nobody was harmed: it was an attempt on its targets.
        tried, untold = whom(deed.target_ids)
        if tried or untold:
            verb = _TRIED.get(word) or _DONE.get(word) or "went after"
            return f"{cap(subject)} {verb} {listing(tried, more=untold)}{place}."
    if word in _ON_PLACES and not on:
        # Razed or burned: told by the places, unless it fell on people they can name.
        places = [
            n for t in deed.target_ids if t in state.places and (n := teller.name(state.places[t]))
        ]
        if places:
            on, unnamed = places, 0
    verb = _DONE.get(word)
    dead = [v for v in deed.victim_ids if teller.believes_dead(v, deed)]
    if harmful and (verb is None or word in _DEADLY or word == "kill") and dead:
        survivors = [v for v in deed.victim_ids if v not in dead]
        if survivors and not hosts:
            # Some died of it and some lived: "killed Han Jie and wounded you".
            fell, more_fell = whom(dead)
            lived, more_lived = whom(survivors)
            return (
                f"{cap(subject)} killed {listing(fell, more=more_fell)} and wounded "
                f"{listing(lived, more=more_lived)}{place}."
            )
        verb = "killed"
    elif harmful and word in _KILLING and not dead:
        verb = "wounded" if word == "kill" else "attacked"  # nobody died of it
    elif harmful and verb is None:
        verb = "hurt"
    if verb is not None and (on or unnamed):
        how = " in a duel" if deed.agreed and verb == "killed" else ""  # W1: both accepted it
        return f"{cap(subject)} {verb} {listing(on, more=unnamed)}{how}{place}."
    return None


def _subject(state: WorldState, deed: Deed, doer: str | None, teller: Teller) -> str:
    if doer is not None:
        return doer
    actor = state.characters.get(deed.actor_id)
    return (teller.name(actor) if actor is not None else None) or "someone"


def _article(word: str) -> str:
    return "an" if word[:1].casefold() in "aeiou" else "a"


def _display(subject: str, word: str, deed: Deed) -> str:
    """A show of power, told by what it showed (A4, G19, G20)."""
    text = plain_text(deed)
    if word == "breakthrough" and " to " in text:
        return f"{subject} broke through to {text.split(' to ', 1)[1]}"
    if word == "reveal" and ": " in text:
        whose = "your" if subject.casefold() == "you" else f"{subject}'s"
        return f"{whose} true strength came out: {text.split(': ', 1)[1]}"
    return f"{subject} made a show of power"


def found(state: WorldState, deed: Deed) -> str:
    """What people found of a deed nobody saw, before anyone knows who did it (W13): the sight
    that gave it away, and who was found dead or harmed. One or two sentences, the last without
    its closing stop, for the rumor to finish ("..., and nobody knows who did it.")."""
    lead = next(
        (t.text.strip() for t in deed.traces if t.kind.value in ("noise", "damage") and t.text),
        "",
    ).rstrip(".")
    place = where(state, deed.place_id)
    if not deed.victim_ids:
        return cap(lead) if lead else f"Something happened{place}"
    names = struck_names(state, deed.victim_ids)
    whom = listing(names) or "someone"
    if killed(state, deed.victim_ids):
        what = f"{whom} {'were' if len(names) > 1 else 'was'} found dead{place}"
    else:
        what = f"{whom} came to harm{place}"
    return f"{cap(lead)}. {cap(what)}" if lead else cap(what)
