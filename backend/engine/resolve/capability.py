"""What the character brings to a rolled step, in log-odds (A2, A3, A8, G13, G14).

The interpret step judges how hard a step is for an ordinary person, average in body and mind and
untrained in it (`Challenge`), and code weighs the character's own sheet against that, so the odds
come from who they are, not from a coin toss: a nimble thief stamping out a lantern almost never
fumbles it, and a clumsy scholar might. What counts:

- **Attributes** the step tests, such as speed for a leap or wits for spotting a trap, against an
  average person's, or against the opponent's where the step is measured against someone (G13).
- **Skills** it draws on, by rank: against someone untrained when the challenge was judged for an
  ordinary person, otherwise against a fair hand or the opponent's own skill (G14, G25).
- **Traits**: a gift used helps and a flaw that gets in the way hurts (G13).
- **A power or a technique** it uses (G22, G25). A power's weight on an axis is already in its
  user's tier, so it counts here only where nobody is measured against them.
- **The situation**: the edges and hindrances the interpret step saw (preparation, position,
  allies, cover), and for a social step the target's attitude (A3).
- **Condition**: wounds and exhaustion, where the tiers don't already carry them (A8).

A run of bad luck counts too (`streak_shift`): every rolled step of the player character that
missed since their last clean one makes their next roll likelier, up to `MAX_MISSES`, so a capable
character doesn't fail the same easy thing five times running. Like every shift, it stays inside
the class's band and never makes a roll certain (A2).
"""

from dataclasses import dataclass, replace
from statistics import mean

from engine.contracts.intent import Challenge, IntentStep, OutcomeClass, SheetPart
from engine.resolve import odds as odds_mod
from engine.resolve.checks import Drawn
from engine.resolve.words import mentions, possessive, stems
from engine.state.cast import Character
from engine.state.records import RollRecord, StepResult
from engine.state.sheet import Attributes, GiftStrength, Health, PowerAxis, SkillLevel, TraitKind
from engine.state.world import WorldState

# How an ordinary person fares at each challenge: average in body and mind, untrained in it.
CHALLENGE_ODDS = {
    Challenge.TRIVIAL: 0.97,
    Challenge.EASY: 0.85,
    Challenge.MODERATE: 0.6,
    Challenge.HARD: 0.35,
    Challenge.VERY_HARD: 0.15,
    Challenge.EXTREME: 0.05,
}
CHALLENGE_WORDS = {
    Challenge.TRIVIAL: "a trivial task",
    Challenge.EASY: "an easy task",
    Challenge.MODERATE: "a real effort",
    Challenge.HARD: "a hard task",
    Challenge.VERY_HARD: "a very hard task",
    Challenge.EXTREME: "a feat almost nobody manages",
}

AVERAGE = 3  # an average person's attribute (`Attributes`)
ATTRIBUTE_SHIFT = 0.45  # each level of the attributes used, above or below the mark
SKILL_SHIFT = 0.5  # each rank of skill above or below the mark
TRAIT_SHIFT = 0.5  # a gift used, or a flaw that gets in the way
MAX_TRAITS = 2
TECHNIQUE_SHIFT = 0.6  # G25: technique matters most within a gap
# A power the step uses where nobody is measured against it, by the gift's strength (G22).
POWER_SHIFT = {
    None: 0.7,
    GiftStrength.NONE: 0.7,
    GiftStrength.SMALL: 0.5,
    GiftStrength.RARE: 0.9,
    GiftStrength.OVERPOWERED: 1.4,
}
EDGE_SHIFT = 0.35  # each edge or hindrance the interpret step proposed
MAX_EDGES = 3  # how many of each count
ATTITUDE_SHIFT = 1.2  # A3: at full devotion or full hatred, on the influence axis
HEALTH_SHIFT = {Health.WOUNDED: -0.5, Health.BADLY_WOUNDED: -1.0, Health.DYING: -2.0}
FATIGUE_SHIFT = {3: -0.35, 4: -0.7}
# A run of misses: each one since the last clean success adds this to the player's next roll.
MISS_SHIFT = 0.6
MAX_MISSES = 3
MAX_WORDS = 3  # how many helps and hindrances the reason names

INTIMIDATION = ("intimidate", "threaten", "menace", "scare", "frighten", "coerce", "bully")

