"""The moment the last scene ended on (R3) and what it holds (R2)."""

from enum import StrEnum

from pydantic import Field

from engine.base import EngineModel, WorldSeconds


class EncounterKind(StrEnum):
    """W10. A fight, a chase, a duel of words or a negotiation. Turns inside one don't count as
    quiet for the director (W16)."""

    FIGHT = "fight"
    CHASE = "chase"
    DUEL = "duel"
    NEGOTIATION = "negotiation"
    OTHER = "other"


class Encounter(EngineModel):
    """W10. Code starts and ends it (`engine.encounters`); the interpret step may propose a kind.
    `opponent_ids` is everyone it has been with, including those already out of it."""

    kind: EncounterKind
    opponent_ids: list[str] = Field(default_factory=list)
    started_turn: int = Field(ge=0)
    started_s: WorldSeconds
    key: bool = Field(
        default=False, description="With a key NPC or a strong monster (M1 picture triggers)."
    )
    last_s: WorldSeconds | None = Field(
        default=None,
        description="When its last exchange ended; None means when it started. It ends once "
        "`engine.encounters.LAPSE_S` of in-world time pass with none.",
    )


class SceneFrame(EngineModel):
    """Where the last scene stopped: same place, same people, same positions, same things in hand
    (R3). `props` are things the narration established in the scene, such as a bottle on the bar,
    which R2's beat check may use. `ended_on` is the moment itself, in a sentence."""

    place_id: str | None = None
    present_ids: list[str] = Field(default_factory=list)
    positions: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)
    ended_on: str = ""
    encounter: Encounter | None = None
