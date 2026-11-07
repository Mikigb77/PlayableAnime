"""What the interpret step proposes (B5 step 2): the player's action read as steps, beats, a chain
of cause and effect, proposed facts and durations.

The interpret model fills this from typed or dictated text (V3) and never refuses: an action that
fits no category still becomes a step. Everything here is a proposal. Code checks the beats (R2),
the facts (A2) and the durations (W10) against the state and decides.

This is a model-output schema, so it avoids free-form maps and unions, which structured output
handles poorly.
"""

from enum import StrEnum
from typing import Any

from pydantic import ConfigDict, Field, field_validator

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


class Challenge(StrEnum):
    """A2, A3, G14. How hard a step is in itself for an ordinary person: average in body and
    mind, with no training in it, in the same situation and against the same things in the way.
    The interpret step judges the task; code weighs the character's own sheet against it
    (`engine.resolve.capability`), so a nimble thief and a clumsy scholar stamping out the same
    lantern get different odds."""

    TRIVIAL = "trivial"  # anyone manages it
    EASY = "easy"  # most people manage it
    MODERATE = "moderate"  # a real effort that often works
    HARD = "hard"  # it usually fails
    VERY_HARD = "very_hard"  # it rarely works
    EXTREME = "extreme"  # almost nobody manages it


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


class ExchangeKind(StrEnum):
    """C10. Which way something moves in a step, between the character and someone else."""

    GIVE = "give"  # hands it over, pays, sells, lends or bribes: to `with_id`
    SPEND = "spend"  # used up, eaten, drunk, burned, broken, thrown away or left behind
    TAKE = "take"  # takes it from `with_id`: steals, snatches, accepts, buys


class Exchange(EngineModel):
    """C10, R2. Something the step moves if it works: a payment, a gift, a bribe, a theft, or
    something used up. Code checks that the character holds what they give or spend before the
    step is tried, and records the move itself, so the narrator can't contradict it. What
    someone else already holds is never given again: letting them keep it moves nothing."""

    kind: ExchangeKind
    thing: str = Field(description="What moves, in plain words: '12 copper coins', 'the dagger'.")
    money: bool = Field(default=False, description="It is money, counted in amount.")
    amount: int = Field(default=1, description="How many, or how much money; 0 for all of it.")
    item_id: str | None = Field(default=None, description="The item's id, when it has one.")
    with_id: str | None = Field(
        default=None, description="Who gets it, or whom it is taken from, by id. Empty to spend."
    )


class Stranger(EngineModel):
    """F1, W1, W2. Someone a harmful step aims at whom the scene hasn't named: "a random guy",
    "the nearest passer-by". Code makes them real when the place holds them, with strength
    the world rolls for them, so the deed has a victim, witnesses and consequences."""

    who: str = Field(description="Who they are, in a few words: 'a dockhand hauling crates'.")
    plausibility: Plausibility = Field(
        description="Whether the place plausibly holds someone like that right now."
    )
    crowd: bool = Field(
        default=False,
        description="Others are around to see it, such as a busy street or a full tavern.",
    )


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


def _challenge_required(schema: dict[str, Any]) -> None:
    """A2, A3. The interpret model must always judge how hard a step is, since Gemini leaves out
    what a schema doesn't require as often as not, and a step with no judgement fell back to even
    odds whoever the character was. Code may still leave it out."""
    schema["required"] = list(dict.fromkeys([*schema.get("required", []), "challenge"]))


