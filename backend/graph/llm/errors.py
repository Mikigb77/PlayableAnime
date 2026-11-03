"""Typed model errors (T7). Each carries the API error code the app shows.

Model failures are retried once inside the client, then surface as one of these, never as a bare
500. The turn graph decides what each means for a turn: a blocked interpret step becomes
`unreadable_action`, while a blocked narration is retold as a cut-away (F4).
"""

from __future__ import annotations

from typing import ClassVar, Literal


class LLMError(Exception):
    code: ClassVar[str] = "llm_unavailable"
    default_message: ClassVar[str] = "The storyteller can't answer right now. Try again."

    def __init__(self, message: str | None = None, *, node: str = "", model: str = ""):
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.node = node
        self.model = model


class LLMUnavailable(LLMError):
    """The model failed twice, timed out, or isn't reachable with our credentials."""

    code = "llm_unavailable"


class LLMBlocked(LLMError):
    """A safety filter stopped the prompt or the response.

    `streamed` is true when part of the response had already been streamed to the player, so the
    caller knows to clear it (`narration.reset`) before retelling the scene.
    """

    code = "blocked"
    default_message = "That part of the story can't be told as written."

    def __init__(
        self,
        message: str | None = None,
        *,
        node: str = "",
        model: str = "",
        categories: tuple[str, ...] = (),
        stage: Literal["prompt", "response"] = "response",
        streamed: bool = False,
    ):
        super().__init__(message, node=node, model=model)
        self.categories = categories
        self.stage = stage
        self.streamed = streamed


class BadKey(LLMError):
    """The player's own API key was rejected (S9). Never raised for our own credentials."""

    code = "bad_key"
    default_message = "Your API key was rejected. Check it in Account, or remove it to use credits."


class UnsupportedProvider(ValueError):
    """A BYOK header named a provider we don't support yet (only `gemini` for now)."""
