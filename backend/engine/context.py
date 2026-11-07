"""Per-turn inputs that live outside the world state.

Story settings sit on the story row and content preferences on the account (API.md), so the turn
graph passes them in with every call instead of copying them into `WorldState`.
"""

from enum import StrEnum

from pydantic import Field

from engine.base import EngineModel


class Rating(StrEnum):
    """F2. Under-17 accounts get Teen only (F8)."""

    TEEN = "teen"
    MATURE = "mature"


class Language(StrEnum):
    """S10. The languages the app speaks, as language codes."""

    EN = "en"
    ES = "es"
    CA = "ca"


class Difficulty(StrEnum):
    """A5. Shifts the odds of rolled steps only, never a certain or ruled-out one (A2)."""

    STORY = "story"
    BALANCED = "balanced"
    BRUTAL = "brutal"


class EventFrequency(StrEnum):
    """W16, S6. How often the director brings in events. It never turns them off."""

    CALM = "calm"
    NORMAL = "normal"
    DRAMATIC = "dramatic"


class ImageSetting(StrEnum):
    """M2, S6. How often automatic pictures come."""

    OFF = "off"
    KEY_MOMENTS = "key_moments"
    MORE = "more"


class Accent(StrEnum):
    """S13. The color the player chose for a story's titles and buttons, by the app's names for
    its accents. Only the app reads it: nothing in the engine or the prompts does (G5)."""

    LUCID = "lucid"
    JADE = "jade"
    AZURE = "azure"
    EMBER = "ember"
    VIOLET = "violet"
    CRIMSON = "crimson"
    CYAN = "cyan"
    ORCHID = "orchid"
    LIME = "lime"
    ROSE = "rose"
    SILVER = "silver"


class NarrationLength(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class GoreLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ContentPrefs(EngineModel):
    """F7. The world and NPCs only start themes that are switched on. The player's own actions
    are bounded only by the rating."""

    gore: GoreLevel = GoreLevel.MEDIUM
    romance: bool = True
    dark_themes: bool = True


class StorySettings(EngineModel):
    """S6, the engine's view of API.md's `StorySettings`."""

    narration_length: NarrationLength = NarrationLength.MEDIUM
    tone: str | None = None
    difficulty: Difficulty = Difficulty.BALANCED
    event_frequency: EventFrequency = EventFrequency.NORMAL
    images: ImageSetting = ImageSetting.KEY_MOMENTS
    suggestions: bool = True
    # S10: the language the story is written in from the next scene on. What it already told
    # stays in the language it was written in.
    language: Language = Language.EN
    # S13: the color the player chose for the story, or None for its genre's.
    accent: Accent | None = None


class TurnContext(EngineModel):
    """Everything about the turn being played that isn't world state."""

    story_id: str = Field(min_length=1)
    turn: int = Field(ge=0, description="The turn being played; the opening scene is turn 1.")
    settings: StorySettings = Field(default_factory=StorySettings)
    rating: Rating = Rating.TEEN
    content_prefs: ContentPrefs = Field(default_factory=ContentPrefs)
