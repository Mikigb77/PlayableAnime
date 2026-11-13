"""C6: what the player character knows, in the world's words (G16).

`memory_view` and `status_view` project the world state onto the player character's knowledge,
in the shapes of API.md's `MemoryView` and `StatusView`. They read only records whose knowledge
lists hold the player character (`known_by`, `met_by`, `heard_at`, a status change's `known_by`),
and never read hidden truth: whether a rumor or fact is true, how accurate a rumor is, secrets,
agendas, real attitudes behind an apparent one, trust (W4), faction plans (W6), witnesses the
player didn't notice, or anything on another timeline. The one exception is what the player
character knows for themselves: a rumor of something they did, saw, were told by someone close or
were there for is confirmed, or false, rather than unconfirmed. A spoiler view after an arc ends is
a separate projection (P1).

The same words heard or done more than once show once: a fight of four blows is one rumor and one
deed on the screen, not four, though the world keeps each blow.

What a drafted story's start holds back shows once the story tells it (G1, `engine.untold`): the
people the character knew before it began, their goals and the threads already running that the
player's own words never named are left out, with what the character knows about those people,
until a scene names them.

URLs for portraits and pictures are left empty here; the API fills them from the scene images.

The fixed words here (attitudes, standing, health, who saw a deed, "Heard 2 days ago") come in the
story's language (S10). What the world itself wrote, such as a fact or a deed's telling, stays in
the language it was written in.
"""

from enum import StrEnum
from functools import cached_property

from pydantic import Field

from engine import bonds, levels, possessions
from engine import path as path_mod
from engine import talent as talent_mod
from engine import untold as untold_mod
from engine.base import EngineModel
from engine.context import Language
from engine.contracts.intent import GrowthKind
from engine.director import goals as goals_mod
from engine.director.goals import GoalKind, GoalOrigin
from engine.kin import descendants
from engine.labels import ago_label, clock_label, date_label, in_label, number_label, of_name
from engine.limits import normalize
from engine.resolve.powers.growth import GainHow, GainKind, rank_of, read_gain, technique_pace
from engine.state.bible import PowerLadder
from engine.state.cast import (
    Character,
    CharacterStatus,
    Faction,
    FactionStatus,
    Place,
    PlaceStatus,
    Reputation,
)
from engine.state.records import (
    Bond,
    BondEnd,
    BondStage,
    Deed,
    EventStatus,
    Fact,
    Goal,
    GoalStatus,
    LeadStatus,
    OriginKind,
    PendingEvent,
    Rumor,
    StatusChange,
    ThreadStatus,
    Transfer,
    Visibility,
)
from engine.state.sheet import (
    Health,
    ItemKind,
    Mastery,
    RankStage,
    SkillLevel,
    TalentFit,
    TalentStrength,
    Technique,
    TraitKind,
)
from engine.state.world import WorldState, natural_key
from engine.world.answers import ARRIVING, Answer
from engine.world.rumors import Certainty, certainty
from engine.world.scheduling import Kind
from engine.world.telling import YOU, own_words, tell, wound_said
from engine.world.tuning import RUMOR_MIN_SEVERITY

SINCE_LIMIT = 6
# How many of their latest gains the sheet lists under how they grew.
GREW_LIMIT = 30
# How many of those they have seen stand above every rung they know of the path names.
HIGHER_NAMES = 3
# C10: how many of the player character's latest gains and losses `/status` weighs among them.
SINCE_TRANSFERS = 3
EN = Language.EN
ES = Language.ES
CA = Language.CA
_DESCENDANT_WORDS = {
    EN: {1: "Your child.", 2: "Your grandchild."},
    ES: {1: "Tu hijo o hija.", 2: "Tu nieto o nieta."},
    CA: {1: "El teu fill o filla.", 2: "El teu nét o néta."},
}


# --- the views, as API.md shapes them ------------------------------------------------------


class Attitude(StrEnum):
    """W4. How someone comes across toward the player character, warmest first."""

    WARM = "warm"
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"
    COLD = "cold"
    HOSTILE = "hostile"


class Esteem(StrEnum):
    """W3. How well a faction thinks of the player character, best first."""

    ADMIRED = "admired"
    RESPECTED = "respected"
    NEUTRAL = "neutral"
    DISLIKED = "disliked"
    DESPISED = "despised"


class Dread(StrEnum):
    """W3. How much a faction fears the player character."""

    NONE = "none"
    WARY = "wary"
    FEARED = "feared"


class DeedSeen(StrEnum):
    """W2, C6. Who saw a deed, as far as the player character knows."""

    WATCHED = "watched"  # someone else's deed, which the character saw
    HEARD_OF = "heard_of"  # someone else's deed, which the character heard of
    SEEN = "seen"  # their own, with someone they noticed watching
    PUBLIC = "public"  # their own, done where anyone could see
    UNSEEN = "unseen"  # their own, with nobody watching as far as they know


class TrailKind(StrEnum):
    """W2, W11, C6. What the player character knows became of a deed of theirs, after it."""

    WENT = "went"  # someone who saw it, whom they saw go off to tell
    DEAD = "dead"  # someone who saw it and is dead, as far as they know
    HEARD = "heard"  # talk of it that a scene told them
    CAME = "came"  # someone came to them over it


class TrailEntry(EngineModel):
    kind: TrailKind
    text: str


class CharacterCard(EngineModel):
    name: str
    lines: list[str] = Field(default_factory=list)
    portrait_url: str | None = None


class PersonEntry(EngineModel):
    """Someone the player character knows. `attitude`, `status` and `presumed` are the values
    the two labels say, so a screen can mark a death or tint a feeling without reading words.
    `bond` is where a romance between the two stands as the character knows it (W17), and
    `bond_line` tells how it came there."""

    id: str
    name: str
    lines: list[str] = Field(default_factory=list)
    attitude: Attitude | None = None
    attitude_label: str | None = None
    portrait_url: str | None = None
    status: str = CharacterStatus.ALIVE.value
    presumed: bool = False
    status_label: str
    bond: BondStage | None = None
    bond_line: str | None = None


class PlaceEntry(EngineModel):
    id: str
    name: str
    lines: list[str] = Field(default_factory=list)
    image_url: str | None = None


class FactionEntry(EngineModel):
    id: str
    name: str
    lines: list[str] = Field(default_factory=list)
    esteem: Esteem = Esteem.NEUTRAL
    dread: Dread = Dread.NONE
    standing_label: str


class GoalEntry(EngineModel):
    id: str
    text: str
    kind: GoalKind = GoalKind.OWN
    origin: GoalOrigin = GoalOrigin.STATED
    origin_label: str = ""
    progress: str | None = None
    """Where it stands as far as the character knows, when a scene said (C6)."""


class GoalDoneEntry(EngineModel):
    """A goal of the player character's that is over, and when it closed."""

    id: str
    text: str
    how: GoalStatus
    when_label: str | None = None


class LeadEntry(EngineModel):
    id: str
    text: str
    expires_label: str | None = None


class RumorEntry(EngineModel):
    id: str
    text: str
    heard_label: str
    certainty: Certainty = Certainty.UNCONFIRMED
    unconfirmed: bool = True
    """`certainty` is unconfirmed: kept for apps older than `certainty`."""


class DeedEntry(EngineModel):
    id: str
    text: str
    when_label: str
    seen: DeedSeen
    known_label: str
    trail: list[TrailEntry] = Field(default_factory=list)
    """What the character knows became of it since, in the order it happened (C6)."""
    open_label: str | None = None
    """That who else knows is nothing they can tell, where that is an open question."""


class ThreadEntry(EngineModel):
    id: str
    title: str
    status: ThreadStatus


class MemoryView(EngineModel):
    character: CharacterCard
    people: list[PersonEntry] = Field(default_factory=list)
    places: list[PlaceEntry] = Field(default_factory=list)
    factions: list[FactionEntry] = Field(default_factory=list)
    goals: list[GoalEntry] = Field(default_factory=list)
    goals_done: list[GoalDoneEntry] = Field(default_factory=list)
    leads: list[LeadEntry] = Field(default_factory=list)
    rumors: list[RumorEntry] = Field(default_factory=list)
    deeds: list[DeedEntry] = Field(default_factory=list)
    threads: list[ThreadEntry] = Field(default_factory=list)


class StatusCharacter(EngineModel):
    name: str
    lines: list[str] = Field(default_factory=list)
    """The sheet as plain lines, for apps from before `StatusView.sheet`."""
    portrait_url: str | None = None


class SheetWound(EngineModel):
    text: str
    lasting: bool = False


class SheetState(EngineModel):
    name: str
    effect: str = ""
    ends_label: str | None = None


class SheetReserve(EngineModel):
    name: str
    level: int


class SheetCondition(EngineModel):
    health: Health
    health_label: str
    wounds: list[SheetWound] = Field(default_factory=list)
    states: list[SheetState] = Field(default_factory=list)
    reserves: list[SheetReserve] = Field(default_factory=list)
    expecting_label: str | None = None


class SheetRung(EngineModel):
    """A rung they climbed, or the one they stand on. `note` is when, where the record holds
    it: "Reached, day 9" for their own, "Left behind, day 9" for one under it. Their own says
    how full their rank is (G19): `stage` in words ("Late stage", or that a breakthrough can
    be tried once it is at its peak) and `filled` from 0 to 1, None for a rung they left
    behind and on a ladder's last rung."""

    name: str
    stage: str = ""
    filled: float | None = None
    description: str = ""
    note: str = ""


class SheetRungAbove(EngineModel):
    """A rung above their own, as far as they know of it (C6, `engine.path`): `known` once the
    story confirmed it, only heard of until then. `note` is how they know ("Everyone has heard
    of it", "Heard of, day 14", "Confirmed before Elder Han, day 15"), `said` what they have
    learned or heard about it, in the record's words, and `gap_below` whether rungs lie under
    it that nobody has named to them. Never what the rung is or what reaching it takes: that is
    the story's to tell."""

    name: str
    known: bool = False
    note: str = ""
    said: list[str] = Field(default_factory=list)
    gap_below: bool = False


class SheetPath(EngineModel):
    """One of the world's ladders (G18). `rungs` runs from its first rung up to where they
    stand, lowest first, so the last one is theirs, and is empty for a ladder they don't stand
    on. `above` holds the rungs over their own that they have heard of, lowest first, and
    nothing else: which rungs lie higher is the story's to tell (C6). `higher` is said once
    someone who stands above all of those has stood before them ("Elder Mo stands somewhere up
    here."), with neither the rung's name nor how far up it lies."""

    name: str
    rungs: list[SheetRung] = Field(default_factory=list)
    above: list[SheetRungAbove] = Field(default_factory=list)
    higher: str = ""


class SheetGain(EngineModel):
    """One thing the character gained (A4, G17), as their sheet tells how they grew: `text` is
    what ("Broke through to Qi Condensation", "Swordsmanship: Skilled", "Learned Falling Leaf
    Palm"), `when` the date in the world's calendar and `how` the way it was made where the
    record says ("With a master", "By doing it")."""

    kind: GainKind
    when: str
    text: str
    how: str = ""


class SheetItem(EngineModel):
    name: str
    kind: ItemKind
    kind_label: str = ""
    description: str = ""
    history: str = ""
    quantity: int = 1
    carried: bool = True


class SheetSkill(EngineModel):
    name: str
    level: SkillLevel
    level_label: str
    dice: int
    notes: str = ""


