"""G1, G2: whether the player's own words name something of a draft.

A draft's summary never gives away how the story starts (Miki, 2026-11-10): its first goal, its
first event and the first people in the character's life are the story's surprise. So a deadline,
a question, a goal or a person is shown before the story starts only when the player's own words
name it: the premise ("the trial of knighthood is in three days") or a change they asked for.
The drafter still writes the rest, and the story tells it in play, all but a goal or a want
their words don't say: that is no surprise but a guess, and the story starts without it
(`graph.drafting.openers.own_aims`).

Plain Python: no model reads the premise for this. The player's words name a thing (`named`)
when they say more than two thirds of it, or all of it but one word where two of those words
stand together in them, so "Find out who killed my father" is named by "someone inside the
family killed my father", and "The council picks the next boss" is not, though both speak of a
boss, and neither is "The heroine tells the prince" by a premise that speaks of both. A deadline
is also named by a clause that sets a time ahead and holds one word of it (`timed`), so "the
knight exam is in 3 days" names "The trial of knighthood". A person is named by their name and
nothing else (`called`): what a premise says of its own character ("the weakest outer
disciple") fits half the people around them, so a description names nobody. And what the
character is after, a goal or a want, is theirs only where a sentence of theirs says it as an
aim (`aimed`): "the knight exam is in 3 days" names "Pass the knight exam" and says no aim, so
there is no such goal until "I must pass the knight exam" makes it the player's.
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


# G1, G2: the words that say a thing as something the character is after, by language: wanting,
# having to, meaning to, looking for, the names of an aim, and what it is to them ("I break
# through or I die"), in the first, second and third person a premise is written in. The
# summary's own labels for a goal and a want are among them, so a line of it the player rewrote
# says one too. They count only beside the aim's own words (`aimed`), so "going to the market"
# says none.
_AIMS = {
    Language.EN: """want(?:s|ed|ing)? wanna wish(?:es|ed)? desires? long(?:s|ing)?_to
        need(?:s|ed)?_to must ha(?:ve|s|d)_to got_to gotta (?:i|we|you)['’]ll
        (?:i|we|you)_will going_to gonna aim(?:s|ed|ing)? hop(?:e|es|ed|ing)
        plan(?:s|ned|ning)? intend(?:s|ed)? mean(?:s|t)?_to tr(?:y|ies|ied|ying)_to determined
        resolved decided set_out swor[en] swears? vow(?:s|ed)? oath promis(?:e|es|ed)
        looking_for search(?:ing)?_for seek(?:s|ing)? sought hunt(?:s|ing)? chas(?:e|es|ing)
        dream(?:s|ed|t)? goals? ambitions? mission quest purpose objective in_order_to
        so_as_to so_(?:that_)?(?:i|we|you)_can
        or_(?:(?:i|we|you|he|she|they)(?:['’]ll|_will)?_)?(?:dies?|perish(?:es)?)""",
    Language.ES: """quier[oea]s? queremos quería quisiera dese[oa]s? ansí[oa]s? necesit[oa]s?
        deb[oe]s? t(?:engo|ienes?)_que h(?:e|as?)_de v(?:oy|as?)_a piens[oa]s? pretend[oe]s?
        intent[oa]s? busc[oa]s? buscando persig[oa] persigues? jur[éoó] juraste jurado
        promet[íoe] prometiste prometido espero sueñ[oa]s? objetivos? metas? ambici[oó]n
        misi[oó]n prop[oó]sito decidid[oa] con_el_fin_de a_fin_de
        o_(?:me_|se_)?(?:muer[oe]s?|morir[éá]s?)""",
    Language.CA: """vull vols? volem volia voldria desitj[oa] desitges anhel[oa] anheles
        necessit[oa] necessites h(?:e|as?)_de haig_de tinc_de tens_de cal_que penso penses
        pretenc pretens pretén intent[oa] intentes busc[oa] busques buscant persegueix(?:o|es)?
        juro jures jurat vaig_jurar vas_jurar prometo promets promès espero somi[oa] somies
        somnis? objectius? metes? meta ambició missió propòsit decidi[td]a? per_tal_de a_fi_de
        o_(?:em_|es_)?(?:mor[oi]?s?|morir[éà]s?)""",
}
# Each marker stands as whole words; a `_` in one is the space between two of its words.
_AIM = {
    language: re.compile(
        rf"(?<!\w)(?:{'|'.join(words.replace('_', r'\s+').split())})(?!\w)", re.IGNORECASE
    )
    for language, words in _AIMS.items()
}
# What an aim is done for, said with its own first word: "I came to the city to become a
# knight", "para pagar la deuda", "per trobar la meva germana". In English "to" follows much
# that is no purpose ("about to take the exam", "never able to draw aura"), so those don't
# count.
_FOR = {
    Language.EN: (("to",),),
    Language.ES: (("para",),),
    Language.CA: (("per", "a"), ("per",)),
}
_NOT_FOR = frozenset(
    """about able unable used supposed due forced made said known how yet fail fails failed bound
    likely seem seems seemed""".split()
)


def aimed(said: str, text: str, language: Language) -> bool:
    """Whether `said`, the player's own words, say the thing `text` tells of as something the
    character is after: a sentence of theirs says an aim ("I want to", "I must", "my goal is",
    "looking for", "or I die", or "to" before the aim's own first word) and names it (`named`),
    or says its first word where their words as a whole name it, as "Someone killed my father.
    I will find out who." does for "Find out who killed my father". An aim's first word is the
    deed, which a drafter says in a verb of its own, so a sentence that says an aim names it
    also by what follows that word: "I want to be a pirate" gives "Become a pirate". "I take
    the knight exam in 3 days" sets a deadline and says no aim, so the goal a drafter makes of
    it is theirs, not the player's."""
    its = content(text, language)
    if not its:
        return False
    lead, rest = its[0], " ".join(its[1:])
    whole: bool | None = None
    for sentence in _SENTENCE.split(said):
        words = [core(word) for word in WORD.findall(sentence)]
        if not (_AIM[language].search(sentence) or _done_for(words, lead, language)):
            continue
        if named(sentence, text, language) or named(sentence, rest, language):
            return True
        if any(alike(word, lead) for word in words):
            if whole is None:
                whole = named(said, text, language)
            if whole:
                return True
    return False


# How long a premise can be and still be one aim and nothing else.
ONE_AIM_WORDS = 12


def one_aim(said: str, language: Language) -> bool:
    """Whether `said`, the player's own words, are one short sentence that says what the
    character is after and nothing more, as "I want to be a pirate." does. A drafter that
    hands such words back whole as the goal has still named the aim."""
    sentences = [sentence for sentence in _SENTENCE.split(said) if WORD.search(sentence)]
    if len(sentences) != 1 or len(WORD.findall(said)) > ONE_AIM_WORDS:
        return False
    return bool(_AIM[language].search(sentences[0]))


# How a sentence opens when it says outright, of its own speaker, what they are after. An aim's
# word further on says less ("My dream died with her."), and so does what is only to come ("I
# will die in three days.") or only supposed ("I must have been cursed.").
_OPENS_ON_AIM = {
    Language.EN: (
        r"(?:i|we) (?:(?:really|only|just) )?"
        r"(?:(?:want|wish|need|have|intend|plan|mean|aim|hope|long) to|must(?! have))\b"
        r"|(?:i['’]m|i am|we['’]re|we are) (?:looking|searching) for\b"
        r"|my (?:goal|dream|aim|ambition|mission|purpose|quest) is\b"
    ),
    Language.ES: (
        r"(?:(?:solo|sólo) )?(?:quiero|queremos|deseo|necesito|debo|tengo que|he de|busco)\b"
        r"|mi (?:objetivo|meta|sueño|ambición|misión|propósito) es\b"
    ),
    Language.CA: (
        r"(?:només )?(?:vull|volem|desitjo|necessito|he de|haig de|tinc de|busco)\b"
        r"|(?:el meu (?:objectiu|somni|propòsit)|la meva (?:meta|ambició|missió)) és\b"
    ),
}
_NO_AIM = r"(?! (?:not|never|no|nunca|jamás|mai)\b)"
_STATED = {
    language: re.compile(rf"\W*(?:{opens}){_NO_AIM}", re.IGNORECASE)
    for language, opens in _OPENS_ON_AIM.items()
}


def stated_aim(said: str, language: Language) -> str:
    """The aim that `said`, the player's own words, give when they are one short sentence that
    opens on what its speaker is after and says nothing more ("I want to be a pirate."): the
    words themselves, which are the goal whatever a drafter made of them. The real drafter,
    asked to write no goal the player didn't state, also left such a premise with none (the
    live check of 2026-11-14). Empty for any other words."""
    words = " ".join(said.split())
    return words if one_aim(said, language) and _STATED[language].match(words) else ""


def _done_for(words: list[str], lead: str, language: Language) -> bool:
    """Whether the words say `lead`, an aim's own first word, as what something is done for."""
    for phrase in _FOR[language]:
        size = len(phrase)
        for at in range(len(words) - size):
            if tuple(words[at : at + size]) != phrase or not alike(words[at + size], lead):
                continue
            if language is not Language.EN or at == 0 or words[at - 1] not in _NOT_FOR:
                return True
    return False


# What can stand between the start of a sentence and its first word: a space, an opening quote,
# a dash or a bracket. A new line, or the mark that ended the sentence before, comes before it.
_OPENS = " \t\"'“”‘’«»(¿¡—–-*_"
_ENDS = ".!?…:\n"


def told_of(scene: str, name: str, language: Language) -> bool:
    """Whether a scene's words call someone by `name`. A scene is prose, which starts every
    sentence with a capital, so a word of the name written with one calls them inside a
    sentence, and at the start of one only when it is all the name has, the next word is the
    name's too, or it starts a second sentence as well: "beside Zhao" and "Elder Mo nods" call
    them, and "Old habits die hard" doesn't call Old Hu. Lower case never does, since prose
    writes a name as one."""
    theirs = {core(word) for word in WORD.findall(name)} - FILLER[language]
    if not theirs:
        return False
    found = list(WORD.finditer(scene))
    started: set[str] = set()
    for at, match in enumerate(found):
        word = core(match.group())
        if not match.group()[0].isupper() or word not in theirs:
            continue
        if len(theirs) == 1 or not _starts_sentence(scene, match.start()):
            return True
        if at + 1 < len(found) and core(found[at + 1].group()) in theirs:
            return True
        if word in started:
            return True
        started.add(word)
    return False


def _starts_sentence(text: str, at: int) -> bool:
    before = text[:at].rstrip(_OPENS)
    return not before or before[-1] in _ENDS


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
