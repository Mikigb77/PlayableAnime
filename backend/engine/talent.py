"""Talent: how fast a character learns each thing (A4).

Talent is a list on the sheet, written when the character is made from the player's own words
(`engine.state.sheet.Talent`). Each entry says what it covers and how strong it is, on one scale
where every step doubles the pace of learning:

- **slow** is a weakness: half the pace;
- an ordinary character learns at the pace of 1;
- a **knack** learns twice as fast, a **genius** four times, and someone **one of a kind** eight
  times, so a move an ordinary person makes second nature in about fifty uses takes them seven.

One of a kind always names one specific thing with a reason behind it: a subject, such as the
sword, or a faculty, such as perception, which reaches whatever comes to them through it. A
character holds three at most, and a fourth reads as a genius. Said about everything, it reads as
a general genius, so the strongest talent is also the narrowest.

**Whether a talent covers a thing** is ruled once, the first time the character sets out to
learn it (`TalentRuling`, made in `engine.resolve.powers.talents`), and never flips:

- **inside**: the thing is what the talent is about, and it grows at the talent's pace;
- **related**: the talent helps but doesn't hand it over, one step under;
- **outside**: the ordinary pace. A talent a ruling doesn't list is outside, and so is every
  talent for a thing not ruled on yet. A general talent is inside everything, with no ruling.

**Bridges** (`TalentBridge`) are work done in the story that connects a talent to a thing: each
one that held lifts that thing a step toward the talent's pace, or two, and never past the talent
it starts from. Someone one of a kind can carry a second thing all the way up, which takes three
ordinary bridges from outside.

Where several talents reach a thing, **their paces add** (decided 2026-11-10, Miki): each
counts for the pace its own steps give that thing, so two one of a kind talents that both cover a
move learn it sixteen times as fast, and one that covers it beside a genius that is related to it
ten times. They add and never multiply, and of the talents that cover everything only the
strongest counts. A weakness that covers the thing halves what the others give. When two talents
both cover a move fully, its violet die also shows an insight on 15 or more instead of 18 (A3).

Nothing here rolls or changes anything: it reads the sheet. A sheet with no talents, saved before
talent was a record of its own, is read from its traits' words as before, as one general talent.
"""

import math
import re
import unicodedata
from dataclasses import dataclass

from engine.contracts.intent import GrowthKind, Training
from engine.state.cast import Character
from engine.state.sheet import (
    CharacterSheet,
    Talent,
    TalentFit,
    TalentStrength,
    TraitKind,
)
from engine.text import stems

# A character holds this many one of a kind talents; the rest read as genius.
MAX_ONE_OF_A_KIND = 3
# A3. The face of a move's violet die that shows an insight, and the one that does when two
# talents both cover the move fully.
INSIGHT_AT = 18
SHARED_INSIGHT_AT = 15
# The pace from which a new move starts a mastery higher, and is learned on sight when watched.
GENIUS_STEPS = TalentStrength.GENIUS.steps
ONE_OF_A_KIND_STEPS = TalentStrength.ONE_OF_A_KIND.steps

# How many times as fast, in words up to ten: a pace is a half, or a whole number.
_TIMES = dict(enumerate("three four five six seven eight nine ten".split(), start=3))
STRENGTH_WORDS = {
    TalentStrength.SLOW: "slow",
    TalentStrength.KNACK: "a knack",
    TalentStrength.GENIUS: "genius",
    TalentStrength.ONE_OF_A_KIND: "one of a kind",
}

# A sheet saved before talent was a record of its own says it in a trait's words, in the three
# languages a sheet can be written in (S10).
_COPY_WORDS = stems(
    "copycat copy copies mimic mimics"
    " imitador imitadora copión copiona"  # Spanish
    " copiador copiadora"  # Catalan
)
_GIFT_WORDS = _COPY_WORDS | stems(
    "genius prodigy talent talented gifted"
    " genio prodigio talento talentoso talentosa superdotado superdotada dotado dotada"
    " geni prodigi talentós superdotat dotat"
)
_GIFT_PHRASES = (
    "fast learner",
    "quick learner",
    "quick study",
    "learns fast",
    "learns quickly",
    "aprende rápido",
    "aprende deprisa",
    "aprèn ràpid",
    "aprèn de pressa",
)
_FLAW_WORDS = stems("untalented")
_FLAW_PHRASES = (
    "slow learner",
    "learns slowly",
    "no talent",
    "no aptitude",
    "sin talento",
    "aprende despacio",
    "aprende lento",
    "sense talent",
    "aprèn a poc a poc",
    "aprèn lent",
)
LEGACY_GIFT = "talent-from-traits"
LEGACY_FLAW = "weakness-from-traits"