class SheetPower(EngineModel):
    name: str
    description: str = ""
    limits: list[str] = Field(default_factory=list)
    cost: str = ""
    ready: bool = True
    ready_label: str
    secret: bool = False


class SheetTechnique(EngineModel):
    name: str
    style: str = ""
    effect: str = ""
    cost: str = ""
    source_label: str = ""
    """Where they have it from, when the record says: "Your own", "Learned from Zhao Kun"."""
    mastery: Mastery
    mastery_label: str
    dice: int
    uses: int = 0
    need: int | None = None
    """The uses that reach the next mastery at their own pace, or None where use alone takes
    it no further."""


class SheetTrait(EngineModel):
    name: str
    kind: TraitKind
    kind_label: str
    description: str = ""


class SheetTalent(EngineModel):
    name: str
    strength: TalentStrength
    strength_label: str
    pace_label: str
    covers: str = ""


class SheetView(EngineModel):
    """The player character's sheet in sections (G13, G16), for a screen to lay out: who they
    are, how they are, where they stand on the world's ladders, what they have, what they can
    do and what they are like. Words the engine adds come in the story's language (S10), next
    to the value they say, so a screen can draw a meter or pick a color without reading them."""

    about: list[str] = Field(default_factory=list)
    description: str = ""
    condition: SheetCondition
    paths: list[SheetPath] = Field(default_factory=list)
    money_label: str | None = None
    items: list[SheetItem] = Field(default_factory=list)
    skills: list[SheetSkill] = Field(default_factory=list)
    powers: list[SheetPower] = Field(default_factory=list)
    techniques: list[SheetTechnique] = Field(default_factory=list)
    traits: list[SheetTrait] = Field(default_factory=list)
    temperament: list[str] = Field(default_factory=list)
    talents: list[SheetTalent] = Field(default_factory=list)
    talent_notes: list[str] = Field(default_factory=list)
    grew: list[SheetGain] = Field(default_factory=list)


class ReputationEntry(EngineModel):
    name: str
    label: str


class ClockView(EngineModel):
    world_s: int
    label: str
    timeline_id: str


class SinceEntry(EngineModel):
    text: str
    ago_label: str


class StatusView(EngineModel):
    character: StatusCharacter
    sheet: SheetView
    reputation: list[ReputationEntry] = Field(default_factory=list)
    clock: ClockView
    since: list[SinceEntry] = Field(default_factory=list)


# --- words --------------------------------------------------------------------------------


# Spanish and Catalan have no gender-free adjective for most of these, and a character's gender
# isn't recorded, so their words are ones that fit anyone: "Cordial", "Con heridas", "Respeto".
_ATTITUDES = {
    EN: ("Warm", "Friendly", "Neutral", "Cold", "Hostile"),
    ES: ("Cordial", "Afable", "Neutral", "Distante", "Hostil"),
    CA: ("Cordial", "Afable", "Neutral", "Distant", "Hostil"),
}
_ATTITUDE_AT = {attitude: at for at, attitude in enumerate(Attitude)}


def attitude_label(affinity: int, language: Language = EN) -> str:
    """How someone comes across toward the player character (W4): what they show, not what
    they feel."""
    return _ATTITUDES[language][_ATTITUDE_AT[attitude_of(affinity)]]


def attitude_of(affinity: int) -> Attitude:
    if affinity >= 60:
        return Attitude.WARM
    if affinity >= 20:
        return Attitude.FRIENDLY
    if affinity > -20:
        return Attitude.NEUTRAL
    if affinity > -60:
        return Attitude.COLD
    return Attitude.HOSTILE


_STANDING = {
    # admired, respected, disliked, despised, feared, wary, "and", neutral
    EN: ("Admired", "Respected", "Disliked", "Despised", "feared", "wary of you", "and", "Neutral"),
    ES: ("Admiración", "Respeto", "Recelo", "Desprecio", "temor", "cautela", "y", "Neutral"),
    CA: ("Admiració", "Respecte", "Recel", "Menyspreu", "temor", "cautela", "i", "Neutral"),
}


def standing_label(reputation: Reputation, language: Language = EN) -> str:
    """Esteem and fear in words (W3): "Respected and feared", "Despised", "Neutral"; in Spanish
    "Respeto y temor", "Desprecio", "Neutral"; in Catalan "Respecte i temor", "Menyspreu"."""
    admired, respected, disliked, despised, feared, wary, and_, neutral = _STANDING[language]
    words = {
        Esteem.ADMIRED: admired,
        Esteem.RESPECTED: respected,
        Esteem.NEUTRAL: "",
        Esteem.DISLIKED: disliked,
        Esteem.DESPISED: despised,
    }[esteem_of(reputation)]
    fear = {Dread.FEARED: feared, Dread.WARY: wary, Dread.NONE: ""}[dread_of(reputation)]
    if words and fear:
        return f"{words} {and_} {fear}"
    if fear:
        return fear[0].upper() + fear[1:]
    return words or neutral


def esteem_of(reputation: Reputation) -> Esteem:
    esteem = reputation.esteem
    if esteem >= 60:
        return Esteem.ADMIRED
    if esteem >= 20:
        return Esteem.RESPECTED
    if esteem > -20:
        return Esteem.NEUTRAL
    if esteem > -60:
        return Esteem.DISLIKED
    return Esteem.DESPISED


def dread_of(reputation: Reputation) -> Dread:
    if reputation.fear >= 60:
        return Dread.FEARED
    return Dread.WARY if reputation.fear >= 20 else Dread.NONE


# A4: how well they have a technique, as Status says it after the technique's name.
_MASTERY_WORDS = {
    EN: {
        Mastery.LEARNING: "learning",
        Mastery.PRACTICED: "practiced",
        Mastery.SKILLED: "skilled",
        Mastery.SECOND_NATURE: "second nature",
        Mastery.OWN: "made your own",
    },
    ES: {
        Mastery.LEARNING: "aprendiendo",
        Mastery.PRACTICED: "practicada",
        Mastery.SKILLED: "dominada",
        Mastery.SECOND_NATURE: "segunda naturaleza",
        Mastery.OWN: "hecha tuya",
    },
    CA: {
        Mastery.LEARNING: "aprenent",
        Mastery.PRACTICED: "practicada",
        Mastery.SKILLED: "dominada",
        Mastery.SECOND_NATURE: "segona naturalesa",
        Mastery.OWN: "feta teva",
    },
}

# A4: how a gain was made, as the sheet says it under what they gained.
_GAIN_HOW_WORDS = {
    EN: {
        GainHow.SELF: "On your own",
        GainHow.MASTER: "With a master",
        GainHow.BOOK: "From a manual",
        GainHow.RIVAL: "Against a rival",
        GainHow.WATCHING: "By watching",
        GainHow.PLAY: "By doing it",
        GainHow.PRACTICE: "With practice",
    },
    ES: {
        GainHow.SELF: "Por tu cuenta",
        GainHow.MASTER: "Con un maestro",
        GainHow.BOOK: "De un manual",
        GainHow.RIVAL: "Frente a un rival",
        GainHow.WATCHING: "Observando",
        GainHow.PLAY: "Sobre la marcha",
        GainHow.PRACTICE: "Con práctica",
    },
    CA: {
        GainHow.SELF: "Pel teu compte",
        GainHow.MASTER: "Amb un mestre",
        GainHow.BOOK: "D'un manual",
        GainHow.RIVAL: "Davant d'un rival",
        GainHow.WATCHING: "Observant",
        GainHow.PLAY: "Sobre la marxa",
        GainHow.PRACTICE: "Amb pràctica",
    },
}

# A4: a talent's strength as Status says it after the talent's name, with the pace it gives.
_TALENT_WORDS = {
    EN: {
        TalentStrength.SLOW: "weakness, half the pace",
        TalentStrength.KNACK: "talent, a knack, twice as fast",
        TalentStrength.GENIUS: "talent, genius, four times as fast",
        TalentStrength.ONE_OF_A_KIND: "talent, one of a kind, eight times as fast",
    },
    ES: {
        TalentStrength.SLOW: "punto débil, a la mitad de ritmo",
        TalentStrength.KNACK: "talento, facilidad, el doble de rápido",
        TalentStrength.GENIUS: "talento, genio, cuatro veces más rápido",
        TalentStrength.ONE_OF_A_KIND: "talento único, ocho veces más rápido",
    },
    CA: {
        TalentStrength.SLOW: "punt feble, a la meitat de ritme",
        TalentStrength.KNACK: "talent, facilitat, el doble de ràpid",
        TalentStrength.GENIUS: "talent, geni, quatre vegades més ràpid",
        TalentStrength.ONE_OF_A_KIND: "talent únic, vuit vegades més ràpid",
    },
}
# A4: how fast a thing grows (`engine.talent.pace_words`): a half, the ordinary pace, twice, and
# so many times, in words up to ten.
_PACE_WORDS = {
    ES: ("a la mitad de ritmo", "al ritmo normal", "el doble de rápido", "{} veces más rápido"),
    CA: ("a la meitat de ritme", "al ritme normal", "el doble de ràpid", "{} vegades més ràpid"),
}
_TIMES_WORDS = {
    ES: "tres cuatro cinco seis siete ocho nueve diez".split(),
    CA: "tres quatre cinc sis set vuit nou deu".split(),
}


def _pace_words(pace: float, language: Language) -> str:
    if language not in _PACE_WORDS:
        return talent_mod.pace_words(pace)
    half, ordinary, twice, times = _PACE_WORDS[language]
    if pace <= 2:
        return half if pace < 1 else ordinary if pace == 1 else twice
    words = dict(enumerate(_TIMES_WORDS[language], start=3))
    return times.format(words.get(int(pace), f"{pace:g}"))


# A4: how a thing they learn stands to each talent that reaches it, once ruled on.
# For one talent, and for several.
_FIT_WORDS = {
    EN: {
        TalentFit.INSIDE: (", inside your talent ({})", ", inside your talents ({})"),
        TalentFit.RELATED: (", related to your talent ({})", ", related to your talents ({})"),
    },
    ES: {
        TalentFit.INSIDE: (", dentro de tu talento ({})", ", dentro de tus talentos ({})"),
        TalentFit.RELATED: (", afín a tu talento ({})", ", afín a tus talentos ({})"),
    },
    CA: {
        TalentFit.INSIDE: (", dins del teu talent ({})", ", dins dels teus talents ({})"),
        TalentFit.RELATED: (", afí al teu talent ({})", ", afí als teus talents ({})"),
    },
}

_HEALTH_WORDS = {
    EN: {
        Health.UNHURT: "Unhurt",
        Health.HURT: "Hurt",
        Health.WOUNDED: "Wounded",
        Health.BADLY_WOUNDED: "Badly wounded",
        Health.DYING: "Dying",
    },
    ES: {
        Health.UNHURT: "Sin heridas",
        Health.HURT: "Con heridas leves",
        Health.WOUNDED: "Con heridas",
        Health.BADLY_WOUNDED: "Con heridas graves",
        Health.DYING: "Al borde de la muerte",
    },
    CA: {
        Health.UNHURT: "Sense ferides",
        Health.HURT: "Amb ferides lleus",
        Health.WOUNDED: "Amb ferides",
        Health.BADLY_WOUNDED: "Amb ferides greus",
        Health.DYING: "A punt de morir",
    },
}

