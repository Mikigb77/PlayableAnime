"""What the model nodes return (structured output). Code checks every field before it counts.

The interpret node returns `engine.contracts.Intent` as it is. The narrator's object puts its
text first, `action` and then `narration`, so the scene streams to the player while the rest is
still being written (S3). `action` is its own field so that every scene tells the character doing
what the player said before anything comes of it (R1), and code can see when one didn't.
"""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from engine.contracts import ChoiceKind, StateDelta

# A blank answer is a failed answer: the model layer retries it once, then gives up (T7).
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SuggestionOut(BaseModel):
    """S2. A suggested action, in the player character's voice of intent."""

    label: str = Field(description="A short action, at most 12 words.")
    kind: ChoiceKind


# R1: how the scene's two parts are joined, as they stream and as the scene is saved.
PARAGRAPH = "\n\n"


def _action_required(schema: dict[str, Any]) -> None:
    """R1. Gemini answers only what a schema requires as often as not (see `Intent`), so the
    model is always asked for `action`, though code may leave it empty (an opening, a template
    line)."""
    schema["required"] = list(dict.fromkeys(["action", *schema.get("required", [])]))


class NarratorOutput(BaseModel):
    """B5 step 5. The scene, its suggestions, the picture prompt and the proposed state update.

    The scene is `action`, the character doing what the player said, then `narration`, what
    comes of it: `text` joins them, as the player reads it (R1).
    """

    model_config = ConfigDict(json_schema_extra=_action_required)

    action: str = Field(
        default="",
        description=(
            "R1: the scene's opening, the player character doing what the player said they do,"
            " told in the story's prose before anything comes of it. Empty only when the brief"
            " has no ACTION."
        ),
    )
    narration: Text = Field(
        description=(
            "The rest of the scene, as the player reads it, picking up where action stops: the"
            " outcome, how the world reacts, and an ending the player can act on. With no"
            " action, the whole scene."
        )
    )
    suggestions: list[SuggestionOut] = Field(
        default_factory=list, description="As many as asked for, 0 to 4 (S2)."
    )
    image_prompt: str | None = Field(
        default=None, description="Only when a picture is planned (M1); otherwise null."
    )
    update: StateDelta = Field(
        default_factory=StateDelta,
        description="What the scene changed, for the engine to check and apply (C1).",
    )

    @property
    def text(self) -> str:
        """The whole scene: the action, a paragraph break, then the narration (R1)."""
        parts = (self.action.strip(), self.narration.strip())
        return PARAGRAPH.join(part for part in parts if part)


class ChapterOutput(BaseModel):
    """C3. A chapter summary, so older scenes can leave the prompt without being lost."""

    summary: Text = Field(description="What happened in these scenes, in at most 200 words.")
