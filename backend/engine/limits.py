"""The hard limits of every rating, enforced in code (F3, G12, and the ratings table under F2).

Prompts ask the models to stay inside these lines and Gemini's filters stand behind them (F5),
but neither is a guarantee, so the engine checks what it can see:

- **Adults only in romance (F3).** Every character in a romantic or sexual step, the one acting
  included, has an adult age recorded and nothing childlike in their appearance or description,
  whatever age they are given. A step at a character who isn't a recorded adult never plays.
- **The rating's line (F2).** A Teen story has attraction and a kiss, and no sexual violence, so a
  sexual step or a sexual assault never plays in one. Mature plays both within the table: sex
  fades out and sexual violence happens off the page, which the narrator's rules and the eval
  cases cover.
- **Fictional people (G12, F3).** No step targets a real living person, and no new character or
  faction takes the name of a real person or organisation (`engine.real_entities`).
- **No real-world harm instructions (F3).** A narration that reads like a working recipe for a
  weapon or a drug, or like a working attack on a computer, is retold as a cut-away (F4).

Each check returns `LimitHit`s and never raises; the turn graph decides what a hit means for the
turn and logs it with its category (F4). Nothing here assumes a genre (G5): the words are about
people, bodies and real-world know-how, never about a setting.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from engine.context import Rating
from engine.contracts.delta import StateDelta
from engine.contracts.intent import Intent, IntentStep
from engine.real_entities import EXACT_ORGANISATIONS, REAL_ORGANISATIONS, REAL_PEOPLE
from engine.state.cast import Character
from engine.state.world import WorldState

# F3: the youngest age that counts as an adult, in every world.
ADULT_AGE = 18


class LimitCategory(StrEnum):
    """What a hit is about, as logged (F4). `minor`, `sexual` and `real_person` share their names
    with the report categories in docs/API.md, so blocks and reports can be counted together."""

    MINOR = "minor"  # romance or sex with someone who isn't a recorded adult (F3)
    SEXUAL_VIOLENCE = "sexual_violence"  # sexual violence in a Teen story (F2)
    SEXUAL = "sexual"  # sex in a Teen story (F2)
    REAL_PERSON = "real_person"  # a real person or organisation (G12)
    HARM_INSTRUCTIONS = "harm_instructions"  # real-world know-how told as instructions (F3)


# The order hits are reported in, the gravest first.
SEVERITY = tuple(LimitCategory)

# What the player reads when a step never plays. No lecture (F1): what the story can't hold, and
# that they can do something else.
MESSAGES = {
    LimitCategory.MINOR: (
        "Romance and sex only happen between characters the story knows are adults. "
        "Try something else."
    ),
    LimitCategory.SEXUAL_VIOLENCE: "That isn't part of a Teen story. Try something else.",
    LimitCategory.SEXUAL: "In a Teen story, romance goes as far as a kiss. Try something else.",
    LimitCategory.REAL_PERSON: (
        "Stories only have fictional people. Try someone from this world instead."
    ),
    LimitCategory.HARM_INSTRUCTIONS: "That part of the story can't be told as written.",
}


@dataclass(frozen=True)
class LimitHit:
    """One line crossed. `subject` is a character id, a real name or the step's words, and
    `detail` says why in plain words; both can hold story text, so they are logged only at
    DEBUG (T6)."""

    category: LimitCategory
    subject: str = ""
    detail: str = ""
    step: int | None = None


def gravest(hits: list[LimitHit]) -> LimitHit | None:
    return min(hits, key=lambda hit: SEVERITY.index(hit.category), default=None)


# --- Text matching -------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Lowercase ASCII words separated by single spaces, so accents, case and punctuation never
    change a match ("Beyoncé's" becomes "beyonce s")."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    ascii_only = folded.encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_only).split())


def _words(*patterns: str) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(patterns) + r")\b")


# --- Adults only (F3) -----------------------------------------------------------------------

_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
}
_AGE = r"(\d{1,3}|" + "|".join(_NUMBERS) + r")"
_YEARS_OLD = r"(?:years? old|year old|yo)"
_PERSON = r"(?:girl|boy|child|kid|body|form|frame|face)"
# A number followed by one of these is a size, a count or a time, not an age: "appears 7 feet
# tall", "seems 3 times stronger", "looks 10 minutes older".
_NOT_AN_AGE = (
    r"(?! (?:feet|foot|ft|inch|inches|cm|centimet\w*|metres?|meters?|m|kg|kilos?|pounds?|lbs?|"
    r"stone|tall|times|seconds?|minutes?|hours?|days?|weeks?|months?|steps|paces|miles?|yards?|"
    r"percent|more|less|of)\b)"
)

# Words for a child's body or manner. "Childlike" is in on purpose: F3 counts a childlike body or
# behaviour whatever age a character is given. "Teen", "young" or "petite" describe adults too,
# and "children" or "a child" in a description is as likely someone's family, so they stay out.
_CHILDLIKE = _words(
    r"child ?like",
    r"childish (?:body|face|figure|frame|build|looks)",
    r"child s (?:body|face|figure|frame|build)",
    r"(?:body|face|figure|frame|build|size|height) of a (?:child|kid|little girl|little boy)",
    r"child ?sized",
    r"(?:looks?|looking|appears?|seems?) (?:like |just like )?a (?:child|kid)",
    r"little (?:girl|boy)",
    r"young (?:girl|boy)",
    r"lolis?",
    r"lolita",
    r"shotas?",
    r"toddler",
    r"infant",
    r"(?:pre ?)?pubescent",
    r"pre ?teens?",
    r"tweens?",
    r"underage",
    r"school ?(?:girl|boy)s?",
    r"school uniform",
    r"(?:elementary|middle|grade|primary|junior high|high) school (?:student|pupil|girl|boy)s?",
    r"(?:elementary|middle|high) schooler",
)
# The age someone looks or is said to be: "looks about twelve", "a girl of fourteen", "the body
# of a ten-year-old", "she is 15 years old", or an appearance that starts with the age ("16,
# slight, black hair"). A "ten-year-old scar" is about the scar, and "her daughter is 6 years
# old" about someone else, so an age counts only when it is the character's own: how they look,
# a person word, or a sentence about them (a pronoun or their name, `_own_age`).
_AGE_PHRASES = (
    re.compile(
        r"\b(?:looks?|looking|appears?|appearing|seems?|aged)"
        rf"(?: (?:like|about|around|maybe|barely|only|just|no more than|at most|a|an))* {_AGE}"
        rf"(?: {_YEARS_OLD})?\b{_NOT_AN_AGE}"
    ),
    re.compile(rf"\b(?:body|form|frame|face) of an? {_AGE} {_YEARS_OLD}\b"),
    re.compile(rf"\b(?:girl|boy|child|kid) of {_AGE}\b{_NOT_AN_AGE}"),
    re.compile(rf"\b{_AGE} {_YEARS_OLD} {_PERSON}\b"),
)
# Present tense only: "she was 15 when the war came" is backstory, and the age now is `age`.
_OWN_AGE_VERBS = (
    r"(?: (?:s|is|are|am|just|only|barely|turns|turning|just turned|recently turned|"
    r"has just turned))+"
)
# An appearance that opens with the age, as the drafter writes them: "16, slight, black hair".
_LEADING_AGE = re.compile(r"^\s*(\d{1,3})\s*,")


def _age_value(value: str) -> int:
    return int(value) if value.isdigit() else _NUMBERS[value]


@lru_cache(maxsize=256)
def _own_age(names: tuple[str, ...]) -> re.Pattern[str]:
    """ "She is 15 years old", "Mira's fifteen": an age stated about the character, by a pronoun
    or one of their names."""
    subjects = ["she", "he", "they", "who", "i", "you", *(re.escape(n) for n in names if n)]
    return re.compile(
        rf"\b(?:{'|'.join(subjects)}){_OWN_AGE_VERBS} {_AGE}(?: {_YEARS_OLD})?\b{_NOT_AN_AGE}"
    )


def childlike_markers(text: str, names: tuple[str, ...] = ()) -> list[str]:
    """The words in a description that make a character read as a child (F3). `names` are the
    character's own names, so "Mira is 15" counts and "her daughter is 6" doesn't."""
    own_age = _own_age(tuple(dict.fromkeys(normalize(n) for n in names)))
    found = []
    for line in text.splitlines():
        leading = _LEADING_AGE.match(line)
        if leading and _age_value(leading.group(1)) < ADULT_AGE:
            found.append(leading.group(0).strip())
        words = normalize(line)
        found += [m.group(0) for m in _CHILDLIKE.finditer(words)]
        for pattern in (*_AGE_PHRASES, own_age):
            for match in pattern.finditer(words):
                if _age_value(match.group(1)) < ADULT_AGE:
                    found.append(match.group(0))
    return list(dict.fromkeys(found))


def adult_problem(character: Character) -> str | None:
    """Why a character can't be in a romantic or sexual scene, or None if they can (F3)."""
    if character.age is None:
        return "no age recorded"
    if character.age < ADULT_AGE:
        return f"aged {character.age}"
    names = (character.name, *character.name.split(), *character.aliases)
    if childlike_markers(character.appearance, names) or childlike_markers(
        character.description, names
    ):
        return "described as childlike"
    return None