# G19: how full a rank is, as the sheet says it under their own rung.
RANK_STAGE_WORDS = {
    EN: {
        RankStage.EARLY: "Early stage",
        RankStage.MIDDLE: "Middle stage",
        RankStage.LATE: "Late stage",
        RankStage.PEAK: "At its peak",
    },
    ES: {
        RankStage.EARLY: "Etapa inicial",
        RankStage.MIDDLE: "Etapa intermedia",
        RankStage.LATE: "Etapa avanzada",
        RankStage.PEAK: "En su cima",
    },
    CA: {
        RankStage.EARLY: "Etapa inicial",
        RankStage.MIDDLE: "Etapa intermèdia",
        RankStage.LATE: "Etapa avançada",
        RankStage.PEAK: "Al seu cim",
    },
}


def rank_stage_label(stage: RankStage, language: Language = EN) -> str:
    """ "Late stage", "Etapa avanzada", "Etapa avançada"."""
    return RANK_STAGE_WORDS[language][stage]


# G16: a skill's level as the sheet says it. In Spanish and Catalan a noun, as "Pericia: espada",
# so it fits a character of any gender.
SKILL_LEVEL_WORDS = {
    ES: {
        SkillLevel.UNTRAINED: "Sin formación",
        SkillLevel.NOVICE: "Nociones",
        SkillLevel.FAIR: "Soltura",
        SkillLevel.SKILLED: "Destreza",
        SkillLevel.EXPERT: "Pericia",
        SkillLevel.MASTER: "Maestría",
    },
    CA: {
        SkillLevel.UNTRAINED: "Sense formació",
        SkillLevel.NOVICE: "Nocions",
        SkillLevel.FAIR: "Soltesa",
        SkillLevel.SKILLED: "Destresa",
        SkillLevel.EXPERT: "Perícia",
        SkillLevel.MASTER: "Mestratge",
    },
}


def skill_level_label(level: SkillLevel, language: Language = EN) -> str:
    """ "Skilled", "Destreza", "Destresa"."""
    words = SKILL_LEVEL_WORDS.get(language)
    return words[level] if words else level.value.capitalize()


# A4: a talent's strength as a noun, strongest first, as a summary lists them.
TALENT_STRENGTH_WORDS = {
    EN: {
        TalentStrength.ONE_OF_A_KIND: "One of a kind",
        TalentStrength.GENIUS: "Genius",
        TalentStrength.KNACK: "A knack",
        TalentStrength.SLOW: "Weakness",
    },
    ES: {
        TalentStrength.ONE_OF_A_KIND: "Talento único",
        TalentStrength.GENIUS: "Genio",
        TalentStrength.KNACK: "Facilidad",
        TalentStrength.SLOW: "Punto débil",
    },
    CA: {
        TalentStrength.ONE_OF_A_KIND: "Talent únic",
        TalentStrength.GENIUS: "Geni",
        TalentStrength.KNACK: "Facilitat",
        TalentStrength.SLOW: "Punt feble",
    },
}

# G13: what kind of thing a belonging is, as the sheet labels it. Anything else has no label.
_ITEM_KIND_WORDS = {
    EN: {
        ItemKind.WEAPON: "Weapon",
        ItemKind.ARMOUR: "Armour",
        ItemKind.GEAR: "Gear",
        ItemKind.TREASURE: "Treasure",
        ItemKind.CONSUMABLE: "Consumable",
        ItemKind.VEHICLE: "Vehicle",
        ItemKind.PROPERTY: "Property",
        ItemKind.DOCUMENT: "Document",
    },
    ES: {
        ItemKind.WEAPON: "Arma",
        ItemKind.ARMOUR: "Armadura",
        ItemKind.GEAR: "Equipo",
        ItemKind.TREASURE: "Tesoro",
        ItemKind.CONSUMABLE: "Consumible",
        ItemKind.VEHICLE: "Vehículo",
        ItemKind.PROPERTY: "Propiedad",
        ItemKind.DOCUMENT: "Documento",
    },
    CA: {
        ItemKind.WEAPON: "Arma",
        ItemKind.ARMOUR: "Armadura",
        ItemKind.GEAR: "Equip",
        ItemKind.TREASURE: "Tresor",
        ItemKind.CONSUMABLE: "Consumible",
        ItemKind.VEHICLE: "Vehicle",
        ItemKind.PROPERTY: "Propietat",
        ItemKind.DOCUMENT: "Document",
    },
}

# G13: what makes them unusual, by kind.
_TRAIT_KIND_WORDS = {
    EN: {TraitKind.GIFT: "Gift", TraitKind.FLAW: "Flaw", TraitKind.QUIRK: "Quirk"},
    ES: {TraitKind.GIFT: "Don", TraitKind.FLAW: "Defecto", TraitKind.QUIRK: "Manía"},
    CA: {TraitKind.GIFT: "Do", TraitKind.FLAW: "Defecte", TraitKind.QUIRK: "Mania"},
}

# S10: every status a person, place or faction can show, in Spanish and Catalan, and how a death
# the player character only believes in reads.
_STATUS_WORDS = {
    ES: {
        CharacterStatus.ALIVE.value: "Con vida",
        CharacterStatus.MISSING.value: "En paradero desconocido",
        CharacterStatus.DEAD.value: "Ha muerto",
        PlaceStatus.THRIVING.value: "Próspero",
        PlaceStatus.DAMAGED.value: "Con daños",
        PlaceStatus.RUINED.value: "En ruinas",
        PlaceStatus.OCCUPIED.value: "Bajo ocupación",
        FactionStatus.INTACT.value: "Intacta",
        FactionStatus.WEAKENED.value: "Ha perdido fuerza",
        FactionStatus.REBUILDING.value: "Se está reconstruyendo",
        FactionStatus.DESTROYED.value: "Ya no existe",
        "presumed_dead": "Se cree que ha muerto",
    },
    CA: {
        CharacterStatus.ALIVE.value: "Amb vida",
        CharacterStatus.MISSING.value: "En parador desconegut",
        CharacterStatus.DEAD.value: "Ha mort",
        PlaceStatus.THRIVING.value: "Pròsper",
        PlaceStatus.DAMAGED.value: "Amb danys",
        PlaceStatus.RUINED.value: "En ruïnes",
        PlaceStatus.OCCUPIED.value: "Sota ocupació",
        FactionStatus.INTACT.value: "Intacta",
        FactionStatus.WEAKENED.value: "Ha perdut força",
        FactionStatus.REBUILDING.value: "S'està reconstruint",
        FactionStatus.DESTROYED.value: "Ja no existeix",
        "presumed_dead": "Es creu que ha mort",
    },
}

# S10: the other fixed words of Memory and Status.
_WORDS = {
    EN: {
        "saw": "You saw it",
        "heard_of": "You heard of it",
        "seen": "You were seen",
        "seen_by": "Seen by {names}",
        "other": "{count} other",
        "others": "{count} others",
        "public": "Done in public",
        "unseen": "No one saw, as far as you know",
        "parent": "Your parent.",
        "not_been": "You haven't been there.",
        "expecting": "Expecting a child, due {due}",
        "ready": "ready",
        "cost": "{power}, cost: {costs}",
        "technique": "{name} (technique, {mastery})",
        "technique_uses": "{name} (technique, {mastery}, {uses} of {need} uses)",
        "talent": "{name} ({strength}): {covers}",
        "ruled": "{what}: grows {pace}",
        "slowed": ", slowed by your weakness ({talent})",
        "outside": "Outside your talents: {things}",
        "bridge": "Bridge: {grounds}",
        "bridges": "Bridges: {grounds}",
        "ends": "Ends {when}",
        "heard": "Heard {when}",
        "and": " and ",
        "to": "To {who}: {what}",
        "from": "From {who}: {what}",
        "gained": "Gained: {what}",
        "lost": "Lost: {what}",
        "someone": "someone",
        "age": "{age} years old",
        "lasts": "Passes {when}",
        "went_to": "{who} went to tell {whom}",
        "went": "{who} went off to tell what they saw",
        "who_saw": "someone who saw it",
        "is_dead": "{who} is dead",
        "is_presumed_dead": "{who} is presumed dead",
        "heard_said": "Heard {when}: “{text}”",
        "came": "{who} came {what}, {when}",
        "came_many": "{who} came {what}, {when}",
        "came_to_face": "to face you over it",
        "came_for_revenge": "for revenge",
        "came_to_arrest": "to arrest you",
        "came_to_look": "to look into it",
        "came_for_you": "for you over it",
        "came_to_you": "to you because of it",
        "who_else": "Who else knows? You can't tell until you hear it, or go and find out.",
        "own_move": "Your own",
        "learned_from": "Learned from {who}",
        "goal_start": "Yours from the start",
        "goal_stated": "You set it yourself",
        "goal_asked": "Asked of you by {who}",
        "goal_taken": "A lead you took up",
        "goal_on": "{what}, {date}",
        "rung_reached": "Reached",
        "rung_left": "Left behind",
        "rung_heard": "Heard of",
        "rung_known": "Confirmed",
        "rung_known_before": "Confirmed before {who}",
        "rung_learned": "From what you have learned",
        "rung_common": "Everyone has heard of it",
        "higher_one": "{who} stands somewhere up here.",
        "higher_many": "{who} stand somewhere up here.",
        "higher_someone": "Someone you have met stands somewhere up here.",
        "rank_ready": "At its peak: you can try to break through",
        "grew_breakthrough": "Broke through to {what}",
        "grew_learned": "Learned {what}",
        "grew_level": "{what}: {level}",
        "grew_new_use": "{what}: a new way to use {power}",
    },
    ES: {
        "saw": "Lo viste",
        "heard_of": "Te enteraste",
        "seen": "Te vieron",
        "seen_by": "Te vieron {names}",
        "other": "{count} persona más",
        "others": "{count} personas más",
        "public": "A la vista de todos",
        "unseen": "Nadie lo vio, que tú sepas",
        "parent": "Tu padre o tu madre.",
        "not_been": "Aún no has estado allí.",
        "expecting": "Esperando un bebé, que nacerá {due}",
        "ready": "disponible",
        "cost": "{power}, coste: {costs}",
        "technique": "{name} (técnica, {mastery})",
        "technique_uses": "{name} (técnica, {mastery}, {uses} de {need} usos)",
        "talent": "{name} ({strength}): {covers}",
        "ruled": "{what}: crece {pace}",
        "slowed": ", con el freno de tu punto débil ({talent})",
        "outside": "Fuera de tus talentos: {things}",
        "bridge": "Puente: {grounds}",
        "bridges": "Puentes: {grounds}",
        "ends": "Termina {when}",
        "heard": "Lo oíste {when}",
        "and": " y ",
        "to": "Para {who}: {what}",
        "from": "De {who}: {what}",
        "gained": "Ganancia: {what}",
        "lost": "Pérdida: {what}",
        "someone": "alguien",
        "age": "{age} años",
        "lasts": "Se pasa {when}",
        "went_to": "{who} fue a contárselo a {whom}",
        "went": "{who} se fue a contar lo que vio",
        "who_saw": "alguien que lo vio",
        "is_dead": "{who} ha muerto",
        "is_presumed_dead": "Se cree que {who} ha muerto",
        "heard_said": "Lo oíste {when}: «{text}»",
        "came": "{who} vino {what}, {when}",
        "came_many": "{who} vinieron {what}, {when}",
        "came_to_face": "a pedirte cuentas",
        "came_for_revenge": "a vengarse",
        "came_to_arrest": "a detenerte",
        "came_to_look": "a investigar lo ocurrido",
        "came_for_you": "a por ti por ello",
        "came_to_you": "a verte por ello",
        "who_else": "¿Quién más lo sabe? No lo sabrás hasta que lo oigas o vayas a averiguarlo.",
        "own_move": "Creación tuya",
        "learned_from": "Aprendida {of_who}",
        "goal_start": "Tuya desde el principio",
        "goal_stated": "Te la marcaste tú",
        "goal_asked": "Te lo pidió {who}",
        "goal_taken": "Una pista que seguiste",
        "goal_on": "{what}, {date}",
        "rung_reached": "Lo alcanzaste",
        "rung_left": "Quedó atrás",
        "rung_heard": "Oíste hablar de ello",
        "rung_known": "Lo comprobaste",
        "rung_known_before": "Lo comprobaste ante {who}",
        "rung_learned": "Por lo que has aprendido",
        "rung_common": "Todo el mundo ha oído hablar de ello",
        "higher_one": "{who} está en algún punto de aquí arriba.",
        "higher_many": "{who} están en algún punto de aquí arriba.",
        "higher_someone": "Alguien con quien te has cruzado está en algún punto de aquí arriba.",
        "rank_ready": "En su cima: puedes intentar dar el salto",
        "grew_breakthrough": "Alcanzaste {what}",
        "grew_learned": "Aprendiste {what}",
        "grew_level": "{what}: {level}",
        "grew_new_use": "{what}: una nueva forma de usar {power}",
    },
    CA: {
        "saw": "Ho vas veure",
        "heard_of": "Te'n vas assabentar",
        "seen": "Et van veure",
        "seen_by": "Et van veure {names}",
        "other": "{count} persona més",
        "others": "{count} persones més",
        "public": "A la vista de tothom",
        "unseen": "Ningú no ho va veure, que tu sàpigues",
        "parent": "El teu pare o la teva mare.",
        "not_been": "Encara no hi has estat.",
        "expecting": "Esperant un nadó, que naixerà {due}",
        "ready": "disponible",
        "cost": "{power}, cost: {costs}",
        "technique": "{name} (tècnica, {mastery})",
        "technique_uses": "{name} (tècnica, {mastery}, {uses} de {need} usos)",
        "talent": "{name} ({strength}): {covers}",
        "ruled": "{what}: creix {pace}",
        "slowed": ", amb el fre del teu punt feble ({talent})",
        "outside": "Fora dels teus talents: {things}",
        "bridge": "Pont: {grounds}",
        "bridges": "Ponts: {grounds}",
        "ends": "Acaba {when}",
        "heard": "Ho vas sentir {when}",
        "and": " i ",
        "to": "Per a {who}: {what}",
        "from": "De {who}: {what}",
        "gained": "Guany: {what}",
        "lost": "Pèrdua: {what}",
        "someone": "algú",
        "age": "{age} anys",
        "lasts": "Passa {when}",
        "went_to": "{who} va anar a explicar-ho a {whom}",
        "went": "{who} va marxar a explicar el que havia vist",
        "who_saw": "algú que ho va veure",
        "is_dead": "{who} ha mort",
        "is_presumed_dead": "Es creu que {who} ha mort",
        "heard_said": "Ho vas sentir {when}: «{text}»",
        "came": "{who} va venir {what}, {when}",
        "came_many": "{who} van venir {what}, {when}",
        "came_to_face": "a demanar-te comptes",
        "came_for_revenge": "a venjar-se",
        "came_to_arrest": "a detenir-te",
        "came_to_look": "a investigar què havia passat",
        "came_for_you": "a buscar-te per això",
        "came_to_you": "a veure't per això",
        "who_else": "Qui més ho sap? No ho sabràs fins que ho sentis o ho vagis a esbrinar.",
        "own_move": "Creació teva",
        "learned_from": "Apresa {of_who}",
        "goal_start": "Teva des del principi",
        "goal_stated": "Te la vas marcar tu",
        "goal_asked": "T'ho va demanar {who}",
        "goal_taken": "Una pista que vas seguir",
        "goal_on": "{what}, {date}",
        "rung_reached": "Hi vas arribar",
        "rung_left": "Va quedar enrere",
        "rung_heard": "En vas sentir a parlar",
        "rung_known": "Ho vas comprovar",
        "rung_known_before": "Ho vas comprovar davant {of_who}",
        "rung_learned": "Pel que has après",
        "rung_common": "Tothom n'ha sentit a parlar",
        "higher_one": "{who} és en algun punt d'aquí dalt.",
        "higher_many": "{who} són en algun punt d'aquí dalt.",
        "higher_someone": "Algú amb qui t'has creuat és en algun punt d'aquí dalt.",
        "rank_ready": "Al seu cim: pots intentar fer el salt",
        "grew_breakthrough": "Vas assolir {what}",
        "grew_learned": "Vas aprendre {what}",
        "grew_level": "{what}: {level}",
        "grew_new_use": "{what}: una nova manera de fer servir {power}",
    },
}


