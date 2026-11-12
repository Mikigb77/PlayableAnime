"""G1, G2: the plain fields of a draft, which the player changes themselves, at once.

The story's title and its tone, the character's name, their age, their looks and how they come
across are plain values, so changing one needs no model: code writes it into the proposal, it
costs nothing, and nothing else is redrafted (Miki, 2026-11-10: "if you want to edit your
character name, you cannot do it"). Everything else of a draft is changed in plain words, by
the drafter (`graph.drafting.chain.revise`).

A new name takes the old one's place wherever the draft says it, hidden parts included, so the
story never meets the character under two names. What someone or something else is called
stays theirs: the Esposito family whatever its son is called now, and Lin Mei beside a
character who was called Lin. A new age takes the old one's place where their looks give it as
a number.

Code reads no meaning: a name that is also a plain word ("Will", "Hope") is swapped where the
draft writes it with a capital, the start of a sentence included.
"""

import re
from collections.abc import Iterator
from dataclasses import astuple, dataclass

from pydantic import ValidationError

from graph.drafting.schema import DraftProposal
from graph.words import WORD, core

# A word of a name this short ("of", "the", "al") is never swapped by itself.
_OWN_WORD_MIN = 3
# Where a record is told by an id, never by words: left as it is.
_ID_KEYS = frozenset({"id", "about", "section", "kind_id"})
# Where a record says what it is called.
_NAME_KEYS = frozenset({"name", "aliases"})


@dataclass(frozen=True)
class Fields:
    """The plain fields as the player set them. `None`, or nothing but spaces, leaves one as it
    is."""

    title: str | None = None
    tone: str | None = None
    name: str | None = None
    age: int | None = None
    looks: str | None = None
    manner: str | None = None

    def __bool__(self) -> bool:
        return any(value is not None for value in astuple(self))


def apply(proposal: DraftProposal, fields: Fields) -> DraftProposal:
    """The proposal with the player's plain fields written in. The name goes first, so the
    looks and the manner the player wrote in the same change stay word for word."""
    if name := _clean(fields.name):
        proposal = renamed(proposal, name)
    world: dict[str, object] = {}
    if title := _clean(fields.title):
        world["title"] = title
    if tone := _clean(fields.tone):
        world["tone"] = tone
    character = proposal.character
    changes: dict[str, object] = {}
    if fields.age is not None and fields.age != character.age:
        changes["age"] = fields.age
        if character.age is not None:
            was = re.compile(rf"(?<!\w){character.age}(?!\w)")
            for text in ("appearance", "description"):
                changes[text] = was.sub(str(fields.age), getattr(character, text))
    if looks := _clean(fields.looks):
        changes["appearance"] = looks
    if manner := _clean(fields.manner):
        changes["description"] = manner
    if not world and not changes:
        return proposal
    return DraftProposal(
        world=proposal.world.model_copy(update=world),
        character=character.model_copy(update=changes),
    )


def renamed(proposal: DraftProposal, name: str) -> DraftProposal:
    """The proposal with the player character called `name`, wherever it says their name: the
    whole old name, and each word of it that is theirs alone ("Feng" of Lin Feng, but not the
    "Esposito" a family shares). A word stands in for the one in its place when both names have
    as many words, and for the new name's first word otherwise."""
    old = " ".join(proposal.character.name.split())
    new = " ".join(name.split())
    if not new or new == old:
        return proposal
    data = proposal.model_dump(mode="json")
    data = _reworded(data, _swaps(proposal, old, new), _theirs(data, old))
    character = data["character"]
    character["name"] = new
    aliases = dict.fromkeys(" ".join(alias.split()) for alias in character.get("aliases", ()))
    character["aliases"] = [a for a in aliases if a and a.casefold() != new.casefold()]
    try:
        return DraftProposal.model_validate(data)
    except ValidationError:
        # A swap that broke a record: the name alone, and the rest as it was.
        return DraftProposal(
            world=proposal.world, character=proposal.character.model_copy(update={"name": new})
        )


def _swaps(proposal: DraftProposal, old: str, new: str) -> list[tuple[re.Pattern[str], str]]:
    """What to put where, longest first: the whole old name, then its own words."""
    if not old:
        return []
    was, now = WORD.findall(old), WORD.findall(new)
    pairs = [(old, new)]
    if now:
        taken = _others(proposal, old) | {core(word) for word in now}
        for at, word in enumerate(was):
            if word == old or len(word) < _OWN_WORD_MIN or not word[0].isupper():
                continue
            if core(word) not in taken:
                pairs.append((word, now[at] if len(now) == len(was) else now[0]))
    return [(_whole(text), to) for text, to in pairs]


