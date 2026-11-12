"""G1, G2: whether the player's own words name something of a draft.

A draft's summary never gives away how the story starts (Miki, 2026-11-10): its first goal, its
first event and the first people in the character's life are the story's surprise. So a deadline,
a question, a goal or a person is shown before the story starts only when the player's own words
name it: the premise ("the trial of knighthood is in three days") or a change they asked for.
The drafter still writes the rest, and the story tells it in play.

Plain Python: no model reads the premise for this. The player's words name a thing (`named`)
when they say more than two thirds of it, or all of it but one word where two of those words
stand together in them, so "Find out who killed my father" is named by "someone inside the
family killed my father", and "The council picks the next boss" is not, though both speak of a
boss, and neither is "The heroine tells the prince" by a premise that speaks of both. A deadline
is also named by a clause that sets a time ahead and holds one word of it (`timed`), so "the
knight exam is in 3 days" names "The trial of knighthood". A person is named by their name and
nothing else (`called`): what a premise says of its own character ("the weakest outer
disciple") fits half the people around them, so a description names nobody.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

from engine.base import DAY, HOUR, WEEK, YEAR
from engine.context import Language
from graph.words import FILLER, WORD, alike, content, core

# Where the player's words stop standing together: the end of a clause or a line.
_BREAK = re.compile(r"[.,;:!?¿¡…—–()\[\]\"«»“”\n]+")
# Where a sentence of theirs ends: a time set in one sentence is not for an event in another.
_SENTENCE = re.compile(r"[.!?¿¡…\n]+")

# A time ahead, by language: "in three days", "nine days left", "tomorrow". A time gone by
# ("three days ago", "hace tres días") is none, and neither is a bare "for ten years".
_AMOUNT = r"(?:[\w'’-]+\s+){1,2}?"
_NOT_MORNING = "".join(rf"(?<!\b{word}\s)" for word in "esta la una cada aquella esa toda".split())
_UNITS = {
    Language.EN: r"(?:hour|day|night|week|month|year|moon)s?",
    Language.ES: r"(?:horas?|d[ií]as?|noches?|semanas?|mes(?:es)?|años?|lunas?)",
    Language.CA: r"(?:hor(?:a|es)|di(?:a|es)|nits?|setman(?:a|es)|mes(?:os)?|anys?|llun(?:a|es))",
}
_AHEAD = {
    Language.EN: (
        r"\b(?:in|within)\s+{amount}{unit}\b",
        r"\b(?:{amount})?{unit}\s+(?:from now|away|left|remain|until|till|before|to go|for the)\b",
        r"\b(?:tomorrow|tonight|next\s+{unit})\b",
    ),
    Language.ES: (
        r"\b(?:en|dentro de)\s+{amount}{unit}\b",
        r"\b(?:faltan?|quedan?)\s+{amount}{unit}\b",
        r"\b(?:{amount})?{unit}\s+(?:para|hasta|antes)\b",
        r"\ba\s+{amount}{unit}\s+del?\b",
        # "esta mañana" and "por la mañana" are the morning, not the day after.
        rf"(?:{_NOT_MORNING}\bmañana|\besta noche)\b",
    ),
    Language.CA: (
        r"(?:\bd'aquí a|\ben|\bdins de)\s+{amount}{unit}\b",
        r"\b(?:falten?|queden?)\s+{amount}{unit}\b",
        r"\b(?:{amount})?{unit}\s+(?:per|fins|abans)\b",
        r"\ba\s+{amount}{unit}\s+del?\b",
        r"\b(?:demà|aquesta nit)\b",
    ),
}
_TIME_AHEAD = {
    language: re.compile(
        "|".join(p.format(amount=_AMOUNT, unit=_UNITS[language]) for p in patterns),
        re.IGNORECASE,
    )
    for language, patterns in _AHEAD.items()
}


def named(said: str, text: str, language: Language) -> bool:
    """Whether `said`, the player's own words, name the thing `text` tells of: they say more
    than two thirds of it, or they say all of it but one word and two of those words stand
    together in them, as "killed my father" does in "Find out who killed my father"."""
    its = content(text, language)
    if not its:
        return False
    clauses = [words for clause in _BREAK.split(said) if (words := content(clause, language))]
    theirs = [word for clause in clauses for word in clause]
    told = sum(any(alike(word, other) for other in theirs) for word in its)
    if 3 * told > 2 * len(its):
        return True
    if told < len(its) - 1:
        return False

    def in_it(word: str) -> bool:
        return any(alike(word, other) for other in its)

    return any(
        in_it(one) and in_it(other)
        for clause in clauses
        for one, other in zip(clause, clause[1:], strict=False)
    )


def called(said: str, name: str, language: Language) -> bool:
    """Whether `said`, the player's own words, call someone by `name`: one word of it written
    with a capital, or all of a name of two words or more in any case, so "Zhao" and "zhao kun"
    both call Zhao Kun, "my old master" doesn't call Old Hu, and "I hope to win" doesn't call
    Hope."""
    theirs = {core(word) for word in WORD.findall(name)}
    if not theirs:
        return False
    words = WORD.findall(said)
    capitals = {core(word) for word in words if word[0].isupper()} - FILLER[language]
    if capitals & theirs:
        return True
    return len(theirs) > 1 and theirs <= {core(word) for word in words}


# How long the time ahead is, where code can read it: an amount and a unit. What each unit
# lasts, and the numbers a premise writes out. A month and a moon are thirty days, as "in a
# month" is meant. Anything else, such as "a few days" or "tomorrow", is a time ahead with no
# length code can tell.
MONTH = 30 * DAY
_SPANS = {
    Language.EN: (
        ("hour", HOUR),
        ("day", DAY),
        ("night", DAY),
        ("week", WEEK),
        ("month", MONTH),
        ("moon", MONTH),
        ("year", YEAR),
    ),
    Language.ES: (
        ("hora", HOUR),
        ("día", DAY),
        ("dia", DAY),
        ("noche", DAY),
        ("semana", WEEK),
        ("mes", MONTH),
        ("luna", MONTH),
        ("año", YEAR),
    ),
    Language.CA: (
        ("hor", HOUR),
        ("di", DAY),
        ("nit", DAY),
        ("setman", WEEK),
        ("mes", MONTH),
        ("llun", MONTH),
        ("any", YEAR),
    ),
}
# The numbers a premise writes out. From one to twenty, each place holds its words.
_COUNT = {
    Language.EN: """a|an|one two three four five six seven eight nine ten eleven twelve thirteen
        fourteen fifteen sixteen seventeen eighteen nineteen twenty""",
    Language.ES: """un|una|uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece
        catorce quince dieciséis diecisiete dieciocho diecinueve veinte""",
    Language.CA: """un|una|u dos|dues tres quatre cinc sis set vuit nou deu onze dotze tretze
        catorze quinze setze disset divuit dinou vint""",
}
_TENS = {
    Language.EN: "twenty thirty forty fifty sixty seventy eighty ninety",
    Language.ES: "veinte treinta cuarenta cincuenta sesenta setenta ochenta noventa",
    Language.CA: "vint trenta quaranta cinquanta seixanta setanta vuitanta noranta",
}
_MORE = {
    Language.EN: {"hundred": 100},
    Language.ES: {
        "veintiún": 21,
        "veintiuno": 21,
        "veintiuna": 21,
        "veintidós": 22,
        "veintitrés": 23,
        "veinticuatro": 24,
        "veinticinco": 25,
        "veintiséis": 26,
        "veintisiete": 27,
        "veintiocho": 28,
        "veintinueve": 29,
        "cien": 100,
    },
    Language.CA: {"cent": 100},
}
# The words a time ends on when it counts down to what comes after it: "three days before the
# exam" is the exam's, and "the caravan left a day before you" is not the caravan's.
_TOWARDS = {
    Language.EN: ("until", "till", "before", "for the"),
    Language.ES: ("para", "hasta", "antes"),
    Language.CA: ("per", "fins", "abans"),
}
# The words that only hedge an amount, and the ones that join a ten to its unit ("treinta y
# un", "vint-i-un").
_HEDGES = {
    Language.EN: "about around roughly nearly almost only just exactly barely another more the",
    Language.ES: "unos unas solo sólo apenas casi exactamente justo otros otras más los las",
    Language.CA: "uns unes només gairebé exactament just altres més els les",
}
_JOINS = ("y", "i")
_TOKEN = re.compile(rf"\d+|{WORD.pattern}")
_UNIT = {language: re.compile(rf"\b{unit}\b", re.IGNORECASE) for language, unit in _UNITS.items()}


def _numbers(language: Language) -> dict[str, int]:
    numbers = {
        word: at
        for at, words in enumerate(_COUNT[language].split(), start=1)
        for word in words.split("|")
    }
    numbers |= {word: 10 * at for at, word in enumerate(_TENS[language].split(), start=2)}
    return numbers | _MORE[language]


_NUMBER = {language: _numbers(language) for language in Language}


@dataclass(frozen=True)
class Ahead:
    """A time ahead the player's own words set: the words it is said of, and how long it is in
    seconds, or None where code can't tell ("in a few days", "tomorrow")."""

    about: tuple[str, ...]
    seconds: int | None = None

    def says(self, text: str, language: Language) -> int:
        """How many of the words of `text`, an event's name, the time is said of."""
        return sum(
            any(alike(word, other) for other in self.about) for word in content(text, language)
        )


