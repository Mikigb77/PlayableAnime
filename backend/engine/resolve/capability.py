"""What a character throws for a step, and the number it has to reach (A2, A3, A8, G13, G14).

The dice say how good the character is, and the number says what they are up against today. Code
builds both from the records, so the model never picks a die, a number or a result.

**The hand** (`hand_for`), from the sheet:

- A technique of theirs the step uses throws by its mastery, one die while they are learning it
  up to five for a move made their own, with the move's own die last (`engine.levels`,
  `engine.resolve.throw`). A move they are trying for the first time throws where their skill
  puts a new move (A4).
- With no named move, the skill the step draws on: untrained or novice one die, fair two,
  skilled three, expert four, master five (G14).
- A raw feat with no skill behind it, such as lifting, enduring or resisting, throws from the
  attributes it tests: two dice for an average adult, one more for each level above (G13).

**Their level** (`level_of`): for a person who can answer, their skill at what answers the step,
or the attribute they answer with, read from their sheet. The interpret step names it in a word
(`StepFacts.answers_with`); with none, their skill at what the step draws on, and failing that
the attributes the step's axis calls on. A thing's level is the six words the interpret step
judges it by (`engine.levels.CHALLENGE_LEVEL`).

**The number** (`number_for`) starts from ten for each level, less what the story's difficulty
takes off (A5), and moves in steps of 5, each named:

- each extra foe near the strongest adds 5, 10 at most (A8);
- wounded adds 5, badly wounded 10 and dying 20; exhausted 5 or 10; a reserve run dry 5. The
  other side's wounds and exhaustion come off the same way (A8);
- each thing in the scene against them adds 5, two at most;
- a flaw in the way adds 5, and a body or mind clearly worse at what the step tests adds 5;
- a body or mind clearly better takes 5 off, a gift that fits takes 5 off, and, in a step of
  words, so does a listener who likes and trusts them, or who fears them when they threaten
  (A3). All help together takes at most 10 off.

Nothing hidden is left: no run of misses lifts the next throw.

**Green dice** (`advantages`): each real advantage the interpret step proposes says where it
comes from, and code checks it before it adds a die: an earlier step of this action that passed,
a record the state holds (a true fact, something they carry, someone alive at their side, the
place they are in), or words the scene itself shows. Two at most count (A3).
"""

import re
from dataclasses import dataclass
from statistics import mean

from engine import levels
from engine import talent as talent_mod
from engine.context import Difficulty
from engine.contracts.intent import Challenge, Edge, EdgeSource, IntentStep, SheetPart
from engine.resolve.checks import Drawn
from engine.resolve.throw import MAX_GREENS, Hand, Number, level_number, own_die
from engine.resolve.words import cap, is_are, mentions, name, possessive, stems
from engine.state.cast import Character
from engine.state.records import DieKind
from engine.state.sheet import (
    Attributes,
    Health,
    Mastery,
    PowerAxis,
    Skill,
    SkillLevel,
    Technique,
    Trait,
    TraitKind,
)
from engine.state.world import WorldState

CHALLENGE_WORDS = {
    Challenge.TRIVIAL: "a trivial task",
    Challenge.EASY: "an easy task",
    Challenge.MODERATE: "a real effort",
    Challenge.HARD: "a hard task",
    Challenge.VERY_HARD: "a very hard task",
    Challenge.EXTREME: "a feat almost nobody manages",
}
# A thing nobody judged, where the facts still leave it open.
UNJUDGED = Challenge.MODERATE

