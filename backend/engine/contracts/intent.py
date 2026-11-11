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
from engine.state.scene import EncounterKind, Terms
from engine.state.sheet import HitMode, PowerAxis, TalentFit


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
    """A2. Code decides the class from the facts. A certain step and one ruled out are settled
    with no throw. A throw decides the rest, and a step whose throw passes fewer than 15 times
    in 100 is a long shot (`engine.resolve.throw`)."""

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
    """A2, A3, G14. How hard a thing is in itself, for an ordinary adult in the same situation:
    average in body and mind, with no training in it. The interpret step judges the task, and
    each word is a level on the one scale (`engine.levels`), which sets the number the
    character's own dice have to reach, so a nimble thief and a clumsy scholar at the same lock
    throw different hands at the same number."""

    TRIVIAL = "trivial"  # anyone manages it: nothing to throw for
    EASY = "easy"  # level 1: most people manage it
    MODERATE = "moderate"  # level 2: a real effort for an average adult
    HARD = "hard"  # level 3: it takes someone skilled
    VERY_HARD = "very_hard"  # level 4: it takes an expert
    EXTREME = "extreme"  # level 5: it takes a master


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
    ref: str = Field(
        description=(
            "The power, item or technique id, a move's name (one made with a power that isn't a"
            " technique on the sheet yet), or the skill or trait name."
        )
    )


class UseSource(StrEnum):
    """R2. Whatever a beat uses has to be the character's own body or powers, something they
    carry, something the scene holds, or something this turn made canon. `new` is something the
    scene hasn't established. Whatever the source, the interpret step's judgement of whether it
    is there is in `plausibility`, and code checks every source against its own records."""

    BODY = "body"
    POWER = "power"
    CARRIED = "carried"
    SCENE = "scene"
    CANON = "canon"  # made canon by an earlier beat this turn
    NEW = "new"


class Plausibility(StrEnum):
    """R2. Whether something a beat uses is there. Plausible is what a place of that kind would
    ordinarily hold, or what the scene showed: it is there with no roll, and so is anything left
    unjudged (decided 2026-11-10, Miki). Uncertain is kept for what might well not be there and
    matters, because it is hidden, rare, valuable or decisive: it is rolled. Absent turns the
    beat into an empty search."""

    PLAUSIBLE = "plausible"
    UNCERTAIN = "uncertain"
    ABSENT = "absent"


def _plausibility_required(schema: dict[str, Any]) -> None:
    """R2. The interpret model must always judge whether a thing is there, since Gemini leaves
    out what a schema doesn't require as often as not (see `StepFacts`), and a use with no
    judgement is one code can only guess at. Code may still leave it out, and then the thing is
    there."""
    schema["required"] = list(dict.fromkeys([*schema.get("required", []), "plausibility"]))


class BeatUse(EngineModel):
    model_config = ConfigDict(json_schema_extra=_plausibility_required)

    source: UseSource
    thing: str = Field(description="What is used, in plain words: 'a stone the size of an egg'.")
    ref: str | None = Field(default=None, description="The power or item id, when there is one.")
    plausibility: Plausibility | None = Field(
        default=None,
        description=(
            "Whether it is there. plausible: their own, or what a place like this would"
            " ordinarily hold, or what the scene showed. uncertain: only what might well not be"
            " there and matters (hidden, rare, valuable or decisive), so code rolls. absent: the"
            " place can't hold it."
        ),
    )


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
        description="As `StepFacts.crowd`, kept for the turns read before it.",
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


def _case_required(schema: dict[str, Any]) -> None:
    """A4. A case the interpret model makes always names the thing and gives its reason, which
    the player reads in the ruling. Code may still leave them out."""
    must = ["what", "reason"]
    schema["required"] = list(dict.fromkeys([*must, *schema.get("required", [])]))


