"""What the model nodes return (structured output). Code checks every field before it counts.

The interpret node returns `engine.contracts.Intent` as it is. The narrator's object puts
`narration` first, so its text streams to the player while the rest is still being written (S3).
"""

from pydantic import BaseModel, Field

from engine.contracts import ChoiceKind, StateDelta


class SuggestionOut(BaseModel):
    """S2. A suggested action, in the player character's voice of intent."""

    label: str = Field(description="A short action, at most 12 words.")
    kind: ChoiceKind


class NarratorOutput(BaseModel):
    """B5 step 5. The scene, its suggestions, the picture prompt and the proposed state update."""

    narration: str = Field(description="The scene, as the player reads it.")
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


class ChapterOutput(BaseModel):
    """C3. A chapter summary, so older scenes can leave the prompt without being lost."""

    summary: str = Field(description="What happened in these scenes, in at most 200 words.")
