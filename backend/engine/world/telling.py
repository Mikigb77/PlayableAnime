"""The world's words for what happened (G16, C6): how people tell a deed, a death or a find.

A deed's own text is the step as resolve settled it, in the player's words and with its outcome
("cut down every villager in the square (it worked)"). People don't talk like that, so the world
never repeats it. It tells a deed from what it records: who did it, what kind of act, to whom and
where, as in "Lin Feng killed Han Jie at the outer-court well". Rumors, grudges and the titles of
the world's events are written here. Nothing here assumes a genre (G5).
"""

import re

from engine.state.records import Deed
from engine.state.world import WorldState
from engine.world.norms import Nature, canonical, deed_nature, killed
from engine.world.tuning import REGION_KINDS

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
# Resolve's outcome note at the end of a step's text: "(it worked)", "(it partly worked)".
_OUTCOME = re.compile(r"\s*\((?:it worked|it partly worked|it failed)\)\s*$")


def cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def number(count: int) -> str:
    return _NUMBERS[count] if 0 <= count < len(_NUMBERS) else str(count)


def listing(names: list[str], *, most: int = 3) -> str:
    """Names as people say them: "A", "A and B", "A, B and C", or "A, B and four others"."""
    names = list(dict.fromkeys(n for n in names if n))
    if not names:
        return ""
    if len(names) > most:
        shown, rest = names[: most - 1], len(names) - (most - 1)
        return f"{', '.join(shown)} and {number(rest)} others"
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def where(state: WorldState, place_id: str | None) -> str:
    """ " in Willow Ford" for a region of its own, " at the outer-court well" for a spot, or
    nothing where the place isn't known."""
    place = state.places.get(place_id) if place_id else None
    if place is None:
        return ""
    word = "in" if place.kind.strip().casefold() in REGION_KINDS else "at"
    return f" {word} {place.name}"


def plain_text(deed: Deed) -> str:
    """The deed's own text without resolve's outcome note."""
    return _OUTCOME.sub("", deed.text).strip().rstrip(".")


def struck_names(state: WorldState, ids: list[str]) -> list[str]:
    """Who a deed fell on, by name: a host such as an army stands for the members of it who fell
    with it, and places and nameless victims are left out."""
    hosts = [i for i in ids if i in state.factions]
    names = [state.factions[h].name for h in hosts]
    for being_id in ids:
        character = state.characters.get(being_id)
        if character is None:
            continue
        if any(character.member_of(h) for h in hosts):
            continue
        names.append(character.name)
    return names


def account(state: WorldState, deed: Deed, *, doer: str | None = None) -> str:
    """One sentence telling a deed as people would: "Lin Feng killed Han Jie at the well." The
    doer is named unless `doer` gives the word to use instead ("Someone")."""
    actor = state.characters.get(deed.actor_id)
    subject = doer if doer is not None else actor.name if actor else "Someone"
    word = canonical(deed.kind)
    place = where(state, deed.place_id)
    what = deed_nature(state, deed)
    if word in ("breakthrough", "reveal", "display"):
        return f"{cap(_display(subject, word, deed))}{place}."
    harmful = what in (Nature.HARM, Nature.HUNT)
    hosts = [t for t in deed.target_ids if t in state.factions]
    on = struck_names(state, [*deed.victim_ids, *hosts] if harmful else deed.target_ids)
    if harmful and not on and word not in _ON_PLACES:
        # Nobody was harmed: it was an attempt on its targets.
        tried = struck_names(state, deed.target_ids)
        if tried:
            verb = _TRIED.get(word) or _DONE.get(word) or "went after"
            return f"{cap(subject)} {verb} {listing(tried)}{place}."
    if word in _ON_PLACES:
        on = on or [state.places[t].name for t in deed.target_ids if t in state.places]
    verb = _DONE.get(word)
    died = bool(killed(state, deed.victim_ids))
    if harmful and (verb is None or word in _DEADLY) and died:
        verb = "killed"
    elif harmful and word in _KILLING and not died:
        verb = "wounded" if word == "kill" else "attacked"  # nobody died of it
    elif harmful and verb is None:
        verb = "hurt"
    if verb is not None and on:
        return f"{cap(subject)} {verb} {listing(on)}{place}."
    text = plain_text(deed)
    if not text:
        return f"{cap(subject)} did something{place}."
    return f"{cap(subject)}: {text[:1].lower()}{text[1:]}."


def _display(subject: str, word: str, deed: Deed) -> str:
    """A show of power, told by what it showed (A4, G19, G20)."""
    text = plain_text(deed)
    if word == "breakthrough" and " to " in text:
        return f"{subject} broke through to {text.split(' to ', 1)[1]}"
    if word == "reveal" and ": " in text:
        return f"{subject}'s true strength came out: {text.split(': ', 1)[1]}"
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