# W17, S10. A romance between someone and the player character, in words: how it came to each
# stage, told with the day ("You became a couple, day 9"), how it stands when it was so as the
# story opened, and what it had come to when it ended. Nothing here says whether anyone is a
# man or a woman.
_BOND_WORDS = {
    EN: {
        "came": {
            BondStage.INTEREST: "You made your interest plain",
            BondStage.COURTING: "You began courting",
            BondStage.TOGETHER: "You became a couple",
            BondStage.PROMISED: "You promised yourselves to each other",
            BondStage.MARRIED: "You married",
        },
        "came_theirs": "{who} made their interest in you plain",
        "is": {
            BondStage.INTEREST: "You have made your interest plain",
            BondStage.COURTING: "You are courting",
            BondStage.TOGETHER: "You are a couple",
            BondStage.PROMISED: "You are promised to each other",
            BondStage.MARRIED: "You are married",
        },
        "is_theirs": "{who} has made their interest in you plain",
        "was": {
            BondStage.COURTING: "You were courting",
            BondStage.TOGETHER: "You were a couple",
            BondStage.PROMISED: "You were promised to each other",
            BondStage.MARRIED: "You were married",
        },
        "until_you": "{was} until you ended it",
        "until_them": "{was} until they ended it",
        "until_over": "{was} until it ended",
        "until_death": "{was} until their death",
    },
    ES: {
        "came": {
            BondStage.INTEREST: "Le dejaste claro tu interés",
            BondStage.COURTING: "Empezó algo entre {who} y tú",
            BondStage.TOGETHER: "Os hicisteis pareja",
            BondStage.PROMISED: "Os prometisteis",
            BondStage.MARRIED: "Os casasteis",
        },
        "came_theirs": "{who} te dejó claro su interés",
        "is": {
            BondStage.INTEREST: "Le has dejado claro tu interés",
            BondStage.COURTING: "Hay algo entre {who} y tú",
            BondStage.TOGETHER: "Sois pareja",
            BondStage.PROMISED: "Os habéis prometido",
            BondStage.MARRIED: "Sois un matrimonio",
        },
        "is_theirs": "{who} te ha dejado claro su interés",
        "was": {
            BondStage.COURTING: "Hubo algo entre {who} y tú",
            BondStage.TOGETHER: "Fuisteis pareja",
            BondStage.PROMISED: "Tuvisteis un compromiso",
            BondStage.MARRIED: "Fuisteis un matrimonio",
        },
        "until_you": "{was} hasta que lo dejaste",
        "until_them": "{was} hasta que te dejó",
        "until_over": "{was} hasta que se acabó",
        "until_death": "{was} hasta su muerte",
    },
    CA: {
        "came": {
            BondStage.INTEREST: "Li vas deixar clar el teu interès",
            BondStage.COURTING: "Va començar alguna cosa entre {who} i tu",
            BondStage.TOGETHER: "Us vau fer parella",
            BondStage.PROMISED: "Us vau prometre",
            BondStage.MARRIED: "Us vau casar",
        },
        "came_theirs": "{who} et va deixar clar el seu interès",
        "is": {
            BondStage.INTEREST: "Li has deixat clar el teu interès",
            BondStage.COURTING: "Hi ha alguna cosa entre {who} i tu",
            BondStage.TOGETHER: "Sou parella",
            BondStage.PROMISED: "Us heu promès",
            BondStage.MARRIED: "Sou un matrimoni",
        },
        "is_theirs": "{who} t'ha deixat clar el seu interès",
        "was": {
            BondStage.COURTING: "Hi va haver alguna cosa entre {who} i tu",
            BondStage.TOGETHER: "Vau ser parella",
            BondStage.PROMISED: "Vau tenir un compromís",
            BondStage.MARRIED: "Vau ser un matrimoni",
        },
        "until_you": "{was} fins que ho vas deixar",
        "until_them": "{was} fins que et va deixar",
        "until_over": "{was} fins que es va acabar",
        "until_death": "{was} fins a la seva mort",
    },
}


def _status_words(status: str, presumed: bool = False, language: Language = EN) -> str:
    if words := _STATUS_WORDS.get(language):
        if status == CharacterStatus.DEAD.value and presumed:
            return words["presumed_dead"]
        return words.get(status) or status.replace("_", " ").capitalize()
    if status == CharacterStatus.DEAD.value:
        return "Presumed dead" if presumed else "Dead"
    return status.replace("_", " ").capitalize()


def believed_status(
    history: list[StatusChange], current: str, player_id: str, *, initial: str
) -> tuple[str, bool]:
    """The status the player character believes, and whether a death was presumed (C6): the
    latest change they know of. With none, it is the status before the first change (`initial`
    if that wasn't recorded), or the current one if it never changed."""
    known = [h for h in history if player_id in h.known_by]
    if known:
        return known[-1].status, known[-1].presumed
    if history:
        return history[0].from_status or initial, False
    return current, False


class _PlayerTeller:
    """The player character telling a deed (C6): "you" for themselves, only the names they
    know, and a death only where they know the deed caused it."""

    def __init__(self, knowledge: "_Knowledge") -> None:
        self.k = knowledge

    def name(self, record: Character | Place | Faction) -> str | None:
        if record.id == self.k.player_id:
            return YOU
        return record.name if self.k.knows(record) else None

    def believes_dead(self, victim_id: str, deed: Deed) -> bool:
        """A death they know of on this timeline, recorded by the deed's turn: one they learned
        of later, from some other cause, isn't laid at this deed's door."""
        victim = self.k.state.characters.get(victim_id)
        if victim is None:
            return True  # a nameless victim, such as a villager of a massacre, is a death
        dead = CharacterStatus.DEAD.value
        known = [
            h
            for h in victim.status_history
            if self.k.player_id in h.known_by and h.timeline_id == self.k.timeline
        ]
        if known:
            return known[-1].status == dead and known[-1].turn <= deed.turn
        if victim.status_history:
            return False  # changed only in ways they never learned of
        return victim.status.value == dead


# --- the projection ------------------------------------------------------------------------