AVERAGE = levels.AVERAGE_ATTRIBUTE  # an average person's attribute (`Attributes`)
STEP = levels.STEP
MAX_HINDRANCES = 2
MAX_HELP = 2 * STEP  # all help together takes at most this off a number
HEALTH_POINTS = {Health.WOUNDED: STEP, Health.BADLY_WOUNDED: 2 * STEP, Health.DYING: 4 * STEP}
HEALTH_WORDS = {
    Health.WOUNDED: "wounded",
    Health.BADLY_WOUNDED: "badly wounded",
    Health.DYING: "dying",
}
FATIGUE_POINTS = {3: STEP, 4: 2 * STEP}
DRY_POINTS = STEP
# A8: allies count. Each other foe within this many levels of the strongest adds a step, up to
# `MAX_NUMBERS` of them.
NEAR_LEVELS = 1
MAX_NUMBERS = 2
# A3: how warmly, or how fearfully, a listener has to feel for it to move a step of words.
ATTITUDE_AT = 40
MASTERY_WORDS = {
    Mastery.LEARNING: "learning",
    Mastery.PRACTICED: "practiced",
    Mastery.SKILLED: "skilled",
    Mastery.SECOND_NATURE: "second nature",
    Mastery.OWN: "made their own",
}

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
    "bearing": "bearing poise authority dignity demeanour demeanor",
}
_ATTRIBUTE_STEMS = {key: stems(words) for key, words in _ATTRIBUTE_WORDS.items()}
# The three groups of attributes, by the words that name a whole group.
_GROUPS = {
    ("strength", "speed", "toughness"): stems("body bodies bodily physical physique"),
    ("wits", "knowledge", "willpower"): stems("mind minds mental"),
    ("charm", "nerve", "bearing"): stems("presence"),
}
# What a step's own words test when the interpret step named no attribute: the activity, in any
# genre ("climb", "leap" and "dodge" are speed; "lift" and "pry" strength; "search" wits).
_ACTIVITY_WORDS = {
    "speed": """climb clamber leap jump vault hop dodge duck evade run sprint dash race flee
        scramble balance tumble flip swing catch snatch grab sneak tiptoe acrobatics parkour
        shoot aim throw hurl toss lob""",
    "strength": "lift heave haul carry push shove pull drag break smash shatter pry wrench wrestle",
    "toughness": "endure withstand survive march",
    "wits": """notice spot search look listen hear track sense scan watch examine inspect perceive
        observe find""",
    "knowledge": """recall remember identify recognise recognize decipher translate study research
        analyse analyze""",
    "willpower": "concentrate meditate",
    "charm": "persuade convince charm flatter seduce negotiate bargain haggle befriend flirt plead",
    "bearing": "command rally inspire",
}
_ACTIVITY_STEMS = {key: stems(words) for key, words in _ACTIVITY_WORDS.items()}
# How many words a skill's or trait's name and description must share with a step that didn't
# name it, for it to count.
RELEVANT_WORDS = 2
# What a step on an axis tests when neither the interpret step nor its words name an attribute.
_BY_AXIS = {
    PowerAxis.MIGHT: ("strength", "speed"),
    PowerAxis.STEALTH: ("speed", "wits"),
    PowerAxis.KNOWLEDGE: ("wits", "knowledge"),
    PowerAxis.INFLUENCE: ("charm", "bearing"),
}
_MENACE = ("nerve", "bearing")


@dataclass(frozen=True)
class Brought:
    """What the actor throws for one step: the hand, the technique whose own die it ends on,
    if any, and whether the dice came from their attributes, which then don't count again.
    `told` is what they do it with and how well they have it, for the telling (R4): a skill or
    a move with its level, "Swordsmanship (novice)", and nothing for a raw feat."""

    hand: Hand
    technique: Technique | None = None
    by_attribute: bool = False
    told: str = ""


@dataclass(frozen=True)
class Level:
    """Where someone or something stands on the one scale, and why, in the world's words."""

    level: int
    why: str
    by_attribute: bool = False


def challenge_words(challenge: Challenge | None) -> str:
    return CHALLENGE_WORDS[challenge] if challenge is not None else ""


def _dice(count: int) -> str:
    return f"{count} die" if count == 1 else f"{count} dice"


