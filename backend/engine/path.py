"""What a character knows of the world's ladders (G18, C6).

A ladder's rungs are the world's (`engine.state.bible.PowerLadder`). Which of them a character
knows is the story's to tell, and the story tells it by itself, with nothing for the player to
tap. For the character, a rung above their own is one of three things:

- **Hidden**, until a scene says its name.
- **Heard of**, from the scene that first names it (`hear`). Code reads the scene's own words for
  the names of the rungs they don't know yet, so nothing depends on a model remembering to say
  that it told them: what the player read is what the character heard.
- **Known**, once the story confirms it: someone who stands on that rung, as far as they let it
  show (G20), has stood before the character, in that scene or an earlier one. A rung the
  character reaches is known from then on, and so is every rung under their own.

A true thing the character knows that names a rung makes it known as well, and a belief that
names one makes it heard of (`known`), since both are on the record already.

The sheet keeps only what play added (`CharacterSheet.rungs_heard`): the rung, when it was first
heard of and when it was confirmed. `known` reads the rest from the state each time, so a ladder
shows from its first rung up to the highest one the character has heard of, with the rungs
between that nobody has named to them left out.

Names are matched as whole words, whatever their case or accents, and in the plural too ("two
knights" names the rank Knight). A name of one or two letters, such as the A and S of a guild's
ranks, counts only next to a word for a rank ("rank A", "an S-class hunter"), since alone it is
only a letter.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from engine.limits import normalize
from engine.resolve.powers.sensing import position, shown_rung
from engine.state.bible import PowerLadder
from engine.state.cast import Character
from engine.state.records import FactKind
from engine.state.sheet import RungHeard
from engine.state.world import WorldState

# A name this short says nothing alone: it has to stand next to one of these.
SHORT_NAME = 2
_RANK_WORDS = (
    "rank ranks ranked class grade level tier "
    "rango rangos clase grado nivel categoria "
    "rang rangs classe grau nivell"
).split()
_RANK = "|".join(_RANK_WORDS)


# A scene's words are read once for every rung, and a thing the character knows once for
# every look at their sheet.
_folded = lru_cache(maxsize=2048)(normalize)


def named(text: str, name: str) -> bool:
    """Whether the text says a rung's name: its words in a row, as whole words, whatever their
    case or accents, the last one in the plural too."""
    pattern, as_written = _pattern(name)
    if pattern is None:
        return False
    return pattern.search(text if as_written else _folded(text)) is not None


@lru_cache(maxsize=512)
def _pattern(name: str) -> tuple[re.Pattern[str] | None, bool]:
    """What finds a rung's name in a text, and whether it reads the text as written. A name of a
    letter or two is read as the world writes it, right beside a word for a rank: "rank A",
    "A-rank", "de rango S". Any other is read in the folded text."""
    words = normalize(name).split()
    if not words:
        return None, False
    if len("".join(words)) <= SHORT_NAME:
        letter = re.escape(name.strip())
        beside = rf"(?:(?i:{_RANK})[ -]{letter}(?![\w-])|(?<![\w-]){letter}[ -](?i:{_RANK})(?!\w))"
        return re.compile(beside), True
    phrase = " ".join(re.escape(word) for word in words)
    return re.compile(rf"(?<![a-z0-9]){phrase}(?:e?s)?(?![a-z0-9])"), False


def own_rung(character: Character, ladder_id: str) -> int:
    """The rung they stand on, or -1 for someone who isn't on that ladder."""
    theirs = position(character, ladder_id)
    return theirs.rung if theirs is not None else -1


def _stands_before(state: WorldState, player: Character, ladder_id: str, rung: int) -> str:
    """Someone who has stood before the player character and shows that rung (G20: their own,
    unless they hide under it): the id of one of them, someone they know by name before a
    stranger, or nothing. Whoever they have met has, and so has everyone in the scene, which is
    theirs."""
    met = []
    for other in state.characters.values():
        if other.id == player.id:
            continue
        seen = player.id in other.met_by or other.id in state.scene.present_ids
        theirs = position(other, ladder_id)
        if seen and theirs is not None and shown_rung(theirs) == rung:
            met.append(other)
    met.sort(key=lambda other: (player.id not in other.known_by, other.id))
    return met[0].id if met else ""


