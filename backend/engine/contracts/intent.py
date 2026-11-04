"""What the interpret step proposes (B5 step 2): the player's action read as steps, beats, a chain
of cause and effect, proposed facts and durations.

The interpret model fills this from typed or dictated text (V3) and never refuses: an action that
fits no category still becomes a step. Everything here is a proposal. Code checks the beats (R2),
the facts (A2) and the durations (W10) against the state and decides.

This is a model-output schema, so it avoids free-form maps and unions, which structured output
handles poorly.
"""

from enum import StrEnum

from pydantic import Field, field_validator

from engine.base import EngineModel
from engine.state.scene import EncounterKind
from engine.state.sheet import HitMode, PowerAxis


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


class Aim(StrEnum):
    """F4, A2. What a step does to the characters it targets if it works, so code records the
    outcome before anything is narrated and a blocked narration never blocks the deed. A partial
    success does less: a kill that only partly works leaves the target badly wounded. Anything
    else a step changes comes back in the narrator's update. A harmful aim also makes its targets
    the step's opposition, so leaving them out of the facts can't buy a free kill."""

    NONE = "none"
    KILL = "kill"
    WOUND = "wound"
    SUBDUE = "subdue"  # knocked out, pinned or bound

    @property
    def harmful(self) -> bool:
        return self is not Aim.NONE


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


class PlaceHarm(StrEnum):
    """A9, W7. What a link of a chain does to a place, such as a hall that burns down."""

    NONE = "none"
    DAMAGED = "damaged"
    RUINED = "ruined"


class ChainLink(EngineModel):
    """A9. One link in a chain of cause and effect, with the facts it rests on. Code settles each
    link as A2 does, and the chain stops at the first link that fails."""

    text: str = Field(description="'The field keeps out air as well as flames.'")
    rests_on: list[str] = Field(
        default_factory=list,
        description="The facts this link rests on: rule, power, fact or character ids, or words.",
    )
    takes_s: int | None = Field(default=None, ge=0, description="In-world seconds it takes.")
    answers: list[str] = Field(
        default_factory=list,
        description=(
            "What would let the target escape or undo this link, in plain words: 'teleport',"
            " 'breathe without air', 'put out the fire'. Code looks for them on the target's"
            " sheet, which the interpret step may not see, and uses them if they are there."
        ),
    )
    proposed_class: OutcomeClass | None = None
    place_id: str | None = Field(
        default=None, description="A place this link changes, such as the hall that burns."
    )
    place_harm: PlaceHarm = Field(
        default=PlaceHarm.NONE, description="What the link does to that place, if it holds."
    )


class Contact(StrEnum):
    """W10a, A9. How a step touches what it acts on, which decides how it plays in stopped time:
    a strike stays in the user's hand, a throw leaves their reach, and a lift picks something up
    or carries it, so it joins the stop."""

    NONE = "none"
    STRIKE = "strike"  # a fist, a kick, a blade or a club that stays in hand
    THROW = "throw"  # a stone, a knife, an arrow or a bullet that leaves the user's reach
    LIFT = "lift"  # picking up, carrying or moving a thing or a person


class GrowthKind(StrEnum):
    """A4, G19, G25. What a training step works toward."""

    SKILL = "skill"
    TECHNIQUE = "technique"  # a named technique of a style, from a master, a manual or watching
    POWER = "power"  # a new way to use a power the character has, such as a refused idea earned
    BREAKTHROUGH = "breakthrough"  # the next rung of one of the world's ladders (G19)


class Teacher(StrEnum):
    """A4. What the character learns from."""

    SELF = "self"  # their own experiments
    MASTER = "master"
    BOOK = "book"  # a manual, a scroll, a record
    RIVAL = "rival"  # sparring, or a rival's example
    WATCHING = "watching"  # watching someone use it


class PowerGrant(StrEnum):
    """W10a, A9. What a technique found for a time stop lets its user do, which code follows."""

    NONE = "none"
    # Released gradually, a thrown thing merges back into time carrying its motion: throws land
    # at relative speed even where the world settled normal force.
    RELATIVE_SPEED_THROWS = "relative_speed_throws"
    # The user chooses how hard a stopped-time hit lands, from a tap to everything it has.
    CONTROLLED_FORCE = "controlled_force"


class Training(EngineModel):
    """A4, G19, G25. A step spent learning or breaking through. Code judges the gain from the
    character's traits, the effort and time, what they learn from and the world's rules."""

    kind: GrowthKind
    what: str = Field(description="The skill's or technique's name, or the new use in words.")
    effect: str = Field(default="", description="What a new technique does, in plain words.")
    power_id: str | None = Field(default=None, description="The power a new use is for.")
    ladder_id: str | None = Field(default=None, description="The ladder of a breakthrough.")
    teacher: Teacher = Teacher.SELF
    teacher_id: str | None = Field(
        default=None, description="The master's or rival's character id, or the manual's item id."
    )
    invents: bool = Field(default=False, description="Nobody taught it: a technique of their own.")
    grants: PowerGrant = PowerGrant.NONE
    rests_on: list[str] = Field(
        default_factory=list,
        description="What makes it possible: power, item, rule or fact ids, or plain words.",
    )
    against_rule_ids: list[str] = Field(
        default_factory=list, description="World rules it would break, if any (G7)."
    )


