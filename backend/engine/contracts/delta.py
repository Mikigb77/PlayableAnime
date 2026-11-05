"""State changes that a narrator or the engine proposes, applied by `engine.apply.apply_delta`,
which enforces C1.

One shape serves both proposers. The narrator's structured output (B5 step 5) fills the ordinary
fields; it replaces `legacy`'s `StateUpdate`. Some fields are **engine only** and are rejected when
the narrator proposes them, because the engine owns the truth: terminal changes (a death, a
destroyed faction, a ruined place), anything that needs a `Cause` (C1), faction reputation (W3),
rulings (A9), gains (A4), accepted backstory (N4), rule changes (G7), and the state of powers,
skills, techniques, ladders, practice and time effects (A4, G19, W10a). The narrator moves an
attitude by at most `engine.apply.NARRATOR_ATTITUDE_CAP` per delta (W4). Resolve puts the
engine's changes for each step in `StepResolution.effects`.

Number fields on changes are deltas, clamped to their bounds when applied. `None` means
"unchanged".
"""

from pydantic import Field

from engine.base import EngineModel, Importance, Name
from engine.state.cast import (
    CharacterStatus,
    DeathCertainty,
    FactionStatus,
    PlaceStatus,
    Prominence,
    Route,
)
from engine.state.records import Cause, FactKind
from engine.state.sheet import (
    Gain,
    Health,
    HitMode,
    ItemKind,
    LadderPosition,
    PowerAxes,
    Practice,
    Ruling,
    Skill,
    Technique,
)
from engine.state.world import ActiveTimeEffect


class AttitudeShift(EngineModel):
    """W4. A change in how a character feels about someone."""

    toward_id: str | None = Field(default=None, description="None means the player character.")
    affinity: int = Field(default=0, ge=-100, le=100)
    fear: int = Field(default=0, ge=-100, le=100)
    trust: int = Field(default=0, ge=-100, le=100)
    grudge: str | None = Field(default=None, description="A new grudge, with its reason.")


class ConditionChange(EngineModel):
    health: Health | None = None
    wounds: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list, description="Passing states that begin.")
    cleared_states: list[str] = Field(default_factory=list)


class PowerSetting(EngineModel):
    """A detail of a power the engine settled (A9), by key, such as `throws: relative_speed`."""

    key: str
    value: str


class PowerChange(EngineModel):
    """Engine only. A power after use: when it is ready again on the user's own clock (W10a), and
    details the engine settled (A9). A settled detail is never changed: a different value for a
    hit mode or a setting already set is refused."""

    id: str
    ready_at_personal_s: int | None = None
    hit_mode: HitMode | None = None
    settings: list[PowerSetting] = Field(default_factory=list)


class CharacterChange(EngineModel):
    """A new character (a name is required) or a change to a known one."""

    id: str
    name: Name | None = None
    aliases: list[str] = Field(default_factory=list)
    prominence: Prominence | None = None
    description: str | None = None
    appearance: str | None = None
    look_change: str | None = Field(
        default=None,
        description="M5, G17: a lasting change to how a known character looks, in a few words, "
        "such as 'lost his left eye' or 'grey-haired with the years', with the whole appearance "
        "written again. Never for mud, blood, clothes or anything else that passes.",
    )
    age: int | None = Field(default=None, ge=0)
    people_id: str | None = Field(
        default=None,
        description="The bible's id of their people (G23), or of their kind for a beast (G24).",
    )
    location_id: str | None = None
    status: CharacterStatus | None = None
    death_certainty: DeathCertainty | None = None
    cause: Cause | None = Field(default=None, description="Engine only (C1).")
    attitudes: list[AttitudeShift] = Field(default_factory=list)
    condition: ConditionChange | None = None
    faction_id: str | None = Field(default=None, description="Joins this faction, or re-ranks.")
    rank: str | None = None
    meets_player: bool = False
    known_to_player: bool = False
    rulings: list[Ruling] = Field(default_factory=list, description="Engine only (A9).")
    gains: list[Gain] = Field(default_factory=list, description="Engine only (A4, G17).")
    backstory: list[str] = Field(default_factory=list, description="Engine only (N4).")
    powers: list[PowerChange] = Field(default_factory=list, description="Engine only (A9, W10a).")
    techniques: list[Technique] = Field(
        default_factory=list, description="Engine only: techniques learned (A4, G25)."
    )
    ladders: list[LadderPosition] = Field(
        default_factory=list,
        description="Engine only: a new place on a ladder (G19) or strength hidden (G20).",
    )
    practice: list[Practice] = Field(
        default_factory=list, description="Engine only: effort so far toward a gain (A4)."
    )
    skills: list[Skill] = Field(
        default_factory=list,
        description="Engine only: a skill learned or raised by training (A4), by name.",
    )
    axes: PowerAxes | None = Field(
        default=None,
        description="Engine only: the A8 tiers of someone new the engine makes real (F1).",
    )


