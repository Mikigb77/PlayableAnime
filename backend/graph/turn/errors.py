"""Errors a turn can end with besides the model layer's own (`graph.llm.errors`)."""

from typing import Any


class UnreadableAction(Exception):
    """F4: the interpret step was blocked, so the action can't be read. The app offers to
    rephrase or retry; it's never shown as an error. API.md's `unreadable_action` (422).

    `details` goes to the app as the error's `details`."""

    code = "unreadable_action"
    default_message = "That action couldn't be read. Try saying it another way."

    def __init__(self, *, categories: tuple[str, ...] = (), message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)
        self.categories = categories
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
