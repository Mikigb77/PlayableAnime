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

# In how many of the last `WORN_SCENES` scenes a phrase has to be.
WORN_MIN = 3
# The most phrases one brief carries: the ones in the most scenes, longest first.
WORN_MAX = 8
PHRASE_WORDS = (2, 3, 4)

# The small words a phrase can't start or end on, by language: articles, pronouns, prepositions,
# conjunctions, the commonest helper verbs and adverbs. A phrase needs a word that says
# something at each end, so "of the" and "and you" are never one.
_FILLER = {
    Language.EN: """a an the and or but nor so yet for of in on at to from by with without into
        onto over under above below between among through across against about around before
        after behind beside near off up down out as than then that this these those there here
        it its is are was were be been being am do does did have has had having will would
        shall should can could may might must not no you your yours yourself he him his she her
        hers they them their theirs we us our i me my mine who whom whose which what when where
        why how if while though although because until unless since once still just only even
        also too very more most much many some any each every all both either neither one two
        own same such again ever never now already almost enough rather quite you're you've
        you'll you'd it's he's she's they're don't doesn't didn't can't won't isn't aren't
        wasn't weren't there's that's i'm i've""",
    Language.ES: """el la los las un una unos unas lo al del de en a por para con sin sobre bajo
        entre hacia hasta desde contra tras ante durante según y e o u ni pero sino que como
        cuando donde mientras aunque porque pues si no sí ya aún todavía también tampoco muy más
        menos mucho mucha muchos muchas poco poca pocos pocas tan tanto todo toda todos todas
        cada otro otra otros otras mismo misma este esta estos estas ese esa esos esas aquel
        aquella aquellos aquellas esto eso aquello tu tus tú te ti tuyo tuya su sus se le les me
        mi mis nos nuestro nuestra él ella ellos ellas yo es son era eran fue fueron ser estar
        está están estaba estaban ha han había habían hay he has soy eres somos qué quién cuál
        cómo dónde cuándo algo nada alguien nadie uno dos sólo solo apenas casi así entonces
        ahora luego después antes aquí allí ahí""",
    Language.CA: """el la els les un una uns unes lo de del dels al als a en amb sense per pel
        pels sobre sota entre cap fins des contra durant segons i o ni però sinó que com quan on
        mentre encara perquè doncs si no sí ja també tampoc molt molta molts moltes més menys
        poc poca pocs poques tan tant tot tota tots totes cada altre altra altres mateix mateixa
        aquest aquesta aquests aquestes aquell aquella aquells aquelles això allò tu et te ti
        teu teva teus teves seu seva seus seves se es li hi ho em me meu meva ens nostre nostra
        ell ella ells elles jo és són era eren va van ser estar està estan estava estaven ha han
        havia havien he has sóc ets som què qui quin quina res algú ningú dos només gairebé
        així llavors ara després abans aquí allà""",
}
FILLER = {language: frozenset(words.split()) for language, words in _FILLER.items()}

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

_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
# Where a phrase can't run on: the end of a clause, a quote, a bracket, a dash, a new line.
_BREAK = re.compile(r"[.,;:!?¿¡…—–()\[\]\"«»“”\n]+")
# The breaks a sentence can start after, where a capital says nothing about a name.
_STARTS_SENTENCE = frozenset('.!?¿¡…—–"«»“”\n')
# "l'espasa" is "espasa", and "Zhao's" is "Zhao".
_ELIDED = re.compile(r"^[ldsnmt]'|'s$")


def _core(word: str) -> str:
    return _ELIDED.sub("", word.replace("’", "'").casefold())


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