class FactionChange(EngineModel):
    id: str
    name: Name | None = None
    kind: str | None = None
    description: str | None = None
    parent_id: str | None = None
    status: FactionStatus | None = None
    cause: Cause | None = Field(default=None, description="Engine only (C1).")
    esteem: int = Field(
        default=0, ge=-100, le=100, description="Player esteem delta. Engine only (W3)."
    )
    fear: int = Field(
        default=0, ge=-100, le=100, description="Player fear delta. Engine only (W3)."
    )
    known_to_player: bool = False


class PlaceChange(EngineModel):
    id: str
    name: Name | None = None
    kind: str | None = None
    description: str | None = None
    parent_id: str | None = None
    status: PlaceStatus | None = None
    cause: Cause | None = Field(default=None, description="Engine only (C1).")
    controller_id: str | None = None
    mood: str | None = None
    routes: list[Route] = Field(default_factory=list, description="Added or updated travel times.")
    visited: bool = Field(default=False, description="The player character is there.")
    known_to_player: bool = False


class NewFact(EngineModel):
    text: str
    kind: FactKind = FactKind.OBSERVATION
    importance: Importance = 3
    is_true: bool = True
    subject_ids: list[str] = Field(default_factory=list)
    known_by: list[str] = Field(default_factory=list)
    known_to_player: bool = True


class ItemChange(EngineModel):
    """Something gained, used up or lost. `quantity` is a delta: 1 gains one, -1 loses one."""

    owner_id: str | None = Field(default=None, description="None means the player character.")
    item_id: str | None = None
    name: Name
    kind: ItemKind | None = None
    description: str | None = None
    quantity: int = 1
    carried: bool | None = None


class NewLead(EngineModel):
    """N2. What the world offers. It can expire on in-world time and never overwrites a goal."""

    text: str
    kind: str = ""
    from_id: str | None = None
    place_id: str | None = None
    expires_in_s: int | None = Field(default=None, gt=0)


class RuleChange(EngineModel):
    """G7. Engine only: an open rule changed by a discovery, for everyone. Fixed rules never
    change."""

    rule_id: str
    text: str
    cause: Cause


class SceneEnd(EngineModel):
    """R3. The moment this scene stops on, which the next scene starts from."""

    ended_on: str
    place_id: str | None = None
    present_ids: list[str] = Field(default_factory=list)
    positions: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)


class StateDelta(EngineModel):
    characters: list[CharacterChange] = Field(default_factory=list)
    factions: list[FactionChange] = Field(default_factory=list)
    places: list[PlaceChange] = Field(default_factory=list)
    facts: list[NewFact] = Field(default_factory=list)
    items: list[ItemChange] = Field(default_factory=list)
    leads: list[NewLead] = Field(default_factory=list)
    rule_changes: list[RuleChange] = Field(default_factory=list, description="Engine only (G7).")
    time_effects: list[ActiveTimeEffect] = Field(
        default_factory=list,
        description="Engine only: a time power taking hold, such as a stop that outlasts the turn.",
    )
    scene_end: SceneEnd | None = None
    summary: str | None = Field(default=None, description="The rolling summary, if it changed.")

    @property
    def empty(self) -> bool:
        return self == StateDelta()
