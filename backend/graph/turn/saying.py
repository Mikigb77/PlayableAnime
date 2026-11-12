"""S10: the engine's own lines of a turn, said in the story's language.

The engine writes in English why each step went the way it did: its reason, what a check found,
what struck back, and around a throw the hand, each green die, what the number is made of, what
it is up against and what a miss costs (A3, A8). The player reads them under "How it played out"
and beside the dice, so in a Spanish or a Catalan story the cheapest model says them in the
story's language first, alongside the narrator (B8).

Model nodes propose and code decides (B5): the model only words a line again, and code checks
each one. A line that lost a number or a name of the English one is dropped, and the English line
stands, as it does when the model is late, blocked or down. A turn never waits long for its
wording and never fails for it.

A line the engine always writes the same way is in a small book here, and the director's titles
are in theirs (`engine.director.titles`), so a turn where nothing stood in the way calls no
model. So is the line of a blow that comes back at the player character, which every exchange
of a fight brings: who strikes back, and what it did to them (`struck`). What the model said is
remembered while the process lives, so a line that comes back, such as a foe's level on every
exchange of a fight, is said the same way each time and asked for once. An English story's
lines are the engine's own, untouched.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from engine.context import Language
from engine.contracts import Aim, DirectorPlan, Resolution
from engine.director import titles
from engine.resolve.core import NOTHING_IN_THE_WAY
from engine.resolve.perils import MISS_COSTS
from engine.state.records import Thread
from graph.language import written_in
from graph.llm import LLMError, Node, Prompt
from graph.turn import prompts
from graph.turn.context import render
from graph.turn.ending import CLAIMED
from graph.turn.errors import RefusedStep
from graph.turn.scene import details
from graph.turn.types import Issue, RollDetail, SceneDetails

if TYPE_CHECKING:
    from graph.llm import ModelClient

# How long the dice wait for their lines (A3). Past it they go out in the engine's English.
GRACE_S = 4.0

# Issue codes (C5, T5). No line said: the model was late (`late`) or failed (its error code).
UNSAID = "lines_unsaid"
# Some lines kept in English: the model left them out, or its wording lost a number or a name.
KEPT = "lines_kept"

# The lines the engine writes the same way every time, so they need no model. Each key is the
# engine's own line, word for word: a test fails when the engine words one another way.
BOOK: Mapping[Language, Mapping[str, str]] = {
    Language.ES: {
        NOTHING_IN_THE_WAY: "Nada lo impide.",
        "It follows.": "Se sostiene.",
        "A close call.": "Va a ir justo.",
        "certain": "segura",
        "your own step missed": "tu propio intento falló",
        "one more at their side": "otro más a su lado",
        "two more at their side": "otros dos a su lado",
        MISS_COSTS[Aim.KILL]: (
            "Fallar por más de 5 te mata. Fallar por poco te deja una herida grave."
        ),
        MISS_COSTS[Aim.WOUND]: (
            "Fallar por más de 5 es una herida. Fallar por poco, una herida leve."
        ),
        MISS_COSTS[Aim.SUBDUE]: (
            "Fallar por más de 5 te deja fuera de combate. Fallar por poco, una herida leve."
        ),
        CLAIMED: "Cómo se lo toman los demás y cómo acaban las cosas lo decide el mundo.",
    },
    Language.CA: {
        NOTHING_IN_THE_WAY: "Res no ho impedeix.",
        "It follows.": "Se sosté.",
        "A close call.": "Anirà just.",
        "certain": "segura",
        "your own step missed": "el teu propi intent ha fallat",
        "one more at their side": "un altre al seu costat",
        "two more at their side": "dos més al seu costat",
        MISS_COSTS[Aim.KILL]: (
            "Fallar per més de 5 et mata. Fallar per poc et deixa una ferida greu."
        ),
        MISS_COSTS[Aim.WOUND]: (
            "Fallar per més de 5 és una ferida. Fallar per poc, una ferida lleu."
        ),
        MISS_COSTS[Aim.SUBDUE]: (
            "Fallar per més de 5 et deixa fora de combat. Fallar per poc, una ferida lleu."
        ),
        CLAIMED: "Com s'ho prenen els altres i com acaben les coses ho decideix el món.",
    },
}


# A blow that comes back at the player character (`engine.resolve.perils`): who strikes back,
# then what it did to them, each a sentence the engine always writes the same way. Code says
# them, in the app's own words for it ("te devuelven el golpe") and the sheet's for health,
# since every exchange of a fight brings one and the small model got the pair wrong in the live
# check of 2026-11-12: "strikes back" left in English beside "Tienes heridas", and a "Fallas"
# nobody wrote. The one who struck is named as the story names them. A test fails when the
# engine words a blow's outcome another way.
STRUCK: Mapping[Language, Mapping[str, str]] = {
    Language.ES: {
        "strikes back": "{who} te devuelve el golpe.",
        "It misses you.": "No te alcanza.",
        "It doesn't hurt you.": "No te hace daño.",
        "You are hurt.": "Tienes heridas leves.",
        "You are wounded.": "Tienes heridas.",
        "You are brought down.": "Quedas fuera de combate.",
        "You are badly wounded.": "Tienes heridas graves.",
        "You are maimed, with a wound that will last.": "Te queda una herida para siempre.",
        "You are dying.": "Estás al borde de la muerte.",
        "It kills you.": "Te mata.",
        "You are brought down, unhurt.": "Quedas fuera de combate, sin heridas.",
        "The blow touches you, pulled.": "El golpe te toca, frenado a tiempo.",
        "You turn the blow, and your next step against them throws a green die.": (
            "Desvías el golpe, y tu próximo paso en su contra tira un dado verde."
        ),
    },
    Language.CA: {
        "strikes back": "{who} et torna el cop.",
        "It misses you.": "No et toca.",
        "It doesn't hurt you.": "No et fa mal.",
        "You are hurt.": "Tens ferides lleus.",
        "You are wounded.": "Tens ferides.",
        "You are brought down.": "Quedes fora de combat.",
        "You are badly wounded.": "Tens ferides greus.",
        "You are maimed, with a wound that will last.": "Et queda una ferida per sempre.",
        "You are dying.": "Estàs a punt de morir.",
        "It kills you.": "Et mata.",
        "You are brought down, unhurt.": "Quedes fora de combat, sense ferides.",
        "The blow touches you, pulled.": "El cop et toca, frenat a temps.",
        "You turn the blow, and your next step against them throws a green die.": (
            "Desvies el cop, i el teu pròxim pas en contra seva tira un dau verd."
        ),
    },
}
_STRUCK = re.compile(r"(?P<who>[^.]+) strikes back\.(?: (?P<then>[^.]+\.))?")


def struck(text: str, language: Language) -> str | None:
    """A lone foe's blow back at the player character, said by code: "Elder Mo strikes back.
    You are wounded." is "Elder Mo te devuelve el golpe. Tienes heridas." None for any other
    line: several foes, whom the engine joins with its "and", a danger that is no one's blow,
    and a blow told with its throw or with what ruled it out."""
    found = _STRUCK.fullmatch(text)
    words = STRUCK.get(language)
    if found is None or words is None:
        return None
    said = words["strikes back"].format(who=found["who"])
    if found["then"] is None:
        return said
    then = words.get(found["then"])
    return f"{said} {then}" if then else None


# What the model said for a line, by language, kept in memory only and never logged (T6): the
# oldest goes once there are more than this many. The same English line is always the same fact,
# whoever's story it is in, so one wording serves them all.
MEMORY_LINES = 4096
_memory: dict[tuple[Language, str], str] = {}


def _remember(language: Language, english: str, said: str) -> None:
    _memory.pop((language, english), None)
    _memory[(language, english)] = said
    while len(_memory) > MEMORY_LINES:
        del _memory[next(iter(_memory))]


def forget() -> None:
    """Empties the memory of said lines, for tests."""
    _memory.clear()


class SaidLine(BaseModel):
    n: int = Field(description="The line's n in LINES.")
    text: str = Field(description="That line in the language LANGUAGE names.")


class Said(BaseModel):
    """S10. The engine's lines of a turn, each said in the story's language under its own n."""

    lines: list[SaidLine]


@dataclass(frozen=True)
class Lines:
    """What the engine wrote for the player about one turn: why it went the way it did (A8),
    and the title of the event its scene carries, if any (W16)."""

    details: SceneDetails
    event_title: str | None = None
    # What is the story's own already and stands as it is: the title of a thread that comes
    # back (N1), and the name of the one who struck.
    kept: frozenset[str] = frozenset()

    def reworded(self, word: Callable[[str], str]) -> Lines:
        """These lines with each one the engine wrote passed through `word`. What the player
        or a model wrote in the story's language already (a step's own text, a check's thing, a
        link of a theory) is left alone."""

        def own(text: str) -> str:
            return text if text in self.kept else word(text)

        def roll(shown: RollDetail | None) -> RollDetail | None:
            if shown is None:
                return None
            thrown = shown.throw
            if thrown is None:
                return shown.model_copy(update={"odds_label": word(shown.odds_label)})
            said = thrown.model_copy(
                update={
                    "hand_why": word(thrown.hand_why),
                    "greens": [word(green) for green in thrown.greens],
                    "made_of": [
                        part.model_copy(update={"text": word(part.text)}) for part in thrown.made_of
                    ],
                    "against": word(thrown.against),
                    "miss_costs": word(thrown.miss_costs),
                }
            )
            return shown.model_copy(update={"throw": said})

        steps = [
            step.model_copy(
                update={
                    "reason": word(step.reason),
                    "roll": roll(step.roll),
                    "beats": [
                        beat.model_copy(
                            update={"reason": word(beat.reason), "roll": roll(beat.roll)}
                        )
                        for beat in step.beats
                    ]
                    if step.beats
                    else None,
                    "struck": [
                        struck.model_copy(
                            update={
                                "by": own(struck.by),
                                "reason": word(struck.reason),
                                "roll": roll(struck.roll),
                            }
                        )
                        for struck in step.struck
                    ]
                    if step.struck
                    else None,
                }
            )
            for step in self.details.steps
        ]
        chain = None
        if self.details.chain:
            chain = [
                link.model_copy(update={"reason": word(link.reason)}) for link in self.details.chain
            ]
        return Lines(
            details=self.details.model_copy(update={"steps": steps, "chain": chain}),
            event_title=own(self.event_title) if self.event_title else self.event_title,
            kept=self.kept,
        )

    def texts(self) -> list[str]:
        """Each line the engine wrote, once, in the order the player meets them."""
        seen: dict[str, None] = {}

        def note(text: str) -> str:
            seen.setdefault(text)
            return text

        self.reworded(note)
        return list(seen)


def lines_of(
    resolution: Resolution,
    plan: DirectorPlan,
    language: Language,
    threads: Mapping[str, Thread] | None = None,
) -> Lines:
    """The turn's lines as the engine wrote them. Outside English each reason comes without the
    sentence that tells its throw, which the dice show (`graph.turn.scene.details`). Two kinds
    of line are the story's own already and are kept as they stand: the title of an event that
    brings back one of the story's `threads` under the thread's own title, unless the director
    titled that thread itself, and the name of a single foe who struck back."""
    event = plan.event
    thread = (threads or {}).get(event.thread_id or "") if event else None
    perils = [peril for step in resolution.steps for peril in step.perils]
    kept = {peril.by for peril in perils if len(peril.by_ids) == 1}
    if thread is not None and thread.title == event.title and not titles.written(event.title):
        kept.add(event.title)
    return Lines(
        details=details(resolution, throws_told=language is Language.EN),
        event_title=event.title if event else None,
        kept=frozenset(kept),
    )


def wording_prompt(texts: list[str], language: Language) -> Prompt:
    lines = [{"n": n, "text": " ".join(text.split())} for n, text in enumerate(texts, start=1)]
    return Prompt.build(
        prompts.WORDING_SYSTEM,
        render(
            [
                ("LANGUAGE", written_in(language)),
                ("WORDS", prompts.WORDING_WORDS[language]),
                ("LINES", lines),
            ]
        ),
    )


def lines_asked(prompt: Prompt) -> list[tuple[int, str]]:
    """The numbered lines a wording prompt asks for, for the scripted model of the evals and
    the tests."""
    _, _, body = prompt.messages[-1].text.rpartition("## LINES\n")
    return [(line["n"], line["text"]) for line in json.loads(body)]


_NUMBER = re.compile(r"\d+")
_WORD = re.compile(r"[^\W\d_][\w'’-]*")
# What a sentence can start after: its first word is capitalized whether or not it is a name.
_OPENERS = frozenset(".!?:;“\"«'(¿¡")


def _names(text: str) -> list[str]:
    """The words of `text` that are capitalized where a sentence doesn't start: its names, or
    the parts of them, such as the Mo of "Elder Mo strikes back." and both words of "against
    Zhao Kun"."""
    names = []
    for found in _WORD.finditer(text):
        word = found.group().removesuffix("'s").removesuffix("’s")
        before = text[: found.start()].rstrip()
        if len(word) < 2 or not word[0].isupper() or not before or before[-1] in _OPENERS:
            continue
        names.append(word)
    return names


