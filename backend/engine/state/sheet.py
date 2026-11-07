"""What a character is made of (G13): the sheet every character has, in every genre.

Key NPCs get the full sheet and minor ones mostly defaults (W15). Creatures, monsters and machines
use whichever parts apply. Nothing here assumes a genre (G5): there is no mana, level or gun unless
the world has one.
"""

from enum import StrEnum

from pydantic import Field, model_validator

from engine.base import (
    Affinity,
    EngineModel,
    Fear,
    Level,
    Name,
    Percent,
    Seconds,
    Strain,
    Tier,
    Trust,
    WorldSeconds,
)


class PowerAxis(StrEnum):
    """A8. The axes power is carried on, so a schemer or a merchant has something to roll with."""

    MIGHT = "might"
    INFLUENCE = "influence"
    WEALTH = "wealth"
    KNOWLEDGE = "knowledge"
    STEALTH = "stealth"


class PowerAxes(EngineModel):
    """A8. Tiers on each axis, worked out from the whole sheet (G13, G14). A world's ladder names
    the tiers (G18). Tier 1 is an ordinary person; 0 is nothing at all."""

    might: Tier = 1
    influence: Tier = 1
    wealth: Tier = 1
    knowledge: Tier = 1
    stealth: Tier = 1

    def on(self, axis: PowerAxis) -> int:
        return getattr(self, axis.value)


class Attributes(EngineModel):
    """G13. Body (strength, speed, toughness), mind (wits, knowledge, willpower) and presence
    (charm, nerve, bearing).

    Scale: 0 none, 1 feeble, 3 an average person, 5 the peak of what a person can be, and 6 to 10
    beyond human, only where the world allows it (G6).
    """

    strength: Level = 3
    speed: Level = 3
    toughness: Level = 3
    wits: Level = 3
    knowledge: Level = 3
    willpower: Level = 3
    charm: Level = 3
    nerve: Level = 3
    bearing: Level = 3


class SkillLevel(StrEnum):
    """One ladder of words for skill in every world (G4 suggestion, G16). The world's own ranks
    are kept for standing, on `Resources.rank`."""

    UNTRAINED = "untrained"
    NOVICE = "novice"
    FAIR = "fair"
    SKILLED = "skilled"
    EXPERT = "expert"
    MASTER = "master"

    @property
    def rank(self) -> int:
        return list(SkillLevel).index(self)


class Skill(EngineModel):
    """G13. Open-ended, never picked from a fixed list."""

    name: Name
    level: SkillLevel = SkillLevel.FAIR
    notes: str = ""


class TraitKind(StrEnum):
    GIFT = "gift"
    FLAW = "flaw"
    QUIRK = "quirk"


class Trait(EngineModel):
    """G13, A4. What makes the character unusual. Traits can bend the usual rules."""

    name: Name
    kind: TraitKind = TraitKind.QUIRK
    description: str = ""


class GiftStrength(StrEnum):
    """G22. Chosen when the character is made."""

    NONE = "none"
    SMALL = "small"
    RARE = "rare"
    OVERPOWERED = "overpowered"


class TimeEffect(StrEnum):
    """W10a. What a time power does to the clocks."""

    STOP = "stop"  # the user's personal clock runs while the world clock stands still
    HASTE = "haste"  # the user's clock runs faster than the world's
    SLOW = "slow"
    LOCAL_REVERSAL = "local_reversal"  # rewinds a wound, an object or a building
    WORLD_REWIND = "world_rewind"  # P2: starts a new timeline


class HitMode(StrEnum):
    """W10a. How hits land in stopped time. The engine decides it with the world and never asks
    the player (A9); once settled it holds."""

    NORMAL_FORCE = "normal_force"
    RELATIVE_SPEED = "relative_speed"
    UNTOUCHABLE = "untouchable"


class TimePower(EngineModel):
    """W10a. The time-bending part of a power, with its limits on the personal clock."""

    effect: TimeEffect
    hit_mode: HitMode | None = Field(
        default=None, description="Stop only. None until the engine settles it (A9)."
    )
    lasts_s: Seconds | None = Field(default=None, description="Personal seconds per use.")
    recharge_s: Seconds | None = Field(default=None, description="Personal seconds to recharge.")
    rate: float | None = Field(
        default=None, gt=0, description="Haste or slow: personal seconds per world second."
    )


class CostKind(StrEnum):
    FATIGUE = "fatigue"
    COOLDOWN = "cooldown"
    ENERGY = "energy"  # aura, qi, mana (G25)
    HEALTH = "health"
    LIFESPAN = "lifespan"  # a price in years
    BLOOD = "blood"
    MONEY = "money"
    ITEM = "item"
    FAVOUR = "favour"
    OTHER = "other"


class PowerCost(EngineModel):
    kind: CostKind
    text: str


