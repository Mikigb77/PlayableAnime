"""What the drafter model proposes (G1, G2, S1): a compact world and a character that code turns
into a `WorldState` (`graph.drafting.assemble`).

The shapes are built for structured output: lists with ids instead of maps, durations in hours,
ladder rungs by name, and plain words everywhere. The model proposes; code decides the rest: clean
ids, tiers, clock times, who knows what, and the rules a world can't break (G7, G8, G18, G22).

Nothing here is bounded in the schema itself. A model that writes a list one item too long or a
number out of range would otherwise fail validation and cost a retry, so code trims and clamps
instead, and the descriptions tell the model the limits.
"""

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from engine.state import (
    CalendarStyle,
    ConnectionKind,
    CostKind,
    GiftStrength,
    ItemKind,
    PowerAxis,
    Prevalence,
    Resurrection,
    RuleTopic,
    SkillLevel,
    ThreadKind,
    TimeEffect,
    TraitKind,
    Zeal,
)

PLAYER_ID = "player"
"""The player character's id, in every proposal and every drafted state."""


class Proposal(BaseModel):
    model_config = ConfigDict(extra="ignore")


# The world (G1, G6, G7, G10, G18, G23, G24, E2, N1, N7).


class ExtraordinaryP(Proposal):
    id: str = Field(description="A short id, such as 'qi', 'aura' or 'vampires'.")
    kind: str = Field(description="What it is, in plain words: 'qi cultivation', 'vampires'.")
    prevalence: Prevalence = Field(
        description="none (it doesn't exist), hidden (real but secret), rare, or common."
    )
    reach: str = Field(default="", description="How far it can go, in plain words (A4).")


class RuleP(Proposal):
    id: str = Field(description="A short id, such as 'no-supernatural' or 'qi-exists'.")
    text: str = Field(description="The rule in one plain sentence that the player reads.")
    fixed: bool = Field(
        description="True for a rule that holds for the whole story. False for an open rule "
        "that a discovery made in the story could change. Whether something extraordinary "
        "exists at all is usually fixed; how far it can go is usually open."
    )
    topic: RuleTopic = RuleTopic.OTHER
    about: list[str] = Field(
        default_factory=list, description="Ids of the extraordinary kinds this rule is about."
    )


class PeopleP(Proposal):
    id: str
    name: str
    description: str = ""
    lifespan_years: int | None = None
    gifts: list[str] = Field(default_factory=list)
    culture: str = ""
    relations: list[str] = Field(
        default_factory=list, description="Old wars, alliances, trade and prejudice (G23)."
    )
    path: str = Field(default="", description="Its own path on the power ladder, if any.")


class CreatureP(Proposal):
    id: str
    name: str
    description: str = ""
    rung: str = Field(default="", description="The ladder rung it matches, by name, if any.")
    habitat: str = ""
    worth: str = Field(default="", description="Cores, hides, blood or bones (G24).")
    can_be_tamed: bool = False


class RungP(Proposal):
    name: str
    description: str = ""


class LadderP(Proposal):
    id: str
    name: str = Field(description="Such as 'cultivation realms' or 'aura ranks'.")
    axis: PowerAxis = PowerAxis.MIGHT
    rungs: list[RungP] = Field(description="Lowest rung first, three to ten of them.")
    sensing: bool = Field(
        default=False, description="Whether people sense strength up to their own rung (G20)."
    )
    standing_follows: bool = Field(
        default=True, description="Whether a higher rung earns a senior's respect (G18)."
    )


class MonthP(Proposal):
    name: str
    days: int = 30


class CalendarP(Proposal):
    style: CalendarStyle = Field(
        default=CalendarStyle.DAY_COUNT,
        description="gregorian for our own calendar, day_count ('Day 3'), or custom months.",
    )
    clock_time: bool = Field(
        default=False,
        description="True where people tell the time with clocks (23:10), false for "
        "dawn, midday, dusk.",
    )
    epoch: str = Field(
        default="",
        description="Gregorian only: the moment the story opens, as YYYY-MM-DDTHH:MM.",
    )
    start_hour: int = Field(default=8, description="The hour of day the story opens, 0 to 23.")
    months: list[MonthP] = Field(default_factory=list, description="Custom calendars only.")
    start_year: int = 1
    start_month: int = 1
    start_day: int = 1
    era: str = Field(default="", description="Custom only: the era name after the year.")