def hand_for(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    drawn: Drawn,
    axis: PowerAxis | None,
    *,
    techniques: list[Technique],
    start: Mastery,
) -> Brought:
    """G14, A4. The dice the actor throws for `step`. `techniques` are the techniques of theirs
    it uses, as the plan has them so far, and `start` is where their skill puts a move they are
    trying for the first time."""
    if techniques:
        best = max(techniques, key=lambda t: (t.mastery.rank, t.uses))
        dice = levels.MASTERY_DICE[best.mastery]
        told = f"{cap(best.name)} ({MASTERY_WORDS[best.mastery]})"
        why = f"{told}, {_dice(dice)}"
        hand = Hand(dice, why, own_die(best.mastery), _insight_at(actor, best.name))
        return Brought(hand, technique=best, told=told)
    if drawn.moves:
        move = drawn.moves[0].name
        dice = levels.MASTERY_DICE[start]
        told = f"{cap(move)} (a new move)"
        hand = Hand(dice, f"{told}, {_dice(dice)}", DieKind.VIOLET, _insight_at(actor, move))
        return Brought(hand, told=told)
    # The skill it draws on: one of theirs the step names or plainly is, and untrained where it
    # names a skill their sheet doesn't hold.
    best_of = best_skill(actor, drawn.skills) or best_skill(actor, skills_for(actor, step))
    if best_of is not None or drawn.skills:
        level = best_of.level if best_of is not None else SkillLevel.UNTRAINED
        dice = levels.SKILL_DICE[level]
        what = best_of.name if best_of is not None else drawn.skills[0]
        told = f"{cap(what)} ({level.value})"
        return Brought(Hand(dice, f"{told}, {_dice(dice)}"), told=told)
    # A raw feat. Where a power of theirs does the work, only the attributes the step names
    # count: the arm doesn't throw a spell.
    names = attributes_used(step, axis, named_only=bool(drawn.powers))
    if names:
        dice = levels.attribute_dice(_whole(_level(actor.sheet.attributes, names)))
        return Brought(Hand(dice, f"{cap(_listed(names))}, {_dice(dice)}"), by_attribute=True)
    dice = levels.AVERAGE_DICE
    what = drawn.powers[0].name if drawn.powers else "An ordinary hand"
    return Brought(Hand(dice, f"{cap(what)}, {_dice(dice)}"), by_attribute=True)


def _insight_at(actor: Character, move: str) -> int:
    """A3, A4. The face of a move's violet die that shows an insight: 18, or 16 when two
    talents of theirs both cover the move fully (`engine.talent`)."""
    return talent_mod.standing(actor, talent_mod.technique_key(move)).insight_at


def defence_hand(state: WorldState, actor: Character, step: IntentStep, drawn: Drawn) -> Hand:
    """N6. What the actor throws to defend: the skill their step drew on, or else their speed,
    whichever serves them better."""
    speed = levels.attribute_dice(actor.sheet.attributes.speed)
    best_of = best_skill(actor, drawn.skills or skills_for(actor, step))
    if best_of is not None and levels.SKILL_DICE[best_of.level] > speed:
        dice = levels.SKILL_DICE[best_of.level]
        return Hand(dice, f"{cap(best_of.name)} ({best_of.level.value}), {_dice(dice)}")
    return Hand(speed, f"Speed, {_dice(speed)}")


def level_of(
    state: WorldState,
    character: Character,
    word: str,
    refs: list[str],
    axis: PowerAxis | None,
) -> Level:
    """A3, G14. Someone's level at what answers a step: a technique or a skill of theirs that
    `word` names, or the attributes it names; with no word their sheet answers to, their skill
    among `refs`, the skills the step draws on, and failing that the attributes its axis calls
    on, or an ordinary adult's two dice."""
    whose = possessive(state, character.id)
    word = word.strip()
    if word:
        technique = next((t for t in character.sheet.techniques if mentions(t.name, word)), None)
        if technique is not None:
            dice = levels.MASTERY_DICE[technique.mastery]
            said = f"{whose} {technique.name} ({MASTERY_WORDS[technique.mastery]})"
            return Level(dice, f"{said}, level {dice}")
        skill = best_skill(character, [word])
        if skill is not None:
            return _skill_level(whose, skill)
        names = attribute_names(word)
        if names:
            return _attribute_level(whose, character, names)
    skill = best_skill(character, refs) if refs else None
    if skill is not None:
        return _skill_level(whose, skill)
    names = _BY_AXIS.get(axis, ()) if axis is not None else ()
    if names:
        return _attribute_level(whose, character, names)
    who = name(state, character.id)
    return Level(levels.AVERAGE_DICE, f"{who}, level {levels.AVERAGE_DICE}", by_attribute=True)