class _Knowledge:
    """The player character's knowledge of one state."""

    def __init__(self, state: WorldState, language: Language = EN) -> None:
        self.state = state
        self.language = language
        self.player_id = state.player_id
        self.now = state.world_s
        self.timeline = state.timeline_id
        # G1: what the story's start still holds back from the player's screens.
        self.untold = untold_mod.held(state)
        # The facts the player character knows, by subject, in the order they were learned.
        known = sorted(
            (
                f
                for f in state.facts.values()
                if self.player_id in f.known_by and f.timeline_id == self.timeline and self.told(f)
            ),
            key=lambda f: (f.world_s, natural_key(f.id)),
        )
        self.facts_by_subject: dict[str, list[str]] = {}
        for fact in known:
            for subject_id in dict.fromkeys(fact.subject_ids):
                self.facts_by_subject.setdefault(subject_id, []).append(fact.text)

    def knows(self, record) -> bool:
        return self.player_id in record.known_by

    def told(self, fact: Fact) -> bool:
        """G1: whether a thing the character knows is the player's to read yet. One about
        someone the story's start still holds back waits for them (`engine.untold`)."""
        return self.untold.people.isdisjoint(fact.subject_ids)

    def name_of(self, record_id: str) -> str | None:
        for collection in (self.state.characters, self.state.places, self.state.factions):
            record = collection.get(record_id)
            if record is not None and (record_id == self.player_id or self.knows(record)):
                return record.name
        return None

    def facts_about(self, subject_id: str) -> list[str]:
        return list(self.facts_by_subject.get(subject_id, []))

    def transfer_text(self, transfer: Transfer) -> str:
        """C10. Something the player character gained or lost, in the story's language, naming
        the other side only if they know who it was: "To Milo: 12 copper coins". How it went
        (stolen, paid) is the model's word, in English, so it is left to the models' record."""
        words = _WORDS[self.language]
        what = transfer.name
        if transfer.money or transfer.quantity > 1:
            what = f"{number_label(transfer.quantity, self.language)} {transfer.name}"
        you = self.player_id
        if transfer.from_id == you:
            key, other = ("to", transfer.to_id) if transfer.to_id else ("lost", None)
        else:
            key, other = ("from", transfer.from_id) if transfer.from_id else ("gained", None)
        who = (self.name_of(other) or words["someone"]) if other else ""
        text = words[key].format(who=who, what=what)
        if key == "from" and self.language is CA and who[:1].casefold() in "aeiouhàèéíòóú":
            text = f"D'{who}: {what}"  # Catalan elides "de" before a vowel
        return _cap(text)

    def deed_text(self, deed: Deed) -> str:
        """A deed in the world's words (G16), naming only whom the player character knows and
        telling a death only where they know of it (C6): "You killed Zhao Kun at the well." A
        deed the world has no words for keeps its own."""
        told = tell(self.state, deed, teller=_PlayerTeller(self), language=self.language)
        return told or own_words(deed, self.language)

    def deeds(self) -> list[Deed]:
        deeds = [
            d
            for d in self.state.deeds.values()
            if d.timeline_id == self.timeline
            and (d.actor_id == self.player_id or self.player_id in d.known_by)
        ]
        deeds.sort(key=lambda d: (d.world_s, natural_key(d.id)))
        return deeds

    def told_deeds(self) -> list[tuple[Deed, str, str, str]]:
        """The deeds the player character knows, in time order, each with its telling, when it
        was and who saw it. Deeds that would read the same in all three show once: a fight of
        four blows is one entry, not four."""
        return [(deeds[0], text, when, known) for deeds, text, when, known in self.deed_groups()]

    def goal(self, goal: Goal) -> GoalEntry:
        """N2. An active goal: where Memory shows it, where it came from in words ("Asked of you
        by Master Wen, day 3") and where it stands. Who brought it is named only if the
        character knows them (C6)."""
        words = _WORDS[self.language]
        origin = goals_mod.origin(self.state, goal)
        lead = self.state.leads.get(goal.lead_id or "")
        who = self.name_of(lead.from_id) if lead is not None and lead.from_id else None
        if origin is GoalOrigin.ASKED and who is None:
            origin = GoalOrigin.TAKEN
        # Asked on the day the lead was offered; the rest on the day the goal was set.
        when = lead.offered_s if origin is GoalOrigin.ASKED and lead is not None else goal.set_s
        label = words[f"goal_{origin.value}"].format(who=who)
        if origin is not GoalOrigin.START and when is not None:
            date = date_label(self.state.bible.calendar, when, self.language)
            label = words["goal_on"].format(what=label, date=date[:1].lower() + date[1:])
        return GoalEntry(
            id=goal.id,
            text=goal.text,
            kind=goals_mod.kind(self.state, goal),
            origin=origin,
            origin_label=label,
            progress=goal.progress or None,
        )

    def goals(self) -> list[GoalEntry]:
        """The active goals: the thread the player follows first, then their own, then the ones
        on the side. Within a group the one set or moved last leads, so a goal the story left
        alone long ago sinks under the ones it is busy with."""
        order = list(GoalKind)
        active = [
            g
            for g in self.state.goals.values()
            # G1: a goal the story's start holds back shows once the story tells it.
            if g.status is GoalStatus.ACTIVE and g.id not in self.untold.goals
        ]
        active.sort(key=lambda g: natural_key(g.id))
        active.sort(key=lambda g: max(g.set_turn, g.moved_turn or 0), reverse=True)
        return sorted(map(self.goal, active), key=lambda e: order.index(e.kind))

    def goals_done(self) -> list[GoalDoneEntry]:
        """The player character's goals that are over, in the order they closed: achieved, failed
        or given up. One that only repeated another isn't listed, and neither are those of the
        character before them (N6)."""
        since = goals_mod.theirs_since(self.state)
        over = [
            g
            for g in self.state.goals.values()
            if g.status not in (GoalStatus.ACTIVE, GoalStatus.MERGED) and g.set_turn > since
        ]
        calendar = self.state.bible.calendar
        return [
            GoalDoneEntry(
                id=g.id,
                text=g.text,
                how=g.status,
                when_label=(
                    date_label(calendar, g.closed_s, self.language)
                    if g.closed_s is not None
                    else None
                ),
            )
            for g in sorted(over, key=lambda g: (g.closed_turn or 0, natural_key(g.id)))
        ]

    def deed_groups(self) -> list[tuple[list[Deed], str, str, str]]:
        """`told_deeds`, each entry with every deed it stands for, the first one first."""
        groups: dict[tuple[str, str, str], tuple[list[Deed], str, str, str]] = {}
        for deed in self.deeds():
            text = self.deed_text(deed)
            when = clock_label(self.state.bible.calendar, deed.world_s, self.language)
            known = self.known_label(deed)
            mark = (normalize(text), when, known)
            if mark in groups:
                groups[mark][0].append(deed)
            else:
                groups[mark] = ([deed], text, when, known)
        return list(groups.values())

    def rumors(self) -> list[RumorEntry]:
        """The rumors the player character heard, by when they last heard them (W2, C6). The same
        words show once, however many deeds or tellers they came from, dated by the latest
        hearing; words they know for sure and words they only heard stay apart. One they know
        firsthand is confirmed, or false, rather than unconfirmed: what they lived needs no
        confirming."""
        said: dict[tuple[str, Certainty], Rumor] = {}
        for rumor in self.state.rumors.values():
            if self.player_id not in rumor.heard_at or rumor.timeline_id != self.timeline:
                continue
            mark = (normalize(rumor.text), certainty(self.state, self.player_id, rumor))
            kept = said.get(mark)
            if kept is None or self._heard(rumor) > self._heard(kept):
                said[mark] = rumor
        words = _WORDS[self.language]
        return [
            RumorEntry(
                id=rumor.id,
                text=rumor.text,
                heard_label=words["heard"].format(
                    when=ago_label(self.now - rumor.heard_at[self.player_id], self.language)
                ),
                certainty=sure,
                unconfirmed=sure is Certainty.UNCONFIRMED,
            )
            for (_, sure), rumor in sorted(said.items(), key=lambda item: self._heard(item[1]))
        ]

    def _heard(self, rumor: Rumor) -> tuple[int, tuple]:
        return rumor.heard_at[self.player_id], natural_key(rumor.id)

    def known_label(self, deed: Deed) -> str:
        """Who saw it, as far as the player character knows (W2, C6)."""
        return self.seen(deed)[1]

    def seen(self, deed: Deed) -> tuple[DeedSeen, str]:
        """W2, C6. Who saw a deed as far as the player character knows, as a value and in
        words."""
        words = _WORDS[self.language]
        if deed.actor_id != self.player_id:
            if self.player_id in deed.witness_ids:
                return DeedSeen.WATCHED, words["saw"]
            return DeedSeen.HEARD_OF, words["heard_of"]
        # In stopped time every witness is immune to the stop and unnoticed (W10a), unless the
        # world later reveals them by taking them off `unnoticed_witness_ids`.
        noticed = [
            w
            for w in deed.witness_ids
            if w != self.player_id and w not in deed.unnoticed_witness_ids
        ]
        if noticed:
            names = [n for n in (self.name_of(w) for w in noticed) if n]
            others = len(noticed) - len(names)
            if not names:
                return DeedSeen.SEEN, words["seen"]
            if others:
                names.append(words["others" if others > 1 else "other"].format(count=others))
            return DeedSeen.SEEN, words["seen_by"].format(names=_join(names, self.language))
        if deed.visibility is Visibility.PUBLIC and not deed.in_stopped_time:
            return DeedSeen.PUBLIC, words["public"]
        return DeedSeen.UNSEEN, words["unseen"]

    def _noticed(self, deed: Deed) -> list[str]:
        """Who saw a deed of the player character's, as far as they know, in a fixed order."""
        return sorted(
            (
                w
                for w in dict.fromkeys(deed.witness_ids)
                if w != self.player_id and w not in deed.unnoticed_witness_ids
            ),
            key=natural_key,
        )

    def trail(self, deeds: list[Deed]) -> list[TrailEntry]:
        """W2, W11, C6. What the player character knows became of a deed of theirs, or of the
        deeds one entry stands for, in the order it happened: who of those who saw it they saw
        go off to tell, and whom; who of them is dead; what a scene told them is being said of
        it; and who came to them over it. Only what was in front of them: whether a runner got
        there, who was told and who has heard are the world's to know, so none of it is here.
        Nothing for someone else's deed."""
        words = _WORDS[self.language]
        state = self.state
        entries: list[TrailEntry] = []

        def add(kind: TrailKind, text: str) -> None:
            entry = TrailEntry(kind=kind, text=_cap(text))
            if entry not in entries:
                entries.append(entry)

        deeds = [d for d in deeds if d.actor_id == self.player_id]
        for deed in deeds:
            noticed = self._noticed(deed)
            for witness_id in noticed:
                faction_id = deed.went_to_tell.get(witness_id)
                if faction_id is None:
                    continue
                who = self.name_of(witness_id) or words["someone"]
                if whom := self.name_of(faction_id):
                    add(TrailKind.WENT, words["went_to"].format(who=who, whom=whom))
                else:
                    add(TrailKind.WENT, words["went"].format(who=who))
            for witness_id in noticed:
                witness = state.characters.get(witness_id)
                if witness is None:
                    continue
                who = self.name_of(witness_id) or words["who_saw"]
                status, presumed = believed_status(
                    witness.status_history,
                    witness.status.value,
                    self.player_id,
                    initial=CharacterStatus.ALIVE.value,
                )
                if status == CharacterStatus.DEAD.value:
                    key = "is_presumed_dead" if presumed else "is_dead"
                    add(TrailKind.DEAD, words[key].format(who=who))
        later: list[tuple[int, tuple, TrailKind, str]] = []
        said: dict[str, Rumor] = {}
        for deed in deeds:
            for rumor in self._heard_of.get(deed.id, []):
                kept = said.get(mark := normalize(rumor.text))
                if kept is None or self._heard(rumor) > self._heard(kept):
                    said[mark] = rumor
            for event in self._answers_to.get(deed.id, []):
                if text := self._came(event):
                    key = natural_key(event.id)
                    later.append((event.applied_s or 0, key, TrailKind.CAME, text))
        for rumor in said.values():
            heard_s = rumor.heard_at[self.player_id]
            when = ago_label(self.now - heard_s, self.language)
            text = words["heard_said"].format(when=when, text=rumor.text)
            later.append((heard_s, natural_key(rumor.id), TrailKind.HEARD, text))
        for _, _, kind, text in sorted(later, key=lambda entry: entry[:2]):
            add(kind, text)
        return entries

    @cached_property
    def _heard_of(self) -> dict[str, list[Rumor]]:
        """The rumors of each deed that a scene told the player character, by the deed's id."""
        heard: dict[str, list[Rumor]] = {}
        for rumor in self.state.rumors.values():
            if rumor.deed_id is None or rumor.timeline_id != self.timeline:
                continue
            if self.player_id in rumor.heard_at:
                heard.setdefault(rumor.deed_id, []).append(rumor)
        return heard

    @cached_property
    def _answers_to(self) -> dict[str, list[PendingEvent]]:
        """The answers the world gave each deed that have arrived, by the deed's id."""
        answers: dict[str, list[PendingEvent]] = {}
        for event in self.state.pending_events.values():
            deed_id = event.payload.get("deed_id")
            if event.kind == Kind.ANSWER and event.status is EventStatus.APPLIED and deed_id:
                answers.setdefault(str(deed_id), []).append(event)
        return answers

    @cached_property
    def _met_events(self) -> set[str]:
        """The events that happened in front of the player character: those a fact they know
        came of."""
        return {
            f.origin.ref_id
            for f in self.state.facts.values()
            if f.origin is not None
            and f.origin.kind is OriginKind.EVENT
            and f.origin.ref_id is not None
            and self.player_id in f.known_by
        }

    def _came(self, event: PendingEvent) -> str | None:
        """W4, W5, C6. Someone who came to the player character over a deed and found them, in
        words: who it was when they know them, and what for. None for an answer that sent
        nobody and for one that came and found them gone."""
        if event.timeline_id != self.timeline or event.id not in self._met_events:
            return None
        if event.payload.get("target_id") != self.player_id:
            return None
        try:
            answer = Answer(str(event.payload.get("answer")))
        except ValueError:
            return None
        if answer not in ARRIVING:
            return None
        words = _WORDS[self.language]
        source_id = event.payload.get("avenger_id") or event.payload.get("faction_id")
        who = self.name_of(str(source_id)) if source_id else None
        # A faction whose name is a plural ("Los Tigres Negros") takes a plural verb.
        many = who is not None and who.split(" ")[0].lower() in _PLURAL_ARTICLES
        applied_s = self.now if event.applied_s is None else event.applied_s
        when = ago_label(self.now - applied_s, self.language)
        return words["came_many" if many else "came"].format(
            who=who or words["someone"], what=words[_CAME_FOR.get(answer, "came_to_you")], when=when
        )

    def open_label(self, deeds: list[Deed], trail: list[TrailEntry]) -> str | None:
        """C6. That who else knows of a deed of theirs is nothing the player character can tell,
        where that is an open question: word of it went somewhere or came back, or someone saw
        what is news by the world's norms (W12) and no bout both sides agreed to (W1). What was
        done in public is known, and what nobody saw and nothing came of is left alone."""
        mine = [d for d in deeds if d.actor_id == self.player_id]
        if not mine or any(
            d.visibility is Visibility.PUBLIC and not d.in_stopped_time for d in mine
        ):
            return None
        news = any(
            d.severity >= RUMOR_MIN_SEVERITY and not d.agreed and self._noticed(d) for d in mine
        )
        stirred = any(entry.kind is not TrailKind.DEAD for entry in trail)
        return _WORDS[self.language]["who_else"] if news or stirred else None

    # --- entries --------------------------------------------------------------------------

    def person(self, c: Character) -> PersonEntry:
        lines = [c.description] if c.description else []
        status, presumed = believed_status(
            c.status_history, c.status.value, self.player_id, initial=CharacterStatus.ALIVE.value
        )
        presumed = presumed and status == CharacterStatus.DEAD.value
        stage, bond_line = self.bond(c, dead=status == CharacterStatus.DEAD.value and not presumed)
        if kin := self.kin_line(c):
            lines.insert(0, kin)
        lines += self.facts_about(c.id)
        attitude = None
        if self.player_id in c.met_by:
            attitude = attitude_of(c.attitude_toward(self.player_id).shown_affinity)
        return PersonEntry(
            id=c.id,
            name=c.name,
            lines=lines,
            attitude=attitude,
            attitude_label=(
                None if attitude is None else _ATTITUDES[self.language][_ATTITUDE_AT[attitude]]
            ),
            status=status,
            presumed=presumed,
            status_label=_status_words(status, presumed, self.language),
            bond=stage,
            bond_line=bond_line,
        )

    def bond(self, c: Character, *, dead: bool) -> tuple[BondStage | None, str | None]:
        """W17, C6. The romance between someone and the player character as the character
        knows it: its stage, and one line on how it came there. The one that still stands, or
        else the latest that ended. An interest nothing has answered doesn't take the place
        of a romance that ended: that one shows until something between the two is answered
        again.

        The character took part in every step of it, so they know them all but one: a death
        they haven't learned of (`dead` is whether they know the other died) ended nothing as
        far as they know, and the romance shows as it stood. How drawn the other is to them
        is hidden truth and never shows. An interest that ended before anything began is
        nothing to remember."""
        state, me = self.state, self.player_id
        live = bonds.live(state, me, c.id)
        shown = self._romance(live, c, dead=dead)
        if live is None or live.stage is BondStage.INTEREST:
            ended = self._romance(bonds.last_over(state, me, c.id), c, dead=dead)
            if ended[0] is not None:
                return ended
        return shown

    def _romance(
        self, bond: Bond | None, c: Character, *, dead: bool
    ) -> tuple[BondStage | None, str | None]:
        """One romance on record as the player character knows it: its stage and its line."""
        me = self.player_id
        steps = [] if bond is None else list(bond.steps)
        if bond is not None and bond.end is BondEnd.DEATH and not dead:
            steps = steps[:-1]
        if bond is None or not steps:
            return None, None
        words = _BOND_WORDS[self.language]
        last = steps[-1]
        if last.stage is not BondStage.OVER:
            theirs = last.stage is BondStage.INTEREST and bond.a_id != me
            if last.by_id is None:
                # As the story opened: how it stands, with no day to give.
                text = words["is_theirs"] if theirs else words["is"][last.stage]
                line = text.format(who=c.name)
            else:
                text = words["came_theirs"] if theirs else words["came"][last.stage]
                line = self._on(text.format(who=c.name), last.world_s)
            return last.stage, f"{line}."
        was = words["was"].get(steps[-2].stage) if len(steps) > 1 else None
        if was is None:
            return None, None
        was = was.format(who=c.name)
        if bond.end is BondEnd.DEATH:
            return BondStage.OVER, words["until_death"].format(was=was) + "."
        key = {me: "until_you", c.id: "until_them"}.get(last.by_id, "until_over")
        line = self._on(words[key].format(was=was), last.world_s)
        return BondStage.OVER, f"{line}."

    def _on(self, what: str, world_s: int) -> str:
        """Words with the day they happened: "You became a couple, day 9"."""
        date = date_label(self.state.bible.calendar, world_s, self.language)
        return _WORDS[self.language]["goal_on"].format(what=what, date=date[:1].lower() + date[1:])

    @cached_property
    def descendants(self) -> dict[str, int]:
        return descendants(self.state, self.player_id)

    def kin_line(self, c: Character) -> str | None:
        """N6: how someone is family to the player character, if they are."""
        if c.id in self.state.player.parent_ids:
            return _WORDS[self.language]["parent"]
        return _DESCENDANT_WORDS[self.language].get(self.descendants.get(c.id, 0))

    def place(self, p: Place) -> PlaceEntry:
        lines = [_cap(p.kind)] if p.kind else []
        if p.description:
            lines.append(p.description)
        status, _ = believed_status(
            p.status_history, p.status.value, self.player_id, initial=PlaceStatus.THRIVING.value
        )
        if status != PlaceStatus.THRIVING.value:
            lines.append(_status_words(status, language=self.language))
        if self.player_id not in p.visited_by:
            lines.append(_WORDS[self.language]["not_been"])
        lines += self.facts_about(p.id)
        return PlaceEntry(id=p.id, name=p.name, lines=lines)

    def faction(self, f: Faction) -> FactionEntry:
        lines = [_cap(f.kind)] if f.kind else []
        if f.description:
            lines.append(f.description)
        status, _ = believed_status(
            f.status_history, f.status.value, self.player_id, initial=FactionStatus.INTACT.value
        )
        if status != FactionStatus.INTACT.value:
            lines.append(_status_words(status, language=self.language))
        lines += self.facts_about(f.id)
        return FactionEntry(
            id=f.id,
            name=f.name,
            lines=lines,
            esteem=esteem_of(f.player_reputation),
            dread=dread_of(f.player_reputation),
            standing_label=standing_label(f.player_reputation, self.language),
        )

    def player_lines(self, player: Character) -> list[str]:
        lines = [player.description] if player.description else []
        resources = player.sheet.resources
        for title in (resources.title, resources.rank):
            if title:
                lines.append(_cap(title))
        lines += self.ladder_lines(player)
        return lines

    def ladder_lines(self, player: Character) -> list[str]:
        lines = []
        for position in player.sheet.ladders:
            ladder = self.state.bible.ladder(position.ladder_id)
            if ladder is None or position.rung >= len(ladder.rungs):
                continue
            rung = ladder.rungs[position.rung].name
            rank = rank_of(player, ladder)
            stage = ""
            if rank is not None:
                # G19: how full their rank is, in a word.
                label = rank_stage_label(rank.stage, self.language)
                stage = f", {label[:1].lower()}{label[1:]}"
            lines.append(_cap(f"{ladder.name}: {rung}{stage}"))
        return lines

    def condition_lines(self, player: Character) -> list[str]:
        condition = player.sheet.condition
        lines = [_HEALTH_WORDS[self.language][condition.health]]
        lines += [_cap(wound_said(w.text, self.language)) for w in condition.wounds]
        lines += [_cap(s.name) for s in condition.states]
        lines += [_cap(f"{r.name}: {r.level}%") for r in condition.reserves]
        expecting = player.expecting
        if expecting is not None and player.alive:
            # N6: a child on the way, born when it is due.
            due = in_label(max(0, expecting.due_s - self.now), self.language)
            lines.append(_WORDS[self.language]["expecting"].format(due=due))
        return lines

    def power_lines(self, player: Character) -> list[str]:
        lived = player.personal_s(self.now)
        lines = []
        ready = _WORDS[self.language]["ready"]
        for power in player.sheet.powers:
            ready_at = power.ready_at_personal_s
            if ready_at is not None and ready_at > lived:
                when = in_label(ready_at - lived, self.language)
                lines.append(_cap(f"{power.name}: {ready} {when}"))
            else:
                lines.append(_cap(f"{power.name}: {ready}"))
            # G13: what using it costs, as the sheet says, so nothing about it is a surprise.
            costs = power.costs_text
            if costs:
                cost = _WORDS[self.language]["cost"].format(power=power.name, costs=costs)
                lines.append(_cap(cost))
        # G25, A4: the techniques they know, those they made their own in play included, each
        # with how well they have it and the uses counted toward the next mastery.
        lines += [
            self.technique_line(t, technique_pace(player, t)) for t in player.sheet.techniques
        ]
        return lines

    def technique_line(self, technique: Technique, gift: float) -> str:
        """A4. A technique with how well they have it, and its count toward the next mastery at
        their own pace of learning."""
        words = _WORDS[self.language]
        mastery = _MASTERY_WORDS[self.language][technique.mastery]
        need = levels.uses_to_next(technique.mastery, gift)
        if need is None:
            return _cap(words["technique"].format(name=technique.name, mastery=mastery))
        line = words["technique_uses"]
        return _cap(
            line.format(name=technique.name, mastery=mastery, uses=technique.uses, need=need)
        )

    def talent_lines(self, player: Character) -> list[str]:
        """A4. The talents on their sheet as the engine reads them, each with its strength and
        the pace it gives, then every thing a talent or a weakness reaches: how fast it grows
        now, how it stands to each talent that reaches it, since their paces add, and the
        bridges that hold. What was ruled outside every talent is one line at the end. A sheet
        saved before talent was a record shows none."""
        sheet = player.sheet
        if not sheet.talents:
            return []
        words = _WORDS[self.language]
        lines = []
        for talent in talent_mod.talents_of(player):
            strength = _TALENT_WORDS[self.language][talent.strength]
            line = words["talent"].format(name=talent.name, strength=strength, covers=talent.covers)
            lines.append(_cap(line if talent.covers else line.removesuffix(": ")))
        return lines + self.talent_notes(player)

    def talent_notes(self, player: Character) -> list[str]:
        """A4. Every thing a talent or a weakness of theirs reaches, once ruled on: how fast it
        grows, which talents reach it and the bridges that hold, then one line for what was
        ruled outside every talent."""
        sheet = player.sheet
        if not sheet.talents:
            return []
        words = _WORDS[self.language]
        lines = []
        named = {r.key: r.what for r in sheet.talent_rulings}
        for bridge in sheet.bridges:
            if bridge.steps:
                named.setdefault(bridge.key, bridge.what)
        outside: list[str] = []
        for key, what in named.items():
            stands = talent_mod.standing(player, key)
            if not stands.reaches and stands.slowed_by is None:
                outside.append(what or key)
                continue
            pace = _pace_words(stands.pace, self.language)
            line = words["ruled"].format(what=what or key, pace=pace)
            for fit, (one, several) in _FIT_WORDS[self.language].items():
                names = [reach.talent.name for reach in stands.reaches if reach.fit is fit]
                if names:
                    said = several if len(names) > 1 else one
                    line += said.format(_join(names, self.language))
            if stands.slowed_by is not None:
                line += words["slowed"].format(talent=stands.slowed_by.name)
            lines.append(_cap(line))
            # The bridges that carry it there, from any talent that reaches it.
            reaching = {reach.talent.id for reach in stands.reaches}
            held = [
                b.rests_on
                for b in sheet.bridges
                if b.key == key and b.talent_id in reaching and b.steps
            ]
            if held:
                label = words["bridges" if len(held) > 1 else "bridge"]
                lines.append(label.format(grounds="; ".join(held)))
        if outside:
            lines.append(words["outside"].format(things="; ".join(outside)))
        return lines

    def resource_lines(self, player: Character) -> list[str]:
        resources = player.sheet.resources
        lines = []
        if resources.money or resources.currency:
            money = number_label(resources.money, self.language)
            lines.append(f"{money} {resources.currency}".strip())
        for item in sorted(resources.items, key=lambda i: natural_key(i.id)):
            if item.carried:
                count = f" ({item.quantity})" if item.quantity > 1 else ""
                lines.append(_cap(f"{item.name}{count}"))
        return lines

    # --- the sheet, in sections -------------------------------------------------------------

    def sheet(self, player: Character) -> SheetView:
        """G13, G16. The player character's sheet in sections, in the world's words."""
        sheet = player.sheet
        resources = sheet.resources
        money = None
        if resources.money or resources.currency:
            amount = number_label(resources.money, self.language)
            money = f"{amount} {resources.currency}".strip()
        held = sorted(resources.items, key=lambda i: (not i.carried, natural_key(i.id)))
        kinds = _ITEM_KIND_WORDS[self.language]
        trait_kinds = _TRAIT_KIND_WORDS[self.language]
        return SheetView(
            about=self.about(player),
            description=player.description,
            condition=self.condition(player),
            paths=self.paths(player),
            money_label=money,
            items=[
                SheetItem(
                    name=_cap(item.name),
                    kind=item.kind,
                    kind_label=kinds.get(item.kind, ""),
                    description=item.description,
                    history=item.history,
                    quantity=item.quantity,
                    carried=item.carried,
                )
                for item in held
                if item.quantity > 0
            ],
            skills=[
                SheetSkill(
                    name=_cap(skill.name),
                    level=skill.level,
                    level_label=skill_level_label(skill.level, self.language),
                    dice=levels.SKILL_DICE[skill.level],
                    notes=skill.notes,
                )
                for skill in sorted(sheet.skills, key=lambda s: -s.level.rank)
            ],
            powers=self.powers(player),
            techniques=[self.technique(player, t) for t in sheet.techniques],
            traits=[
                SheetTrait(
                    name=_cap(trait.name),
                    kind=trait.kind,
                    kind_label=trait_kinds[trait.kind],
                    description=trait.description,
                )
                for trait in sheet.traits
            ],
            temperament=[t for t in sheet.disposition.temperament.traits if t.strip()],
            talents=self.talents(player),
            talent_notes=self.talent_notes(player),
            grew=self.grew(player),
        )

    def about(self, player: Character) -> list[str]:
        """Who they are in a few words: their place in each faction they know they belong to,
        a title, and their age."""
        resources = player.sheet.resources
        parts = []
        for membership in player.memberships:
            faction = self.state.factions.get(membership.faction_id)
            name = faction.name if faction is not None and self.knows(faction) else ""
            parts.append(", ".join(part for part in (membership.rank, name) if part))
        parts.append(resources.title)
        if not player.memberships:
            parts.append(resources.rank)
        if player.age is not None:
            parts.append(_WORDS[self.language]["age"].format(age=player.age))
        said: dict[str, str] = {}
        for part in parts:
            if part.strip():
                said.setdefault(part.strip().casefold(), _cap(part.strip()))
        return list(said.values())

    def condition(self, player: Character) -> SheetCondition:
        """G13. How they are: health, each wound, each passing state with when it passes, and
        what is left of each reserve."""
        condition = player.sheet.condition
        lived = player.personal_s(self.now)
        words = _WORDS[self.language]
        states = []
        for state in condition.states:
            until = state.until_personal_s
            ends = None
            if until is not None and until > lived:
                ends = words["lasts"].format(when=in_label(until - lived, self.language))
            states.append(SheetState(name=_cap(state.name), effect=state.effect, ends_label=ends))
        expecting = None
        if player.expecting is not None and player.alive:
            due = in_label(max(0, player.expecting.due_s - self.now), self.language)
            expecting = words["expecting"].format(due=due)
        return SheetCondition(
            health=condition.health,
            health_label=_HEALTH_WORDS[self.language][condition.health],
            wounds=[
                SheetWound(text=_cap(wound_said(w.text, self.language)), lasting=w.lasting)
                for w in condition.wounds
            ],
            states=states,
            reserves=[SheetReserve(name=_cap(r.name), level=r.level) for r in condition.reserves],
            expecting_label=expecting,
        )

    def paths(self, player: Character) -> list[SheetPath]:
        """G18, C6. Each ladder as far as they know it: the rungs they climbed with when, their
        own, over it the rungs they have heard of (`engine.path`), and whoever they have seen
        stand higher still. A ladder they don't stand on shows once they have heard of a rung
        of it."""
        paths = []
        for ladder in self.state.bible.ladders:
            own = path_mod.own_rung(player, ladder.id)
            if own >= len(ladder.rungs):
                continue
            reached = self._reached(player, ladder)
            rungs = [
                SheetRung(name=_cap(rung.name), note=self._dated("rung_left", reached.get(i + 1)))
                for i, rung in enumerate(ladder.rungs[: max(own, 0)])
            ]
            if own >= 0:
                here = ladder.rungs[own]
                rank = rank_of(player, ladder)
                stage = ""
                if rank is not None:
                    # G19: the rank fills toward the next rung, and at its peak it can be tried.
                    stage = rank_stage_label(rank.stage, self.language)
                    if rank.full:
                        stage = _WORDS[self.language]["rank_ready"]
                rungs.append(
                    SheetRung(
                        name=_cap(here.name),
                        stage=stage,
                        filled=round(rank.filled, 3) if rank is not None else None,
                        description=here.description,
                        note=self._dated("rung_reached", reached.get(own)),
                    )
                )
            standings = path_mod.known(self.state, player, ladder)
            above = [
                SheetRungAbove(
                    name=_cap(ladder.rungs[standing.rung].name),
                    known=standing.known,
                    note=self._rung_note(standing),
                    said=path_mod.about(self.state, player, ladder.rungs[standing.rung].name),
                    gap_below=standing.gap_below,
                )
                for standing in standings
            ]
            if rungs or above:
                top = standings[-1].rung if standings else own
                higher = self._higher(path_mod.higher_still(self.state, player, ladder, top))
                paths.append(
                    SheetPath(name=_cap(ladder.name), rungs=rungs, above=above, higher=higher)
                )
        return paths

    def _higher(self, ids: list[str]) -> str:
        """Who they have seen stand above every rung they know of, by name as far as they know
        the names, or that someone does."""
        if not ids:
            return ""
        words = _WORDS[self.language]
        names = [name for name in map(self.name_of, ids) if name][:HIGHER_NAMES]
        if not names:
            return words["higher_someone"]
        key = "higher_one" if len(names) == 1 else "higher_many"
        return words[key].format(who=_join(names, self.language))

    def _reached(self, player: Character, ladder: PowerLadder) -> dict[int, int]:
        """When they reached each rung of a ladder, by its index, as far as their growth holds
        it: a breakthrough is recorded under the rung's name (`engine.resolve.powers.growth`)."""
        index = {rung.name: i for i, rung in enumerate(ladder.rungs)}
        return {
            index[gain.what]: gain.world_s
            for gain in player.sheet.growth
            if gain.source == GrowthKind.BREAKTHROUGH.value and gain.what in index
        }

    def _dated(self, key: str, world_s: int | None, **names: str) -> str:
        """Words of the sheet with the day they hold for ("Reached, day 9"), or nothing where
        the record holds no day."""
        if world_s is None:
            return ""
        return self._on(_WORDS[self.language][key].format(**names), world_s)

    def _rung_note(self, standing: path_mod.Standing) -> str:
        """How they know of a rung above their own: confirmed before someone they can name, or
        only confirmed (C6), learned from something they know, heard of as everyone has, or
        heard of in a scene."""
        if standing.known_s is not None:
            who = self.name_of(standing.known_from or "")
            if who is None:
                return self._dated("rung_known", standing.known_s)
            of_who = of_name(who, self.language)
            return self._dated("rung_known_before", standing.known_s, who=who, of_who=of_who)
        if standing.known:
            return _WORDS[self.language]["rung_learned"]
        if standing.common:
            return _WORDS[self.language]["rung_common"]
        return self._dated("rung_heard", standing.heard_s)

    def grew(self, player: Character) -> list[SheetGain]:
        """A4, G17. How the character grew, latest first: each gain on their record with its
        date, in the story's language. The record keeps a gain in the engine's own words, so it
        is read back (`growth.read_gain`) and said here; a loss, or a gain in words nobody
        writes any more, is left out."""
        words = _WORDS[self.language]
        calendar = self.state.bible.calendar
        found: list[SheetGain] = []
        for gain in reversed(player.sheet.growth):
            read = None if gain.loss else read_gain(gain)
            if read is None:
                continue
            what = _cap(gain.what)
            if read.kind is GainKind.BREAKTHROUGH:
                text = words["grew_breakthrough"].format(what=what)
            elif read.kind is GainKind.LEARNED:
                text = words["grew_learned"].format(what=what)
            elif read.kind is GainKind.NEW_USE:
                text = words["grew_new_use"].format(what=what, power=read.power)
            elif isinstance(read.now, SkillLevel):
                level = skill_level_label(read.now, self.language)
                text = words["grew_level"].format(what=what, level=level)
            elif isinstance(read.now, RankStage):
                level = rank_stage_label(read.now, self.language)
                text = words["grew_level"].format(what=what, level=level)
            else:
                level = _cap(_MASTERY_WORDS[self.language][read.now])
                text = words["grew_level"].format(what=what, level=level)
            found.append(
                SheetGain(
                    kind=read.kind,
                    when=date_label(calendar, gain.world_s, self.language),
                    text=text,
                    how=_GAIN_HOW_WORDS[self.language][read.how] if read.how else "",
                )
            )
            if len(found) == GREW_LIMIT:
                break
        return found

    def powers(self, player: Character) -> list[SheetPower]:
        """G13. Each power with its limits, what it costs as the sheet says, and whether it is
        ready (W10a)."""
        lived = player.personal_s(self.now)
        ready = _WORDS[self.language]["ready"]
        powers = []
        for power in player.sheet.powers:
            ready_at = power.ready_at_personal_s
            waiting = ready_at is not None and ready_at > lived
            label = f"{ready} {in_label(ready_at - lived, self.language)}" if waiting else ready
            powers.append(
                SheetPower(
                    name=_cap(power.name),
                    description=power.description,
                    limits=[_cap(limit) for limit in power.limits if limit.strip()],
                    cost=_cap(power.costs_text),
                    ready=not waiting,
                    ready_label=_cap(label),
                    secret=power.secret,
                )
            )
        return powers

    def technique(self, player: Character, technique: Technique) -> SheetTechnique:
        """A4, G25. A technique with how well they have it, the dice it throws (A3) and its
        count toward the next mastery at their own pace."""
        return SheetTechnique(
            name=_cap(technique.name),
            style=technique.style,
            effect=technique.effect,
            cost=technique.cost,
            source_label=self.technique_source(technique),
            mastery=technique.mastery,
            mastery_label=_cap(_MASTERY_WORDS[self.language][technique.mastery]),
            dice=levels.MASTERY_DICE[technique.mastery],
            uses=technique.uses,
            need=levels.uses_to_next(technique.mastery, technique_pace(player, technique)),
        )

    def technique_source(self, technique: Technique) -> str:
        """Where a technique comes from, as far as the record names it: their own making, or
        someone they know (C6). Anything else says nothing."""
        words = _WORDS[self.language]
        source = technique.learned_from
        if source in ("their own", "self"):
            return words["own_move"]
        teacher = self.state.characters.get(source)
        if teacher is None or not self.knows(teacher):
            return ""
        of_who = of_name(teacher.name, self.language)
        return words["learned_from"].format(who=teacher.name, of_who=of_who)

    def talents(self, player: Character) -> list[SheetTalent]:
        """A4. Their talents as the engine reads them, each with the pace it gives. A sheet
        saved before talent was a record shows none."""
        if not player.sheet.talents:
            return []
        strengths = TALENT_STRENGTH_WORDS[self.language]
        return [
            SheetTalent(
                name=_cap(talent.name),
                strength=talent.strength,
                strength_label=strengths[talent.strength],
                pace_label=_cap(_pace_words(2.0**talent.strength.steps, self.language)),
                covers=talent.covers,
            )
            for talent in talent_mod.talents_of(player)
        ]