class TalentCase(EngineModel):
    """A4. Whether one talent of the character's covers one thing a step sets out to learn,
    with the reason. The interpret step proposes it, weighing the player's own case, the first
    time the thing is learned; code records it once and it never flips."""

    model_config = ConfigDict(json_schema_extra=_case_required)

    what: str = Field(
        default="", description="The technique, skill or power being learned, by its name."
    )
    talent_id: str = Field(description="The talent's id on PLAYER CHARACTER.")
    fit: TalentFit = Field(
        description=(
            "inside: the thing is what the talent is about. related: the talent helps but"
            " doesn't hand it over. outside: it has nothing to do with it."
        )
    )
    reason: str = Field(default="", description="Why, in one sentence, in LANGUAGE.")


class Bridge(EngineModel):
    """A4. A step of real work that connects a talent of the character's to something a ruling
    left outside it or only related, such as deriving the formula behind a blade's shape. The
    interpret step says what it reaches and what new thing it rests on; code throws for it with
    the skill the step draws on, and keeps a bridge that held on the sheet."""

    talent_id: str = Field(description="The talent it starts from, by its id.")
    what: str = Field(description="The technique, skill or power it reaches, by its name.")
    rests_on: str = Field(
        description=(
            "The new thing it rests on, in a few words: a formula they derive, a teacher's"
            " notes, a blade to measure. Never an argument already made."
        )
    )
    heart: bool = Field(
        default=False,
        description="True when it covers the heart of the thing, false for one side of it.",
    )
    reason: str = Field(default="", description="Why it reaches that far, in one sentence.")


class ShowStrength(EngineModel):
    """G20. Hiding one's strength, or revealing it."""

    ladder_id: str
    shown_rung: int | None = Field(
        default=None,
        ge=0,
        description="The rung others may sense, counted from the lowest; None reveals the truth.",
    )


class EdgeSource(StrEnum):
    """A3. Where an advantage comes from, so code can check that it holds before it gives a
    green die."""

    STEP = "step"  # an earlier step of this same action that worked
    RECORD = "record"  # something on record: a fact, an item they carry, someone at their side
    SCENE = "scene"  # what the scene's own words show


class Edge(EngineModel):
    """A3. One real advantage the character has in a step, and where it comes from. Code checks
    the source, and only an advantage that holds adds a green die, two at most."""

    text: str = Field(description="The advantage in a few plain words: 'from behind'.")
    source: EdgeSource = EdgeSource.SCENE
    ref: str = Field(
        default="",
        description=(
            "step: the number of the earlier step, counted from 1. record: the id of the fact,"
            " the item or the character. scene: the few words of LAST SCENE or SCENE that show"
            " it, exactly as written there."
        ),
    )


def _facts_required(schema: dict[str, Any]) -> None:
    """A2, A3, W1, W2. The interpret model must always judge how hard a step is, whether it
    meets what stands in the way head-on, whether a fight is a bout both sides agreed to (null
    when it isn't) and whether a crowd is around to see the step, since Gemini leaves out what
    a schema doesn't require as often as not: a step with no judgement fell back to a guess
    whoever the character was, a lesson whose first blow carried no terms began as an attack,
    and a killing in a full square with no word of the crowd would have no witness. Code may
    still leave them out. So is whether a blow goes beyond a bout's terms: left to the model,
    two of three blows meant to blind a teacher in a lesson were read as part of the lesson
    (2026-11-11). And whether the step asks what people are saying (W2): a neighbour asked
    for the village's talk told of a wolf and an empty cart, while the village was talking of
    a killing (2026-11-11)."""
    must = ["challenge", "head_on", "terms", "breaks_terms", "crowd", "asks_talk"]
    schema["required"] = list(dict.fromkeys([*schema.get("required", []), *must]))