def is_adult(character: Character) -> bool:
    return adult_problem(character) is None


# --- Romantic and sexual steps --------------------------------------------------------------


class Intimacy(StrEnum):
    ROMANCE = "romance"  # a kiss, a flirt, a courtship: as far as Teen goes
    SEXUAL = "sexual"  # beyond a kiss
    SEXUAL_VIOLENCE = "sexual_violence"


_SEXUAL_VIOLENCE = _words(
    r"rap(?:e|es|ed|ing|ist)",
    r"sexual(?:ly)? (?:assault|abuse|violence)\w*",
    r"(?:assault|abuse)\w* (?:her|him|them) sexually",
    r"molest\w*",
    r"(?:force|forces|forced|forcing) (?:myself|himself|herself|themselves|yourself) (?:on|upon)",
    r"violat(?:e|es|ed|ing) (?:her|him|them)",
)
# Each word needs its sexual sense: "the sex of the foal", "grope for the lever" and "strip them
# of their weapons" are ordinary actions.
_SEXUAL = _words(
    r"(?:have|has|had|having) sex",
    r"sex (?:with|act|acts|scene)",
    r"sexual(?:ly)?",
    r"sleep(?:s|ing)? with",
    r"slept with",
    r"(?:make|makes|making|made) love",
    r"love ?making",
    r"intercourse",
    r"foreplay",
    r"fondl(?:e|es|ed|ing)(?! (?:the|a|an|his|my|your|its|their|with)\b)",
    r"grop(?:e|es|ed|ing)(?! (?:in|for|around|about|through|along|across|blindly|toward|towards|"
    r"into|under|over|on|the|a|an|his|my|your|its|their|her way|one s)\b)",
    r"(?:undress|undresses|undressed|undressing) (?:her|him|them|each other)",
    r"(?:strip|strips|stripped|stripping) (?:her|him|them|each other) (?:naked|nude|bare)",
    r"(?:strip|strips|stripped|stripping) (?:her|him|them) of (?:her|his|their) "
    r"(?:clothes|clothing|dress|underwear)",
    r"(?:take|takes|took|taking) (?:her|his|their) clothes off",
    r"erotic\w*",
    r"lewd\w*",
    r"orgasm\w*",
    r"bed (?:her|him|them)(?! down\b)",
)
_ROMANCE = _words(
    r"kiss\w*",
    r"flirt\w*",
    r"(?:make|makes|making|made) out",
    r"cuddl\w+",
    r"snuggl\w+",
    r"caress\w*",
    r"romanc\w+",
    r"romantic\w*",
    r"seduc\w+",
    r"(?:court|courts|courted|courting) (?:her|him|them)",
    r"(?:woo|woos|wooed|wooing)",
    r"propos\w+ (?:marriage|to (?:her|him|them))",
    r"(?:marry|marries|marrying)",
    r"(?:get|gets|got|getting) married",
    r"on a date",
    r"(?:ask|asks|asked|asking) \w+ out",
)
# A kiss on the hand, a ring or a cheek is a greeting or an oath in many worlds, and a blade's
# kiss is a cut, so neither is a romance.
_NOT_A_ROMANTIC_KISS = (
    re.compile(
        r"\bkiss\w*(?: (?:the|a|an|his|her|their|my|your|its|\w+ s))*"
        r" (?:hand|hands|ring|rings|cheek|cheeks|forehead|brow|feet|foot|boot|boots|hem|"
        r"blade|sword|cross|relic|ground|earth|banner)\b"
    ),
    re.compile(
        r"\b(?:blade|sword|knife|dagger|steel|edge|arrow|bolt|bullet|fist|knuckles|whip|"
        r"flame|flames|fire|frost|lightning|spear|axe|hammer|lash)s?(?: \w+)? kiss\w*"
    ),
)