# W4, W5: what someone who came to the player character came for, as Memory words it.
_CAME_FOR = {
    Answer.CONFRONT: "came_to_face",
    Answer.REVENGE: "came_for_revenge",
    Answer.ARREST: "came_to_arrest",
    Answer.INVESTIGATE: "came_to_look",
    Answer.HUNTERS: "came_for_you",
    Answer.ARMY: "came_for_you",
    Answer.ELITE: "came_for_you",
    Answer.ASSASSIN: "came_for_you",
    Answer.SEAL: "came_for_you",
}
# The words a plural name opens with, in the three languages.
_PLURAL_ARTICLES = frozenset({"los", "las", "els", "les"})


def _cap(text: str) -> str:
    """Capitalises the first letter only, keeping names such as "Qi Condensation" intact."""
    return text[:1].upper() + text[1:]


def _join(names: list[str], language: Language = EN) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + _WORDS[language]["and"] + names[-1]


def _sort_name(name: str) -> str:
    folded = name.casefold()
    for article in ("the ", "a ", "an "):
        if folded.startswith(article):
            return folded[len(article) :]
    return folded


def _by_name(records):
    """Alphabetical, ignoring a leading article: "the Azure Cloud Sect" sorts under A."""
    return sorted(records, key=lambda r: (_sort_name(r.name), natural_key(r.id)))