def _skill_level(whose: str, skill: Skill) -> Level:
    dice = levels.SKILL_DICE[skill.level]
    return Level(dice, f"{whose} {skill.name.lower()} ({skill.level.value}), level {dice}")


def _attribute_level(whose: str, character: Character, names: tuple[str, ...]) -> Level:
    dice = levels.attribute_dice(_whole(_level(character.sheet.attributes, names)))
    return Level(dice, f"{whose} {_listed(names)}, level {dice}", by_attribute=True)


def thing_level(challenge: Challenge | None) -> int:
    """A thing's level, from the six words; one nobody judged is a real effort."""
    return levels.CHALLENGE_LEVEL[challenge or UNJUDGED]


def thing_number(what: str, challenge: Challenge | None, difficulty: Difficulty) -> Number:
    """The number a thing sets: "the lock, a hard task, level 3"."""
    level = thing_level(challenge)
    words = challenge_words(challenge or UNJUDGED)
    said = f"{what}, {words}" if what else words
    return level_number(level, f"{said}, level {level}", difficulty)


def thing_key(step: IntentStep) -> str:
    """A3. What a place remembers a judged thing by: the word stems of what was tried and what
    stood in the way, or of the step's own words where nothing was named, in order. Only the
    same words find it again, so a kept level never lands on something else."""
    what = step.facts.opposition.strip() or step.text
    return " ".join(sorted(stems(f"{step.verb} {what}")))


def condition_points(character: Character, health: Health | None = None) -> list[tuple[str, int]]:
    """A8. What a character's own state costs them, in points: wounds, exhaustion and a reserve
    run dry, each with its word. `health` is theirs as it stands now, where a step just
    changed it."""
    condition = character.sheet.condition
    health = health or condition.health
    found: list[tuple[str, int]] = []
    if health in HEALTH_POINTS:
        found.append((HEALTH_WORDS[health], HEALTH_POINTS[health]))
    if condition.fatigue in FATIGUE_POINTS:
        found.append(("exhausted", FATIGUE_POINTS[condition.fatigue]))
    dry = [r.name for r in condition.reserves if r.level == 0]
    if dry:
        found.append((f"drained of {dry[0]}", DRY_POINTS))
    return found


def number_for(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    drawn: Drawn,
    base: Number,
    brought: Brought,
    *,
    axis: PowerAxis | None,
    rival: Character | None = None,
    rival_by_attribute: bool = False,
    extra_foes: int = 0,
) -> Number:
    """A3, A8. `base`, the number the level sets, moved by everything else that counts, each in
    a step of 5 and each named. `rival` is whoever answers the step, the strongest of them,
    whose own state comes off, and `extra_foes` how many more stand near them."""
    player = actor.id == state.player_id
    you_are = "you are" if player else f"{actor.name} is"
    whose = "your" if player else possessive(state, actor.id)
    number = base
    more = min(MAX_NUMBERS, max(0, extra_foes))
    if more:
        count = {1: "one more", 2: "two more"}[more]
        number = number.plus(f"{count} at their side", STEP * more)
    if rival is not None:
        for word, points in condition_points(rival):
            number = number.plus(
                f"{name(state, rival.id)} {is_are(state, rival.id)} {word}", -points
            )
    for word, points in condition_points(actor):
        number = number.plus(f"{you_are} {word}", points)
    for hindrance in [h.strip() for h in step.facts.hindrances if h.strip()][:MAX_HINDRANCES]:
        number = number.plus(hindrance, STEP)

    traits = traits_for(actor, step, drawn.traits)
    flaw = next((t for t in traits if t.kind is TraitKind.FLAW), None)
    if flaw is not None:
        number = number.plus(f"{whose} {flaw.name}", STEP)

    help_: list[tuple[str, int]] = []
    # G13. A body or mind clearly better or worse at what the step tests, unless the dice already
    # came from it. Against someone who answers with a skill it is set against theirs.
    names = (
        () if brought.by_attribute else attributes_used(step, axis, named_only=rival is not None)
    )
    if names:
        mine = _level(actor.sheet.attributes, names)
        mark = float(AVERAGE)
        if rival is not None and not rival_by_attribute:
            mark = _level(rival.sheet.attributes, names)
        if mine - mark >= 1:
            help_.append((f"{whose} {_listed(names)}", -STEP))
        elif mine - mark <= -1:
            number = number.plus(f"{whose} {_listed(names)}", STEP)
    gift = next((t for t in traits if t.kind is TraitKind.GIFT), None)
    if gift is not None:
        help_.append((f"{whose} {gift.name}", -STEP))
    if axis is PowerAxis.INFLUENCE and rival is not None:
        # A3. How the listener feels about the actor moves a step of words.
        attitude = rival.attitude_toward(actor.id)
        them = name(state, rival.id)
        if intimidates(step):
            if attitude.fear >= ATTITUDE_AT:
                help_.append((f"{them} fears {'you' if player else actor.name}", -STEP))
        else:
            warmth = (attitude.affinity + attitude.trust) / 2
            if warmth >= ATTITUDE_AT:
                help_.append((f"{them} likes and trusts {'you' if player else actor.name}", -STEP))
            elif warmth <= -ATTITUDE_AT:
                number = number.plus(
                    f"{them} neither likes nor trusts {'you' if player else actor.name}", STEP
                )
    left = MAX_HELP
    for word, points in help_:
        if left <= 0:
            break
        number = number.plus(word, points)
        left += points
    return number