class TravelP(Proposal):
    description: str = ""
    instant_messages: bool = Field(
        default=False, description="Phones or the like: a witness can call within seconds."
    )


class MedicineP(Proposal):
    healing: str = ""
    resurrection: Resurrection = Resurrection.NONE
    resurrection_means: str = ""


class LawP(Proposal):
    id: str
    text: str
    enforcer: str = ""
    enforcer_faction_id: str = ""
    zeal: Zeal = Zeal.MEDIUM
    corruptible: bool = False


class RouteP(Proposal):
    to_id: str
    travel_hours: float = Field(description="Rough travel time, in hours.")
    mode: str = ""


class PlaceP(Proposal):
    id: str
    name: str
    kind: str = Field(default="", description="region, city, village, building, room, wilds")
    description: str = ""
    parent_id: str = ""
    controller_id: str = Field(default="", description="The faction that controls it, if any.")
    mood: str = ""
    known_to_player: bool = True
    routes: list[RouteP] = Field(default_factory=list)


class FactionRelationP(Proposal):
    faction_id: str
    stance: int = Field(default=0, description="-100 open war to 100 sworn allies.")


class FactionP(Proposal):
    id: str
    name: str
    kind: str = Field(default="", description="family, crew, sect, court, kingdom, fleet...")
    description: str = Field(
        default="", description="How it looks from outside. Never its secrets or plans."
    )
    parent_id: str = Field(default="", description="The larger faction it sits inside (G10).")
    leader_ids: list[str] = Field(default_factory=list)
    goal: str = Field(default="", description="What it wants now. Hidden from the player.")
    methods: str = Field(default="", description="How it goes about it. Hidden.")
    strength: str = Field(default="", description="What it really has to answer with (W5).")
    relations: list[FactionRelationP] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    known_to_player: bool = True


class SkillP(Proposal):
    name: str
    level: SkillLevel = SkillLevel.FAIR
    notes: str = ""


class TraitP(Proposal):
    name: str
    kind: TraitKind = TraitKind.QUIRK
    description: str = ""


class CostP(Proposal):
    kind: CostKind = CostKind.OTHER
    text: str


class TimeP(Proposal):
    effect: TimeEffect
    lasts_seconds: int | None = Field(
        default=None, description="Lived seconds per use. Leave out for the default."
    )
    recharge_seconds: int | None = Field(
        default=None, description="Lived seconds to recharge. Leave out for the default."
    )
    rate: float | None = Field(
        default=None, description="Haste or slow only: lived seconds per world second."
    )


class PowerP(Proposal):
    id: str
    name: str
    description: str = ""
    kind_id: str = Field(
        description="The id of the extraordinary kind this power comes from. A power must "
        "come from a kind the world has (G8)."
    )
    gift: bool = Field(
        default=False,
        description="True for the character's special gift (G22), false for ordinary powers "
        "anyone of their kind could learn.",
    )
    strength: GiftStrength | None = Field(
        default=None, description="Gifts only: small, rare or overpowered."
    )
    limits: list[str] = Field(default_factory=list)
    costs: list[CostP] = Field(default_factory=list)
    secret: bool = False
    time: TimeP | None = Field(default=None, description="Only for powers over time (W10a).")


class TechniqueP(Proposal):
    name: str
    style: str = ""
    effect: str = ""
    cost: str = ""
    requirements: str = ""


class TemperamentP(Proposal):
    traits: list[str] = Field(default_factory=list, description="hot-headed, loyal, cautious")
    values: list[str] = Field(default_factory=list)
    loves: list[str] = Field(default_factory=list)
    fears: list[str] = Field(default_factory=list)
    wants: list[str] = Field(default_factory=list)
    voice: str = Field(default="", description="How they talk.")


class MembershipP(Proposal):
    faction_id: str
    rank: str = ""
    loyalty: int = Field(default=50, description="0 to 100.")