@dataclass(frozen=True)
class Told:
    """What a scene added to what the character knows of a ladder: a rung heard of, or one
    known, with who stood before them on it."""

    ladder_id: str
    rung: int
    known: bool
    before: str = ""


def news(state: WorldState, text: str) -> list[Told]:
    """What a scene adds to what the player character knows of the world's ladders, changing
    nothing: each rung above their own that the scene's words name is heard of, and each rung
    they have heard of is known once someone who shows it has stood before them."""
    player = state.player
    found: list[Told] = []
    for ladder in state.bible.ladders:
        own = own_rung(player, ladder.id)
        heard = {h.rung: h for h in player.sheet.rungs_heard if h.ladder_id == ladder.id}
        for index, rung in enumerate(ladder.rungs):
            if index <= own:
                continue
            entry = heard.get(index)
            if entry is None:
                if not (text and named(text, rung.name)):
                    continue
                found.append(Told(ladder.id, index, known=False))
            elif entry.known_s is not None:
                continue
            before = _stands_before(state, player, ladder.id, index)
            if before:
                found.append(Told(ladder.id, index, known=True, before=before))
    return found


def keep(state: WorldState, found: list[Told]) -> None:
    """Writes what a scene added (`news`) on the player character's sheet, in place, dated now."""
    heard = state.player.sheet.rungs_heard
    for told in found:
        entry = next(
            (h for h in heard if (h.ladder_id, h.rung) == (told.ladder_id, told.rung)), None
        )
        if entry is None:
            entry = RungHeard(ladder_id=told.ladder_id, rung=told.rung, heard_s=state.world_s)
            heard.append(entry)
        if told.known:
            entry.known_s = state.world_s
            entry.known_from = told.before


def hear(state: WorldState, text: str) -> list[Told]:
    """After a scene, in place: what its words added to what the player character knows of the
    world's ladders (`news`), kept on their sheet. Returns what changed."""
    found = news(state, text)
    keep(state, found)
    return found


@dataclass(frozen=True)
class Standing:
    """One rung above the character's own, as far as they know of it."""

    rung: int
    known: bool
    heard_s: int | None = None
    known_s: int | None = None
    known_from: str | None = None
    gap_below: bool = False


def known(state: WorldState, character: Character, ladder: PowerLadder) -> list[Standing]:
    """C6. The rungs above the character's own that they know of, lowest first: the ones the
    story named to them, and the ones a thing they know names. `gap_below` marks a rung with
    rungs under it that nobody has named to them, so a screen can leave that room open."""
    own = own_rung(character, ladder.id)
    heard = {h.rung: h for h in character.sheet.rungs_heard if h.ladder_id == ladder.id}
    facts = [
        fact
        for fact in state.facts.values()
        if character.id in fact.known_by and fact.timeline_id == state.timeline_id and fact.text
    ]
    found: list[Standing] = []
    last = own
    for index, rung in enumerate(ladder.rungs):
        if index <= own:
            continue
        entry = heard.get(index)
        naming = [fact for fact in facts if named(fact.text, rung.name)]
        sure = any(fact.is_true and fact.kind is not FactKind.BELIEF for fact in naming)
        if entry is None and not naming:
            continue
        found.append(
            Standing(
                rung=index,
                known=sure or (entry is not None and entry.known_s is not None),
                heard_s=entry.heard_s if entry is not None else None,
                known_s=entry.known_s if entry is not None else None,
                known_from=entry.known_from if entry is not None else None,
                gap_below=index != last + 1,
            )
        )
        last = index
    return found


def about(state: WorldState, character: Character, name: str, *, limit: int = 3) -> list[str]:
    """C6. What the character has learned or heard about a rung, in the record's own words: the
    things they know and the rumors they heard that name it, the latest first."""
    said: list[tuple[int, str]] = []
    for fact in state.facts.values():
        mine = character.id in fact.known_by and fact.timeline_id == state.timeline_id
        if mine and fact.text and named(fact.text, name):
            said.append((fact.world_s, fact.text))
    for rumor in state.rumors.values():
        mine = character.id in rumor.heard_at and rumor.timeline_id == state.timeline_id
        if mine and named(rumor.text, name):
            said.append((rumor.heard_at[character.id], rumor.text))
    said.sort(key=lambda entry: entry[0], reverse=True)
    return list(dict.fromkeys(text for _, text in said))[:limit]