def advantages(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    drawn: Drawn,
    *,
    passed: set[int] | frozenset[int] = frozenset(),
    scene: str = "",
    openings: list[str] | tuple[str, ...] = (),
) -> list[str]:
    """A3. The reasons for the green dice of a step, two at most: an opening the actor already
    won (`openings`, which code recorded), then each advantage the interpret step proposed whose
    source holds. `passed` holds the earlier steps of this plan that came off cleanly, counted
    from 0, and `scene` the words of the scene the player is answering."""
    found: list[str] = [o for o in openings if o]
    seen: set[tuple[str, frozenset[str]]] = set()
    for edge in step.facts.edges:
        text = edge.text.strip() or edge.ref.strip()
        key = (edge.source.value, stems(edge.ref or edge.text))
        if not text or key in seen:
            continue
        seen.add(key)
        if holds(state, actor, step, drawn, edge, passed=passed, scene=scene):
            found.append(text)
    return found[:MAX_GREENS]


def holds(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    drawn: Drawn,
    edge: Edge,
    *,
    passed: set[int] | frozenset[int],
    scene: str,
) -> bool:
    """A3. Whether an advantage's source holds. A step: an earlier step of this plan, by its
    number counted from 1, that came off cleanly. A record: a true fact, something the actor
    carries, someone alive at their side (with them, and not whom the step is up against), or
    the place they are in, by id. The scene: its own words show it, each meaningful word of the
    quote."""
    ref = edge.ref.strip()
    if edge.source is EdgeSource.STEP:
        digits = re.findall(r"\d+", ref)
        return bool(digits) and int(digits[0]) - 1 in passed
    if edge.source is EdgeSource.RECORD:
        fact = state.facts.get(ref)
        if fact is not None:
            return fact.is_true
        item = actor.sheet.item(ref)
        if item is not None:
            return item.carried and item.quantity > 0
        other = state.characters.get(ref)
        if other is not None:
            # Someone at their side: alive, with them, and not whom the step is up against.
            against = {*step.target_ids, *step.facts.opposition_ids}
            encounter = state.scene.encounter
            if encounter is not None:
                against.update(encounter.opponent_ids)
            if other.id == actor.id or other.id in against:
                return False
            return other.alive and _with(state, actor, other)
        here = actor.location_id or state.scene.place_id
        return ref in state.places and ref == here
    quote = ref or edge.text
    return mentions(scene_words(state, scene), quote)