# Words of the engine's lines that only English has: none is a word of Spanish or of Catalan.
_ENGLISH = frozenset(
    "the is are you your there here and of with against it but their they this that from not "
    "was were have its them what who when which than too by at for if will would level speed "
    "strength wounded hurt missed own strike strikes back step task hard easy short above below "
    "rung rungs".split()
)


def _left_in_english(english: str, said: str) -> bool:
    """Whether the model handed an English line back as it stood. A line that was in the
    story's language already, such as a danger the player named, comes back the same too,
    and that one is said."""
    if " ".join(said.split()).casefold() != " ".join(english.split()).casefold():
        return False
    return any(word.casefold() in _ENGLISH for word in _WORD.findall(english))


def _partly_in_english(english: str, said: str) -> bool:
    """Whether a part of the engine's line came back as it stood: two words in a row that only
    English has, as the engine wrote them, such as the "strikes back" of "El trol strikes back.
    Tienes heridas." Words inside a name are the name's ("Sword of the Dawn")."""
    engine_words = " ".join(english.casefold().split())
    words = list(_WORD.finditer(said))

    def joined(i: int) -> bool:
        """Whether word i and the one after it stand side by side in one sentence."""
        return 0 <= i < len(words) - 1 and said[words[i].end() : words[i + 1].start()] == " "

    def capital(i: int) -> bool:
        return 0 <= i < len(words) and words[i].group()[:1].isupper()

    def opens(i: int) -> bool:
        before = said[: words[i].start()].rstrip()
        return not before or before[-1] in _OPENERS

    for i in range(len(words) - 1):
        pair = [words[i].group().casefold(), words[i + 1].group().casefold()]
        if not joined(i) or not all(word in _ENGLISH for word in pair):
            continue
        if capital(i + 1) or (capital(i) and not opens(i)):
            continue  # a name's own words, capitalized where no sentence starts
        named = (
            joined(i + 1) and capital(i + 2) and (capital(i) or (joined(i - 1) and capital(i - 1)))
        )
        if not named and " ".join(pair) in engine_words:
            return True
    return False


