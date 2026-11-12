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

from engine.context import Language
from graph.words import FILLER, WORD, alike, content, core

# Where the player's words stop standing together: the end of a clause or a line.
_BREAK = re.compile(r"[.,;:!?¿¡…—–()\[\]\"«»“”\n]+")
# Where a sentence of theirs ends: a time set in one sentence is not for an event in another.
_SENTENCE = re.compile(r"[.!?¿¡…\n]+")

# A time ahead, by language: "in three days", "nine days left", "tomorrow". A time gone by
# ("three days ago", "hace tres días") is none, and neither is a bare "for ten years".
_AMOUNT = r"(?:[\w']+\s+){1,2}?"
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
        r"\b(?:mañana|esta noche)\b",
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


def timed(said: str, text: str, language: Language) -> bool:
    """Whether `said`, the player's own words, set a time for the event `text` names: a clause
    of theirs gives a time ahead and holds a word of it. When the time is all its clause says,
    it is for the rest of the sentence ("The tax collector comes with the first snow, in thirty
    days"). "I take the knight exam in 3 days" times "The trial of knighthood"; "my father was
    killed three days ago" times nothing; and "I'm sure the killer is in the family, and the
    council names the next boss in ten days" times the council's vote, not "The killer strikes
    again"."""
    its = content(text, language)
    ahead = _TIME_AHEAD[language]
    for sentence in _SENTENCE.split(said):
        clauses = _BREAK.split(sentence)
        for at, clause in enumerate(clauses):
            found = ahead.search(clause)
            if found is None:
                continue
            about = content(f"{clause[: found.start()]} {clause[found.end() :]}", language)
            if not about:
                about = content(" ".join(clauses[:at] + clauses[at + 1 :]), language)
            if any(alike(word, other) for word in about for other in its):
                return True
    return False
