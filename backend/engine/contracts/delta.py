"""State changes that a narrator or the engine proposes, applied by `engine.apply.apply_delta`,
which enforces C1.

One shape serves both proposers. The narrator's structured output (B5 step 5) fills the ordinary
fields; it replaces `legacy`'s `StateUpdate`. Some fields are **engine only** and are rejected when
the narrator proposes them, because the engine owns the truth: terminal changes (a death, a
destroyed faction, a ruined place), anything that needs a `Cause` (C1), faction reputation (W3),
rulings (A9), gains (A4), accepted backstory (N4), rule changes (G7), the state of powers,
skills, techniques, ladders, practice and time effects (A4, G19, W10a), and a romance: the
bond between two people and how drawn someone is to another (W17). The narrator moves an
attitude by at most `engine.apply.NARRATOR_ATTITUDE_CAP` per delta (W4). Resolve puts the
engine's changes for each step in `StepResolution.effects`. A rung above a ladder's highest
is the narrator's to name when its scene told one (`NewRung`), and the engine's to accept
(`engine.path.beyond_problem`): nobody on record is put on it (G18, G7).

Number fields on changes are deltas, clamped to their bounds when applied. `None` means
"unchanged".
"""

from enum import StrEnum
from typing import Any

from pydantic import ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from engine.base import EngineModel, Importance, Name
from engine.state.cast import (
    CharacterStatus,
    DeathCertainty,
    FactionStatus,
    Judged,
    PlaceSetting,
    PlaceStatus,
    Prominence,
    Route,
)
from engine.state.records import BondStage, Cause, FactKind
from engine.state.sheet import (
    Attributes,
    Gain,
    Health,
    HitMode,
    ItemKind,
    LadderPosition,
    PowerAxes,
    Practice,
    Ruling,
    Skill,
    TalentBridge,
    TalentRuling,
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
    attraction: SkipJsonSchema[int] = Field(
        default=0, ge=-100, le=100, description="Engine only (W17): their own heart."
    )


class BondChange(EngineModel):
    """W17. Engine only: the romance between two people comes to a stage. The first such change
    between a pair opens their bond. `by_id` is who made the move and `how` what happened, in
    the world's words."""

    a_id: str
    b_id: str
    stage: BondStage
    by_id: str | None = None
    how: str = ""


class ConditionChange(EngineModel):
    health: Health | None = None
    wounds: list[str] = Field(default_factory=list)
    lasting_wounds: list[str] = Field(
        default_factory=list,
        description="Engine only (N6, G17): wounds that last, such as a lost hand or an eye.",
    )
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


class Expecting(EngineModel):
    """N6. A child on the way, as the scene made it so, or a pregnancy that ended."""

    other_parent_id: str | None = Field(
        default=None, description="The child's other parent, by id, when the story knows them."
    )
    ended: bool = Field(
        default=False,
        description="The pregnancy ended without a birth, as the scene showed, or was never real.",
    )


def _rung_required(schema: dict[str, Any]) -> None:
    """G18. Gemini answers only what a schema requires as often as not (see `Intent`), and
    someone a scene brought in whose rung went unsaid is an ordinary person on record, whatever
    the scene told of them. So the model is always asked for it, empty for whoever stands on
    none, though code may leave it out."""
    schema["required"] = list(dict.fromkeys([*schema.get("required", []), "rung"]))
    rung = schema["properties"]["rung"]
    schema["properties"]["rung"] = {"type": "string", "description": rung["description"]}


class CharacterChange(EngineModel):
    """A new character (a name is required) or a change to a known one."""

    model_config = ConfigDict(json_schema_extra=_rung_required)

    id: str
    name: Name | None = None
    aliases: list[str] = Field(default_factory=list)
    prominence: Prominence | None = None
    description: str | None = None
    appearance: str | None = Field(
        default=None,
        description="C9: looks and usual clothes, for every picture of them. Never what they "
        "carry, such as a weapon: those are items (C10).",
    )
    look_change: str | None = Field(
        default=None,
        description="M5, G17: a lasting change to how a known character looks, in a few words, "
        "such as 'lost his left eye' or 'grey-haired with the years', with the whole appearance "
        "written again. Never for mud, blood, clothes or anything else that passes.",
    )
    age: int | None = Field(
        default=None,
        ge=0,
        description="W10: only for someone new, or whose age the record doesn't have. An age on "
        "record moves with the world's years, never by a scene.",
    )
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
    rung: str | None = Field(
        default=None,
        description="G18: only for someone new, where the world has a ladder and they are "
        "someone who stands on it: the name of their rung, as WORLD lists it, or the rung "
        "above the top where the form asked this scene to name one. Most people the story "
        "brings in stand on the lowest rungs or on none. Empty for whoever stands on none, "
        "and for someone already on record: nobody is lifted, they climb.",
    )
    meets_player: bool = False
    known_to_player: bool = False
    parent_ids: list[str] = Field(
        default_factory=list,
        description="N6: their parents, by id: for someone met as someone's child, or a "
        "parentage the scene reveals. Added to what the story has, never taken back; two at most. "
        "Never the player character's parents or children: their family comes from their story.",
    )
    expecting: Expecting | None = Field(
        default=None,
        description="N6: they now carry a child, as the scene made it so, or with ended, a "
        "pregnancy is over. The child is born when it is due, if they live.",
    )
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
    # Kept out of the form the models fill: only the engine ever writes it.
    attributes: SkipJsonSchema[Attributes | None] = Field(
        default=None,
        description="Engine only: the body and mind of someone new the engine makes real (F1, "
        "G13), where they are not an average adult's.",
    )
    talent_rulings: SkipJsonSchema[list[TalentRuling]] = Field(
        default_factory=list,
        description="Engine only (A4): which talents cover a thing they set out to learn, "
        "ruled once. A thing already ruled on keeps its ruling.",
    )
    bridges: SkipJsonSchema[list[TalentBridge]] = Field(
        default_factory=list,
        description="Engine only (A4): work that connects a talent to something outside it.",
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
    parent_id: str | None = Field(
        default=None,
        description="R8: the place it lies within, such as the temple a chamber is in, or the "
        "forest outside it for a clearing.",
    )
    setting: PlaceSetting | None = Field(
        default=None,
        description="R8: outdoors (open sky), indoors (under a roof), underground or "
        "underwater. Set once: a place's setting doesn't change.",
    )
    status: PlaceStatus | None = None
    cause: Cause | None = Field(default=None, description="Engine only (C1).")
    controller_id: str | None = None
    mood: str | None = None
    routes: list[Route] = Field(default_factory=list, description="Added or updated travel times.")

    @field_validator("setting", mode="before")
    @classmethod
    def _setting_or_untold(cls, value: object) -> object:
        """R8: a setting written in another case is read, and one that is none of the four is
        left untold, so a stray word never costs the narrator's whole answer."""
        if isinstance(value, str):
            word = value.strip().casefold()
            return word if word in PlaceSetting._value2member_map_ else None
        return value

    visited: bool = Field(default=False, description="The player character is there.")
    known_to_player: bool = False
    # Kept out of the form the models fill: only the engine ever writes it.
    judged: SkipJsonSchema[list[Judged]] = Field(
        default_factory=list,
        description="Engine only (A3): things of the place whose level was judged this turn. "
        "A thing already judged keeps its level.",
    )


class NewFact(EngineModel):
    text: str
    kind: FactKind = FactKind.OBSERVATION
    importance: Importance = 3
    is_true: bool = True
    subject_ids: list[str] = Field(default_factory=list)
    known_by: list[str] = Field(default_factory=list)
    known_to_player: bool = True


# C10: the id that stands for the world in an `ItemChange`, for what comes from it (found, made)
# or leaves it (used up, eaten, lost).
WORLD = "world"


class ItemChange(EngineModel):
    """C10, C2. Something that changes hands, money included: paid, given, sold, stolen, found,
    used up or lost. One entry per thing that moves, so it is never in two places at once:
    `from_id` loses it and `to_id` gains it, each a character id (the player character's
    included) or `world`, for what the world gives (found, made) or takes (used up, eaten,
    broken, lost). The same id on both sides changes how the thing is described or whether it is
    on them, and moves nothing. `engine.possessions` applies it: nobody gives what they don't
    have."""

    name: Name = Field(description="What it is, in plain words: 'copper coins', 'the Beretta'.")
    from_id: str = Field(
        description="Who had it: a character id, the player character's included, or 'world' "
        "when the world gives it (found, made, picked up)."
    )
    to_id: str = Field(
        description="Who has it now: a character id, the player character's included, or "
        "'world' when it is gone (used up, eaten, broken, lost, spent where nobody keeps it)."
    )
    money: bool = Field(default=False, description="It is money, counted in quantity.")
    quantity: int = Field(default=1, description="How many, or how much money.")
    item_id: str | None = Field(default=None, description="A known item's id.")
    how: str = Field(
        default="", description="How, in a word or two: stolen, paid, given, found, eaten."
    )
    kind: ItemKind | None = None
    description: str | None = None
    carried: bool | None = Field(
        default=None, description="Whether the one who has it now carries it on them."
    )


class NewLead(EngineModel):
    """N2. What the world offers. It can expire on in-world time and never overwrites a goal."""

    text: str
    kind: str = ""
    from_id: str | None = None
    place_id: str | None = None
    expires_in_s: int | None = Field(default=None, gt=0)


class GoalEnd(StrEnum):
    ACHIEVED = "achieved"
    FAILED = "failed"
    REPEATS = "repeats"


class GoalOver(EngineModel):
    """N2. One of the player character's goals that is over: play achieved it for good, it can
    no longer happen, or it only says again what another of their goals says. The engine closes
    it on a turn the player acted; it never rewrites one."""

    goal_id: str
    how: GoalEnd
    same_as: str | None = Field(
        default=None, description="For repeats: the id of the goal it says again."
    )


class GoalMoved(EngineModel):
    """N2, C6. One of the player character's goals that this scene moved forward, and where it
    stands now as far as they know. The engine keeps the sentence beside the goal; it never
    rewrites the goal."""

    goal_id: str
    progress: str = Field(
        description="Where it stands now, as the character knows it, in one sentence."
    )


class NewRung(EngineModel):
    """G18, G7. A rung above a ladder's highest that this scene told by name, because the story
    reached past the top: beings stronger than its highest rung came into it, or someone at the
    top found that something lies beyond. Never a rung WORLD's ladders already list, and never
    for a stage or a title within a rung. The engine decides whether it holds."""

    ladder_id: str
    name: Name = Field(description="The rung's name, exactly as the scene says it.")
    description: str = Field(default="", description="What it is, in a sentence.")
    stands: list[str] = Field(
        default_factory=list,
        description="The ids of characters this same update creates who stand on it, three at "
        "most. Never someone already on record: nobody is lifted there.",
    )


class RuleChange(EngineModel):
    """G7. Engine only: an open rule changed by a discovery, for everyone. Fixed rules never
    change."""

    rule_id: str
    text: str
    cause: Cause


def _place_required(schema: dict[str, Any]) -> None:
    """R8. Gemini answers only what a schema requires as often as not (see `Intent`), and a scene
    end without its place left the character in the last one, wherever the scene took them. So
    the model is always asked for the place's id, though code may leave it out."""
    schema["required"] = list(dict.fromkeys([*schema.get("required", []), "place_id"]))
    place = schema["properties"]["place_id"]
    schema["properties"]["place_id"] = {"type": "string", "description": place["description"]}


class SceneEnd(EngineModel):
    """R3, R8. The moment this scene stops on, which the next scene starts from."""

    model_config = ConfigDict(json_schema_extra=_place_required)

    ended_on: str
    place_id: str | None = Field(
        default=None,
        description="R8: the id of the place the scene ends in: SCENE's place while the "
        "character is still there, else a known place or one this update adds under places.",
    )
    present_ids: list[str] = Field(default_factory=list)
    positions: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)


def _scene_end_required(schema: dict[str, Any]) -> None:
    """R3, R8. The narrator always says what moment its scene stops on, and where (`SceneEnd`),
    so the next scene starts there. Code may still leave it out, as the engine's own deltas and
    the offline model's minimal answer do."""
    schema["required"] = list(dict.fromkeys([*schema.get("required", []), "scene_end"]))


class StateDelta(EngineModel):
    model_config = ConfigDict(json_schema_extra=_scene_end_required)

    characters: list[CharacterChange] = Field(default_factory=list)
    factions: list[FactionChange] = Field(default_factory=list)
    places: list[PlaceChange] = Field(default_factory=list)
    facts: list[NewFact] = Field(default_factory=list)
    items: list[ItemChange] = Field(default_factory=list)
    leads: list[NewLead] = Field(default_factory=list)
    goals_over: list[GoalOver] = Field(default_factory=list)
    goals_moved: list[GoalMoved] = Field(default_factory=list)
    rungs: list[NewRung] = Field(
        default_factory=list,
        description="G18: a rung the scene told of above a ladder's highest. Almost always empty.",
    )
    rule_changes: list[RuleChange] = Field(default_factory=list, description="Engine only (G7).")
    time_effects: list[ActiveTimeEffect] = Field(
        default_factory=list,
        description="Engine only: a time power taking hold, such as a stop that outlasts the turn.",
    )
    bonds: SkipJsonSchema[list[BondChange]] = Field(
        default_factory=list,
        description="Engine only (W17): a romance on record coming to a stage.",
    )
    scene_end: SceneEnd | None = Field(
        default=None, description="R3, R8: the moment this scene stops on, and where."
    )
    summary: str | None = Field(default=None, description="The rolling summary, if it changed.")

    @property
    def empty(self) -> bool:
        return self == StateDelta()