def faithful(english: str, said: str) -> bool:
    """Whether `said` can stand for the engine's line: it says something, keeps every number in
    figures and every name as spelled, doesn't run on, and isn't the English line again, whole
    or in part."""
    if not said.strip() or len(said) > 3 * len(english) + 40:
        return False
    if _left_in_english(english, said) or _partly_in_english(english, said):
        return False
    if Counter(_NUMBER.findall(english)) != Counter(_NUMBER.findall(said)):
        return False
    heard = said.casefold()
    return all(name.casefold() in heard for name in _names(english))


# Where a preposition meets the article after it, the language runs them together, and the
# small model sometimes leaves them apart ("el aguante de el trol"). Only the article in small
# letters: a name's own capital article stays apart ("a El Paso"). A name the story spells with
# its article in small letters ("el trol de las cavernas") brings that article along, and the
# model, told to keep a name as spelled, says it twice ("del el trol", in Catalan "d'el trol",
# live check of 2026-11-12): the article is said once.
_CONTRACTIONS: Mapping[Language, tuple[tuple[re.Pattern[str], str], ...]] = {
    Language.ES: (
        (re.compile(r"\b([Dd])e el\b"), r"\1el"),
        (re.compile(r"\b([Aa]) el\b"), r"\1l"),
        (re.compile(r"\b([Dd]el|[Aa]l) el\b"), r"\1"),
    ),
    Language.CA: (
        (re.compile(r"\b([Dd])e el(s?)\b"), r"\1el\2"),
        (re.compile(r"\b([Aa]) el(s?)\b"), r"\1l\2"),
        (re.compile(r"\b([Pp])er el(s?)\b"), r"\1el\2"),
        (re.compile(r"\b([Dd])'el(s?)\b"), r"\1el\2"),
        (re.compile(r"\b([Dd]el|[Aa]l|[Pp]el)(s?) el\2\b"), r"\1\2"),
    ),
}