class StepFacts(EngineModel):
    """A2, A8. The facts the interpret step proposes for one step. Code checks them against the
    state wherever the state can tell, and settles the step itself: the model never proposes a
    class, a number or a result."""

    model_config = ConfigDict(json_schema_extra=_facts_required)

    opposition_ids: list[str] = Field(default_factory=list)
    opposition: str = Field(default="", description="What stands in the way, in words.")
    can_respond: bool | None = Field(
        default=None, description="Whether the opposition can respond at all; None if none."
    )
    why_not: str = Field(default="", description="Frozen, asleep, bound or unaware.")
    answers_with: str = Field(
        default="",
        description=(
            "A3: what of theirs answers this step, in a word or two: a skill of theirs or an"
            " attribute, such as 'swordplay', 'speed' or 'willpower'. Code reads their level at"
            " it from their sheet. Empty when nobody answers."
        ),
    )
    head_on: bool | None = Field(
        default=None,
        description=(
            "A3, G18: whether the step meets their power head-on (a clash, a block, a contest of"
            " strength, a blow at their body) or goes around it (a feint, a bait, slipping past,"
            " a word). Their rungs above the character count only head-on. None when nobody"
            " answers."
        ),
    )
    means: MeansVerdict | None = None
    world_allows: bool = Field(default=True, description="G8: whether the world allows it.")
    against_rule_ids: list[str] = Field(default_factory=list)
    edges: list[Edge] = Field(
        default_factory=list,
        description=(
            "A3: each real advantage the character has here, with where it comes from: an"
            " earlier step of this action that worked, something on record, or what the scene's"
            " own words show. Code checks each one, and one that holds adds a die."
        ),
    )
    hindrances: list[str] = Field(
        default_factory=list,
        description=(
            "What in the situation works against them: position, ground, light, missing tools."
            " Never their own wounds, health or tiredness, and never how many stand against"
            " them: code weighs those (N6, A8)."
        ),
    )
    challenge: Challenge | None = Field(
        default=None,
        description=(
            "A2, A3: how hard the step is in itself for an ordinary adult, average in body and"
            " mind and untrained in it, in this situation: trivial, easy, moderate, hard,"
            " very_hard or extreme. Judge the thing, never this character and never the people"
            " who answer: code reads their sheets."
        ),
    )
    up_against: str = Field(
        default="",
        description=(
            "A8: what this step is up against, in one short sentence the player reads before"
            " the dice, in LANGUAGE: who or what, and what makes it hard or easy. No numbers."
        ),
    )
    miss_costs: str = Field(
        default="",
        description=(
            "N6: when those fighting the character mean to kill, or a danger can, what failing"
            " to defend costs, in one short sentence in LANGUAGE. Empty otherwise."
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
    terms: Terms | None = Field(
        default=None,
        description=(
            "W1: when the fight is a bout both sides agreed to, the worst both accepted: no_harm"
            " (sparring, a lesson, a test of skill, a play fight), wounds (first blood, a duel or"
            " a trial that accepts wounds) or death (to the death). Given on every step that"
            " fights in the bout, for as long as it goes on as agreed. Null for any other fight"
            " and for a step that fights nobody."
        ),
    )
    breaks_terms: bool = Field(
        default=False,
        description=(
            "W1: the character means to go beyond the terms of the bout they are in: a blow to"
            " maim or kill in a friendly bout, or one struck after the other yielded. Then it is"
            " an attack."
        ),
    )
    crowd: bool = Field(
        default=False,
        description="W2: people the scene doesn't name are around and would see this step done.",
    )
    asks_talk: bool = Field(
        default=False,
        description=(
            "W2: the step asks or listens for what people are saying: the news, the rumors,"
            " the talk of the place. Code then offers the scene what the place is saying."
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

    @field_validator("edges", mode="before")
    @classmethod
    def _plain_edges(cls, value):
        """An advantage given as plain words is one the scene's own words have to show."""
        if isinstance(value, list):
            return [
                {"text": v, "source": EdgeSource.SCENE.value, "ref": v} if isinstance(v, str) else v
                for v in value
            ]
        return value


def _step_required(schema: dict[str, Any]) -> None:
    """A2, G14, A4. Every step the interpret model writes carries its facts, so its challenge
    is judged, what it uses from the sheet, so the character counts, and its answer on talent:
    how the character's talents stand to what it learns, an empty list when there is nothing to
    rule on, and the bridge it builds, null on any other step. Gemini leaves out what a schema
    doesn't require as often as not: without `uses` a nimble climber rolled like anyone, and
    without these two no talent was ruled on at all in the first live run (2026-11-10). Code
    may still leave them out. `destination` is asked for the same way (W10): a trip the model
    doesn't name is a trip code can't time. So is `show_strength` (G20), null on any step that
    neither hides strength nor shows it: left to the model, "I hide my cultivation" hid nothing
    in the first live story about it (2026-11-11), so nothing was there to reveal. And so are
    `target_ids` and `aim` (V3, F4), an empty list and none for a step that is aimed at nobody:
    "I cut Han's throat" was read as a killing with no target (2026-11-11), so nobody died on
    record. Where a reading still names nobody, `graph.turn.check` finds who the words point
    at."""
    must = [
        "target_ids",
        "aim",
        "facts",
        "uses",
        "talent_cases",
        "bridge",
        "destination",
        "show_strength",
    ]
    schema["required"] = list(dict.fromkeys([*schema.get("required", []), *must]))


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
    destination: str = Field(
        default="",
        description=(
            "W10: when the step takes the character to another place than SCENE's, that place:"
            " its id when SCENE or KNOWN lists it, else its name in a few words. Empty for a"
            " step that stays where they are. Code takes the trip's time from the map where"
            " its routes cover the way."
        ),
    )
    proposed_duration_s: int = Field(ge=0, description="World seconds it should take (W10).")
    until: str | None = Field(
        default=None,
        description=(
            "W10: when the step lasts until a time of day ('until nightfall', 'sleep till"
            " dawn'), that time on the world's 24-hour clock, as HH:MM. Code counts the seconds"
            " to it in place of proposed_duration_s."
        ),
    )
    timed: bool = Field(
        default=False,
        description=(
            "W10: the player says how long the step lasts ('for two hours', 'three days'), or"
            " only that it lasts a while ('walk a bit'), and proposed_duration_s is that time."
            " A trip timed this way stops when the time is up, on the way when the way is"
            " longer."
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
    talent_cases: list[TalentCase] = Field(
        default_factory=list,
        description=(
            "A4: always given. Empty unless TALENTS is given and the step learns, trains,"
            " practises or uses something TALENTS.ruled doesn't name yet: then one entry for"
            " each talent in TALENTS.talents, saying how it stands to that thing."
        ),
    )
    bridge: Bridge | None = Field(
        default=None,
        description=(
            "A4: always given. null unless TALENTS is given and the whole step is work that"
            " connects one of those talents to a thing it doesn't fully cover."
        ),
    )
    show_strength: ShowStrength | None = Field(
        default=None,
        description=(
            "G20: always given. null unless the step hides how strong the character is, or"
            " lets it show again."
        ),
    )

    @field_validator("bridge", mode="before")
    @classmethod
    def _no_empty_bridge(cls, value):
        """A form that must always answer sometimes answers with an empty bridge where it
        means none: one that names no talent, reaches nothing and rests on nothing is none."""
        if isinstance(value, dict) and not any(
            str(value.get(key) or "").strip() for key in ("talent_id", "what", "rests_on")
        ):
            return None
        return value

    @field_validator("show_strength", mode="before")
    @classmethod
    def _no_empty_show(cls, value):
        """A form that must always answer sometimes answers with an empty one where it means
        none: a show of strength that names no ladder is none."""
        if isinstance(value, dict) and not str(value.get("ladder_id") or "").strip():
            return None
        return value


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
        default_factory=list,
        description="N2: lasting aims the player states for their character, not already held.",
    )
    dropped_goals: list[str] = Field(
        default_factory=list,
        description=(
            "N2: ids of the character's goals that the player gives up or replaces in these "
            "words. Code checks each id against the state."
        ),
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
