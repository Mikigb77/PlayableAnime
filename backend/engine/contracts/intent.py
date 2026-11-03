"""What the interpret step proposes (B5 step 2): the player's action read as steps, beats, a chain
of cause and effect, proposed facts and durations.

The interpret model fills this from typed or dictated text (V3) and never refuses: an action that
fits no category still becomes a step. Everything here is a proposal. Code checks the beats (R2),
the facts (A2) and the durations (W10) against the state and decides.

This is a model-output schema, so it avoids free-form maps and unions, which structured output
handles poorly.
"""

from enum import StrEnum

from pydantic import Field

from engine.base import EngineModel
from engine.state.sheet import PowerAxis


class ActionKind(StrEnum):
    """W10. What kind of action a step is, which bounds how long it can take. The bounds are in
    `engine.timekeeping.DURATION_BOUNDS`."""

    INSTANT = "instant"  # a word, a glance, drawing a blade
    EXCHANGE = "exchange"  # a sword exchange, a spell, a shot, a throw
    MOVE = "move"  # crossing a room or a square, a climb, a short run
    CONVERSATION = "conversation"
    TASK = "task"  # brewing a potion, a search, picking a lock, crafting
    REST = "rest"  # a nap, a night's sleep
    WORK = "work"  # a day's work, a shift, a ritual
    TRAVEL = "travel"
    WAIT = "wait"  # the standing action (S2)
    OBSERVE = "observe"  # the standing action (S2)
    TIME_SKIP = "time_skip"  # a montage: "I train here for a year" (E7)


class OutcomeClass(StrEnum):
    """A2. Code decides the class from the facts; only contested and long-shot steps are rolled."""

    CERTAIN = "certain"
    CONTESTED = "contested"
    LONG_SHOT = "long_shot"
    RULED_OUT = "ruled_out"


class MeansVerdict(StrEnum):
    """A2. When nothing can push back, whether the character's means are enough. Only a genuinely
    close call is rolled."""

    CLEARLY_ENOUGH = "clearly_enough"
    CLOSE_CALL = "close_call"
    CLEARLY_NOT = "clearly_not"


class SheetPart(StrEnum):
    """G13, G14. Which part of the sheet a step draws on."""

    ATTRIBUTE = "attribute"
    SKILL = "skill"
    TRAIT = "trait"
    POWER = "power"
    TECHNIQUE = "technique"
    ITEM = "item"
    STANDING = "standing"  # a title, a rank, a family name
    CONNECTION = "connection"
    CONDITION = "condition"


class SheetUse(EngineModel):
    part: SheetPart
    ref: str = Field(description="The power, item or technique id, or the skill or trait name.")


class UseSource(StrEnum):
    """R2. Whatever a beat uses has to be the character's own body or powers, something they
    carry, something the scene holds, or something this turn made canon. `new` is something the
    scene hasn't established, with the interpret step's judgement in `plausibility`."""

    BODY = "body"
    POWER = "power"
    CARRIED = "carried"
    SCENE = "scene"
    CANON = "canon"  # made canon by an earlier beat this turn
    NEW = "new"


class Plausibility(StrEnum):
    """R2. Whether the place plausibly holds something the scene hasn't established. Plausible
    becomes canon, uncertain is rolled, and absent turns the beat into an empty search."""

    PLAUSIBLE = "plausible"
    UNCERTAIN = "uncertain"
    ABSENT = "absent"


class BeatUse(EngineModel):
    source: UseSource
    thing: str = Field(description="What is used, in plain words: 'a stone the size of an egg'.")
    ref: str | None = Field(default=None, description="The power or item id, when there is one.")
    plausibility: Plausibility | None = Field(default=None, description="Only for source 'new'.")


class Beat(EngineModel):
    """R2. One of the small steps an action implies: crouch, feel along the floor, find a stone,
    throw. Beats add no decision the player didn't make."""

    text: str
    uses: list[BeatUse] = Field(default_factory=list)