class Power(EngineModel):
    """G13, G22. An extraordinary ability, only where the world has one (G6), with its limits and
    costs. Some are known to the world and some are secret."""

    id: str
    name: Name
    description: str = ""
    strength: GiftStrength | None = None
    limits: list[str] = Field(default_factory=list)
    costs: list[PowerCost] = Field(default_factory=list)
    secret: bool = False
    time: TimePower | None = None
    settings: dict[str, str] = Field(
        default_factory=dict, description="Details the engine has settled, by key (A9)."
    )
    ready_at_personal_s: int | None = Field(
        default=None, description="Cooldown: usable again at this personal-clock second (W10a)."
    )

    @property
    def costs_text(self) -> str:
        """G13. What using it costs, in one line ("a night's sleep; a drop of blood"), or ""."""
        return "; ".join(c.text.strip().rstrip(".") for c in self.costs if c.text.strip())


class Technique(EngineModel):
    """G25. A named technique from a style, with its effect, cost and requirements."""

    id: str
    name: Name
    style: str = ""
    effect: str = ""
    cost: str = ""
    requirements: str = ""
    learned_from: str = ""
    power_id: str | None = Field(
        default=None, description="The power it is a way of using, if any (A9, W10a)."
    )


class Grudge(EngineModel):
    """W4. Kept until something changes it, with the deed behind it when there is one."""

    reason: str
    deed_id: str | None = None
    since_turn: int = Field(default=0, ge=0)


class Attitude(EngineModel):
    """W4. How one character feels about another.

    `apparent_affinity` is how warm they act when it differs from how they feel, such as a planted
    traitor. The player only ever sees the apparent side (C6).
    """

    affinity: Affinity = 0
    fear: Fear = 0
    trust: Trust = 0
    apparent_affinity: Affinity | None = None
    grudges: list[Grudge] = Field(default_factory=list)

    @property
    def shown_affinity(self) -> int:
        return self.affinity if self.apparent_affinity is None else self.apparent_affinity


class Temperament(EngineModel):
    """G13, G15. Who they are. It colours how others see them but never chooses for the player."""

    traits: list[str] = Field(default_factory=list)  # hot-headed, loyal, cautious
    values: list[str] = Field(default_factory=list)
    loves: list[str] = Field(default_factory=list)
    fears: list[str] = Field(default_factory=list)
    wants: list[str] = Field(default_factory=list)
    voice: str = Field(default="", description="How they talk (C9).")


class Disposition(EngineModel):
    """G13. Temperament, and attitudes toward particular characters, keyed by character id. The
    attitude toward the player is keyed by the player character's id."""

    temperament: Temperament = Field(default_factory=Temperament)
    attitudes: dict[str, Attitude] = Field(default_factory=dict)


class ItemKind(StrEnum):
    WEAPON = "weapon"
    ARMOUR = "armour"
    GEAR = "gear"
    TREASURE = "treasure"
    CONSUMABLE = "consumable"
    VEHICLE = "vehicle"
    PROPERTY = "property"
    DOCUMENT = "document"
    OTHER = "other"


class Item(EngineModel):
    """C2, G25. Something the character owns. `carried` says whether it is on them now, which R2's
    beat check needs."""

    id: str
    name: Name
    kind: ItemKind = ItemKind.OTHER
    description: str = ""
    quantity: int = Field(default=1, ge=0)
    carried: bool = True
    history: str = Field(default="", description="For legendary items (G25).")


class ConnectionKind(StrEnum):
    OWES_THEM = "owes_them"  # someone owes the character
    OWED = "owed"  # the character owes someone
    TRUSTS_THEM = "trusts_them"
    FEARS_THEM = "fears_them"
    ALLY = "ally"
    FAMILY = "family"
    OTHER = "other"


class Connection(EngineModel):
    """G13. People who owe them, trust them or fear them."""

    name: Name
    kind: ConnectionKind = ConnectionKind.OTHER
    character_id: str | None = None
    note: str = ""


class Resources(EngineModel):
    """G13. Equipment, money, property, standing and connections. Reputation with factions and
    regions lives on `Faction` and `Place` (W3)."""

    items: list[Item] = Field(default_factory=list)
    money: int = Field(default=0, ge=0)
    currency: str = ""
    title: str = ""
    rank: str = Field(default="", description="Standing in the world's own ranks.")
    family_name: str = ""
    connections: list[Connection] = Field(default_factory=list)


class Health(StrEnum):
    UNHURT = "unhurt"
    HURT = "hurt"
    WOUNDED = "wounded"
    BADLY_WOUNDED = "badly_wounded"
    DYING = "dying"

    def worse_than(self, other: "Health") -> bool:
        order = list(Health)
        return order.index(self) > order.index(other)


class Wound(EngineModel):
    text: str
    lasting: bool = Field(default=False, description="An injury that lasts, such as a lost eye.")
    heals_at_personal_s: int | None = None


class PassingState(EngineModel):
    """A passing state such as drunk, poisoned, grieving or drained by a power. Each takes lived
    time to pass (W10, W10a)."""

    name: Name
    effect: str = ""
    until_personal_s: int | None = None


class Reserve(EngineModel):
    """G25. The world's fighting energy (aura, qi, mana), as a share of what the character can
    hold. A character who runs dry is weakened until it comes back."""

    name: Name
    level: Percent = 100
    recovery_s: Seconds | None = Field(default=None, description="Lived seconds from dry to full.")


