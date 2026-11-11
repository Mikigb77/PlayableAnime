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


class Terms(StrEnum):
    """W1. The worst that both sides of a fight agreed it may do to them: consent covers the
    bout, not the wound. A blow inside the terms is no attack, and one beyond them is one
    (`engine.resolve.bouts`)."""

    NO_HARM = "no_harm"  # sparring, a lesson, a play fight: a touch, a throw or a pin decides it
    WOUNDS = "wounds"  # first blood, a duel or a trial that accepts wounds
    DEATH = "death"  # to the death


class Bout(EngineModel):
    """W1. A fight both sides agreed to, inside an encounter: its terms and whom the player
    character agreed them with. Code keeps it from the step that began it until the encounter
    ends or a blow goes beyond the terms (`engine.resolve.bouts`, `engine.encounters`)."""

    terms: Terms
    with_ids: list[str] = Field(default_factory=list)


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
    bout: Bout | None = Field(
        default=None,
        description="W1: the terms it is fought under, when both sides agreed to it. None for "
        "any other encounter, and for a fight that has no terms or broke them.",
    )
    in_earnest: bool = Field(
        default=False,
        description="W1: someone in it was harmed outside any terms, or its terms were broken, "
        "so it can never become a bout: an attack isn't relabelled as one.",
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
