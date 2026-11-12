"""The scripted model behind deterministic mode: no model is called, and every run is the same.

Each story gets its own fake backend (`graph.llm.FakeBackend`) under the real model client, so a
deterministic turn still goes through the client's parsing, streaming, retries and telemetry.
The interpret node gets the line's scripted interpretation, the narrator the line's scripted
answer or a stock scene, the summarizer a stock chapter, and the wording step each line as it
stands.

Token counts follow the prompts the graph really builds, with fixed answer sizes, so the costs
a deterministic run reports compare turns fairly (K8) without being real prices.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from engine.context import NarrationLength
from engine.contracts import Intent
from graph.llm import Block, Fail, FakeBackend, Hang, Node, Reply, offline_reply
from graph.llm.fake import TINY_PNG, Step
from graph.llm.types import Request, Usage
from graph.turn import NarratorOutput
from graph.turn.saying import lines_asked

# Answer sizes in tokens, about what Gemini writes for each (T5's first live numbers will
# replace them).
INTERPRET_TOKENS = 350
NARRATION_TOKENS = {
    NarrationLength.SHORT: 450,
    NarrationLength.MEDIUM: 900,
    NarrationLength.LONG: 1600,
}
SUMMARY_TOKENS = 300

STOCK_SUGGESTIONS = (
    {"label": "Press on", "kind": "thread"},
    {"label": "Take a moment for yourself", "kind": "personal"},
    {"label": "Look into something else", "kind": "side"},
    {"label": "Do something unexpected", "kind": "wild"},
)
STOCK_SUMMARY = "(A scripted chapter: the scenes played as the eval wrote them.)"

type Narration = NarratorOutput | dict[str, Any] | Block | Fail | Hang


class MissingInterpretation(AssertionError):
    """Deterministic mode was asked to read an action that has no scripted interpretation."""


@dataclass
class Line:
    """What the scripted model answers for the turn being played."""

    turn: int
    action: str | None = None
    interpretation: Intent | None = None
    narration: deque[Narration] = field(default_factory=deque)

    @classmethod
    def of(
        cls,
        turn: int,
        action: str | None,
        interpretation: Intent | None,
        narration: Narration | Iterable[Narration] | None,
    ) -> Line:
        if narration is None:
            answers: deque[Narration] = deque()
        elif isinstance(narration, NarratorOutput | dict | Block | Fail | Hang):
            answers = deque([narration])
        else:
            answers = deque(narration)
        return cls(turn, action, interpretation, answers)


def tokens(text: str) -> int:
    """The fake backend's estimate: about four characters per token."""
    return (len(text) + 3) // 4


def prompt_tokens(request: Request) -> int:
    prompt = request.prompt
    return tokens(prompt.system) + sum(tokens(m.text) for m in prompt.messages)


def stock_narration(turn: int, action: str | None) -> dict[str, Any]:
    told = f"the player tried: {action}" if action else "the story opens"
    return {
        "narration": f"(Scripted scene for turn {turn}: {told}.)",
        "suggestions": list(STOCK_SUGGESTIONS),
        "image_prompt": f"A key moment of turn {turn}.",
        "update": {},
    }


class ScriptedModel:
    """The fake backend's answers for one story. Set `line` before each turn."""

    def __init__(self, length: NarrationLength = NarrationLength.MEDIUM) -> None:
        self.line = Line(turn=0)
        self.length = length
        self.backend = FakeBackend(default=self.reply, chunk_size=64, keep_requests=False)
        # The last prompt each node was sent, so a scenario can check what code put in front of
        # a model (R3, R4, R7). Kept in memory for the checks only, never logged (T6).
        self.prompts: dict[Node, str] = {}

    def reply(self, request: Request) -> Step:
        node = request.node
        prompt = request.prompt
        self.prompts[node] = "\n".join([prompt.system, *(m.text for m in prompt.messages)])
        if node in (Node.INTERPRET, Node.SECOND_READING):
            # B8: a turn read twice is read the same both times, as its script wrote it.
            intent = self.line.interpretation
            if intent is None:
                raise MissingInterpretation(
                    f"Turn {self.line.turn}: deterministic mode needs a scripted interpretation "
                    f"for {self.line.action!r}"
                )
            return self._answer(request, intent, INTERPRET_TOKENS)
        if node is Node.NARRATOR:
            answer = (
                self.line.narration.popleft()
                if self.line.narration
                else stock_narration(self.line.turn, self.line.action)
            )
            if isinstance(answer, Block | Fail | Hang):
                return answer
            return self._answer(request, answer, NARRATION_TOKENS[self.length])
        if node is Node.SUMMARIZER:
            return self._answer(request, {"summary": STOCK_SUMMARY}, SUMMARY_TOKENS)
        if node is Node.WORDING:
            # S10: each line between « and », with its numbers and names as they stand. A line
            # handed back unchanged would count as left in English (`saying.faithful`).
            lines = [{"n": n, "text": f"«{text}»"} for n, text in lines_asked(prompt)]
            return self._answer(
                request, {"lines": lines}, sum(tokens(line["text"]) for line in lines)
            )
        if node is Node.PICTURE:
            return Reply(images=(TINY_PNG,))
        return offline_reply(request)

    @staticmethod
    def _answer(request: Request, value: BaseModel | dict[str, Any], output: int) -> Reply:
        return Reply(json=value, usage=Usage(prompt_tokens(request), output))
