"""Errors a turn can end with besides the model layer's own (`graph.llm.errors`)."""

from dataclasses import dataclass
from typing import Any


class UnreadableAction(Exception):
    """F4: the interpret step was blocked, so the action can't be read. The app offers to
    rephrase or retry; it's never shown as an error. API.md's `unreadable_action` (422).

    `details` goes to the app as the error's `details`. `stage` is where the model's filter
    stopped it ("prompt" or "response"), for the logs and the evals only."""

    code = "unreadable_action"
    default_message = "That action couldn't be read. Try saying it another way."

    def __init__(
        self, *, categories: tuple[str, ...] = (), message: str | None = None, stage: str = ""
    ) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)
        self.categories = categories
        self.stage = stage
        self.details: dict[str, Any] = {}


class LimitReached(UnreadableAction):
    """F3, G12, F2: the action crosses a hard limit (`engine.limits`), so none of it plays and
    nothing is narrated or charged. The app shows it like an unreadable action, with its own
    message, and offers to rephrase. `details` is `{"category": ...}`, one of
    `engine.limits.LimitCategory`."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(categories=(category,), message=message)
        self.category = category
        self.details = {"category": category}


@dataclass(frozen=True)
class RefusedStep:
    """A part of an ending's note the world won't grant, with its reason in the world's words."""

    text: str
    reason: str
    outcome_class: str


class EndingRefused(Exception):
    """N6: an ending's note asks for something the world rules out, or that would take a long
    shot to earn, so no epilogue is told. Nothing is saved or charged. The app offers to play on
    or to end without it (`drop_refused`)."""

    code = "ending_refused"
    default_message = "The world won't give your story that ending yet."

    def __init__(self, refused: list[RefusedStep]) -> None:
        self.message = self.default_message
        super().__init__(self.message)
        self.refused = refused