def fold(text: str) -> str:
    """A name as a key: lower case, accents folded, other scripts kept, words joined by "-"."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", "-", plain).strip("-")


def technique_key(name: str) -> str:
    return f"technique:{fold(name)}"


def skill_key(name: str) -> str:
    return f"skill:{fold(name)}"


def ladder_key(ladder_id: str | None) -> str:
    return f"ladder:{ladder_id or ''}"


def training_key(training: Training) -> str:
    """The thing a training step learns, as rulings name it. A new way to use a power goes on
    the sheet as a technique, so it is one from the start: what they train, practise and use
    later is the same thing."""
    if training.kind is GrowthKind.SKILL:
        return skill_key(training.what)
    if training.kind is GrowthKind.BREAKTHROUGH:
        return ladder_key(training.ladder_id)
    return technique_key(training.what)


def _says(texts: list[str], words: frozenset[str], phrases: tuple[str, ...]) -> bool:
    for text in texts:
        if stems(text) & words:
            return True
        folded = text.casefold()
        if any(p in folded for p in phrases):
            return True
    return False


def _trait_texts(sheet: CharacterSheet, kind: TraitKind) -> list[str]:
    return [f"{t.name} {t.description}" for t in sheet.traits if t.kind is kind]


def _from_traits(sheet: CharacterSheet) -> list[Talent]:
    """The talents of a sheet that records none: a gift for learning said in a trait's words
    is one general genius, and a flaw one general weakness."""
    found: list[Talent] = []
    for kind, words, phrases, talent_id, strength in (
        (TraitKind.GIFT, _GIFT_WORDS, _GIFT_PHRASES, LEGACY_GIFT, TalentStrength.GENIUS),
        (TraitKind.FLAW, _FLAW_WORDS, _FLAW_PHRASES, LEGACY_FLAW, TalentStrength.SLOW),
    ):
        said = next(
            (t for t in sheet.traits if t.kind is kind and _says([t.name], words, phrases)),
            None,
        ) or next(
            (
                t
                for t in sheet.traits
                if t.kind is kind and _says([f"{t.name} {t.description}"], words, phrases)
            ),
            None,
        )
        if said is not None:
            found.append(
                Talent(
                    id=talent_id,
                    name=said.name,
                    covers="everything they learn",
                    strength=strength,
                    general=True,
                )
            )
    return found


def as_read(talents: list[Talent]) -> list[Talent]:
    """A4. A list of talents as the engine reads it. One of a kind said about everything is a
    general genius, and past three one of a kind talents the rest are genius, in the order they
    are listed."""
    found: list[Talent] = []
    top = 0
    for talent in talents:
        if talent.strength is TalentStrength.ONE_OF_A_KIND:
            top += 0 if talent.general else 1
            if talent.general or top > MAX_ONE_OF_A_KIND:
                talent = talent.model_copy(update={"strength": TalentStrength.GENIUS})
        found.append(talent)
    return found


def talents_of(character: Character) -> list[Talent]:
    """A4. The character's talents as the engine reads them (`as_read`). A sheet with no
    talents is read from its traits' words."""
    sheet = character.sheet
    if not sheet.talents:
        return _from_traits(sheet)
    return as_read(sheet.talents)


def copies_on_sight(character: Character) -> bool:
    """A sheet saved before talent was a record: a copycat, said in a gift's words."""
    if character.sheet.talents:
        return False
    return _says(_trait_texts(character.sheet, TraitKind.GIFT), _COPY_WORDS, ())


def pace_words(pace: float) -> str:
    """A pace as a reason says it: "at half the pace", "twice as fast", "12 times as fast"."""
    if pace < 1:
        return "at half the pace"
    if pace == 1:
        return "at the ordinary pace"
    if pace == 2:
        return "twice as fast"
    return f"{_TIMES.get(int(pace), f'{pace:g}')} times as fast"


