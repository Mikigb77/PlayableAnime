"""The world's words for what happened (G16, C6): how people tell a deed, a death or a find.

A deed's own text is the step as resolve settled it, in the player's words and with its outcome
("cut down every villager in the square (it worked)"). People don't talk like that, so the world
never repeats it. It tells a deed from what it records: who did it, what kind of act, to whom and
where, as in "Lin Feng killed Han Jie at the outer-court well". Rumors, grudges and the titles of
the world's events are written here. Nothing here assumes a genre (G5).

Whoever tells a deed tells it by what they know (C6): a `Teller` gives the name they know each
person, place or faction by, and whether they believe a victim died of the deed. The world tells
by the truth; the player's Memory screen tells by what the player character knows, as "you".

A deed is told in the story's language (S10): English, Spanish or Catalan. The same facts pick
the same kind of sentence in each, and each language says it its own way: Spanish puts "a"
before a person a deed fell on and says "you" with the verb ("Mataste a Zhao Kun en el pozo."),
Catalan tells the past with "va" ("Lin Feng va matar Han Jie al pou."). Nothing on record says
whether someone is a man or a woman, so no sentence here needs to know: people are "otras dos
personas", and someone found dead "apareció sin vida".
"""

import re
from dataclasses import dataclass
from typing import Protocol

from engine.context import Language
from engine.state.cast import Character, Faction, Place
from engine.state.records import GARBLED_LEAD, Deed, WorldChange, WorldChangeKind
from engine.state.scene import Terms
from engine.state.world import WorldState
from engine.world.norms import Nature, canonical, creature_of, deed_nature, killed
from engine.world.tuning import REGION_KINDS

EN, ES, CA = Language.EN, Language.ES, Language.CA

# Who a telling is about when that is no name. A teller calls the player character YOU (the
# player's Memory, C6), a doer nobody can name is SOMEONE, and a doer their own deed fell on is
# SELF. Each language says them its own way: "you", a verb in the second person, "te", "et".
YOU = "you"
SOMEONE = "someone"
SELF = "themselves"


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


@dataclass(frozen=True)
class _Verb:
    """A kind of deed in the past tense: as anyone did it, as "you" did it where the language
    says that another way, and the word that stands before whom it fell on where the verb
    brings its own ("with", Spanish "con", Catalan "a")."""

    they: str
    you: str = ""
    before: str = ""

    def said(self, you: bool) -> str:
        return self.you if you and self.you else self.they


def _ca(infinitive: str, before: str = "") -> _Verb:
    """Catalan tells the past with "va" and the infinitive: "va matar", "vas matar"."""
    return _Verb(f"va {infinitive}", f"vas {infinitive}", before)