class ChainLink(EngineModel):
    """A9. One link in a chain of cause and effect, with the facts it rests on. Code settles each
    link as A2 does, and the chain stops at the first link that fails."""

    text: str = Field(description="'The field keeps out air as well as flames.'")
    rests_on: list[str] = Field(
        default_factory=list,
        description="The facts this link rests on: rule, power, fact or character ids, or words.",
    )
    takes_s: int | None = Field(default=None, ge=0, description="In-world seconds it takes.")
    proposed_class: OutcomeClass | None = None


class StepFacts(EngineModel):
    """A2, A8. The facts the interpret step proposes for one step. Code checks them against the
    state wherever the state can tell."""

    opposition_ids: list[str] = Field(default_factory=list)
    opposition: str = Field(default="", description="What stands in the way, in words.")
    can_respond: bool | None = Field(
        default=None, description="Whether the opposition can respond at all; None if none."
    )
    why_not: str = Field(default="", description="Frozen, asleep, bound or unaware.")
    means: MeansVerdict | None = None
    world_allows: bool = Field(default=True, description="G8: whether the world allows it.")
    against_rule_ids: list[str] = Field(default_factory=list)
    edges: list[str] = Field(
        default_factory=list, description="Preparation, allies, items or position in their favour."
    )
    hindrances: list[str] = Field(default_factory=list)
    proposed_class: OutcomeClass | None = None


class IntentStep(EngineModel):
    """One step of what the player does. A chained plan ("I throw the stone, then run for the
    tunnel") has several, resolved in order (R6)."""

    text: str = Field(description="The step in plain words.")
    verb: str = Field(description="Free-form: attack, persuade, search, stop time, flee.")
    method: str = ""
    target_ids: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list, description="Targets in words.")
    axis: PowerAxis | None = None
    uses: list[SheetUse] = Field(default_factory=list)
    beats: list[Beat] = Field(default_factory=list)
    chain: list[ChainLink] = Field(default_factory=list)
    facts: StepFacts = Field(default_factory=StepFacts)
    lines: list[str] = Field(
        default_factory=list,
        description="R7: the player's own words for the character, cleaned of dictation filler.",
    )
    gist: str = Field(default="", description="R7: what to say, when the player gave only gist.")
    kind: ActionKind
    proposed_duration_s: int = Field(ge=0, description="World seconds it should take (W10).")
    duration_uncertain: bool = Field(
        default=False, description="W10: how long it takes is itself an outcome to roll."
    )
    proposed_personal_s: int | None = Field(
        default=None,
        ge=0,
        description="W10a: the actor's own lived seconds, when they differ, as in a time stop.",
    )
    stakes: str = ""


class StandingAction(StrEnum):
    """S2. Always offered next to the suggestions."""

    WAIT = "wait"
    OBSERVE = "observe"


class PowerTheory(EngineModel):
    """A9. The player reasoning about how their own power works. The engine rules on it once."""

    power_id: str | None = None
    topic: str = Field(description="A stable key for what it settles, such as 'throw_speed'.")
    claim: str = Field(description="The theory in the player's words.")


class Intent(EngineModel):
    """B5 step 2. What the character tries, read from the player's words."""

    actor_id: str | None = Field(default=None, description="None means the player character.")
    summary: str = Field(default="", description="The action in one sentence.")
    steps: list[IntentStep] = Field(default_factory=list)
    standing: StandingAction | None = None
    theories: list[PowerTheory] = Field(default_factory=list)
    backstory: list[str] = Field(
        default_factory=list, description="N4: claims about the character's own past."
    )
    goals: list[str] = Field(
        default_factory=list, description="N2: goals the player states for their character."
    )
    responds_to: list[str] = Field(
        default_factory=list,
        description=(
            "W16, N1, N2: ids of the open threads or leads in the scene's context that this "
            "action takes up. Code checks each id against the state."
        ),
    )
    outcome_claims: list[str] = Field(
        default_factory=list,
        description="A6: outcomes or others' reactions the player wrote, which play as hopes.",
    )