# G13's attributes and the words a step names them by. Body, mind and presence name all three of
# theirs. Matching is on word stems, so "agile", "agility" and "dexterous" all find speed.
_ATTRIBUTE_WORDS = {
    "strength": "strength strong might mighty muscle muscles brawn force lift",
    "speed": """speed fast quick quickness agile agility dexterity dexterous nimble reflex
        reflexes grace graceful balance coordination finesse deft precise precision""",
    "toughness": """toughness tough endurance stamina constitution resilience resilient hardy
        vitality""",
    "wits": """wits wit perception perceptive awareness aware senses sense observation observant
        alert alertness attention intuition cunning insight sharp""",
    "knowledge": "knowledge learning learned education lore intellect intelligence memory",
    "willpower": "willpower will resolve determination discipline composure focus",
    "charm": "charm charming charisma charismatic persuasion likeable allure beauty appeal",
    "nerve": "nerve nerves courage brave bravery guts daring steady steadiness",
    "bearing": "bearing presence poise authority dignity demeanour demeanor",
}
_ATTRIBUTE_STEMS = {key: stems(words) for key, words in _ATTRIBUTE_WORDS.items()}
_GROUPS = {
    "body": ("strength", "speed", "toughness"),
    "mind": ("wits", "knowledge", "willpower"),
    "presence": ("charm", "nerve", "bearing"),
}
# What a step on an axis tests when the interpret step named no attribute (A8).
_BY_AXIS = {
    PowerAxis.MIGHT: ("strength", "speed"),
    PowerAxis.STEALTH: ("speed", "wits"),
    PowerAxis.KNOWLEDGE: ("wits", "knowledge"),
    PowerAxis.INFLUENCE: ("charm", "bearing"),
}
_MENACE = ("nerve", "bearing")


@dataclass(frozen=True)
class Weighed:
    """What the actor brings to one step: the shift in log-odds, and the parts of it worth naming
    in the reason, in the world's words (A8, G16)."""

    shift: float
    helps: tuple[str, ...] = ()
    hinders: tuple[str, ...] = ()
    luck: float = 0.0  # A3: from a run of misses; it moves the odds, never the class

    def with_misses(self, misses: int) -> "Weighed":
        """The same, with the lift a run of `misses` gives the roll, named last among the
        helps."""
        luck = streak_shift(misses)
        if not luck:
            return self
        helps = (*self.helps[: MAX_WORDS - 1], streak_words(misses))
        return replace(self, luck=luck, helps=helps)

    def words(self, state: WorldState, actor: Character) -> str:
        """ ", your speed and your Agile in your favour", or nothing."""
        whose = "your" if actor.id == state.player_id else possessive(state, actor.id)
        favour = f" in {whose} favour"
        against = " against you" if actor.id == state.player_id else f" against {actor.name}"
        parts = []
        if self.helps:
            parts.append(_listed(self.helps[:MAX_WORDS]) + favour)
        if self.hinders:
            parts.append(_listed(self.hinders[:MAX_WORDS]) + against)
        return "".join(f", {p}" for p in parts)


def base_logit(challenge: Challenge | None, proposed: OutcomeClass | None) -> float:
    """The log-odds an ordinary person starts from: the challenge the interpret step judged, or,
    with none, the class it proposed: a trivial task's odds for a certain one, a long shot's for
    a long shot, and even odds otherwise."""
    if challenge is not None:
        return odds_mod.logit(CHALLENGE_ODDS[challenge])
    if proposed is OutcomeClass.CERTAIN:
        return odds_mod.logit(CHALLENGE_ODDS[Challenge.TRIVIAL])
    if proposed is OutcomeClass.LONG_SHOT:
        return odds_mod.logit(odds_mod.UNMEASURED_ODDS[OutcomeClass.LONG_SHOT])
    return odds_mod.logit(odds_mod.UNMEASURED_ODDS[OutcomeClass.CONTESTED])


def challenge_words(challenge: Challenge | None) -> str:
    return CHALLENGE_WORDS[challenge] if challenge is not None else ""