class LadderPositionP(Proposal):
    ladder_id: str
    rung: str = Field(description="The rung's name, exactly as in the ladder.")
    stage: str = Field(default="", description="Finer steps in the world's words: 'third stage'.")


class AxesP(Proposal):
    """A8 tiers: 1 is an ordinary person, 0 is nothing at all, and higher is stronger, up to 20.
    A ladder rung sets the tier of its own axis."""

    might: int = 1
    influence: int = 1
    wealth: int = 1
    knowledge: int = 1
    stealth: int = 1


class AttitudeP(Proposal):
    affinity: int = Field(default=0, description="-100 hatred to 100 devotion.")
    fear: int = Field(default=0, description="0 to 100.")
    trust: int = Field(default=0, description="-100 to 100.")
    shown_affinity: int | None = Field(
        default=None, description="How warm they act, when it differs from how they feel."
    )


class AgendaP(Proposal):
    goal: str
    method: str = ""
    secret: str = ""
    clock_id: str = ""


class AttributesP(Proposal):
    """0 none, 1 feeble, 3 an average person, 5 the peak of what a person can be, and 6 to 10
    beyond human, only where the world allows it."""

    strength: int = 3
    speed: int = 3
    toughness: int = 3
    wits: int = 3
    knowledge: int = 3
    willpower: int = 3
    charm: int = 3
    nerve: int = 3
    bearing: int = 3


PlayerKnows = Literal["met", "heard_of", "unknown"]


class NpcP(Proposal):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str = Field(
        default="", description="How they come across to anyone who meets them. No secrets."
    )
    appearance: str = Field(default="", description="For portraits.")
    age: int | None = Field(default=None, description="In years. Every adult needs one.")
    people_id: str = ""
    location_id: str = ""
    memberships: list[MembershipP] = Field(default_factory=list)
    parent_ids: list[str] = Field(
        default_factory=list,
        description="N6: their mother and father among the key characters, by id, or the "
        "player character's id for the player character's own child. Two at most. Only family "
        "the player character knows of when they are part of it; a hidden parentage is a secret.",
    )
    temperament: TemperamentP = Field(default_factory=TemperamentP)
    attributes: AttributesP = Field(default_factory=AttributesP)
    skills: list[SkillP] = Field(default_factory=list)
    traits: list[TraitP] = Field(default_factory=list)
    powers: list[PowerP] = Field(default_factory=list)
    techniques: list[TechniqueP] = Field(default_factory=list)
    ladders: list[LadderPositionP] = Field(default_factory=list)
    axes: AxesP = Field(default_factory=AxesP)
    attitude_to_player: AttitudeP = Field(default_factory=AttitudeP)
    agenda: AgendaP | None = Field(default=None, description="Hidden from the player.")
    secrets: list[str] = Field(default_factory=list)
    player_knows: PlayerKnows = Field(
        default="met",
        description="Whether the player character has met them, only heard of "
        "them, or doesn't know they exist.",
    )


class ClockP(Proposal):
    id: str
    name: str = Field(description="Such as 'The council picks the next boss'.")
    steps: list[str] = Field(description="What happens at each step, two to six of them.")
    step_every_hours: float | None = Field(
        default=None, description="In-world hours per step when time alone advances it."
    )
    owner_id: str = ""
    thread_id: str = ""
    known_to_player: bool = True


class ThreadP(Proposal):
    id: str
    title: str
    kind: ThreadKind
    stakes: str = ""
    involved_ids: list[str] = Field(default_factory=list)
    clock_id: str = ""
    known_to_player: bool = True


class MysteryP(Proposal):
    id: str
    question: str = Field(description="The question as the player character would ask it.")
    answer: str = Field(description="The truth, decided now so investigations stay fair (N7).")
    clues: list[str] = Field(default_factory=list)
    thread_id: str = ""
    known_to_player: bool = Field(
        default=True, description="Whether the player character already knows to ask it."
    )


class OpeningP(Proposal):
    place_id: str = ""
    present_ids: list[str] = Field(default_factory=list)
    positions: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)
    situation: str = Field(
        default="", description="The moment the story opens on, in a sentence (N5)."
    )