class ShowStrength(EngineModel):
    """G20. Hiding one's strength, or revealing it."""

    ladder_id: str
    shown_rung: int | None = Field(
        default=None,
        ge=0,
        description="The rung others may sense, counted from the lowest; None reveals the truth.",
    )


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
    inner: bool = Field(
        default=False,
        description=(
            "G15: only the character's own temperament, fear or pride stands in the way, as in"
            " keeping calm under an insult. It can make the step harder, never take the choice"
            " from the player."
        ),
    )


class IntentStep(EngineModel):
    """One step of what the player does. A chained plan ("I throw the stone, then run for the
    tunnel") has several, resolved in order (R6)."""

    text: str = Field(description="The step in plain words.")
    verb: str = Field(description="Free-form: attack, persuade, search, stop time, flee.")
    method: str = ""
    target_ids: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list, description="Targets in words.")
    aim: Aim = Field(default=Aim.NONE, description="What success does to the targets (F4).")
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
    encounter: EncounterKind | None = Field(
        default=None,
        description=(
            "W10: the encounter this step starts or carries on with someone it faces, if any: a"
            " fight, a chase, a duel of words or a negotiation. Code decides; a harmful aim at"
            " someone is always a fight."
        ),
    )
    contact: Contact = Field(
        default=Contact.NONE, description="W10a: strike, throw or lift, which a time stop follows."
    )
    mass_kg: float | None = Field(
        default=None, gt=0, description="The mass of what is thrown, swung or lifted, in kg."
    )
    range_m: float | None = Field(
        default=None, ge=0, description="How far from the actor it lands or strikes, in meters."
    )
    full_force: bool = Field(
        default=False,
        description="W10a: the player asked for everything a controlled time stop can give.",
    )
    training: Training | None = Field(default=None, description="A4, G19: what the step trains.")
    show_strength: ShowStrength | None = Field(
        default=None, description="G20: hiding or revealing strength."
    )


class StandingAction(StrEnum):
    """S2. Always offered next to the suggestions."""

    WAIT = "wait"
    OBSERVE = "observe"


class TheoryAbout(StrEnum):
    """A9, W10a. The details of a time stop that code rules on itself. Anything else is `other`,
    ruled on from the facts the theory rests on."""

    HIT_FORCE = "hit_force"  # how hard stopped-time hits land
    MOVE_FROZEN = "move_frozen"  # whether frozen things can be picked up and moved
    OTHER = "other"


class EffectScale(StrEnum):
    """A9. How big an effect a theory claims, so code can tell when nothing in the power explains
    it: a flick of a finger doesn't blow up the planet unless the world works at that scale."""

    PERSON = "person"
    BUILDING = "building"
    TOWN = "town"
    CITY = "city"
    REGION = "region"
    WORLD = "world"  # a planet
    STARS = "stars"


class PowerTheory(EngineModel):
    """A9. The player reasoning about how their own power works. The engine rules on it once,
    from the facts it rests on, and never because it would make the character too strong."""

    power_id: str | None = None
    topic: str = Field(description="A stable key for what it settles, such as 'throw_speed'.")
    claim: str = Field(description="The theory in the player's words.")
    about: TheoryAbout = TheoryAbout.OTHER
    claims_hit_mode: HitMode | None = Field(
        default=None, description="For hit_force: the way of landing the player expects."
    )
    rests_on: list[str] = Field(
        default_factory=list,
        description=(
            "What in the power, the sheet or the world explains it: ids or plain words. Empty"
            " when nothing does."
        ),
    )
    scale: EffectScale | None = Field(default=None, description="How big an effect it claims.")
    adds_power: bool = Field(
        default=False, description="It would give an ability the character doesn't have."
    )
    against_rule_ids: list[str] = Field(
        default_factory=list, description="World rules it would break, if any (G7)."
    )


class PastClaim(EngineModel):
    """N4. A fact the player states about their own character's past or inner life, with the
    interpret step's reading of it. Code decides whether it is recorded."""

    text: str
    grants_power: bool = Field(
        default=False,
        description="It would give an ability, an item, a rank or an ally the sheet doesn't hold.",
    )
    against_rule_ids: list[str] = Field(
        default_factory=list, description="World rules it would break (G7)."
    )
    contradicts_ids: list[str] = Field(
        default_factory=list, description="Fact or character ids it contradicts."
    )
    about_others: bool = Field(
        default=False, description="It says how other people feel or react (A6, A7)."
    )


class Intent(EngineModel):
    """B5 step 2. What the character tries, read from the player's words."""

    actor_id: str | None = Field(default=None, description="None means the player character.")
    summary: str = Field(default="", description="The action in one sentence.")
    steps: list[IntentStep] = Field(default_factory=list)
    standing: StandingAction | None = None
    theories: list[PowerTheory] = Field(default_factory=list)
    backstory: list[PastClaim] = Field(
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

    @field_validator("backstory", mode="before")
    @classmethod
    def _plain_claims(cls, value):
        """A claim given as plain words is a claim with nothing flagged."""
        if isinstance(value, list):
            return [{"text": v} if isinstance(v, str) else v for v in value]
        return value