def memory_view(state: WorldState, language: Language = EN) -> MemoryView:
    """The Memory screen (C6): only what the player character knows, with its fixed words in the
    story's language (S10)."""
    k = _Knowledge(state, language)
    player = state.player

    # G1: who and what the story's start still holds back shows once the story tells it
    # (`engine.untold`).
    people = [
        k.person(c) for c in _by_name(state.npcs()) if k.knows(c) and c.id not in k.untold.people
    ]
    places = [k.place(p) for p in _by_name(state.places.values()) if k.knows(p)]
    factions = [k.faction(f) for f in _by_name(state.factions.values()) if k.knows(f)]
    leads = []
    for lead in sorted(state.leads.values(), key=lambda le: (le.offered_s, natural_key(le.id))):
        if lead.status is not LeadStatus.OPEN:
            continue
        if lead.expires_s is not None and lead.expires_s <= k.now:
            continue
        expires = None
        if lead.expires_s is not None:
            when = in_label(lead.expires_s - k.now, language)
            expires = _WORDS[language]["ends"].format(when=when)
        leads.append(LeadEntry(id=lead.id, text=lead.text, expires_label=expires))
    rumors = k.rumors()
    deeds = []
    for group, text, when, known in k.deed_groups():
        trail = k.trail(group)
        deeds.append(
            DeedEntry(
                id=group[0].id,
                text=text,
                when_label=when,
                seen=k.seen(group[0])[0],
                known_label=known,
                trail=trail,
                open_label=k.open_label(group, trail),
            )
        )
    threads = [
        ThreadEntry(id=t.id, title=t.title, status=t.status)
        for t in sorted(state.threads.values(), key=lambda t: (t.opened_turn, natural_key(t.id)))
        if k.knows(t) and t.id not in k.untold.threads
    ]
    return MemoryView(
        character=CharacterCard(name=player.name, lines=k.player_lines(player)),
        people=people,
        places=places,
        factions=factions,
        goals=k.goals(),
        goals_done=k.goals_done(),
        leads=leads,
        rumors=rumors,
        deeds=deeds,
        threads=threads,
    )