def _others(proposal: DraftProposal, old: str) -> set[str]:
    """The words someone or something else in the draft is called by: a person, a faction, a
    place, a people, a creature or a rung. A name that says the character's whole name, such
    as "Lin Feng's mother", lends them no word of it."""
    world = proposal.world
    names = [name for npc in world.npcs for name in (npc.name, *npc.aliases)]
    for records in (world.factions, world.places, world.peoples, world.creatures):
        names += [record.name for record in records]
    names += [rung.name for ladder in world.ladders for rung in ladder.rungs]
    whole = _whole(old)
    return {core(word) for name in names for word in WORD.findall(whole.sub(" ", name))}


@dataclass(frozen=True)
class Theirs:
    """What others are called that holds the character's old name as a word of its own. A
    record called just that keeps its name, and the longer ones stay wherever a text says
    them."""

    old: str
    names: re.Pattern[str]

    def pieces(self, text: str) -> Iterator[tuple[str, bool]]:
        """`text` in order, piece by piece, with whether each one is theirs to keep."""
        if not self.names.pattern:
            yield text, False
            return
        at = 0
        for found in self.names.finditer(text):
            yield text[at : found.start()], False
            yield found.group(), True
            at = found.end()
        yield text[at:], False


def _theirs(data: dict, old: str) -> Theirs | None:
    """What stays of what others are called when the character's old name is one word, which
    another name may hold as a word of its own: Lin Mei, Old Lin or the Lin family beside a
    character called Lin, and a month called May beside one called May. A name that only leans
    on the character's ("Lin's mother", "the oath of Lin") is theirs to follow. None when the
    old name has more words, since each of them is weighed by itself (`_others`)."""
    if len(old.split()) != 1:
        return None
    said = _whole(old)
    character = {k: v for k, v in data["character"].items() if k not in _NAME_KEYS}
    names = {" ".join(name.split()) for name in _names({"world": data["world"], "pc": character})}
    held = {name for name in names if any(_part_of(name, at) for at in said.finditer(name))}
    if not held:
        return None
    longer = sorted(held - {old}, key=len, reverse=True)
    return Theirs(old, re.compile("|".join(_whole(name).pattern for name in longer)))


def _whole(text: str) -> re.Pattern[str]:
    """`text` where it stands as whole words."""
    return re.compile(rf"(?<!\w){re.escape(text)}(?!\w)")


def _part_of(name: str, at: re.Match[str]) -> bool:
    """Whether the word found in `name` is a word of that name itself: all of it, or next to
    another of its capitalised words."""
    before, after = name[: at.start()], name[at.end() :]
    if not before and not after:
        return True
    led = before[-1:] in (" ", "-") and (WORD.findall(before) or [""])[-1][:1].isupper()
    return led or (after[:1] in (" ", "-") and after[1:2].isupper())


def _names(value, key: str = "") -> Iterator[str]:
    """Every name and alias in `value`."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _names(v, k)
    elif isinstance(value, list):
        for item in value:
            yield from _names(item, key)
    elif isinstance(value, str) and key in _NAME_KEYS:
        yield value


def _reworded(
    value, swaps: list[tuple[re.Pattern[str], str]], theirs: Theirs | None, key: str = ""
):
    """`value` with every swap made in its texts. Ids and references to them stay, and so does
    what is `theirs`."""
    if isinstance(value, dict):
        return {k: _reworded(v, swaps, theirs, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_reworded(item, swaps, theirs, key) for item in value]
    if not isinstance(value, str) or key in _ID_KEYS or key.endswith(("_id", "_ids")):
        return value
    if theirs is None:
        return _swapped(value, swaps)
    if key in _NAME_KEYS and " ".join(value.split()) == theirs.old:
        return value
    return "".join(
        piece if kept else _swapped(piece, swaps) for piece, kept in theirs.pieces(value)
    )


def _swapped(text: str, swaps: list[tuple[re.Pattern[str], str]]) -> str:
    for pattern, to in swaps:
        text = pattern.sub(lambda _, to=to: to, text)
    return text


def _clean(text: str | None) -> str:
    return " ".join(text.split()) if text else ""
