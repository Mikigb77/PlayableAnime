"""What a character knows of the world's ladders (G18, C6).

A ladder's rungs are the world's (`engine.state.bible.PowerLadder`). Which of them a character
knows is the story's to tell, and the story tells it by itself, with nothing for the player to
tap. For the character, a rung above their own is one of three things:

- **Hidden**, until a scene says its name.
- **Heard of**, from the scene that first names it (`hear`). Code reads the scene's own words for
  the names of the rungs they don't know yet, so nothing depends on a model remembering to say
  that it told them: what the player read is what the character heard. The rungs everyone in the
  world has heard of (`PowerLadder.known_to_all`, the lowest ones) are heard of from the start,
  and the summary the player reads before the story begins names the same ones (G1).
- **Known**, once the story confirms it: someone who stands on that rung, as far as they let it
  show (G20), has stood before the character, in that scene or an earlier one. A rung the
  character reaches is known from then on, and so is every rung under their own.

A true thing the character knows that names a rung makes it known as well, and a belief that
names one makes it heard of (`known`), since both are on the record already.

The sheet keeps only what play added (`CharacterSheet.rungs_heard`): the rung, when it was first
heard of and when it was confirmed. `known` reads the rest from the state each time, so a ladder
shows from its first rung up to the highest one the character has heard of, with the rungs
between that nobody has named to them left out.

Someone can stand above every rung the character knows of. Once they have stood before the
character, the path says that they stand somewhere higher still and nothing else, neither the
rung's name nor how far up it lies (`higher_still`), so a ladder widens when the story reaches
past what the character knew.

A ladder can gain a rung in the middle of a story, above the highest it had (G7: how far a
power goes is open). The story names it and code decides whether it holds (`beyond_problem`):
only once the character has been told of the ladder's highest rung, so the rungs the world
started with are told first, and a rung the story added has to be climbed by someone before
the ladder grows again, so it grows no faster than someone earns it. Nobody on record is put
on a new rung: whoever stands on it came into the story with it, or climbed there.

Names are matched as whole words, whatever their case or accents, and in the plural too ("two
knights" names the rank Knight). A name of one or two letters, such as the A and S of a guild's
ranks, counts only next to a word for a rank ("rank A", "an S-class hunter"), since alone it is
only a letter.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from statistics import median

from engine.base import TIER_MAX
from engine.contracts.intent import GrowthKind
from engine.invariants import is_real_name
from engine.limits import normalize
from engine.resolve.powers.sensing import position, shown_rung
from engine.state.bible import PowerLadder, RuleTopic, WorldRule
from engine.state.cast import Character, Prominence
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


def _shown_before(
    state: WorldState, player: Character, ladder_id: str
) -> list[tuple[int, Character]]:
    """Everyone who has stood before the player character and stands on that ladder, each with
    the rung they show (G20: their own, unless they hide under it), those the character knows
    by name before strangers and the story's key people before the rest. Whoever they have met
    has stood before them, and so has everyone in the scene, which is theirs."""
    met = []
    for other in state.characters.values():
        if other.id == player.id:
            continue
        seen = player.id in other.met_by or other.id in state.scene.present_ids
        theirs = position(other, ladder_id)
        if seen and theirs is not None:
            met.append((shown_rung(theirs), other))
    met.sort(
        key=lambda shown: (
            player.id not in shown[1].known_by,
            shown[1].prominence is not Prominence.KEY,
            shown[1].id,
        )
    )
    return met


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
    they have heard of is known once someone who shows it has stood before them. A rung
    everyone has heard of is no news when a scene names it, and is known the same way."""
    player = state.player
    found: list[Told] = []
    for ladder in state.bible.ladders:
        own = own_rung(player, ladder.id)
        heard = {h.rung: h for h in player.sheet.rungs_heard if h.ladder_id == ladder.id}
        met: list[tuple[int, Character]] | None = None
        for index, rung in enumerate(ladder.rungs):
            if index <= own:
                continue
            entry = heard.get(index)
            if entry is None and index >= ladder.known_to_all:
                if not (text and named(text, rung.name)):
                    continue
                found.append(Told(ladder.id, index, known=False))
            elif entry is not None and entry.known_s is not None:
                continue
            if met is None:
                met = _shown_before(state, player, ladder.id)
            # Someone they know by name before a stranger.
            before = next((other.id for shown, other in met if shown == index), "")
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
    common: bool = False


def known(state: WorldState, character: Character, ladder: PowerLadder) -> list[Standing]:
    """C6. The rungs above the character's own that they know of, lowest first: the ones
    everyone in the world has heard of (`common`), the ones the story named to them, and the
    ones a thing they know names. `gap_below` marks a rung with rungs under it that nobody has
    named to them, so a screen can leave that room open."""
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
        common = index < ladder.known_to_all
        if entry is None and not naming and not common:
            continue
        found.append(
            Standing(
                rung=index,
                known=sure or (entry is not None and entry.known_s is not None),
                heard_s=entry.heard_s if entry is not None else None,
                known_s=entry.known_s if entry is not None else None,
                known_from=entry.known_from if entry is not None else None,
                gap_below=index != last + 1,
                common=common,
            )
        )
        last = index
    return found