def scene_words(state: WorldState, scene: str = "") -> str:
    """The words of the scene the actor is in: what was last told, where it ended, where people
    stand, what is at hand, and the place."""
    frame = state.scene
    words = [scene, frame.ended_on, *frame.positions, *frame.props]
    place = state.places.get(frame.place_id or "")
    if place is not None:
        words += [place.name, place.description, place.mood]
    return " ".join(w for w in words if w)


def _with(state: WorldState, actor: Character, other: Character) -> bool:
    if other.id in state.scene.present_ids:
        return True
    return other.location_id is not None and other.location_id == actor.location_id


def _whole(level: float) -> int:
    """A level worked out from several attributes, as a whole number: halves count up."""
    return int(level + 0.5)


def attributes_used(
    step: IntentStep, axis: PowerAxis | None, *, named_only: bool = False
) -> tuple[str, ...]:
    """The attributes a step tests: those it names (by attribute, by a word for one, or by body,
    mind or presence), else, unless `named_only`, those its own words call on ("climb the tree"
    is speed, "search the room" wits), else those its axis calls on."""
    found: list[str] = []
    for use in step.uses:
        if use.part is SheetPart.ATTRIBUTE:
            found += attribute_names(use.ref)
    if found or named_only:
        return tuple(dict.fromkeys(found))
    if axis is PowerAxis.INFLUENCE and intimidates(step):
        return _MENACE
    words = step_words(step)
    by_words = tuple(key for key, found in _ACTIVITY_STEMS.items() if found & words)
    if by_words:
        return by_words
    return _BY_AXIS.get(axis, ()) if axis is not None else ()


def step_words(step: IntentStep) -> frozenset[str]:
    """The meaningful word stems of what the step does: its words, its verb and its method."""
    return stems(f"{step.text} {step.verb} {step.method}")


def skills_for(actor: Character, step: IntentStep) -> list[str]:
    """G14. The actor's own skills a step plainly is, for when the interpret step named none:
    one its words name ("climb" for Climbing), or one whose name and notes share two words
    with it."""
    words = step_words(step)
    return [s.name for s in actor.sheet.skills if _relevant(s.name, s.notes, words)]


def traits_for(actor: Character, step: IntentStep, refs: list[str]) -> list[Trait]:
    """G13. The actor's traits a step draws on: those it names, matched either way ("nimble" or
    "a nimble tree-runner" both find Nimble), or, where it names none, those its words name or
    whose name and description share two words with it ("leap onto a tree" and a gift for years
    of leaping from tree to tree)."""
    if refs:
        return [
            t
            for t in actor.sheet.traits
            if any(mentions(t.name, ref) or mentions(ref, t.name) for ref in refs)
        ]
    words = step_words(step)
    return [t for t in actor.sheet.traits if _relevant(t.name, t.description, words)]


def _relevant(name: str, more: str, words: frozenset[str]) -> bool:
    named = stems(name)
    if named and named <= words:
        return True
    return len((named | stems(more)) & words) >= RELEVANT_WORDS


def attribute_names(ref: str) -> tuple[str, ...]:
    """The attributes a word names: "agility" is speed, "mind" is wits, knowledge and willpower."""
    words = stems(ref)
    for members, named_by in _GROUPS.items():
        if named_by & words:
            return members
    if "will" in re.findall(r"[a-z]+", ref.casefold()):
        return ("willpower",)  # "will" or "force of will": a stopword `stems` drops
    return tuple(key for key, found in _ATTRIBUTE_STEMS.items() if found & words)


def intimidates(step: IntentStep) -> bool:
    return any(mentions(step.verb, word) for word in INTIMIDATION)


def best_skill(character: Character, refs: list[str]) -> Skill | None:
    """Their best skill among `refs`, by name, or by its words either way ("climbing" finds
    Tree climbing, "free-running and climbing" finds Climbing)."""
    found = [
        s
        for s in character.sheet.skills
        if any(
            s.name.casefold() == ref.casefold() or mentions(s.name, ref) or mentions(ref, s.name)
            for ref in refs
        )
    ]
    return max(found, key=lambda s: s.level.rank, default=None)


def _level(attributes: Attributes, names: tuple[str, ...]) -> float:
    return mean(getattr(attributes, n) for n in names)


def _listed(items: list[str] | tuple[str, ...]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"