class WorldProposal(Proposal):
    title: str = Field(description="The story's title, a few words.")
    genre: str = Field(description="In a few words: 'grounded crime', 'cultivation'.")
    tone: str = Field(description="The narration's voice: noir, wonder, dread...")
    era: str = Field(
        description="Where and when, with its technology, in one line: 'Naples, 1974: pistols, "
        "cars and telephones'."
    )
    extraordinary: list[ExtraordinaryP] = Field(
        default_factory=list,
        description="Every kind of extraordinary thing, with how common it is. A grounded world "
        "lists one kind with prevalence none.",
    )
    rules: list[RuleP] = Field(default_factory=list, description="Two to eight rules.")
    dropped_rule_ids: list[str] = Field(
        default_factory=list,
        description="Revisions only: ids of fixed rules the player asked to remove or change.",
    )
    peoples: list[PeopleP] = Field(default_factory=list)
    creatures: list[CreatureP] = Field(default_factory=list)
    nature: list[str] = Field(
        default_factory=list, description="Only where nature works differently from ours (A9)."
    )
    ladders: list[LadderP] = Field(default_factory=list, description="Power ladders, if any.")
    calendar: CalendarP = Field(default_factory=CalendarP)
    travel: TravelP = Field(default_factory=TravelP)
    medicine: MedicineP = Field(default_factory=MedicineP)
    laws: list[LawP] = Field(default_factory=list)
    norms: list[str] = Field(
        default_factory=list, description="What the world finds monstrous or normal."
    )
    places: list[PlaceP] = Field(default_factory=list, description="Two to ten places.")
    factions: list[FactionP] = Field(default_factory=list, description="At most eight.")
    npcs: list[NpcP] = Field(default_factory=list, description="Two to eight key characters.")
    clocks: list[ClockP] = Field(default_factory=list, description="One to four first clocks.")
    threads: list[ThreadP] = Field(default_factory=list)
    mysteries: list[MysteryP] = Field(default_factory=list)
    known_facts: list[str] = Field(
        default_factory=list, description="What the player character knows at the start."
    )
    opening: OpeningP = Field(default_factory=OpeningP)
    summary: str = Field(default="", description="Two or three sentences: the situation.")


# A change to the world (G1): only what it touches.

# The world's lists whose records have ids, which a change adds to, changes or removes from.
WorldSection = Literal[
    "extraordinary",
    "rules",
    "peoples",
    "creatures",
    "ladders",
    "laws",
    "places",
    "factions",
    "npcs",
    "clocks",
    "threads",
    "mysteries",
]
WORLD_SECTIONS: tuple[WorldSection, ...] = get_args(WorldSection)


class RemovalP(Proposal):
    # The schema lists the lists, and Gemini keeps to them when it takes the schema. Validation
    # takes any text all the same: a schema sent in the prompt isn't enforced, and a list named a
    # little off ("place") shouldn't fail the whole change. Code reads it (`chain.apply_change`).
    section: str = Field(
        description="The list the record is in.", json_schema_extra={"enum": list(WORLD_SECTIONS)}
    )
    id: str