def higher_still(state: WorldState, player: Character, ladder: PowerLadder, top: int) -> list[str]:
    """C6, G20. Who has stood before the player character and shows a rung above `top`, the
    highest rung they know of on that ladder (`known`, or their own): the ids of the living
    ones, those they know by name first. The character knows that these stand higher still,
    and neither the rung's name nor how far up it lies."""
    return [
        other.id
        for shown, other in _shown_before(state, player, ladder.id)
        if shown > top and other.alive
    ]


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


def rung_called(state: WorldState, name: str) -> tuple[PowerLadder, int] | None:
    """The ladder and the index of the rung of that name, whatever its case or accents, or
    None where no ladder of the world has one."""
    said = normalize(name)
    for ladder in state.bible.ladders:
        for index, rung in enumerate(ladder.rungs):
            if normalize(rung.name) == said:
                return ladder, index
    return None


def rung_said(state: WorldState, words: str) -> tuple[PowerLadder, int] | None:
    """The rung a few words name: the one called exactly that (`rung_called`), or else the only
    rung of the world whose name they hold, as "late Core Formation" does. None where they
    hold no rung's name, or more than one."""
    exact = rung_called(state, words)
    if exact is not None:
        return exact
    held = [
        (ladder, index)
        for ladder in state.bible.ladders
        for index, rung in enumerate(ladder.rungs)
        if named(words, rung.name)
    ]
    return held[0] if len(held) == 1 else None


# --- A rung above the top (G18, G7) --------------------------------------------------------

# How many people a new rung may bring into the story standing on it.
CAME_WITH = 3


def top_told(state: WorldState, ladder: PowerLadder) -> bool:
    """Whether the story has told the player character of the ladder's highest rung: they
    stand on it, or it is one of the rungs they know of (`known`), heard of or confirmed."""
    player = state.player
    top = len(ladder.rungs) - 1
    if own_rung(player, ladder.id) >= top:
        return True
    return any(standing.rung == top for standing in known(state, player, ladder))


def climbed_to(state: WorldState, name: str) -> bool:
    """Whether anyone on record climbed to the rung of that name: their growth holds the
    breakthrough to it, the player character's (`engine.resolve.powers.growth`) or anyone
    else's over the years (`engine.world.lives`). Whoever came into the story already
    standing on a rung never climbed to it."""
    return any(
        gain.source == GrowthKind.BREAKTHROUGH.value and gain.what == name and not gain.loss
        for character in state.characters.values()
        for gain in character.sheet.growth
    )


def above_tier(ladder: PowerLadder) -> int | None:
    """A8. The tier of a rung above the ladder's highest: as far above it as the ladder's
    rungs usually lie apart, a tier at least, and no further than the scale goes. None where
    the highest rung already stands at the end of the scale."""
    top = ladder.rungs[-1].tier
    if top >= TIER_MAX:
        return None
    steps = [b.tier - a.tier for a, b in zip(ladder.rungs, ladder.rungs[1:], strict=False)]
    steps = [step for step in steps if step > 0]
    step = max(1, round(median(steps))) if steps else 1
    return min(TIER_MAX, top + step)


def ceilings(state: WorldState, ladder: PowerLadder) -> list[WorldRule]:
    """G7. The world's rules that hold the ladder at its highest rung: those on how far a
    power goes that name that rung, such as "nobody is known to have passed the S rank". A
    fixed one ends the ladder for good. An open one is what a discovery breaks: it holds
    until the story tells of a rung above, and is struck from the world's rules then
    (`engine.apply`), since from then on the ladder itself says how far it goes."""
    top = ladder.rungs[-1].name
    return [
        rule
        for rule in state.bible.rules
        if rule.topic is RuleTopic.LIMITS and named(rule.text, top)
    ]


def top_problem(state: WorldState, ladder: PowerLadder) -> str | None:
    """G18, G7. Why nothing can be put above the ladder's highest rung right now, whatever it
    is called, or None where the story can reach past it.

    - No rule that never changes holds the ladder there (G7): a fixed rule on how far a power
      goes that names the highest rung, such as "nobody ever passes the S rank" (`ceilings`).
      An open one is what a discovery breaks, so it stops nothing here.
    - The scale has room above the highest rung (`above_tier`).
    - The player character has been told of the highest rung (`top_told`). While rungs they
      haven't heard of lie above what they know, the world has more to tell before the story
      can reach past it.
    - A rung the story added is climbed before the ladder grows again (`climbed_to`): someone
      broke through to it, by their own work or the world's years. So however the story goes,
      a ladder grows no faster than someone earns its last rung."""
    top = ladder.rungs[-1]
    if any(rule.fixed for rule in ceilings(state, ladder)):
        return f"a rule that never changes holds the ladder at {top.name} (G7)"
    if above_tier(ladder) is None:
        return f"nothing stands above {top.name}: the scale ends there"
    if not top_told(state, ladder):
        return f"the story hasn't told them of {top.name} yet: the rungs it has come first"
    if top.added_s is not None and not climbed_to(state, top.name):
        return f"nobody has climbed to {top.name} yet, and the ladder grows no faster than that"
    return None


def beyond_problem(state: WorldState, ladder: PowerLadder, name: str) -> str | None:
    """G18, G7. Why the story can't put a rung called `name` above the ladder's highest right
    now, or None where it can: the name is a name, no rung of the world's ladders has it
    already, and the story has reached the ladder's top (`top_problem`)."""
    if not is_real_name(name):
        return f"{name!r} isn't a name"
    taken = rung_called(state, name)
    if taken is not None:
        return f"{taken[0].name} already has a rung called {name}"
    return top_problem(state, ladder)