def contracted(said: str, language: Language, english: str = "") -> str:
    """`said` with each article run into the preposition before it, as the language writes
    them: "del trol" and "al pozo" in Spanish, and in Catalan "dels turons" and "pel camí"
    too, with an article said twice said once ("del el trol" is "del trol"). What the
    engine's own line already holds apart is the story's wording, such as a name spelled that
    way, and stays as it is."""
    for apart, together in _CONTRACTIONS.get(language, ()):
        if not apart.search(english):
            said = apart.sub(together, said)
    return said


def _needs_words(text: str) -> bool:
    return any(char.isalpha() for char in text)


async def say(llm: ModelClient, texts: list[str], language: Language) -> dict[str, str]:
    """The model's wording of each of `texts` that came back faithful, by its English line,
    with the contractions the language requires (`contracted`)."""
    answer = await llm.structured(Node.WORDING, wording_prompt(texts, language), Said)
    said: dict[str, str] = {}
    for line in answer.lines:
        if not 1 <= line.n <= len(texts):
            continue
        english = texts[line.n - 1]
        worded = contracted(" ".join(line.text.split()), language, english)
        if english not in said and faithful(english, worded):
            said[english] = worded
            _remember(language, english, worded)
    return said


@dataclass
class Wording:
    """A turn's lines on their way to the story's language. `said` holds the lines said at
    once, from the book and from memory; `settle` adds what the model says, by the deadline."""

    said: dict[str, str] = field(default_factory=dict)
    asked: int = 0
    task: asyncio.Task[dict[str, str]] | None = None
    deadline: float = 0.0

    def word(self, text: str) -> str:
        return self.said.get(text, text)

    async def settle(self) -> list[Issue]:
        """Waits for the model until the deadline and takes what it said. Whatever it didn't
        say by then, or said unfaithfully, stays in the engine's English. A late call is left
        to finish, so what it says is remembered for the next turn with the same lines."""
        task, self.task = self.task, None
        if task is None:
            return []
        wait = max(0.0, self.deadline - asyncio.get_running_loop().time())
        done, _ = await asyncio.wait({task}, timeout=wait)
        if not done:
            return [Issue(UNSAID, "the lines stay in the engine's words", area="late")]
        try:
            said = task.result()
        except LLMError as error:
            return [Issue(UNSAID, "the lines stay in the engine's words", area=error.code)]
        self.said.update(said)
        kept = self.asked - len(said)
        return [Issue(KEPT, f"{kept} of {self.asked}")] if kept else []