# Code merges a change into the world (`graph.drafting.chain.apply_change`), so the model never
# copies the whole world back: on 2026-11-04 that ran past the drafter's output limit on a real
# draft, twice per request, and every change failed.
class WorldChange(Proposal):
    """A change to the world: only what it touches. Everything left out stays exactly as it is."""

    title: str = Field(default="", description="Only if the change renames the story.")
    genre: str = Field(default="", description="Only if the change alters the genre.")
    tone: str = Field(default="", description="Only if the change alters the tone.")
    era: str = Field(default="", description="Only if the change alters the era.")
    summary: str = Field(default="", description="Only if the change alters the situation.")
    extraordinary: list[ExtraordinaryP] = Field(
        default_factory=list,
        description="Each record in these lists is one the change adds or changes, written in "
        "full. A record with an id already in the world replaces it; a new id adds one.",
    )
    rules: list[RuleP] = Field(default_factory=list)
    peoples: list[PeopleP] = Field(default_factory=list)
    creatures: list[CreatureP] = Field(default_factory=list)
    ladders: list[LadderP] = Field(default_factory=list)
    laws: list[LawP] = Field(default_factory=list)
    places: list[PlaceP] = Field(default_factory=list)
    factions: list[FactionP] = Field(default_factory=list)
    npcs: list[NpcP] = Field(default_factory=list)
    clocks: list[ClockP] = Field(default_factory=list)
    threads: list[ThreadP] = Field(default_factory=list)
    mysteries: list[MysteryP] = Field(default_factory=list)
    removed: list[RemovalP] = Field(
        default_factory=list,
        description="Each record the change removes, including anything it makes untrue.",
    )
    dropped_rule_ids: list[str] = Field(
        default_factory=list,
        description="Ids of fixed rules the player asked to remove or change.",
    )
    nature: list[str] = Field(
        default_factory=list, description="Only if the change alters it: the whole new list."
    )
    norms: list[str] = Field(
        default_factory=list, description="Only if the change alters it: the whole new list."
    )
    known_facts: list[str] = Field(
        default_factory=list, description="Only if the change alters it: the whole new list."
    )
    calendar: CalendarP | None = Field(default=None, description="Only if the change alters it.")
    travel: TravelP | None = Field(default=None, description="Only if the change alters it.")
    medicine: MedicineP | None = Field(default=None, description="Only if the change alters it.")
    opening: OpeningP | None = Field(default=None, description="Only if the change alters it.")


# The player character (G2, G13, A1, G21, G22).


class ItemP(Proposal):
    name: str
    kind: ItemKind = ItemKind.OTHER
    description: str = ""
    quantity: int = 1
    carried: bool = Field(default=True, description="Whether it is on them right now.")


class ConnectionP(Proposal):
    name: str = Field(description="A person or group: 'three loyal soldiers'.")
    kind: ConnectionKind = ConnectionKind.OTHER
    character_id: str = Field(default="", description="The key character's id, if it is one.")
    note: str = ""


class ReserveP(Proposal):
    name: str = Field(description="The world's fighting energy: qi, aura, mana.")
    level: int = Field(default=100, description="0 to 100, as a share of what they can hold.")


class CharacterProposal(Proposal):
    name: str
    aliases: list[str] = Field(default_factory=list)
    age: int | None = None
    people_id: str = ""
    description: str = Field(default="", description="How they come across.")
    appearance: str = Field(default="", description="For portraits.")
    location_id: str = ""
    attributes: AttributesP = Field(default_factory=AttributesP)
    skills: list[SkillP] = Field(default_factory=list)
    traits: list[TraitP] = Field(default_factory=list)
    powers: list[PowerP] = Field(default_factory=list)
    techniques: list[TechniqueP] = Field(default_factory=list)
    temperament: TemperamentP = Field(default_factory=TemperamentP)
    items: list[ItemP] = Field(default_factory=list)
    money: int = 0
    currency: str = ""
    title: str = ""
    rank: str = Field(default="", description="Standing in the world's own ranks.")
    family_name: str = ""
    connections: list[ConnectionP] = Field(default_factory=list)
    parent_ids: list[str] = Field(
        default_factory=list,
        description="N6: the character's mother and father among the key characters, by id, as "
        "the character knows them. Two at most; a hidden parentage is someone's secret.",
    )
    memberships: list[MembershipP] = Field(default_factory=list)
    ladders: list[LadderPositionP] = Field(default_factory=list)
    axes: AxesP = Field(default_factory=AxesP)
    reserves: list[ReserveP] = Field(default_factory=list)
    goals: list[str] = Field(
        default_factory=list, description="Goals the premise gives the player, in their words."
    )
    backstory: list[str] = Field(default_factory=list)
    hidden_past: list[str] = Field(
        default_factory=list,
        description="What others remember about this body's past that the character doesn't "
        "know (G21). Hidden from the player.",
    )


class DraftProposal(Proposal):
    """A whole first draft: the world, then the character drafted from it (G1, G2)."""

    world: WorldProposal
    character: CharacterProposal
