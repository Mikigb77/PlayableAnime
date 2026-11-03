"""Shared building blocks: the base model, in-world time units and bounded number types."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class EngineModel(BaseModel):
    """Base for every engine model.

    Unknown keys are ignored when loading, so a state saved by an older or newer engine version
    still loads (new fields need defaults). Values are validated when a model is built or loaded,
    not on every assignment: engine code mutates copies freely, and `engine.invariants` (PR 2)
    re-checks a state before it is saved.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# In-world time (W10) is a whole number of seconds since the story's epoch, the moment the story
# opens. Turns never measure world time.
SECOND = 1
MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY
YEAR = 365 * DAY

# The id of the only timeline until someone rewinds the world (W10a).
MAIN_TIMELINE = "main"

# A name must have at least one visible character (C1: no nameless characters).
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

WorldSeconds = Annotated[int, Field(ge=0, description="Seconds since the story's epoch (W10).")]
Seconds = Annotated[int, Field(ge=0, description="A span of in-world time in seconds.")]

# Bounded scales (C1: stats stay within bounds).
Affinity = Annotated[int, Field(ge=-100, le=100)]  # hatred -100, indifference 0, devotion 100
Trust = Annotated[int, Field(ge=-100, le=100)]  # sure betrayal -100, unknown 0, total trust 100
Esteem = Annotated[int, Field(ge=-100, le=100)]  # W3: how much they like you
Fear = Annotated[int, Field(ge=0, le=100)]  # W3, W4: how dangerous they think you are
Percent = Annotated[int, Field(ge=0, le=100)]
Severity = Annotated[int, Field(ge=1, le=5)]  # W1, W12, by the world's norms
Importance = Annotated[int, Field(ge=1, le=5)]  # C2: 1 is flavour, 5 must never be forgotten
Tier = Annotated[int, Field(ge=0, le=20)]  # A8 power tiers; a world's ladder names them (G18)
Level = Annotated[int, Field(ge=0, le=10)]  # G13 attributes, see `engine.state.sheet.Attributes`
Strain = Annotated[int, Field(ge=0, le=4)]  # fatigue, hunger, stress: none 0 to extreme 4
Probability = Annotated[float, Field(ge=0.0, le=1.0)]

AFFINITY_MIN, AFFINITY_MAX = -100, 100
TRUST_MIN, TRUST_MAX = -100, 100
ESTEEM_MIN, ESTEEM_MAX = -100, 100
FEAR_MIN, FEAR_MAX = 0, 100
TIER_MIN, TIER_MAX = 0, 20
THREAT_MIN, THREAT_MAX = 0, 5