def times_ahead(said: str, language: Language) -> Iterator[Ahead]:
    """Each time ahead `said` sets, clause by clause. A time is said of the rest of its clause,
    or, when it is all its clause says, of the rest of the sentence ("The tax collector comes
    with the first snow, in thirty days"); one that counts down to something ("three days
    before the exam") is said of what follows it. A clause that sets two times ("the exam in
    three days and the wedding in a week") gives no length, since code can't tell whose each
    is."""
    ahead = _TIME_AHEAD[language]
    for sentence in _SENTENCE.split(said):
        clauses = _BREAK.split(sentence)
        for at, clause in enumerate(clauses):
            found = list(ahead.finditer(clause))
            if not found:
                continue
            first = found[0]
            if first.group(0).casefold().endswith(_TOWARDS[language]):
                about = content(clause[first.end() :], language)
            else:
                about = content(f"{clause[: first.start()]} {clause[first.end() :]}", language)
                if not about:
                    about = content(" ".join(clauses[:at] + clauses[at + 1 :]), language)
            seconds = _span(first.group(0), language) if len(found) == 1 else None
            yield Ahead(tuple(about), seconds)


def timed(said: str, text: str, language: Language) -> bool:
    """Whether `said`, the player's own words, set a time for the event `text` names: a clause
    of theirs gives a time ahead and holds a word of it. "I take the knight exam in 3 days"
    times "The trial of knighthood"; "my father was killed three days ago" times nothing; and
    "I'm sure the killer is in the family, and the council names the next boss in ten days"
    times the council's vote, not "The killer strikes again"."""
    return any(time.says(text, language) for time in times_ahead(said, language))