def _at_hand(language: Language, text: str) -> str | None:
    """A line that needs no model: one of the book's, a lone foe's blow back, a title the
    director wrote, which has a book of its own (W16), or one the model has said before."""
    said = BOOK[language].get(text) or struck(text, language)
    if said is None and titles.written(text):
        said = titles.said(text, language)
    return said or _memory.get((language, text))


def begin(llm: ModelClient, texts: Iterable[str], language: Language) -> Wording:
    """Starts saying `texts` in `language`. The book's lines, the director's titles and the
    lines the model has said before are said at once. The rest go to the model in one call that
    runs alongside the turn: the caller cancels `task` when the turn ends, if it is still
    running."""
    book = BOOK.get(language)
    if book is None:
        return Wording()
    wanted = list(dict.fromkeys(text for text in texts if _needs_words(text)))
    known = {text: _at_hand(language, text) for text in wanted}
    wording = Wording(said={text: said for text, said in known.items() if said})
    left = [text for text in wanted if text not in wording.said]
    if left:
        wording.asked = len(left)
        wording.task = asyncio.create_task(say(llm, left, language))
        wording.deadline = asyncio.get_running_loop().time() + GRACE_S
    return wording


async def refusals_said(
    llm: ModelClient, refused: list[RefusedStep], language: Language
) -> list[RefusedStep]:
    """N6: why the world refused parts of an ending's note, in the story's language."""
    wording = begin(llm, [step.reason for step in refused], language)
    asked = wording.task
    try:
        await wording.settle()
    finally:
        if asked is not None:
            asked.cancel()  # the turn ends here, so nothing is left running after it
    return [replace(step, reason=wording.word(step.reason)) for step in refused]
