"""Errors a turn can end with besides the model layer's own (`graph.llm.errors`)."""


class UnreadableAction(Exception):
    """F4: the interpret step was blocked, so the action can't be read. The app offers to
    rephrase or retry; it's never shown as an error. API.md's `unreadable_action` (422)."""

    code = "unreadable_action"
    default_message = "That action couldn't be read. Try saying it another way."

    def __init__(self, *, categories: tuple[str, ...] = ()) -> None:
        super().__init__(self.default_message)
        self.message = self.default_message
        self.categories = categories