def intimacy(step: IntentStep) -> Intimacy | None:
    """Whether a step is romantic or sexual, read from the interpret step's own words for it:
    its verb, method, text and beats."""
    text = normalize(" ".join([step.verb, step.method, step.text, *(b.text for b in step.beats)]))
    if _SEXUAL_VIOLENCE.search(text):
        return Intimacy.SEXUAL_VIOLENCE
    if _SEXUAL.search(text):
        return Intimacy.SEXUAL
    for pattern in _NOT_A_ROMANTIC_KISS:
        text = pattern.sub(" ", text)
    if _ROMANCE.search(text):
        return Intimacy.ROMANCE
    return None


# --- Real people and organisations (G12) ----------------------------------------------------

RealKind = Literal["person", "organisation"]


@dataclass(frozen=True)
class RealEntity:
    name: str
    kind: RealKind


@lru_cache(maxsize=1)
def _real_names() -> tuple[re.Pattern[str], dict[str, RealEntity], dict[str, RealEntity]]:
    phrases: dict[str, RealEntity] = {}
    for kind, names in (("person", REAL_PEOPLE), ("organisation", REAL_ORGANISATIONS)):
        for name in names:
            phrases.setdefault(normalize(name), RealEntity(name, kind))
    exact = {normalize(name): RealEntity(name, "organisation") for name in EXACT_ORGANISATIONS}
    # Longest first, so "Kim Kardashian" wins over "Kardashian".
    ordered = sorted(phrases, key=len, reverse=True)
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in ordered) + r")\b")
    return pattern, phrases, exact