class StepFacts(EngineModel):
    """A2, A8. The facts the interpret step proposes for one step. Code checks them against the
    state wherever the state can tell."""

    model_config = ConfigDict(json_schema_extra=_challenge_required)

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
    hindrances: list[str] = Field(
        default_factory=list,
        description=(
            "What in the situation works against them: position, ground, light, numbers, missing"
            " tools. Never their own wounds, health or tiredness: code weighs those (N6, A8)."
        ),
    )
    proposed_class: OutcomeClass | None = None
    challenge: Challenge | None = Field(
        default=None,
        description=(
            "A2, A3: how hard the step is for an ordinary person, average in body and mind and"
            " untrained in it, in this situation and against what stands in the way: trivial,"
            " easy, moderate, hard, very_hard or extreme. Judge the task, never this character:"
            " code weighs their sheet."
        ),
    )
    inner: bool = Field(
        default=False,
        description=(
            "G15: only the character's own temperament, fear or pride stands in the way, as in"
            " keeping calm under an insult. It can make the step harder, never take the choice"
            " from the player."
        ),
    )
    foes_mean: Aim | None = Field(
        default=None,
        description=(
            "N6: in a fight, what those fighting the character are out to do to them: kill,"
            " wound, subdue (a sparring partner holding back, guards taking them alive), or none"
            " when they won't strike back. None when there is no fight or it follows the"
            " character's own aim."
        ),
    )
    danger: str = Field(
        default="",
        description=(
            "N6: what can hurt the character in this step however it goes, that no one in the"
            " scene embodies: a long drop, fire, a collapsing roof, a stampede, a pack of wolves"
            " SCENE doesn't list. Empty when nothing does."
        ),
    )
    danger_class: OutcomeClass | None = Field(
        default=None,
        description=(
            "N6: how surely the danger hurts an ordinary person: certain, contested, long_shot,"
            " or ruled_out when it can't. Code adjusts it for the character's body."
        ),
    )
    danger_harm: Aim | None = Field(
        default=None, description="N6: what the danger does when it hurts: kill or wound."
    )


def _step_required(schema: dict[str, Any]) -> None:
    """A2, G14. Every step the interpret model writes carries its facts, so its challenge is
    judged, and what it uses from the sheet, so the character counts: Gemini left `uses` out as
    often as not, and a nimble climber then rolled like anyone."""
    schema["required"] = list(dict.fromkeys([*schema.get("required", []), "facts", "uses"]))


class IntentStep(EngineModel):
    """One step of what the player does. A chained plan ("I throw the stone, then run for the
    tunnel") has several, resolved in order (R6)."""

    model_config = ConfigDict(json_schema_extra=_step_required)

    text: str = Field(description="The step in plain words.")
    verb: str = Field(description="Free-form: attack, persuade, search, stop time, flee.")
    method: str = ""
    target_ids: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list, description="Targets in words.")
    aim: Aim = Field(default=Aim.NONE, description="What success does to the targets (F4).")
    stranger: Stranger | None = Field(
        default=None,
        description=(
            "A harmful aim at someone SCENE doesn't list, when nobody there fits: who they are"
            " and whether the place holds them now (F1, W1)."
        ),
    )
    axis: PowerAxis | None = None
    uses: list[SheetUse] = Field(
        default_factory=list,
        description=(
            "G14: every part of the character's sheet the step draws on, so code can weigh it:"
            " the attributes it tests by name (strength, speed, toughness, wits, knowledge,"
            " willpower, charm, nerve, bearing), each skill and trait that helps or gets in the"
            " way by name, and powers, techniques and items by id."
        ),
    )
    beats: list[Beat] = Field(default_factory=list)
    exchanges: list[Exchange] = Field(
        default_factory=list,
        description=(
            "C10: what the step pays, gives, spends, uses up or takes from someone if it works,"
            " money included. Nothing for what someone already holds."
        ),
    )
    chain: list[ChainLink] = Field(default_factory=list)
    facts: StepFacts = Field(default_factory=StepFacts)
    lines: list[str] = Field(
        default_factory=list,
        description="R7: the player's own words for the character, cleaned of dictation filler.",
    )
    gist: str = Field(default="", description="R7: what to say, when the player gave only gist.")
    kind: ActionKind
    proposed_duration_s: int = Field(ge=0, description="World seconds it should take (W10).")
    until: str | None = Field(
        default=None,
        description=(
            "W10: when the step lasts until a time of day ('until nightfall', 'sleep till"
            " dawn'), that time on the world's 24-hour clock, as HH:MM. Code counts the seconds"
            " to it in place of proposed_duration_s."
        ),
    )
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


def _model_must_answer(schema: dict[str, Any]) -> None:
    """B5. The fields the interpret model must always give, though code may leave them out.
    Gemini answers only what a schema requires as often as not, and an intent with no `steps`
    played every action as a five-second nothing (W10): on 2026-11-04 most turns came back that
    way. An empty list still says the action is only a standing one."""
    schema["required"] = list(dict.fromkeys([*schema.get("required", []), "summary", "steps"]))


class Intent(EngineModel):
    """B5 step 2. What the character tries, read from the player's words."""

    model_config = ConfigDict(json_schema_extra=_model_must_answer)

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
