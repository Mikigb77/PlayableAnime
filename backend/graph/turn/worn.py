"""R9: what the last scenes already leaned on, so the next one says it another way.

In Miki's long story, read on 2026-11-10, "deep black eyes" came back in 16 scenes of 187, the
leather boots in 17 and "absolute body mastery" in 17. Two things in code keep that from
happening, and the narrator only writes to them:

- `worn_phrases` reads the last scenes for the wording they repeated: a phrase of two to four
  words that three or more of the last twelve scenes used. The narrator is handed the list and
  says those things another way, or leaves them out. What the story calls its people, its
  places and the things of its world is never on it: a name has no other way to be said.
- `touches` says whether the player's own words are about how the character looks (a mirror,
  or something of their own look, such as "my hair"), which is one of the reasons a scene is
  handed their appearance (`graph.turn.context.shows_looks`).

Plain Python over the saved scenes: no model reads them for this, and nothing here is logged.
"""

import re
from collections import Counter
from collections.abc import Iterable, Sequence

from engine.context import Language
from graph.turn.types import WORN_SCENES, PastScene
from graph.words import FILLER
from graph.words import WORD as _WORD
from graph.words import core as _core

# In how many of the last `WORN_SCENES` scenes a phrase has to be.
WORN_MIN = 3
# The most phrases one brief carries: the ones in the most scenes, longest first.
WORN_MAX = 8
PHRASE_WORDS = (2, 3, 4)

# What a player's words say when the action is about how the character looks, whoever's words
# follow: a mirror, a disguise.
_SHOWING = {
    Language.EN: "mirror reflection appearance disguise dressed",
    Language.ES: "espejo reflejo aspecto apariencia disfraz",
    Language.CA: "mirall reflex aspecte aparença disfressa",
}
SHOWING = {language: frozenset(words.split()) for language, words in _SHOWING.items()}
# What is part of anyone's look, which counts when the words say it is the character's own: "I
# wipe my face", never "I hit him in the face".
_OWN = {
    Language.EN: "face hair clothes looks",
    Language.ES: "cara rostro pelo cabello ropa",
    Language.CA: "cara rostre cabell cabells roba",
}
OWN = {language: frozenset(words.split()) for language, words in _OWN.items()}
# How a player says a thing is their own, and how many words before it that can stand: "my
# long black hair", "me recojo el pelo", "em recullo els cabells".
_MINE = {
    Language.EN: "my",
    Language.ES: "mi mis me",
    Language.CA: "meu meva meus meves em me",
}
MINE = {language: frozenset(words.split()) for language, words in _MINE.items()}
MINE_REACH = 3

# Where a phrase can't run on: the end of a clause, a quote, a bracket, a dash, a new line.
_BREAK = re.compile(r"[.,;:!?¿¡…—–()\[\]\"«»“”\n]+")
# The breaks a sentence can start after, where a capital says nothing about a name.
_STARTS_SENTENCE = frozenset('.!?¿¡…—–"«»“”\n')


class _Names:
    """The names on the story's record, as a scene's words are checked against them: every
    word of a name, and each name whole without the small words at its ends, so "The Outer
    Court" is ("outer", "court")."""

    def __init__(self, names: Iterable[str], filler: frozenset[str]) -> None:
        words: set[str] = set()
        whole: dict[str, set[tuple[str, ...]]] = {}
        for name in names:
            term = [_core(word) for word in _WORD.findall(name)]
            words.update(term)
            while term and term[0] in filler:
                del term[0]
            while term and term[-1] in filler:
                del term[-1]
            if term:
                whole.setdefault(term[0], set()).add(tuple(term))
        self.words = frozenset(words)
        self._whole = whole

    def cut(self, clause: list[str]) -> list[list[str]]:
        """The clause without the names it holds whole, cut where each stood, however the scene
        wrote it: "the outer court" in lower case is still the Outer Court."""
        cores = [_core(word) for word in clause]
        named = [False] * len(clause)
        for at, core in enumerate(cores):
            for term in self._whole.get(core, ()):
                if tuple(cores[at : at + len(term)]) == term:
                    named[at : at + len(term)] = [True] * len(term)
        pieces: list[list[str]] = [[]]
        for word, is_name in zip(clause, named, strict=True):
            if is_name:
                pieces.append([])
            else:
                pieces[-1].append(word)
        return pieces