def real_entities(name: str) -> list[RealEntity]:
    """Every real person and organisation a name or phrase refers to, in order (G12)."""
    pattern, phrases, exact = _real_names()
    words = normalize(name)
    bare = words.removeprefix("the ")
    if bare in exact:
        return [exact[bare]]
    found = [phrases[match.group(0)] for match in pattern.finditer(words)]
    return list(dict.fromkeys(found))


def real_entity(name: str) -> RealEntity | None:
    """The real person or organisation a name refers to, or None (G12). A person wins, so
    "Microsoft founder Bill Gates" is Bill Gates."""
    found = real_entities(name)
    return next((e for e in found if e.kind == "person"), found[0] if found else None)


def _names_of(state: WorldState, ids: list[str]) -> list[str]:
    names: list[str] = []
    for ref in ids:
        character = state.characters.get(ref)
        if character is not None:
            names += [character.name, *character.aliases]
    return names


# --- The player's action --------------------------------------------------------------------


def check_action(state: WorldState, intent: Intent, rating: Rating) -> list[LimitHit]:
    """The lines the player's checked intent crosses, before anything resolves or is narrated.

    A romantic or sexual step needs the actor and every character it targets to be recorded
    adults (F3). A partner the story doesn't know yet is the narrator's to introduce as an adult
    with an age (its prompt's rule); once they are known, this check holds them to it. In a Teen
    story a sexual step or a sexual assault never plays (F2). No step targets a real living
    person (G12). Naming a real organisation in an action is allowed, as a backdrop; it just
    never becomes a faction (`strip_real_entities`).
    """
    hits: list[LimitHit] = []
    actor_id = intent.actor_id or state.player_id
    for index, step in enumerate(intent.steps):
        kind = intimacy(step)
        if kind is not None:
            hits += _intimacy_hits(state, step, index, actor_id, kind, rating)
        for words in [*step.targets, step.facts.opposition, *_names_of(state, step.target_ids)]:
            entity = real_entity(words) if words else None
            if entity is not None and entity.kind == "person":
                hits.append(LimitHit(LimitCategory.REAL_PERSON, entity.name, "a target", index))
    return hits