# Each kind of deed, and what it reads as when it harmed nobody (`try:`), in each language. A
# bout both sides agreed to is told by its terms (W1), "hurt" is harm the world has no word for,
# and "went_after" an attempt of a kind it has none for. "court", "lie_with" and "wed" are the
# moves in a romance the engine records as deeds (W17).
_BOOK: dict[Language, dict[str, _Verb]] = {
    EN: {
        "kill": _Verb("killed"),
        "massacre": _Verb("massacred"),
        "rape": _Verb("raped"),
        "torture": _Verb("tortured"),
        "enslave": _Verb("enslaved"),
        "raze": _Verb("razed"),
        "wound": _Verb("wounded"),
        "kidnap": _Verb("kidnapped"),
        "poison": _Verb("poisoned"),
        "conquer": _Verb("conquered"),
        "betray": _Verb("betrayed"),
        "assault": _Verb("attacked"),
        "burn": _Verb("burned"),
        "destroy": _Verb("destroyed"),
        "extort": _Verb("extorted"),
        "blackmail": _Verb("blackmailed"),
        "frame": _Verb("framed"),
        "curse": _Verb("cursed"),
        "steal": _Verb("robbed"),
        "threaten": _Verb("threatened"),
        "insult": _Verb("insulted"),
        "humiliate": _Verb("humiliated"),
        "save": _Verb("saved"),
        "heal": _Verb("healed"),
        "protect": _Verb("protected"),
        "defend": _Verb("defended"),
        "free": _Verb("freed"),
        "feed": _Verb("fed"),
        "give": _Verb("gave gifts", before="to"),
        "help": _Verb("helped"),
        "spare": _Verb("spared"),
        "pardon": _Verb("pardoned"),
        "court": _Verb("courted"),
        "lie_with": _Verb("slept", before="with"),
        "wed": _Verb("married"),
        "try:kill": _Verb("tried to kill"),
        "try:massacre": _Verb("tried to kill"),
        "try:rape": _Verb("tried to rape"),
        "try:torture": _Verb("tried to torture"),
        "try:enslave": _Verb("tried to enslave"),
        "try:wound": _Verb("tried to hurt"),
        "try:kidnap": _Verb("tried to kidnap"),
        "try:poison": _Verb("tried to poison"),
        "try:conquer": _Verb("tried to conquer"),
        "try:steal": _Verb("tried to rob"),
        "hurt": _Verb("hurt"),
        "went_after": _Verb("went after"),
        "bout:no_harm": _Verb("sparred", before="with"),
        "bout:wounds": _Verb("fought a duel", before="with"),
        "bout:death": _Verb("fought a duel to the death", before="with"),
        "something": _Verb("did something"),
        "display": _Verb("made a show of power"),
        "breakthrough": _Verb("broke through", before="to"),
    },
    ES: {
        "kill": _Verb("mató", "mataste"),
        "massacre": _Verb("masacró", "masacraste"),
        "rape": _Verb("violó", "violaste"),
        "torture": _Verb("torturó", "torturaste"),
        "enslave": _Verb("esclavizó", "esclavizaste"),
        "raze": _Verb("arrasó", "arrasaste"),
        "wound": _Verb("hirió", "heriste"),
        "kidnap": _Verb("secuestró", "secuestraste"),
        "poison": _Verb("envenenó", "envenenaste"),
        "conquer": _Verb("conquistó", "conquistaste"),
        "betray": _Verb("traicionó", "traicionaste"),
        "assault": _Verb("atacó", "atacaste"),
        "burn": _Verb("quemó", "quemaste"),
        "destroy": _Verb("destruyó", "destruiste"),
        "extort": _Verb("extorsionó", "extorsionaste"),
        "blackmail": _Verb("chantajeó", "chantajeaste"),
        "frame": _Verb("incriminó", "incriminaste"),
        "curse": _Verb("maldijo", "maldijiste"),
        "steal": _Verb("robó", "robaste"),
        "threaten": _Verb("amenazó", "amenazaste"),
        "insult": _Verb("insultó", "insultaste"),
        "humiliate": _Verb("humilló", "humillaste"),
        "save": _Verb("salvó", "salvaste"),
        "heal": _Verb("curó", "curaste"),
        "protect": _Verb("protegió", "protegiste"),
        "defend": _Verb("defendió", "defendiste"),
        "free": _Verb("liberó", "liberaste"),
        "feed": _Verb("dio de comer", "diste de comer"),
        "give": _Verb("hizo regalos", "hiciste regalos"),
        "help": _Verb("ayudó", "ayudaste"),
        "spare": _Verb("perdonó la vida", "perdonaste la vida"),
        "pardon": _Verb("indultó", "indultaste"),
        "court": _Verb("cortejó", "cortejaste"),
        "lie_with": _Verb("se acostó", "te acostaste", before="con"),
        "wed": _Verb("se casó", "te casaste", before="con"),
        "try:kill": _Verb("intentó matar", "intentaste matar"),
        "try:massacre": _Verb("intentó matar", "intentaste matar"),
        "try:rape": _Verb("intentó violar", "intentaste violar"),
        "try:torture": _Verb("intentó torturar", "intentaste torturar"),
        "try:enslave": _Verb("intentó esclavizar", "intentaste esclavizar"),
        "try:wound": _Verb("intentó hacer daño", "intentaste hacer daño"),
        "try:kidnap": _Verb("intentó secuestrar", "intentaste secuestrar"),
        "try:poison": _Verb("intentó envenenar", "intentaste envenenar"),
        "try:conquer": _Verb("intentó conquistar", "intentaste conquistar"),
        "try:steal": _Verb("intentó robar", "intentaste robar"),
        "hurt": _Verb("hizo daño", "hiciste daño"),
        "went_after": _Verb("fue", "fuiste", before="a por"),
        "bout:no_harm": _Verb("midió fuerzas", "mediste fuerzas", before="con"),
        "bout:wounds": _Verb("se batió en duelo", "te batiste en duelo", before="con"),
        "bout:death": _Verb(
            "se batió en duelo a muerte", "te batiste en duelo a muerte", before="con"
        ),
        "something": _Verb("hizo algo", "hiciste algo"),
        "display": _Verb("hizo una demostración de poder", "hiciste una demostración de poder"),
        "breakthrough": _Verb("dio el salto", "diste el salto", before="a"),
    },
    CA: {
        "kill": _ca("matar"),
        "massacre": _ca("massacrar"),
        "rape": _ca("violar"),
        "torture": _ca("torturar"),
        "enslave": _ca("esclavitzar"),
        "raze": _ca("arrasar"),
        "wound": _ca("ferir"),
        "kidnap": _ca("segrestar"),
        "poison": _ca("enverinar"),
        "conquer": _ca("conquerir"),
        "betray": _ca("trair"),
        "assault": _ca("atacar"),
        "burn": _ca("cremar"),
        "destroy": _ca("destruir"),
        "extort": _ca("extorquir"),
        "blackmail": _ca("fer xantatge", "a"),
        "frame": _ca("incriminar"),
        "curse": _ca("maleir"),
        "steal": _ca("robar", "a"),
        "threaten": _ca("amenaçar"),
        "insult": _ca("insultar"),
        "humiliate": _ca("humiliar"),
        "save": _ca("salvar"),
        "heal": _ca("curar"),
        "protect": _ca("protegir"),
        "defend": _ca("defensar"),
        "free": _ca("alliberar"),
        "feed": _ca("donar menjar", "a"),
        "give": _ca("fer regals", "a"),
        "help": _ca("ajudar"),
        "spare": _ca("perdonar la vida", "a"),
        "pardon": _ca("indultar"),
        "court": _ca("fer la cort", "a"),
        "lie_with": _Verb("se'n va anar al llit", "te'n vas anar al llit", before="amb"),
        "wed": _Verb("es va casar", "et vas casar", before="amb"),
        "try:kill": _ca("intentar matar"),
        "try:massacre": _ca("intentar matar"),
        "try:rape": _ca("intentar violar"),
        "try:torture": _ca("intentar torturar"),
        "try:enslave": _ca("intentar esclavitzar"),
        "try:wound": _ca("intentar fer mal", "a"),
        "try:kidnap": _ca("intentar segrestar"),
        "try:poison": _ca("intentar enverinar"),
        "try:conquer": _ca("intentar conquerir"),
        "try:steal": _ca("intentar robar", "a"),
        "hurt": _ca("fer mal", "a"),
        "went_after": _ca("anar", "contra"),
        "bout:no_harm": _ca("mesurar forces", "amb"),
        "bout:wounds": _Verb("es va batre en duel", "et vas batre en duel", before="amb"),
        "bout:death": _Verb(
            "es va batre en duel a mort", "et vas batre en duel a mort", before="amb"
        ),
        "something": _ca("fer alguna cosa"),
        "display": _ca("fer una demostració de poder"),
        "breakthrough": _ca("fer el salt", "a"),
    },
}
# The kinds the world has a word for.
_KINDS = frozenset(k for k in _BOOK[EN] if ":" not in k) - {
    "hurt",
    "went_after",
    "something",
    "display",
    "breakthrough",
}
# Counted in words up to twelve, as they stand before "people": "tres personas", "dues persones".
_NUMBERS = {
    EN: (
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
    ),
    ES: (
        "ninguna",
        "una",
        "dos",
        "tres",
        "cuatro",
        "cinco",
        "seis",
        "siete",
        "ocho",
        "nueve",
        "diez",
        "once",
        "doce",
    ),
    CA: (
        "cap",
        "una",
        "dues",
        "tres",
        "quatre",
        "cinc",
        "sis",
        "set",
        "vuit",
        "nou",
        "deu",
        "onze",
        "dotze",
    ),
}
# The small words of a telling, by language. `others` and `people` take a count above one.
_WORDS = {
    EN: {
        "someone": "someone",
        "other": "one other",
        "others": "{n} others",
        "people": "{n} people",
        "you": "you",
        "yourself": "yourself",
        "themselves": "themselves",
        "duel": " in a duel",
        "reveal_you": "your true strength came out: {what}",
        "reveal": "{who}'s true strength came out: {what}",
        "happened": "Something happened",
        "dead": "was found dead",
        "dead_many": "were found dead",
        "harm": "came to harm",
        "harm_many": "came to harm",
        "blamed": "{what}. {Who} did it, people say.",
        "accident": "{what}: an accident, people say.",
        "unknown": "{what}, and nobody knows who did it.",
        "bounty": "{who} puts a price on {target}'s head.",
    },
    ES: {
        "someone": "alguien",
        "other": "otra persona",
        "others": "otras {n} personas",
        "people": "{n} personas",
        "you": "tú",
        "yourself": "tu propia persona",
        "themselves": "su propia persona",
        "duel": " en duelo",
        "reveal_you": "tu verdadera fuerza salió a la luz: {what}",
        "reveal": "la verdadera fuerza {of} salió a la luz: {what}",
        "happened": "Algo pasó",
        "dead": "apareció sin vida",
        "dead_many": "aparecieron sin vida",
        "harm": "sufrió daños",
        "harm_many": "sufrieron daños",
        "blamed": "{what}. La gente culpa {to}.",
        "accident": "{what}: un accidente, dicen.",
        "unknown": "{what}, y nadie sabe quién lo hizo.",
        "bounty": "{who} pone precio a la cabeza {of}.",
    },
    CA: {
        "someone": "algú",
        "other": "una altra persona",
        "others": "{n} persones més",
        "people": "{n} persones",
        "you": "tu",
        "yourself": "la teva pròpia persona",
        "themselves": "la seva pròpia persona",
        "duel": " en duel",
        "reveal_you": "la teva veritable força va sortir a la llum: {what}",
        "reveal": "la veritable força {of} va sortir a la llum: {what}",
        "happened": "Alguna cosa va passar",
        "dead": "va aparèixer sense vida",
        "dead_many": "van aparèixer sense vida",
        "harm": "va patir danys",
        "harm_many": "van patir danys",
        "blamed": "{what}. La gent culpa {who}.",
        "accident": "{what}: un accident, diuen.",
        "unknown": "{what}, i ningú no sap qui ho va fer.",
        "bounty": "{who} posa preu al cap {of}.",
    },
}
# How a retelling that lost the doer's name begins (W2).
GARBLED_LEADS = {
    EN: GARBLED_LEAD,
    ES: "Corre una versión confusa: ",
    CA: "Corre una versió confusa: ",
}
# Kinds done to places, told by the places when nobody was harmed: "burned the granary".
_ON_PLACES = frozenset({"raze", "burn", "destroy", "conquer"})
# Kinds that say less than a death: an attack that killed is told as a killing.
_DEADLY = frozenset({"assault", "wound"})
_KILLING = frozenset({"kill", "massacre"})
# Resolve's outcome note at the end of a step's text: "(it worked)", "(it partly worked)".
_OUTCOME = re.compile(r"\s*\((it worked|it partly worked|it failed)\)\s*$")
_OUTCOME_SAID = {
    ES: {
        "it worked": "salió bien",
        "it partly worked": "salió a medias",
        "it failed": "salió mal",
    },
    CA: {
        "it worked": "va sortir bé",
        "it partly worked": "va sortir a mitges",
        "it failed": "va sortir malament",
    },
}
# The wounds the engine names itself, as (Spanish, Catalan): a breakthrough that went badly
# (A4) and a blast thrown in stopped time (W10a). Any other wound is named by the story.
_WOUNDS = {
    "a breakthrough that stalled": (
        "un salto que se quedó a medias",
        "un salt que es va quedar a mitges",
    ),
    "a breakthrough gone wrong": ("un salto que salió mal", "un salt que va sortir malament"),
    "caught in the blast": ("golpe de la explosión", "cop de l'explosió"),
    "caught in the edge of their own blast": (
        "el borde de la propia explosión",
        "la vora de la pròpia explosió",
    ),
    "knocked down by the distant blast": (
        "sacudida de la explosión lejana",
        "sotragada de l'explosió llunyana",
    ),
}
# Spanish nouns that take "una" without ending in -a, and ones in -a that take "un", for a
# beast told by its kind ("una serpiente", "un fantasma").
_ES_UNA = frozenset({"serpiente", "liebre", "sierpe", "res", "perdiz", "lombriz", "esfinge"})
_ES_UN = frozenset({"fantasma"})
# W1. A bout both sides agreed to, told by its terms.
_BOUT = {Terms.NO_HARM: "bout:no_harm", Terms.WOUNDS: "bout:wounds", Terms.DEATH: "bout:death"}
_VOWELS = "aeiouhàáèéíïòóúü"


def cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def number(count: int, language: Language = EN) -> str:
    words = _NUMBERS[language]
    return words[count] if 0 <= count < len(words) else str(count)


def _and(language: Language, following: str) -> str:
    """The word that joins the last of a list: "and", Catalan "i", and Spanish "y", which is
    "e" before a word that starts with the sound of an i ("Han Jie e Ilya", "e hirió")."""
    if language is EN:
        return "and"
    if language is CA:
        return "i"
    start = following.casefold()
    for opening in ("i", "hi"):
        rest = start.removeprefix(opening)
        if rest != start and rest[:1] not in tuple("aeoáéó"):
            return "e"
    return "y"


def _joined(language: Language, items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {_and(language, items[-1])} {items[-1]}"


def with_word(language: Language, word: str, name: str) -> str:
    """`word` before `name`, run together where the language does: "al pozo", "del viejo Hu",
    "als turons", "d'Olot". A name's own capital article stays apart ("a El Paso")."""
    if not word:
        return name
    if language is not EN and word in ("a", "de"):
        first, _, rest = name.partition(" ")
        if rest and first == "el":
            return f"{word}l {rest}"
        if rest and first == "els" and language is CA:
            return f"{word}ls {rest}"
        if word == "de" and language is CA and name[:1].casefold() in _VOWELS:
            return f"d'{name}"
    return f"{word} {name}"


def _counted(language: Language, names: list[str], more: int, most: int) -> list[str]:
    """The names as people list them, then how many more: at most `most` things said."""
    words = _WORDS[language]
    names = list(dict.fromkeys(n for n in names if n))
    if not names:
        if more <= 0:
            return []
        return [words["someone"] if more == 1 else words["people"].format(n=number(more, language))]
    if len(names) + (1 if more > 0 else 0) > most:
        rest = len(names) - (most - 1) + max(0, more)
        return [*names[: most - 1], words["others"].format(n=number(rest, language))]
    if more == 1:
        return [*names, words["other"]]
    if more > 1:
        return [*names, words["others"].format(n=number(more, language))]
    return names


def listing(names: list[str], *, most: int = 3, more: int = 0, language: Language = EN) -> str:
    """Names as people say them: "A", "A and B", "A, B and C", or "A, B and four others".
    `more` counts those without a name: "A and one other", "someone", "three people"."""
    return _joined(language, _counted(language, names, more, most))


def where(
    state: WorldState,
    place_id: str | None,
    teller: Teller | None = None,
    language: Language = EN,
) -> str:
    """ " in Willow Ford" for a region of its own, " at the outer-court well" for a spot, or
    nothing where the place isn't known. Spanish says both with "en", Catalan with "a"."""
    place = state.places.get(place_id) if place_id else None
    named = (teller or Truth(state)).name(place) if place is not None else None
    if not named:
        return ""
    if language is ES:
        return f" en {named}"
    if language is CA:
        return f" {with_word(CA, 'a', named)}"
    word = "in" if place.kind.strip().casefold() in REGION_KINDS else "at"
    return f" {word} {named}"


def plain_text(deed: Deed) -> str:
    """The deed's own text without resolve's outcome note."""
    return _OUTCOME.sub("", deed.text).strip().rstrip(".")


def own_words(deed: Deed, language: Language = EN) -> str:
    """A deed the world has no words for, in its own: the step as the player put it, with
    resolve's outcome note in the story's language ("(salió bien)")."""
    found = _OUTCOME.search(deed.text)
    if found is None or language is EN:
        return cap(deed.text)
    return cap(f"{deed.text[: found.start()].rstrip()} ({_OUTCOME_SAID[language][found[1]]})")


def wound_said(text: str, language: Language = EN) -> str:
    """A wound's name as a sheet shows it: one the engine named, in the story's language."""
    said = _WOUNDS.get(text.strip())
    if said is None or language is EN:
        return text
    return said[0 if language is ES else 1]


def struck_names(state: WorldState, ids: list[str], language: Language = EN) -> list[str]:
    """Who a deed fell on, by name: a host such as an army stands for the members of it who fell
    with it, and places and nameless victims are left out."""
    return _struck(state, ids, Truth(state), language=language)[0]


def _struck(
    state: WorldState,
    ids: list[str],
    teller: Teller,
    *,
    doer_id: str | None = None,
    language: Language = EN,
) -> tuple[list[str], int]:
    """Who a deed fell on, as the teller knows them, and how many more they can't name: a host
    such as an army stands for its members who fell with it, a beast they don't know is "an ash
    wolf", the doer is SELF, and nameless victims (the villagers of a massacre) are counted.
    Places are left out. A name already given counts as one more."""
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
            named = SELF
        elif not named and creature is not None:
            named = f"{_article(creature.name, language)} {creature.name}"
        if named and named not in names:
            names.append(named)
        else:
            unnamed += 1
    return names, unnamed


def _clause(
    language: Language,
    verb: _Verb,
    on: list[str],
    more: int = 0,
    *,
    you: bool = False,
    people: bool = True,
) -> str:
    """The verb and whom it fell on, as its doer did it: "killed Han Jie and one other", "te
    hirió", "va fer regals a Han Jie". `you` is whether the player character did it, and
    `people` is false for a deed told by the places it fell on."""
    words = _WORDS[language]
    said = verb.said(you)
    alone = len(on) == 1 and not more
    own = words["yourself" if you else "themselves"]
    if language is EN:
        names = [own if n == SELF else n for n in on]
        before = f" {verb.before}" if verb.before else ""
        return f"{said}{before} {listing(names, more=more)}"
    # Spanish puts "a" before a person, and Catalan before a pronoun. Where a verb brings no
    # word of its own (Catalan "a" aside), the one telling it is a small word before the verb:
    # "te hirió", "es va ferir".
    before = verb.before or ("a" if people and language is ES else "")
    small = ""
    if people and (not verb.before or (language is CA and verb.before == "a")):
        mine, theirs = ("te", "se") if language is ES else ("et", "es")
        if SELF in on:
            # "se hirió", and with others "se hirió e hirió a Zhao Kun".
            own_way = f"{mine if you else theirs} {said}"
            if alone:
                return own_way
            others = _clause(language, verb, [n for n in on if n != SELF], more, you=you)
            return f"{own_way} {_and(language, others)} {others}"
        if YOU in on:
            if alone:
                return f"{mine} {said}"
            small, before = f"{mine} ", "a"
    items = []
    for item in _counted(language, on, more, 3):
        if item == YOU:
            item = (
                "contigo"
                if before == "con"
                else with_word(language, before, "ti" if language is ES else "tu")
            )
        else:
            item = with_word(language, before, own if item == SELF else item)
        items.append(item)
    return f"{small}{said} {_joined(language, items)}"


def _who(language: Language, subject: str) -> str:
    return _WORDS[language]["someone"] if subject == SOMEONE else subject


def _sentence(language: Language, subject: str, clauses: list[str], tail: str = "") -> str:
    """One sentence of a telling: who, what they did and to whom, and where. Spanish and
    Catalan say "you" with the verb alone."""
    body = clauses[0]
    for clause in clauses[1:]:
        body = f"{body} {_and(language, clause)} {clause}"
    if subject == YOU and language is not EN:
        return f"{cap(body)}{tail}."
    return f"{cap(_who(language, subject))} {body}{tail}."


def account(
    state: WorldState,
    deed: Deed,
    *,
    doer: str | None = None,
    teller: Teller | None = None,
    language: Language = EN,
) -> str:
    """One sentence telling a deed as people would: "Lin Feng killed Han Jie at the well." The
    doer is named unless `doer` says otherwise (SOMEONE)."""
    told = tell(state, deed, doer=doer, teller=teller, language=language)
    if told is not None:
        return told
    subject = _subject(state, deed, doer, teller or Truth(state))
    text = plain_text(deed)
    if not text:
        did = _BOOK[language]["something"].said(subject == YOU)
        return _sentence(language, subject, [did], where(state, deed.place_id, teller, language))
    who = _WORDS[language]["you"] if subject == YOU else _who(language, subject)
    return f"{cap(who)}: {text[:1].lower()}{text[1:]}."


def tell(
    state: WorldState,
    deed: Deed,
    *,
    doer: str | None = None,
    teller: Teller | None = None,
    language: Language = EN,
) -> str | None:
    """The deed told from what it records, or None where only its own text could tell it (a
    kind the world has no words for, done to nobody it can name)."""
    teller = teller or Truth(state)
    subject = _subject(state, deed, doer, teller)
    you = subject == YOU
    word = canonical(deed.kind)
    place = where(state, deed.place_id, teller, language)
    what = deed_nature(state, deed)
    book = _BOOK[language]
    if word in ("breakthrough", "reveal", "display"):
        return _display(language, subject, word, deed, place)

    def whom(ids: list[str]) -> tuple[list[str], int]:
        return _struck(state, ids, teller, doer_id=deed.actor_id, language=language)

    def did(key: str, on: list[str], more: int, people: bool = True) -> str:
        return _clause(language, book[key], on, more, you=you, people=people)

    def said(*clauses: str, how: str = "") -> str:
        return _sentence(language, subject, list(clauses), f"{how}{place}")

    if deed.is_bout:
        # W1. A fight both sides agreed to is told as one, never as an attack.
        partners, others = whom(deed.target_ids)
        return said(did(_BOUT[deed.terms], partners, others))
    harmful = what in (Nature.HARM, Nature.HUNT)
    hosts = [t for t in deed.target_ids if t in state.factions]
    on, unnamed = whom([*deed.victim_ids, *hosts] if harmful else deed.target_ids)
    people = True
    if harmful and not on and not unnamed and word not in _ON_PLACES:
        # Nobody was harmed: it was an attempt on its targets.
        tried, untold = whom(deed.target_ids)
        if tried or untold:
            attempt = f"try:{word}"
            key = attempt if attempt in book else word if word in _KINDS else "went_after"
            return said(did(key, tried, untold))
    if word in _ON_PLACES and not on:
        # Razed or burned: told by the places, unless it fell on people they can name.
        places = [
            n for t in deed.target_ids if t in state.places and (n := teller.name(state.places[t]))
        ]
        if places:
            on, unnamed, people = places, 0, False
    key = word if word in _KINDS else None
    dead = [v for v in deed.victim_ids if teller.believes_dead(v, deed)]
    if harmful and (key is None or word in _DEADLY or word == "kill") and dead:
        survivors = [v for v in deed.victim_ids if v not in dead]
        if survivors and not hosts:
            # Some died of it and some lived: "killed Han Jie and wounded you".
            fell, more_fell = whom(dead)
            lived, more_lived = whom(survivors)
            return said(did("kill", fell, more_fell), did("wound", lived, more_lived))
        key = "kill"
    elif harmful and word in _KILLING and not dead:
        key = "wound" if word == "kill" else "assault"  # nobody died of it
    elif harmful and key is None:
        key = "hurt"
    if key is not None and (on or unnamed):
        # W1: a death both accepted was "in a duel".
        how = _WORDS[language]["duel"] if deed.agreed and key == "kill" else ""
        return said(did(key, on, unnamed, people), how=how)
    return None


def _subject(state: WorldState, deed: Deed, doer: str | None, teller: Teller) -> str:
    if doer is not None:
        return doer
    actor = state.characters.get(deed.actor_id)
    return (teller.name(actor) if actor is not None else None) or SOMEONE


def _article(word: str, language: Language = EN) -> str:
    """ "a" or "an" before a kind of beast, and "un" or "una" by how the word ends."""
    if language is EN:
        return "an" if word[:1].casefold() in "aeiou" else "a"
    first = word.split(" ")[0].casefold()
    if language is ES and first in _ES_UNA:
        return "una"
    if language is ES and first in _ES_UN:
        return "un"
    return "una" if first.endswith("a") else "un"


def _display(language: Language, subject: str, word: str, deed: Deed, place: str) -> str:
    """A show of power, told by what it showed (A4, G19, G20)."""
    text = plain_text(deed)
    words = _WORDS[language]
    book = _BOOK[language]
    you = subject == YOU
    if word == "breakthrough" and " to " in text:
        rung = text.split(" to ", 1)[1]
        reached = _clause(language, book[word], [rung], you=you, people=False)
        return _sentence(language, subject, [reached], place)
    if word == "reveal" and ": " in text:
        what = text.split(": ", 1)[1]
        who = _who(language, subject)
        came_out = (
            words["reveal_you"].format(what=what)
            if you
            else words["reveal"].format(who=who, of=with_word(language, "de", who), what=what)
        )
        return f"{cap(came_out)}{place}."
    return _sentence(language, subject, [book["display"].said(you)], place)


def found(state: WorldState, deed: Deed, language: Language = EN) -> str:
    """What people found of a deed nobody saw, before anyone knows who did it (W13): the sight
    that gave it away, and who was found dead or harmed. One or two sentences, the last without
    its closing stop, for the rumor to finish ("..., and nobody knows who did it."). The sight
    is in the engine's own English, so only an English story tells it."""
    lead = ""
    if language is EN:
        lead = next(
            (t.text.strip() for t in deed.traces if t.kind.value in ("noise", "damage") and t.text),
            "",
        ).rstrip(".")
    words = _WORDS[language]
    place = where(state, deed.place_id, language=language)
    if not deed.victim_ids:
        return cap(lead) if lead else f"{words['happened']}{place}"
    names = struck_names(state, deed.victim_ids, language)
    whom = listing(names, language=language) or words["someone"]
    many = "_many" if len(names) > 1 else ""
    fate = "dead" if killed(state, deed.victim_ids) else "harm"
    what = f"{whom} {words[fate + many]}{place}"
    return f"{cap(lead)}. {cap(what)}" if lead else cap(what)


def garbled(told: str, language: Language = EN) -> str:
    """A retelling that strayed far from what happened, as it goes round (W2)."""
    return f"{GARBLED_LEADS[language]}{told}"


def unexplained(what: str, how: str, blamed: str = "", language: Language = EN) -> str:
    """What people say of a find nobody can explain (W13): `how` is "unknown", "accident" or
    "blamed", which lays it at the door of the faction `blamed` names."""
    return _WORDS[language][how].format(
        what=what, who=blamed, Who=cap(blamed), to=with_word(language, "a", blamed)
    )


def bounty(who: str, target: str, language: Language = EN) -> str:
    """Word that a price is on someone's head (W5), as the rumor of it goes round."""
    return _WORDS[language]["bounty"].format(
        who=cap(who), target=target, of=with_word(language, "de", target)
    )


# What people say of a change to the wider world (W6), by its kind. A war's end is told of the
# war, so no verb has to agree with a faction's name, which may be one or many ("los Lobos
# Grises"): what follows a place agrees with how many places there are.
_CHANGES = {
    EN: {
        "beaten": "{Winner} beat {loser} in their war",
        "took": " and took {places}",
        "took_many": " and took {places}",
        "fell": "{Loser} fell to {winner} in their war",
        "fell_took": ", and what was theirs is {winner}'s now",
        "spent": "The war between {both} wore both sides down, and neither won",
        "both_fell": "{Both} destroyed each other in their war",
        "both_left": ", and what was theirs is nobody's now",
        "seized": "{Winner} took {places}, which nobody had held since the war",
    },
    ES: {
        "beaten": "La guerra entre {both} se decantó del lado {of_winner}",
        "took": ", y {places} pasó a sus manos",
        "took_many": ", y {places} pasaron a sus manos",
        "fell": "La guerra entre {both} acabó con la caída {of_loser}",
        "fell_took": ", y lo que era suyo pasó a manos {of_winner}",
        "spent": "La guerra entre {both} dejó exhaustos a ambos bandos, sin vencedor",
        "both_fell": "La guerra entre {both} acabó con ambos bandos",
        "both_left": ", y lo que era suyo quedó sin dueño",
        "seized": "{Places} pasó a manos {of_winner}, tras quedar sin dueño en la guerra",
    },
    CA: {
        "beaten": "La guerra entre {both} es va decantar del costat {of_winner}",
        "took": ", i {places} va passar a les seves mans",
        "took_many": ", i {places} van passar a les seves mans",
        "fell": "La guerra entre {both} va acabar amb la caiguda {of_loser}",
        "fell_took": ", i el que era seu va passar a mans {of_winner}",
        "spent": "La guerra entre {both} va deixar exhaustos tots dos bàndols, sense cap vencedor",
        "both_fell": "La guerra entre {both} va acabar amb tots dos bàndols",
        "both_left": ", i el que era seu va quedar sense amo",
        "seized": "{Places} va passar a mans {of_winner}, després de quedar sense amo a la guerra",
    },
}
_CHANGE_TAILS = {
    WorldChangeKind.BEATEN: "took",
    WorldChangeKind.FELL: "fell_took",
    WorldChangeKind.BOTH_FELL: "both_left",
}


def world_change(state: WorldState, change: WorldChange, language: Language = EN) -> str:
    """What people say of a change to the wider world (W6, `engine.world.strife`): a war
    that came to a head, or land nobody held that someone took. One sentence in the story's
    language (S10), by the names on record: whoever hears it learns them. A war's end names
    the places it took only where one side was beaten: a side that fell lost all it had."""
    words = _CHANGES[language]
    nobody = _WORDS[language]["someone"]
    sides = [state.factions[i].name if i in state.factions else nobody for i in change.faction_ids]
    winner, loser = sides[0], sides[-1]
    places = [state.places[i].name for i in change.place_ids if i in state.places]
    named = listing(places, language=language)
    both = _joined(language, [winner, loser])
    said = {
        "winner": winner,
        "Winner": cap(winner),
        "loser": loser,
        "Loser": cap(loser),
        "both": both,
        "Both": cap(both),
        "of_winner": with_word(language, "de", winner),
        "of_loser": with_word(language, "de", loser),
        "places": named,
        "Places": cap(named),
    }
    text = words[change.kind.value].format(**said)
    tail = _CHANGE_TAILS.get(change.kind)
    if tail and places:
        if tail == "took" and len(places) > 1:
            tail = "took_many"
        text += words[tail].format(**said)
    return f"{text}."
