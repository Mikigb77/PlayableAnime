"""What the model nodes return (structured output). Code checks every field before it counts.

The interpret node returns `engine.contracts.Intent` as it is. The narrator's object puts its
text first, `action` and then `narration`, so the scene streams to the player while the rest is
still being written (S3). `action` is its own field so that every scene tells the character doing
what the player said before anything comes of it (R1), and code can see when one didn't.
"""

from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from engine.contracts import ChoiceKind, StateDelta
from graph.llm.jsonstream import PARAGRAPH

# A blank answer is a failed answer: the model layer retries it once, then gives up (T7).
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SuggestionOut(BaseModel):
    """S2. A suggested action, in the player character's voice of intent."""

    label: str = Field(description="A short action, at most 12 words.")
    kind: ChoiceKind


def _action_required(schema: dict[str, Any]) -> None:
    """R1, R8. Gemini answers only what a schema requires as often as not (see `Intent`), so the
    model is always asked for `action`, though code may leave it empty (an opening, a template
    line), for `told_talk` and `told_news`, so talk and news a scene told are never left
    unrecorded (W2, W6), and for `update`, whose scene end says where the next scene starts
    (R3, R8)."""
    required = ["action", *schema.get("required", []), "told_talk", "told_news", "update"]
    schema["required"] = list(dict.fromkeys(required))


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
    # Required, but it may be blank when `action` holds the whole scene: a told scene is never
    # thrown away for where the model split it. `_told` refuses only a blank scene.
    narration: str = Field(
        description=(
            "The rest of the scene, as the player reads it, picking up where action stops: the"
            " outcome, how the world reacts, and an ending the player can act on. With no"
            " action, the whole scene."
        )
    )
    told_talk: bool = Field(
        default=False,
        description=(
            "W2: true only when the brief has TALK and the scene let the character catch it."
            " False when there is no TALK, or the scene had no room for it."
        ),
    )
    told_news: list[str] = Field(
        default_factory=list,
        description=(
            "W6: the id of every piece of news (news under a person in the brief, or under"
            " WIDER WORLD) that this scene showed or said, naming whoever it came with,"
            " the faction or place it came to, or the one who died. Empty when the brief"
            " has no news, or the scene told none."
        ),
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

    @model_validator(mode="after")
    def _told(self) -> Self:
        """A blank scene is a failed answer: the model layer retries it once, then gives up (T7)."""
        if not self.text:
            raise ValueError("the scene is blank")
        return self

    @property
    def text(self) -> str:
        """The whole scene, as it streamed (`JsonFieldStreamer`): the action, a paragraph break,
        then the narration, each without the spaces around it (R1)."""
        parts = (self.action.strip(), self.narration.strip())
        return PARAGRAPH.join(part for part in parts if part)


class ChapterOutput(BaseModel):
    """C3. A chapter summary, so older scenes can leave the prompt without being lost."""

    summary: Text = Field(description="What happened in these scenes, in at most 200 words.")