# Gemini 3.5 Transcribe takes up to 1,000 terms but works best with about 100 (V6).
SPEECH_VOCABULARY_LIMIT = 100


def speech_vocabulary(state: WorldState, *, limit: int = SPEECH_VOCABULARY_LIMIT) -> list[str]:
    """The names the player character knows, as the speech model's custom vocabulary (V6, C6),
    so a dictated "Senior Brother Jo" comes back as Zhao.

    Most relevant first: the character's own name, the people in the scene, the place it is in,
    then everyone, everywhere and every faction the character knows, without a leading article.
    Never a name the character doesn't know (C6), and each name once.
    """
    k = _Knowledge(state)
    present = [state.characters.get(i) for i in state.scene.present_ids]
    here = state.places.get(state.scene.place_id or state.player.location_id or "")
    known = [
        *(c for c in present if c is not None and c.id != state.player_id and k.knows(c)),
        *([here] if here is not None and k.knows(here) else []),
        *(c for c in _by_name(state.npcs()) if k.knows(c)),
        *(p for p in _by_name(state.places.values()) if k.knows(p)),
        *(f for f in _by_name(state.factions.values()) if k.knows(f)),
    ]
    names: dict[str, str] = {}
    for name in (state.player.name, *(record.name for record in known)):
        name = _without_article(" ".join(name.split()))
        if name and name.casefold() not in names:
            names[name.casefold()] = name
    return list(names.values())[:limit]


def _without_article(name: str) -> str:
    """ "the Azure Cloud Sect" is heard as "Azure Cloud Sect": "the" is a common word. Only
    "the": "A" and "An" start names such as A Qing and An Lushan."""
    if name.casefold().startswith("the ") and len(name) > len("the "):
        return name[len("the ") :]
    return name


def clock_view(state: WorldState, language: Language = EN) -> ClockView:
    return ClockView(
        world_s=state.world_s,
        label=clock_label(state.bible.calendar, state.world_s, language),
        timeline_id=state.timeline_id,
    )


def status_view(state: WorldState, language: Language = EN) -> StatusView:
    """`/status` (A8, G16, W10): the player character's sheet in the world's words, their
    standing with the factions they know, the clock, and how long ago key events happened, with
    the fixed words in the story's language (S10)."""
    k = _Knowledge(state, language)
    player = state.player
    lines = (
        k.ladder_lines(player)
        + k.condition_lines(player)
        + k.power_lines(player)
        + k.talent_lines(player)
        + k.resource_lines(player)
    )
    reputation = [
        ReputationEntry(name=f.name, label=standing_label(f.player_reputation, language))
        for f in _by_name(state.factions.values())
        if k.knows(f)
    ]
    moments: list[tuple[int, str, str]] = [
        (d.world_s, d.id, text)
        for d, text, _, _ in k.told_deeds()
        if d.actor_id == k.player_id or d.severity >= 3
    ]
    moments += [
        (f.world_s, f.id, f.text)
        for f in state.facts.values()
        if k.knows(f) and f.importance >= 4 and f.timeline_id == k.timeline and k.told(f)
    ]
    # C10: what the player character gained and lost lately, and to whom.
    mine = possessions.involving(state, k.player_id)[-SINCE_TRANSFERS:]
    moments += [(t.world_s, f"transfer-{n}", k.transfer_text(t)) for n, t in enumerate(mine)]
    moments.sort(key=lambda m: (m[0], natural_key(m[1])), reverse=True)
    since = [
        SinceEntry(text=text, ago_label=ago_label(k.now - when, language))
        for when, _, text in moments[:SINCE_LIMIT]
    ]
    return StatusView(
        character=StatusCharacter(name=player.name, lines=lines),
        sheet=k.sheet(player),
        reputation=reputation,
        clock=clock_view(state, language),
        since=since,
    )