@dataclass(frozen=True)
class Reach:
    """One talent that reaches a thing, and how many of its own steps do once its bridges are
    counted: all of them when it covers the thing fully."""

    talent: Talent
    steps: int

    @property
    def pace(self) -> float:
        """What it adds to how fast the thing grows."""
        return 2.0**self.steps

    @property
    def fit(self) -> TalentFit:
        """How the thing stands to it now: inside once every step reaches it."""
        full = self.steps >= self.talent.strength.steps
        return TalentFit.INSIDE if full else TalentFit.RELATED


@dataclass(frozen=True)
class Standing:
    """How one thing stands with a character's talents: how fast it grows, 1 for an ordinary
    character, each talent that reaches it, strongest reach first, and a weakness that slows
    it."""

    pace: float = 1.0
    reaches: tuple[Reach, ...] = ()
    slowed_by: Talent | None = None

    @property
    def steps(self) -> int:
        """The doublings of the ordinary pace it is worth, rounded down. What a pace unlocks is
        read from this: a genius's pace is 2 and one of a kind's 3, however it adds up."""
        return math.floor(math.log2(self.pace))

    @property
    def insight_at(self) -> int:
        """A3. The face of the move's violet die that shows an insight: lower when two talents
        both cover it fully."""
        full = sum(1 for reach in self.reaches if reach.fit is TalentFit.INSIDE)
        return SHARED_INSIGHT_AT if full >= 2 else INSIGHT_AT

    @property
    def words(self) -> str:
        return pace_words(self.pace)


def reach(sheet: CharacterSheet, talent: Talent, key: str) -> int:
    """How many of the talent's own steps reach the thing: all of them inside, one fewer when
    it is related, none outside, and one more for each step a bridge of theirs lifted it, never
    past the talent."""
    top = talent.strength.steps
    if top <= 0:
        return 0
    if talent.general:
        return top
    fit = fit_of(sheet, talent, key)
    base = {TalentFit.INSIDE: top, TalentFit.RELATED: top - 1, TalentFit.OUTSIDE: 0}[fit]
    lifted = sum(b.steps for b in sheet.bridges if b.key == key and b.talent_id == talent.id)
    return min(top, base + lifted)


def fit_of(sheet: CharacterSheet, talent: Talent, key: str) -> TalentFit:
    """How the ruling on a thing placed one talent, before any bridge: outside when the thing
    was never ruled on or the ruling doesn't list the talent."""
    if talent.general:
        return TalentFit.INSIDE
    ruling = sheet.talent_ruling(key)
    covers = ruling.covers if ruling is not None else []
    return next((c.fit for c in covers if c.talent_id == talent.id), TalentFit.OUTSIDE)


def standing(character: Character, key: str) -> Standing:
    """A4. How fast the character learns the thing `key` names. The paces of the talents that
    reach it add, counting only the strongest of those that cover everything, and a weakness
    that covers it halves the sum. With none it is the ordinary pace."""
    sheet = character.sheet
    talents = talents_of(character)
    reaches: list[Reach] = []
    general: Reach | None = None
    for talent in talents:
        reached = reach(sheet, talent, key)
        if reached <= 0:
            continue
        if not talent.general:
            reaches.append(Reach(talent, reached))
        elif general is None or reached > general.steps:
            general = Reach(talent, reached)
    if general is not None:
        reaches.append(general)
    reaches.sort(key=lambda found: -found.steps)
    pace = sum(found.pace for found in reaches) or 1.0
    slow = next(
        (
            t
            for t in talents
            if t.strength is TalentStrength.SLOW and fit_of(sheet, t, key) is TalentFit.INSIDE
        ),
        None,
    )
    if slow is not None:
        pace /= 2
    return Standing(pace=pace, reaches=tuple(reaches), slowed_by=slow)


def unruled(character: Character, key: str) -> bool:
    """Whether the thing still wants a ruling: the character has a talent that isn't general,
    and no ruling names the thing yet."""
    if character.sheet.talent_ruling(key) is not None:
        return False
    return any(not t.general for t in talents_of(character))
