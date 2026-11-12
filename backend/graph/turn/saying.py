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
model. What the model said is remembered while the process lives, so a line that comes back,
such as a foe's level on every exchange of a fight, is said the same way each time and asked
for once. An English story's lines are the engine's own, untouched.
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
    # The title is a thread's own, which the story keeps in its language already (N1).
    title_kept: bool = False

    def reworded(self, word: Callable[[str], str]) -> Lines:
        """These lines with each one the engine wrote passed through `word`. What the player
        or a model wrote in the story's language already (a step's own text, a check's thing, a
        link of a theory) is left alone."""

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
                                "by": word(struck.by),
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
        title = self.event_title
        return Lines(
            details=self.details.model_copy(update={"steps": steps, "chain": chain}),
            event_title=word(title) if title and not self.title_kept else title,
            title_kept=self.title_kept,
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
    sentence that tells its throw, which the dice show (`graph.turn.scene.details`). An event
    that brings back one of the story's `threads` under the thread's own title is in the
    story's words already, unless the director titled that thread itself."""
    event = plan.event
    thread = (threads or {}).get(event.thread_id or "") if event else None
    own = thread is not None and thread.title == event.title and not titles.written(event.title)
    return Lines(
        details=details(resolution, throws_told=language is Language.EN),
        event_title=event.title if event else None,
        title_kept=own,
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


def faithful(english: str, said: str) -> bool:
    """Whether `said` can stand for the engine's line: it says something, keeps every number in
    figures and every name as spelled, and doesn't run on."""
    if not said.strip() or len(said) > 3 * len(english) + 40:
        return False
    if Counter(_NUMBER.findall(english)) != Counter(_NUMBER.findall(said)):
        return False
    heard = said.casefold()
    return all(name.casefold() in heard for name in _names(english))


def _needs_words(text: str) -> bool:
    return any(char.isalpha() for char in text)


async def say(llm: ModelClient, texts: list[str], language: Language) -> dict[str, str]:
    """The model's wording of each of `texts` that came back faithful, by its English line."""
    answer = await llm.structured(Node.WORDING, wording_prompt(texts, language), Said)
    said: dict[str, str] = {}
    for line in answer.lines:
        if not 1 <= line.n <= len(texts):
            continue
        english = texts[line.n - 1]
        worded = " ".join(line.text.split())
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
    """A line that needs no model: one of the book's, a title the director wrote, which has
    a book of its own (W16), or one the model has said before."""
    said = BOOK[language].get(text)
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