def weigh(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    drawn: Drawn,
    *,
    rivals: list[Character],
    axis: PowerAxis | None,
    measured: bool,
) -> Weighed:
    """The log-odds shift from what the actor brings to `step` (G14).

    `measured` means the base came from the gap to `rivals` on `axis` (A8), so attributes and
    skills are weighed against the strongest rival's, and powers and condition, which their tiers
    already carry, don't count again. Otherwise they are weighed against an ordinary person's:
    one untrained in the skill where the interpret step judged the challenge for them, a fair hand
    where it didn't."""
    facts = step.facts
    helps: list[str] = []
    hinders: list[str] = []
    rival = rivals[0] if rivals else None
    whose = "your" if actor.id == state.player_id else possessive(state, actor.id)

    edges = [e.strip() for e in facts.edges if e.strip()][:MAX_EDGES]
    hindrances = [h.strip() for h in facts.hindrances if h.strip()][:MAX_EDGES]
    shift = EDGE_SHIFT * (len(edges) - len(hindrances))

    # Attributes (G13): against the rival's where measured, else an average person's.
    names = attributes_used(step, axis, named_only=measured)
    if names:
        mine = _level(actor.sheet.attributes, names)
        mark = _level(rival.sheet.attributes, names) if measured and rival else AVERAGE
        gap = mine - mark
        shift += ATTRIBUTE_SHIFT * gap
        said = f"{whose} {_listed(list(names))}"
        if gap >= 1:
            helps.append(said)
        elif gap <= -1:
            hinders.append(said)

    # Skills (G14, G25).
    if drawn.skills:
        found = [actor.sheet.skill(s) for s in drawn.skills]
        known = [s for s in found if s is not None]
        best = max(known, key=lambda s: s.level.rank, default=None)
        rank = best.level.rank if best is not None else SkillLevel.UNTRAINED.rank
        untrained_mark = facts.challenge is not None and not measured
        mark = SkillLevel.UNTRAINED.rank if untrained_mark else SkillLevel.FAIR.rank
        if measured and rival is not None:
            theirs = [rival.sheet.skill(s) for s in drawn.skills]
            ranks = [s.level.rank for s in theirs if s is not None]
            if ranks:
                mark = max(ranks)
        shift += SKILL_SHIFT * (rank - mark)
        if best is not None and rank > mark:
            helps.append(f"{whose} {best.name.lower()} ({best.level.value})")
        elif rank < mark:
            skill = best.name.lower() if best is not None else drawn.skills[0]
            level = best.level.value if best is not None else "untrained"
            hinders.append(f"{whose} {skill} ({level})")

    if drawn.techniques:
        shift += TECHNIQUE_SHIFT
        helps.append(f"{whose} {drawn.techniques[0].name}")

    # Traits (G13): gifts used help, flaws that get in the way hurt.
    traits = [t for t in actor.sheet.traits if any(mentions(t.name, ref) for ref in drawn.traits)]
    gifts = [t for t in traits if t.kind is TraitKind.GIFT][:MAX_TRAITS]
    flaws = [t for t in traits if t.kind is TraitKind.FLAW][:MAX_TRAITS]
    shift += TRAIT_SHIFT * (len(gifts) - len(flaws))
    helps += [f"{whose} {t.name}" for t in gifts]
    hinders += [f"{whose} {t.name}" for t in flaws]

    if not measured:
        # A power used where nobody is measured against it (G22); time powers are settled by
        # the stop itself (W10a).
        powers = [p for p in drawn.powers if p.time is None]
        if powers:
            strongest = max(powers, key=lambda p: POWER_SHIFT[p.strength])
            shift += POWER_SHIFT[strongest.strength]
            helps.append(f"{whose} {strongest.name}")
        # Condition (A8), which a measured gap already carries in the tiers.
        condition = actor.sheet.condition
        hurt = HEALTH_SHIFT.get(condition.health, 0.0)
        tired = FATIGUE_SHIFT.get(condition.fatigue, 0.0)
        shift += hurt + tired
        if hurt:
            hinders.append(f"{whose} wounds")
        if tired:
            hinders.append(f"{whose} exhaustion")

    if axis is PowerAxis.INFLUENCE and rival is not None:
        attitude = rival.attitude_toward(actor.id)
        if intimidates(step):
            shift += ATTITUDE_SHIFT * attitude.fear / 100
        else:
            shift += ATTITUDE_SHIFT * (attitude.affinity + attitude.trust) / 200

    helps += edges
    hinders += hindrances
    return Weighed(shift, tuple(helps), tuple(hinders))


def attributes_used(
    step: IntentStep, axis: PowerAxis | None, *, named_only: bool = False
) -> tuple[str, ...]:
    """The attributes a step tests: those it names (by attribute, by a word for one, or by body,
    mind or presence), else, unless `named_only`, those its axis calls on."""
    found: list[str] = []
    for use in step.uses:
        if use.part is SheetPart.ATTRIBUTE:
            found += attribute_names(use.ref)
    if found or named_only:
        return tuple(dict.fromkeys(found))
    if axis is PowerAxis.INFLUENCE and intimidates(step):
        return _MENACE
    return _BY_AXIS.get(axis, ()) if axis is not None else ()


def attribute_names(ref: str) -> tuple[str, ...]:
    """The attributes a word names: "agility" is speed, "mind" is wits, knowledge and willpower."""
    words = stems(ref)
    for group, members in _GROUPS.items():
        if group in words:
            return members
    return tuple(key for key, found in _ATTRIBUTE_STEMS.items() if found & words)


def intimidates(step: IntentStep) -> bool:
    return any(mentions(step.verb, word) for word in INTIMIDATION)


def streak_shift(misses: int) -> float:
    """A3. The lift a run of misses gives the player character's next roll."""
    return MISS_SHIFT * min(MAX_MISSES, max(0, misses))


def streak_words(misses: int) -> str:
    if misses <= 0:
        return ""
    if misses == 1:
        return "your last miss"
    count = {2: "two", 3: "three"}.get(misses, "several")
    return f"your last {count} misses"


def misses_after(misses: int, roll: RollRecord | None, result: StepResult) -> int:
    """The run of misses after a step: a clean success on a roll ends it, and a roll that could
    fail and didn't come off cleanly adds to it. Steps the facts settled, with no roll, and a
    roll only of how long something took, leave it as it was."""
    if roll is None or roll.odds >= 1:
        return misses
    if result is StepResult.SUCCESS:
        return 0
    if StepResult.FAILURE in roll.allowed:
        return misses + 1
    return misses


def _level(attributes: Attributes, names: tuple[str, ...]) -> float:
    return mean(getattr(attributes, n) for n in names)


def _listed(items: list[str] | tuple[str, ...]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"