def _span(text: str, language: Language) -> int | None:
    """How long the time ahead `text` is, in seconds: its amount times its unit, "in 3 days",
    "dentro de cinco días", "d'aquí a dues setmanes". None for an amount code can't read, and
    for "tomorrow" and "tonight", whose length hangs on the hour the story opens at."""
    unit = _UNIT[language].search(text)
    if unit is None:
        return None
    name = unit.group(0).casefold()
    size = next(seconds for stem, seconds in _SPANS[language] if name.startswith(stem))
    amount = _amount(text[: unit.start()], language)
    if amount is None or not 0 < amount * size <= 10 * YEAR:
        return None
    return amount * size


def _amount(text: str, language: Language) -> int | None:
    """The number `text` ends on, in figures or in words: "3", "three", "twenty-one",
    "vint-i-un", "a hundred". None when the word before the unit is no number ("a few")."""
    numbers, hedges = _NUMBER[language], _HEDGES[language].split()
    words = [core(word) for token in _TOKEN.findall(text) for word in token.split("-")]
    values: list[int] = []
    for word in reversed(words):
        if word in hedges or (values and word in _JOINS):
            continue
        if word.isdigit():
            values.insert(0, int(word))
        elif word in numbers:
            values.insert(0, numbers[word])
        else:
            break
    match values:
        case [value]:
            return value
        # "twenty one": a ten and what is added to it.
        case [ten, one] if ten >= 20 and ten % 10 == 0 and one < 10:
            return ten + one
        case [1, 100]:
            return 100
    return None