class Condition(EngineModel):
    """G13. Health and wounds, fatigue, hunger, stress, lasting injuries and passing states.
    `weakened_tiers` is how far below their sheet they stand right now (A8: a god that has lost
    most of its power)."""

    health: Health = Health.UNHURT
    wounds: list[Wound] = Field(default_factory=list)
    fatigue: Strain = 0
    hunger: Strain = 0
    stress: Strain = 0
    states: list[PassingState] = Field(default_factory=list)
    reserves: list[Reserve] = Field(default_factory=list)
    weakened_tiers: Tier = 0

    @model_validator(mode="after")
    def _healed_wounds_gone(self) -> "Condition":
        """A state saved before healed wounds were cleared loads without them."""
        self._heal_if_unhurt()
        return self

    def set_health(self, health: Health) -> None:
        """Health as it is now. A body back to unhurt has healed every wound that doesn't last,
        so none lingers in the record to be "reopened" (`engine.injuries`)."""
        self.health = health
        self._heal_if_unhurt()

    def _heal_if_unhurt(self) -> None:
        if self.health is Health.UNHURT and any(not w.lasting for w in self.wounds):
            self.wounds = [w for w in self.wounds if w.lasting]


class LadderPosition(EngineModel):
    """G18. Where the character stands on one of the world's ladders."""

    ladder_id: str
    rung: int = Field(ge=0, description="Index into the ladder's rungs, lowest first.")
    stage: str = Field(default="", description="Finer steps in the world's words: 'third stage'.")
    shown_rung: int | None = Field(
        default=None,
        ge=0,
        description="G20: the rung others sense while strength is hidden; None if not hiding.",
    )


class RulingSource(StrEnum):
    """Who raised the question a ruling settles (A9)."""

    THEORY = "theory"  # the player reasoned about how their power works
    TEST = "test"  # the player tried something and the engine settled it
    WORLD = "world"  # the engine had to decide it when it started to matter
    GROWTH = "growth"  # a technique found later (A4)


class Ruling(EngineModel):
    """A9. The engine rules on a question about a power, or about the world, once. The answer is
    set in stone: a later ruling on the same `(power_id, topic)` is never accepted. A refused idea
    can still be earned later as a new technique with its own topic."""

    id: str
    topic: str = Field(min_length=1, description="A stable key, such as 'throw_speed'.")
    power_id: str | None = None
    question: str
    answer: str
    holds: bool
    cost: str = Field(default="", description="A yes can come with a cost (A9, G22).")
    source: RulingSource = RulingSource.THEORY
    turn: int = Field(default=0, ge=0)
    world_s: WorldSeconds = 0


class Gain(EngineModel):
    """A4, G17. A gain or a loss, recorded with its turn, source and reason."""

    what: str
    change: str
    source: str
    reason: str
    loss: bool = False
    turn: int = Field(default=0, ge=0)
    world_s: WorldSeconds = 0


class Practice(EngineModel):
    """A4. Effort toward a gain not made yet, in lived seconds, so training over many sessions
    adds up. `key` names what it is for, such as `skill:swordsmanship`."""

    key: str = Field(min_length=1)
    what: str
    effort_s: Seconds = 0


class BackstoryClaim(EngineModel):
    """N4. A fact about the character's own past or inner life that the engine accepted."""

    text: str
    turn: int = Field(default=0, ge=0)


class CharacterSheet(EngineModel):
    """A1, G13. Everything a character is made of, plus the A8 axes, the A9 rulings on their
    powers, and their growth and losses (A4, G17)."""

    attributes: Attributes = Field(default_factory=Attributes)
    skills: list[Skill] = Field(default_factory=list)
    traits: list[Trait] = Field(default_factory=list)
    powers: list[Power] = Field(default_factory=list)
    techniques: list[Technique] = Field(default_factory=list)
    disposition: Disposition = Field(default_factory=Disposition)
    resources: Resources = Field(default_factory=Resources)
    condition: Condition = Field(default_factory=Condition)
    axes: PowerAxes = Field(default_factory=PowerAxes)
    ladders: list[LadderPosition] = Field(default_factory=list)
    rulings: list[Ruling] = Field(default_factory=list)
    growth: list[Gain] = Field(default_factory=list)
    practice: list[Practice] = Field(default_factory=list)
    backstory: list[BackstoryClaim] = Field(default_factory=list)

    def power(self, power_id: str) -> Power | None:
        return next((p for p in self.powers if p.id == power_id), None)

    def item(self, item_id: str) -> Item | None:
        return next((i for i in self.resources.items if i.id == item_id), None)

    def skill(self, name: str) -> Skill | None:
        wanted = name.casefold()
        return next((s for s in self.skills if s.name.casefold() == wanted), None)

    def technique(self, technique_id: str) -> Technique | None:
        return next((t for t in self.techniques if t.id == technique_id), None)

    def practiced(self, key: str) -> Practice | None:
        return next((p for p in self.practice if p.key == key), None)

    def ruling(self, topic: str, power_id: str | None = None) -> Ruling | None:
        return next(
            (r for r in self.rulings if r.topic == topic and r.power_id == power_id),
            None,
        )