def _intimacy_hits(
    state: WorldState,
    step: IntentStep,
    index: int,
    actor_id: str,
    kind: Intimacy,
    rating: Rating,
) -> list[LimitHit]:
    hits: list[LimitHit] = []
    partners = [*step.target_ids, *step.facts.opposition_ids]
    for ref in dict.fromkeys([actor_id, *partners]):
        character = state.characters.get(ref)
        if character is None:
            continue  # a place or a faction: nobody to check
        problem = adult_problem(character)
        if problem is not None:
            hits.append(LimitHit(LimitCategory.MINOR, ref, problem, index))
    if rating is Rating.TEEN and kind is Intimacy.SEXUAL_VIOLENCE:
        hits.append(LimitHit(LimitCategory.SEXUAL_VIOLENCE, step.text, "a Teen story", index))
    elif rating is Rating.TEEN and kind is Intimacy.SEXUAL:
        hits.append(LimitHit(LimitCategory.SEXUAL, step.text, "a Teen story", index))
    return hits


# --- The narrator's update ------------------------------------------------------------------


def strip_real_entities(delta: StateDelta, state: WorldState) -> tuple[StateDelta, list[LimitHit]]:
    """The update without real people or organisations (G12): a new character or faction named
    after one is left out, and a known one keeps the name it had."""
    hits: list[LimitHit] = []
    delta = delta.model_copy(deep=True)

    characters = []
    for change in delta.characters:
        real = {n: e for n in [change.name, *change.aliases] if n and (e := real_entity(n))}
        if real and change.id not in state.characters:
            entity = next(iter(real.values()))
            hits.append(LimitHit(LimitCategory.REAL_PERSON, entity.name, "a new character"))
            continue
        if real:
            entity = next(iter(real.values()))
            hits.append(LimitHit(LimitCategory.REAL_PERSON, entity.name, "a renamed character"))
            change.name = None if change.name in real else change.name
            change.aliases = [alias for alias in change.aliases if alias not in real]
        characters.append(change)
    delta.characters = characters

    factions = []
    for change in delta.factions:
        entity = real_entity(change.name) if change.name else None
        if entity is not None and change.id not in state.factions:
            hits.append(LimitHit(LimitCategory.REAL_PERSON, entity.name, "a new faction"))
            continue
        if entity is not None:
            hits.append(LimitHit(LimitCategory.REAL_PERSON, entity.name, "a renamed faction"))
            change.name = None
        factions.append(change)
    delta.factions = factions
    return delta, hits


# --- Real-world harm instructions (F3) ------------------------------------------------------