def _clauses(text: str, names: _Names) -> list[list[str]]:
    """The scene's words in lower case, clause by clause, cut again at every name: a word with
    a capital inside a sentence, a word of a name on record at a sentence's start, and a name
    on record written whole, in capitals or not. Names are how the story calls people, places
    and things, so they are never wording to avoid."""
    clauses: list[list[str]] = []
    at, first = 0, True
    for stop in [*_BREAK.finditer(text), None]:
        end = stop.start() if stop is not None else len(text)
        clause: list[str] = []
        for found in _WORD.finditer(text, at, end):
            word = found.group()
            named = word[0].isupper() and (not first or _core(word) in names.words)
            first = False
            if named:
                clauses.append(clause)
                clause = []
            else:
                clause.append(word.replace("’", "'").casefold())
        clauses.append(clause)
        if stop is not None:
            at = stop.end()
            first = bool(_STARTS_SENTENCE.intersection(stop.group()))
    pieces = [piece for clause in clauses for piece in names.cut(clause)]
    return [piece for piece in pieces if len(piece) >= PHRASE_WORDS[0]]


def _phrases(text: str, filler: frozenset[str], names: _Names) -> set[str]:
    found: set[str] = set()
    for clause in _clauses(text, names):
        says = [_core(word) not in filler for word in clause]
        for size in PHRASE_WORDS:
            for start in range(len(clause) - size + 1):
                if says[start] and says[start + size - 1]:
                    found.add(" ".join(clause[start : start + size]))
    return found


def phrases(text: str, language: Language, names: Iterable[str] = ()) -> set[str]:
    """Every phrase of two to four words in `text` that starts and ends on a word that says
    something. `names` are the names on the story's record, which no phrase holds."""
    filler = FILLER[language]
    return _phrases(text, filler, _Names(names, filler))


def worn_phrases(
    scenes: Sequence[PastScene], language: Language, names: Iterable[str] = ()
) -> list[str]:
    """The wording the last scenes leaned on: each phrase that at least `WORN_MIN` of the last
    `WORN_SCENES` scenes used, the ones in the most scenes first and the longest of those
    first, at most `WORN_MAX`. Of phrases that share a word that says something only the first
    is kept, so one worn sentence gives one phrase: the longer when the shorter never came
    without it, and the shorter otherwise. `names` are the names on the story's record, which
    are no wording."""
    filler = FILLER[language]
    known = _Names(names, filler)
    counts: Counter[str] = Counter()
    for scene in scenes[-WORN_SCENES:]:
        counts.update(_phrases(scene.narration, filler, known))
    often = sorted(
        (phrase for phrase, count in counts.items() if count >= WORN_MIN),
        key=lambda phrase: (-counts[phrase], -len(phrase.split()), phrase),
    )
    kept: list[str] = []
    said: set[str] = set()
    for phrase in often:
        says = {_core(word) for word in phrase.split()} - filler
        if not says & said:
            kept.append(phrase)
            said |= says
    return kept[:WORN_MAX]


def touches(words: str, looks: str, language: Language) -> bool:
    """Whether the player's own words are about how the character looks: they speak of a look
    itself (a mirror, a disguise), or of something of the character's own that is part of it,
    their face, their clothes or a word of the looks on record, such as the hair they tie back.
    "Own" is said in the words, so stepping back or meeting someone's eyes is no look of theirs
    though the record has hair tied back and steady eyes."""
    filler = FILLER[language]
    said = [word.replace("’", "'").casefold() for word in _WORD.findall(words)]
    cores = [_core(word) for word in said]
    if SHOWING[language].intersection(cores):
        return True
    shown = {_core(word) for word in _WORD.findall(looks)}
    theirs = OWN[language] | {word for word in shown if len(word) >= 4 and word not in filler}
    mine = MINE[language]
    return any(
        core in theirs
        and any(
            word in mine or word.startswith("m'") for word in said[max(0, at - MINE_REACH) : at]
        )
        for at, core in enumerate(cores)
    )
