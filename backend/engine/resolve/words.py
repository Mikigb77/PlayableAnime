"""Plain-word helpers: matching what a model wrote against what the state holds, and writing reasons
in the world's words (A8).

The interpret step names things in words ("a stone the size of an egg", "teleport"), and the state
names them in words too (a scene prop, a power's description). Matching is on word stems and goes
one way only: every meaningful word the model wrote must be in what the state holds. So "my pistol"
finds the "Beretta pistol" and "teleport" finds "Void Step: teleports her a mile", while "a shotgun
under the bar" doesn't find the bar, and a trait called "Fire" doesn't answer "put out the fire".
A word the state doesn't hold is never a match, so the model gives ids (`ref`) where it can and
words are the fallback. It is deliberately simple and genre-free (G5).
"""

import re

from engine.state.cast import Character
from engine.state.world import WorldState

_STOPWORDS = frozenset(
    """a an the of to and or in on at by for from with without into onto out up down off over
    under through her his its their your my our me them him she he they it this that these those
    is are be was were been has have had can could would should will shall do does did not no
    any some all just very one own so as if then than there here who whom which what when""".split()
)
_SUFFIXES = ("ation", "ing", "ed", "es", "s")
_VOWELS_AND_DOUBLES = set("aeioulsz")


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            # "stopped" -> "stopp" -> "stop", but "asleep" and "spell" keep their letters.
            if len(word) >= 3 and word[-1] == word[-2] and word[-1] not in _VOWELS_AND_DOUBLES:
                word = word[:-1]
            break
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]  # "breathe" and "breath", "fire" and "fires"
    return word


def stems(text: str) -> frozenset[str]:
    """The meaningful word stems of a text."""
    words = re.findall(r"[a-z0-9]+", text.casefold())
    return frozenset(_stem(w) for w in words if w not in _STOPWORDS and len(w) > 1)


def mentions(haystack: str, needle: str) -> bool:
    """Whether the needle names something the haystack holds: every meaningful word of the needle
    appears in the haystack. One way only, so extra words in the needle never match by accident."""
    hay, wanted = stems(haystack), stems(needle)
    return bool(wanted) and wanted <= hay


def any_mentions(haystacks: list[str], needle: str) -> str | None:
    """The first haystack that mentions the needle."""
    return next((h for h in haystacks if mentions(h, needle)), None)


def name(state: WorldState, character_id: str) -> str:
    """'you' for the player character, otherwise the character's name (A8 reasons speak to the
    player)."""
    if character_id == state.player_id:
        return "you"
    character = state.characters.get(character_id)
    return character.name if character is not None else character_id


def name_of(state: WorldState, character: Character) -> str:
    return name(state, character.id)


def possessive(state: WorldState, character_id: str) -> str:
    if character_id == state.player_id:
        return "your"
    who = name(state, character_id)
    return f"{who}'" if who.endswith("s") else f"{who}'s"


def is_are(state: WorldState, character_id: str) -> str:
    return "are" if character_id == state.player_id else "is"


def cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def odds_label(odds: float) -> str:
    """The odds in words, as the scene details show them (A8)."""
    if odds < 0.2:
        return f"about 1 in {max(2, round(1 / max(odds, 0.001)))}"
    if odds < 0.4:
        return "unlikely"
    if odds <= 0.6:
        return "even odds"
    if odds < 0.8:
        return "likely"
    return "very likely"