# Real-world materials and tools that turn a story into a manual. Fictional chemistry (dragon's
# blood, spirit grass, mana crystals) never matches, so a cultivator can still brew a pill by
# the gram.
_DRUGS = _words(
    r"meth(?:amphetamine)?",
    r"pseudo ?ephedrine",
    r"ephedrine",
    r"red phosphorus",
    r"anhydrous ammonia",
    r"phenyl ?acetone",
    r"p2p",
    r"methylamine",
    r"safrole",
    r"fentanyl",
    r"carfentanil",
    r"heroin",
    r"cocaine",
    r"lsd",
    r"lysergic",
    r"ergotamine",
    r"mdma",
    r"ghb",
)
_WEAPONS = _words(
    r"pipe bombs?",
    r"detonators?",
    r"blasting caps?",
    r"ammonium nitrate",
    r"anfo",
    r"tatp",
    r"acetone peroxide",
    r"hmtd",
    r"nitroglycerin\w*",
    r"potassium (?:chlorate|perchlorate|nitrate)",
    r"saltpet(?:er|re)",
    r"thermite",
    r"napalm",
    r"black powder",
    r"gun ?powder",
    r"ieds?",
    r"auto ?sears?",
    r"lower receivers?",
    r"ghost guns?",
    r"sarin",
    r"ricin",
    r"vx",
    r"nerve agents?",
    r"mustard gas",
    r"chlorine gas",
    r"anthrax",
)
_HACKING = _words(
    r"sql injection",
    r"or 1 ?1",
    r"cross site scripting",
    r"xss",
    r"buffer overflow",
    r"shell ?code",
    r"reverse shell",
    r"privilege escalation",
    r"keyloggers?",
    r"ransomware",
    r"metasploit",
    r"nmap",
    r"hashcat",
    r"rootkits?",
    r"botnets?",
    r"cve \d{4} \d+",
    r"payloads?",
    r"exploits?",
)
# Signs that text is a procedure rather than a story: amounts in a lab's units, numbered or
# bulleted steps, and code or commands. Everyday units (pounds, minutes, cups) are left out,
# because stories use them all the time.
_QUANTITY = re.compile(
    r"\b\d+(?:[.,]\d+)?\s?(?:%|percent|g|grams?|mg|milligrams?|kg|kilograms?|ml|"
    r"millilit(?:er|re)s?|lit(?:er|re)s?|l|moles?|molar|psi|volts?|°\s?[cf]|"
    r"degrees (?:celsius|fahrenheit))(?=\W|$)",
    re.IGNORECASE,
)
# Numbered steps only: a dash opens a line of dialogue in many languages.
_STEP_LINE = re.compile(r"^\s*(?:\d+[.)]|step \d+\b)", re.IGNORECASE | re.MULTILINE)
# What a recipe tells you to do. A story says what was done ("you cook a 90% pure batch").
_PROCEDURE = _words(
    r"mix(?:es|ed|ing)?",
    r"combin(?:e|es|ed|ing)",
    r"dissolv(?:e|es|ed|ing)",
    r"heat(?:s|ed|ing)?",
    r"boil(?:s|ed|ing)?",
    r"stir(?:s|red|ring)?",
    r"add(?:s|ed|ing)?",
    r"filter(?:s|ed|ing)?",
    r"crush(?:es|ed|ing)?",
    r"grind(?:s|ing)?",
    r"ground",
    r"pour(?:s|ed|ing)?",
    r"distil(?:l|ls|led|ling)?",
    r"evaporat(?:e|es|ed|ing)",
    r"reflux(?:es|ed|ing)?",
    r"extract(?:s|ed|ing)?",
    r"cool(?:s|ed|ing)?",
    r"dry(?:ing)?",
    r"dried",
    r"pack(?:s|ed|ing)?",
    r"wir(?:e|es|ed|ing)",
    r"solder(?:s|ed|ing)?",
    r"attach(?:es|ed|ing)?",
    r"connect(?:s|ed|ing)?",
    r"measur(?:e|es|ed|ing)",
    r"weigh(?:s|ed|ing)?",
)
_CODE = (
    re.compile(
        r"```|^\s*(?:\$|>>>) \S|^\s*import [\w.]+\s*$|^\s*from [\w.]+ import \w+", re.MULTILINE
    ),
    re.compile(r"\bSELECT\b.+\bFROM\b|<script\b|\bexec\(|\b0x[0-9a-fA-F]{4,}"),
    re.compile(r"\b(?:sudo|curl|wget|chmod|powershell|nc|netcat)\s+-|\bpython3?\s+\S+\.py\b"),
    re.compile(r"'\s*or\s*'?1'?\s*=\s*'?1", re.IGNORECASE),
)


def harm_instructions(text: str) -> str | None:
    """The real-world domain ("drugs", "weapons" or "hacking") a passage gives working
    instructions for, or None (F3).

    Know-how told as an outcome passes ("you cook a batch through the night; by dawn the trays
    glitter"). A passage is instructions when it names real-world materials or tools and reads
    like a procedure: code or commands, two or more numbered steps, or (for drugs and weapons)
    two or more lab amounts with two or more things to do with them.
    """
    words = normalize(text)
    code = sum(len(pattern.findall(text)) for pattern in _CODE)
    steps = len(_STEP_LINE.findall(text))
    quantities = len(_QUANTITY.findall(text))
    actions = len({match.group(0) for match in _PROCEDURE.finditer(words)})
    recipe = code or steps >= 2 or (quantities >= 2 and actions >= 2)
    if recipe and _DRUGS.search(words):
        return "drugs"
    if recipe and _WEAPONS.search(words):
        return "weapons"
    if (code or steps >= 2) and _HACKING.search(words):
        return "hacking"
    return None
