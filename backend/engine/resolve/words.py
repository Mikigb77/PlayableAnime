"""Plain-word helpers: matching what a model wrote against what the state holds
(`engine.text`), and writing reasons in the world's words (A8)."""

from engine.state.cast import Character
from engine.state.world import WorldState
from engine.text import any_mentions as any_mentions
from engine.text import mentions as mentions
from engine.text import stems as stems


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


def names(state: WorldState, people: list[Character]) -> str:
    """'A, B and C', each as `name` gives them."""
    named = [name(state, p.id) for p in people]
    if len(named) <= 2:
        return " and ".join(named)
    return f"{', '.join(named[:-1])} and {named[-1]}"


def is_are(state: WorldState, character_id: str) -> str:
    return "are" if character_id == state.player_id else "is"


def cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


_COUNTED = "one two three four five six seven eight nine ten eleven twelve".split()


def counted(count: int) -> str:
    """A small count in words, "six rungs", and in figures past twelve."""
    return _COUNTED[count - 1] if 1 <= count <= len(_COUNTED) else str(count)
