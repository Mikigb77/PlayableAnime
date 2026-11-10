"""Growth (A4), breakthroughs (G19) and new ways to use a power (A9, W10a).

Code decides every gain, from the character's traits, the effort and time they put in, what they
learn from and the world's rules (A4). Effort is lived time, so training in a time stop or a
haste counts on the trainer's own clock (W10a), and it adds up across sessions on the sheet's
`practice` until the gain is made.

- **Effort.** The first twelve hours of a stretch count in full and the rest at a third, since
  nobody trains every waking hour of a year. A master doubles the pace, a manual, a rival or
  watching someone helps less, a gift for learning (a genius, a copycat) makes it four times
  faster, and a flaw halves it. A copycat who watches a technique learns it at once.
- **Skills** climb the one ladder of words, novice to master, each rank taking longer.
- **Techniques** take about 150 hours with a teacher's pace, three times that when the character
  invents one with no gift for it.
- **A new way to use a power** (an idea refused once, now earned) takes about 200 hours. For a
  time stop, it is how its throws land: released gradually, a stone merges back into time carrying
  its motion, or lands exactly as hard as its user chooses. It goes on the sheet as a technique,
  with a ruling of its own, and never flips the power's first ruling (A9).
- **A move pulled off in play** (A4, G25). A move the character makes with a power of theirs,
  such as an aura blade made with their aura, is that power at work even before it is learned
  (`engine.resolve.checks.Move`), and so is one their records make theirs to try: a technique
  they are still learning, or a move made of the world's energy they hold. The first time it
  comes off cleanly, it goes on the sheet as a technique of their own, learned by doing it, once
  however many steps of the plan use it: from then on it counts like any technique and is never
  "never learned" again. A technique someone else in the world knows is their school's, and is
  learned from them, not picked up by improvising something like it.
- **Mastery** (A4, `engine.levels`). Every technique has one: learning, practiced, skilled or
  second nature. A new move starts at learning, or two steps under the skill it belongs to. It
  grows with use: each turn the character uses it counts once, or twice when a roll decided the
  step, and each hour of practising it counts once, more with a teacher. Hours never stand
  between a character and a move the story already let them do. Talent sets the pace
  (`talent`): with a gift for learning a move takes a quarter of the uses, an hour of practice
  counts four, and a new move starts at practiced; a slow learner needs twice the uses.
- **Breakthroughs** (G19) are events, not counters: the next rung's needs (a pill, a master's
  guidance) are checked against the state and any missing one is a bottleneck. Otherwise the
  attempt is rolled: success climbs a rung, a partial result shakes the character and a failure
  wounds them, and how long it takes is rolled too, so the world can interrupt it (W10). A loud
  rung's breakthrough is seen from afar (W1).

A world with nothing extraordinary never grows a power (G6, G8).
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from engine import levels
from engine.base import HOUR
from engine.contracts.delta import (
    CharacterChange,
    ConditionChange,
    PowerChange,
    PowerSetting,
    StateDelta,
)
from engine.contracts.intent import GrowthKind, IntentStep, OutcomeClass, PowerGrant, Teacher
from engine.contracts.resolution import ProposedDeed, TrainingSoFar
from engine.resolve import odds as odds_mod
from engine.resolve.checks import Move, Settled, same_way
from engine.resolve.powers import time_stop as stop
from engine.resolve.words import cap, mentions, name, possessive, stems
from engine.rng import SeededRng
from engine.state.cast import Character
from engine.state.records import RollRecord, StepResult, Trace, TraceKind, Visibility
from engine.state.sheet import (
    Gain,
    Health,
    LadderPosition,
    Mastery,
    Power,
    Practice,
    Ruling,
    RulingSource,
    Skill,
    SkillLevel,
    Technique,
    TraitKind,
)
from engine.state.world import WorldState

FULL_EFFORT_S = 12 * HOUR
LONG_STRETCH_RATE = 1 / 3
TEACHER_RATE = {
    Teacher.SELF: 1.0,
    Teacher.MASTER: 2.0,
    Teacher.BOOK: 1.3,
    Teacher.RIVAL: 1.5,
    Teacher.WATCHING: 1.2,
}
GIFT_RATE = 4.0
FLAW_RATE = 0.5
# Hours of ordinary effort, alone, from each level of skill to the next.
SKILL_HOURS = {
    SkillLevel.UNTRAINED: 50,
    SkillLevel.NOVICE: 300,
    SkillLevel.FAIR: 1_500,
    SkillLevel.SKILLED: 5_000,
    SkillLevel.EXPERT: 15_000,
}
TECHNIQUE_HOURS = 150
# How well they have a technique they trained all the way through (`engine.levels`).
TRAINED = Mastery.PRACTICED
INVENT_FACTOR = 3
POWER_HOURS = 200
# Shifts to a breakthrough's log-odds.
MASTER_SHIFT = 0.6
GIFT_SHIFT = 0.6
EDGE_SHIFT = 0.35
MAX_EDGES = 3
LOUD_STRENGTH = 90

# A gift or a flaw for learning is read from a trait's words until talent is a record of its
# own, in the three languages a sheet can be written in (S10).
_COPY_STEMS = stems(
    "copycat copy copies mimic mimics"
    " imitador imitadora copión copiona"  # Spanish
    " copiador copiadora"  # Catalan
)
_GIFT_STEMS = _COPY_STEMS | stems(
    "genius prodigy talent talented gifted"
    " genio prodigio talento talentoso talentosa superdotado superdotada dotado dotada"
    " geni prodigi talentós superdotat dotat"
)
_GIFT_PHRASES = (
    "fast learner",
    "quick learner",
    "quick study",
    "learns fast",
    "learns quickly",
    "aprende rápido",
    "aprende deprisa",
    "aprèn ràpid",
    "aprèn de pressa",
)
_FLAW_STEMS = stems("untalented")
_FLAW_PHRASES = (
    "slow learner",
    "learns slowly",
    "no talent",
    "no aptitude",
    "sin talento",
    "aprende despacio",
    "aprende lento",
    "sense talent",
    "aprèn a poc a poc",
    "aprèn lent",
)
_MASTER_STEMS = stems("master teacher guidance mentor")
# Teachers who must be a living character beside the learner to count (A4).
_GUIDES = (Teacher.MASTER, Teacher.RIVAL, Teacher.WATCHING)

GRANT_WORDS = {
    PowerGrant.RELATIVE_SPEED_THROWS: (
        "Released into time gradually, a thrown thing merges back carrying its motion and lands"
        " at relative speed."
    ),
    PowerGrant.CONTROLLED_FORCE: (
        "Let back into time gradually, a stopped-time hit lands exactly as hard as its user"
        " chooses, from a tap to everything the power can give."
    ),
}
GRANT_SETTINGS = {
    PowerGrant.RELATIVE_SPEED_THROWS: PowerSetting(key=stop.THROWS, value=stop.RELATIVE),
    PowerGrant.CONTROLLED_FORCE: PowerSetting(key=stop.CONTROL, value=stop.CONTROLLED),
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-") or "technique"


def technique_id(name: str, taken: set[str]) -> str:
    """A new technique's id from its name, in any language ("Puño de fuego" is
    technique-puno-de-fuego, accents folded, other scripts kept), unique among `taken`."""
    folded = unicodedata.normalize("NFKD", name.casefold())
    plain = "".join(c for c in folded if not unicodedata.combining(c))
    words = re.sub(r"[\W_]+", "-", plain).strip("-") or "technique"
    base = f"technique-{words}"
    found, n = base, 2
    while found in taken:
        found, n = f"{base}-{n}", n + 1
    return found


def practice_key(step: IntentStep) -> str:
    training = step.training
    assert training is not None
    if training.kind is GrowthKind.SKILL:
        return f"skill:{slug(training.what)}"
    if training.kind is GrowthKind.POWER:
        return f"power:{training.power_id or ''}:{training.grants.value}:{slug(training.what)}"
    return f"technique:{slug(training.what)}"


def effort_s(lived_s: int) -> float:
    """A4. How much of a stretch of lived time counts as training effort."""
    lived = max(0, lived_s)
    return min(lived, FULL_EFFORT_S) + max(0, lived - FULL_EFFORT_S) * LONG_STRETCH_RATE


def _trait_texts(actor: Character, kind: TraitKind) -> list[str]:
    return [f"{t.name} {t.description}" for t in actor.sheet.traits if t.kind is kind]


def _says(texts: list[str], words: frozenset[str], phrases: tuple[str, ...]) -> bool:
    for text in texts:
        if stems(text) & words:
            return True
        folded = text.casefold()
        if any(p in folded for p in phrases):
            return True
    return False


def learning_gift(actor: Character) -> bool:
    return _says(_trait_texts(actor, TraitKind.GIFT), _GIFT_STEMS, _GIFT_PHRASES)


def learning_flaw(actor: Character) -> bool:
    return _says(_trait_texts(actor, TraitKind.FLAW), _FLAW_STEMS, _FLAW_PHRASES)


def copycat(actor: Character) -> bool:
    return any(stems(t) & _COPY_STEMS for t in _trait_texts(actor, TraitKind.GIFT))


def pace(actor: Character, teacher: Teacher) -> float:
    rate = TEACHER_RATE[teacher]
    if learning_gift(actor):
        rate *= GIFT_RATE
    if learning_flaw(actor):
        rate *= FLAW_RATE
    return rate


def talent(actor: Character) -> float:
    """A4. How fast they learn whoever teaches them: 1 for an ordinary character, more with a
    gift for learning and less with a flaw. It sets how many uses a move's next mastery takes
    (`engine.levels.uses_to_next`)."""
    return pace(actor, Teacher.SELF)


def stop_power(actor: Character, power_id: str | None) -> Power | None:
    if power_id:
        found = actor.sheet.power(power_id)
        return found if stop.stops_time(found) else None
    stoppers = [p for p in actor.sheet.powers if stop.stops_time(p)]
    return stoppers[0] if len(stoppers) == 1 else None


def check(
    state: WorldState, actor: Character, step: IntentStep, canon: list[str]
) -> Settled | None:
    """What settles a training step at once, with no roll: a fixed rule it would break, a power
    growing where the world has none, a teacher who isn't there, the top of a ladder, or a
    breakthrough's bottleneck. Practising a technique they already know is never refused
    (`already_known`)."""
    training = step.training
    assert training is not None
    fixed = [r for r in (state.bible.rule(i) for i in training.against_rule_ids) if r and r.fixed]
    if fixed:
        return _ruled_out(_rule_text(fixed[0].text))
    who = name(state, actor.id)
    teacher = _teacher_missing(state, actor, step)
    if teacher:
        return _ruled_out(teacher)
    if training.kind is GrowthKind.POWER:
        if state.bible.grounded:
            grounded = [r for r in state.bible.rules if r.fixed]
            return _ruled_out(
                _rule_text(grounded[0].text) if grounded else "Nothing like that exists here."
            )
        if training.grants is not PowerGrant.NONE:
            power = stop_power(actor, training.power_id)
            if power is None:
                return _ruled_out(f"{cap(who)} {_have(state, actor)} no power to grow that way.")
            setting = GRANT_SETTINGS[training.grants]
            if stop.Settlements().get(power, setting.key) == setting.value:
                return _ruled_out(f"{cap(who)} can already do that.")
        elif training.power_id and actor.sheet.power(training.power_id) is None:
            return _ruled_out(f"{cap(who)} {_have(state, actor)} no power like that.")
    if training.kind is GrowthKind.SKILL:
        skill = actor.sheet.skill(training.what)
        if skill is not None and skill.level is SkillLevel.MASTER:
            return _ruled_out(f"{cap(who)} {_have(state, actor)} mastered {skill.name} already.")
    if training.kind is GrowthKind.BREAKTHROUGH:
        return _breakthrough_check(state, actor, step, canon)
    return None


def already_known(
    state: WorldState, actor: Character, step: IntentStep, earlier: Sequence[Technique] = ()
) -> tuple[Settled, Technique] | None:
    """A4 (decided 2026-11-10, Miki). Training a technique the character already knows, on
    their sheet or made theirs `earlier` in this plan, is practice: it simply happens, and
    nothing new is learned, so it is never refused and never learned twice. The practice counts
    toward the technique's mastery (`practised`)."""
    training = step.training
    assert training is not None
    if training.kind is not GrowthKind.TECHNIQUE:
        return None
    theirs = [*actor.sheet.techniques, *earlier]
    known = next((t for t in theirs if mentions(t.name, training.what)), None)
    if known is None:
        return None
    who = name(state, actor.id)
    reason = f"{cap(who)} already {_know(state, actor)} {known.name}, so this is practice."
    return Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, reason), known


def _breakthrough_check(
    state: WorldState, actor: Character, step: IntentStep, canon: list[str]
) -> Settled | None:
    training = step.training
    assert training is not None
    who = name(state, actor.id)
    ladder, position = _ladder(state, actor, training.ladder_id)
    if ladder is None:
        return _ruled_out("There is no such ladder to climb here.")
    current = position.rung if position is not None else -1
    if current + 1 >= len(ladder.rungs):
        top = ladder.rungs[-1].name
        return _ruled_out(f"There is no rung above {top} here.")
    rung = ladder.rungs[current + 1]
    missing = [n for n in rung.needs if not _need_met(state, actor, step, n, canon)]
    if missing:
        return _ruled_out(
            f"Breaking through to {rung.name} takes {missing[0].strip().rstrip('.')}, which"
            f" {who} {_lack(state, actor)}: a bottleneck."
        )
    return None


def _ladder(state: WorldState, actor: Character, ladder_id: str | None):
    ladder = state.bible.ladder(ladder_id) if ladder_id else None
    if ladder is None and ladder_id is None:
        on = [p for p in actor.sheet.ladders if state.bible.ladder(p.ladder_id) is not None]
        if len(on) == 1:
            ladder = state.bible.ladder(on[0].ladder_id)
        elif len(state.bible.ladders) == 1:
            ladder = state.bible.ladders[0]
    if ladder is None:
        return None, None
    position = next((p for p in actor.sheet.ladders if p.ladder_id == ladder.id), None)
    return ladder, position


def _need_met(
    state: WorldState, actor: Character, step: IntentStep, need: str, canon: list[str]
) -> bool:
    """G19. A rung's need is met by what the state holds: something carried, a technique, a true
    fact the character knows, this turn's canon, or a master's guidance."""
    training = step.training
    assert training is not None
    carried = [
        f"{i.name} {i.description}"
        for i in actor.sheet.resources.items
        if i.carried and i.quantity > 0
    ]
    techniques = [f"{t.name} {t.effect}" for t in actor.sheet.techniques]
    facts = [
        f.text for f in state.facts.values() if f.is_true and actor.id in f.known_by and f.text
    ]
    if any(_matches(text, need) for text in [*carried, *techniques, *facts, *canon]):
        return True
    return bool(stems(need) & _MASTER_STEMS) and teacher_of(state, actor, step) is Teacher.MASTER


def _matches(text: str, need: str) -> bool:
    """Whether `text` names the need, in either direction of words: "a Foundation Pill" meets
    "Foundation Establishment Pill", and "a pill" meets "Foundation Pill"."""
    have, wanted = stems(text), stems(need)
    if not have or not wanted:
        return False
    return wanted <= have or (have <= wanted and len(have) >= len(wanted) - 1)


def _here(state: WorldState, actor: Character, other: Character) -> bool:
    if other.location_id is not None and other.location_id == actor.location_id:
        return True
    present = state.scene.present_ids
    return actor.id in present and other.id in present


def teacher_of(state: WorldState, actor: Character, step: IntentStep) -> Teacher:
    """A4. The teacher the step really has. A master, a rival or someone to watch counts only
    as a living character here, named by the step; otherwise the character learns alone."""
    training = step.training
    assert training is not None
    if training.teacher not in _GUIDES:
        return training.teacher
    guide = state.characters.get(training.teacher_id) if training.teacher_id else None
    if guide is None or guide.id == actor.id or not guide.alive or not _here(state, actor, guide):
        return Teacher.SELF
    return training.teacher


def _shows_it(state: WorldState, step: IntentStep) -> bool:
    """Whether the one being watched knows the technique, so a copycat can take it at once."""
    training = step.training
    assert training is not None
    guide = state.characters.get(training.teacher_id) if training.teacher_id else None
    return guide is not None and any(
        mentions(t.name, training.what) for t in guide.sheet.techniques
    )


def _teacher_missing(state: WorldState, actor: Character, step: IntentStep) -> str:
    """A teacher, rival or manual the step names has to be there: alive and here, or on the
    sheet."""
    training = step.training
    assert training is not None
    ref = training.teacher_id
    if ref is None:
        return ""
    character = state.characters.get(ref)
    if character is not None:
        if not character.alive:
            return f"{cap(character.name)} is dead."
        if training.teacher in _GUIDES and not _here(state, actor, character):
            return f"{cap(character.name)} isn't here."
        return ""
    if training.teacher is Teacher.BOOK:
        item = actor.sheet.item(ref)
        if item is None or item.quantity <= 0:
            return f"{cap(name(state, actor.id))} {_have(state, actor)} no such manual."
    return ""


def _have(state: WorldState, actor: Character) -> str:
    return "have" if actor.id == state.player_id else "has"


def _know(state: WorldState, actor: Character) -> str:
    return "know" if actor.id == state.player_id else "knows"


def _lack(state: WorldState, actor: Character) -> str:
    return "lack" if actor.id == state.player_id else "lacks"


def _rule_text(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _ruled_out(reason: str) -> Settled:
    return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason)


# --- breakthroughs (G19) ---------------------------------------------------------------------


def breakthrough(
    state: WorldState, actor: Character, step: IntentStep, rng: SeededRng, difficulty
) -> Settled:
    """G19. The attempt is rolled, never certain: success, a partial result or a failure."""
    training = step.training
    assert training is not None
    ladder, position = _ladder(state, actor, training.ladder_id)
    assert ladder is not None
    rung = ladder.rungs[(position.rung if position is not None else -1) + 1]
    shift = 0.0
    if teacher_of(state, actor, step) is Teacher.MASTER:
        shift += MASTER_SHIFT
    if learning_gift(actor):
        shift += GIFT_SHIFT
    if learning_flaw(actor):
        shift -= GIFT_SHIFT
    facts = step.facts
    edges = sum(1 for e in facts.edges if e.strip())
    hindrances = sum(1 for h in facts.hindrances if h.strip())
    shift += EDGE_SHIFT * (min(MAX_EDGES, edges) - min(MAX_EDGES, hindrances))
    band = odds_mod.BANDS[OutcomeClass.CONTESTED]
    odds = odds_mod.settle(0.0, shift, band, difficulty)
    roll = odds_mod.roll(
        rng.child("outcome"),
        odds,
        label=f"break through to {rung.name}",
        allowed=odds_mod.ALL_RESULTS,
        difficulty=difficulty,
    )
    reason = f"Breaking through to {rung.name}: {roll.odds_label}."
    return Settled(OutcomeClass.CONTESTED, roll.result, reason, roll)


def breakthrough_effects(
    state: WorldState, actor: Character, step: IntentStep, result: StepResult, roll: RollRecord
) -> tuple[str, StateDelta, ProposedDeed | None]:
    """What a breakthrough attempt did: a new rung, a shaken cultivator or a wounded one."""
    training = step.training
    assert training is not None
    ladder, position = _ladder(state, actor, training.ladder_id)
    assert ladder is not None
    current = position.rung if position is not None else -1
    rung = ladder.rungs[current + 1]
    who = name(state, actor.id)
    if result is StepResult.SUCCESS:
        shown = position.shown_rung if position is not None else None
        climbed = LadderPosition(ladder_id=ladder.id, rung=current + 1, shown_rung=shown)
        gain = Gain(
            what=rung.name,
            change=f"broke through to {rung.name}",
            source=GrowthKind.BREAKTHROUGH.value,
            reason=step.text,
        )
        change = CharacterChange(id=actor.id, ladders=[climbed], gains=[gain])
        deed = _loud_deed(state, actor, rung.name) if rung.loud else None
        return (
            f"{cap(who)} {_break(state, actor)} through to {rung.name}.",
            (StateDelta(characters=[change])),
            deed,
        )
    if result is StepResult.PARTIAL:
        hurt = ConditionChange(health=Health.HURT, wounds=["a breakthrough that stalled"])
        change = CharacterChange(id=actor.id, condition=hurt)
        why = f"The breakthrough to {rung.name} stalls, leaving {_them(state, actor)} shaken."
        return why, StateDelta(characters=[change]), None
    worse = _worse(actor.sheet.condition.health, Health.WOUNDED)
    wound = ConditionChange(health=worse, wounds=["a breakthrough gone wrong"])
    change = CharacterChange(id=actor.id, condition=wound)
    why = f"The breakthrough to {rung.name} goes wrong and wounds {_them(state, actor)}."
    return why, StateDelta(characters=[change]), None


def _break(state: WorldState, actor: Character) -> str:
    return "break" if actor.id == state.player_id else "breaks"


def _them(state: WorldState, actor: Character) -> str:
    return "you" if actor.id == state.player_id else "them"


def _worse(current: Health, floor: Health) -> Health:
    order = list(Health)
    return floor if order.index(floor) > order.index(current) else current


def _loud_deed(state: WorldState, actor: Character, rung: str) -> ProposedDeed:
    return ProposedDeed(
        kind="breakthrough",
        text=f"{cap(possessive(state, actor.id))} breakthrough to {rung}",
        actor_id=actor.id if actor.id != state.player_id else None,
        place_id=actor.location_id or state.scene.place_id,
        severity=2,
        visibility=Visibility.PUBLIC,
        traces=[
            Trace(
                kind=TraceKind.NOISE,
                text=f"Signs of a breakthrough to {rung}, seen from afar.",
                strength=LOUD_STRENGTH,
            )
        ],
    )


# --- skills, techniques and powers (A4, A9) -------------------------------------------------


@dataclass(frozen=True)
class Progress:
    """What a stretch of training did: the reason in words, the engine's changes, and the effort
    now recorded toward the gain (zero once it is made)."""

    reason: str
    effects: StateDelta
    effort_s: float
    made: bool


def needed_hours(actor: Character, step: IntentStep) -> float:
    training = step.training
    assert training is not None
    if training.kind is GrowthKind.SKILL:
        skill = actor.sheet.skill(training.what)
        level = skill.level if skill is not None else SkillLevel.UNTRAINED
        return SKILL_HOURS.get(level, SKILL_HOURS[SkillLevel.EXPERT])
    if training.kind is GrowthKind.POWER:
        return POWER_HOURS
    hours = TECHNIQUE_HOURS
    if training.invents and not learning_gift(actor):
        hours *= INVENT_FACTOR
    return hours


def pace_and_need(state: WorldState, actor: Character, step: IntentStep) -> tuple[float, float]:
    """A4. The effective effort per hour of effort put in, and the effort the gain needs in
    seconds: none for a copycat watching someone who knows the move."""
    training = step.training
    assert training is not None
    teacher = teacher_of(state, actor, step)
    instant = (
        training.kind is GrowthKind.TECHNIQUE
        and teacher is Teacher.WATCHING
        and copycat(actor)
        and _shows_it(state, step)
    )
    return pace(actor, teacher), 0.0 if instant else needed_hours(actor, step) * HOUR


def progress(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    lived_s: int,
    effort_so_far: float,
    power_settled: stop.Settlements,
    start: Mastery = Mastery.LEARNING,
) -> Progress:
    """A4. Add the stretch's effort to what was put in before, and make the gain once it is
    enough. A copycat watching a technique learns it at once. `start` is where the actor's skill
    puts a new move (`engine.levels`): a technique trained through is practiced, or there if
    that is higher, and one copied at a glance starts there."""
    training = step.training
    assert training is not None
    teacher = teacher_of(state, actor, step)
    if teacher is not training.teacher:
        training = training.model_copy(update={"teacher": teacher})
        step = step.model_copy(update={"training": training})
    rate, need = pace_and_need(state, actor, step)
    total = effort_so_far + effort_s(lived_s) * rate
    instant = need == 0
    key = practice_key(step)
    who = name(state, actor.id)
    if not instant and total < need:
        practice = Practice(key=key, what=training.what, effort_s=int(total))
        change = CharacterChange(id=actor.id, practice=[practice])
        hours = total / HOUR
        reason = (
            f"{cap(who)} {_make(state, actor)} progress toward {training.what}: about"
            f" {_hours(hours)} of the {_hours(need / HOUR)} it takes at this pace."
        )
        return Progress(reason, StateDelta(characters=[change]), total, made=False)

    done = Practice(key=key, what=training.what, effort_s=0)
    if training.kind is GrowthKind.SKILL:
        return _skill_made(state, actor, step, done)
    if training.kind is GrowthKind.POWER and training.grants is not PowerGrant.NONE:
        return _grant_made(state, actor, step, done, power_settled)
    return _technique_made(state, actor, step, done, instant, start)


def _make(state: WorldState, actor: Character) -> str:
    return "make" if actor.id == state.player_id else "makes"


def _hours(hours: float) -> str:
    if hours < 1:
        return f"{max(1, round(hours * 60))} minutes"
    if hours < 10:
        return f"{hours:.1f} hours".replace(".0 hours", " hours")
    return f"{round(hours):,} hours"


def _skill_made(state: WorldState, actor: Character, step: IntentStep, done: Practice) -> Progress:
    training = step.training
    assert training is not None
    skill = actor.sheet.skill(training.what)
    level = skill.level if skill is not None else SkillLevel.UNTRAINED
    raised = list(SkillLevel)[min(level.rank + 1, SkillLevel.MASTER.rank)]
    skill_name = skill.name if skill is not None else training.what.strip()
    new = Skill(name=skill_name, level=raised, notes=skill.notes if skill is not None else "")
    gain = Gain(
        what=skill_name,
        change=f"{level.value} to {raised.value}",
        source=f"training ({training.teacher.value})",
        reason=step.text,
    )
    change = CharacterChange(id=actor.id, skills=[new], gains=[gain], practice=[done])
    who = name(state, actor.id)
    reason = f"{cap(who)} {_become(state, actor)} {_article(raised.value)} at {skill_name}."
    return Progress(reason, StateDelta(characters=[change]), 0.0, made=True)


def _become(state: WorldState, actor: Character) -> str:
    return "become" if actor.id == state.player_id else "becomes"


def _article(level: str) -> str:
    return (
        level if level in ("skilled", "fair") else f"{'an' if level[0] in 'aeiou' else 'a'} {level}"
    )


def _technique(
    actor: Character,
    step: IntentStep,
    power_id: str | None,
    mastery: Mastery = TRAINED,
) -> Technique:
    training = step.training
    assert training is not None
    new_id = technique_id(training.what, {t.id for t in actor.sheet.techniques})
    effect = training.effect.strip()
    if not effect and training.grants is not PowerGrant.NONE:
        effect = GRANT_WORDS[training.grants]
    learned = "their own" if training.invents else training.teacher.value
    if training.teacher_id:
        learned = training.teacher_id
    return Technique(
        id=new_id,
        name=training.what.strip(),
        effect=effect,
        learned_from=learned,
        power_id=power_id,
        mastery=mastery,
    )


def _technique_made(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    done: Practice,
    instant: bool,
    start: Mastery,
) -> Progress:
    training = step.training
    assert training is not None
    mastery = start if instant else max(start, TRAINED, key=lambda m: m.rank)
    technique = _technique(actor, step, training.power_id, mastery)
    gain = Gain(
        what=technique.name,
        change="learned",
        source="watching" if instant else f"training ({training.teacher.value})",
        reason=step.text,
    )
    change = CharacterChange(id=actor.id, techniques=[technique], gains=[gain], practice=[done])
    who = name(state, actor.id)
    how = "picks up" if actor.id != state.player_id else "pick up"
    verb = f"{how} {technique.name} just by watching" if instant else f"{_learn(state, actor)}"
    reason = f"{cap(who)} {verb}." if instant else f"{cap(who)} {verb} {technique.name}."
    return Progress(reason, StateDelta(characters=[change]), 0.0, made=True)


def _learn(state: WorldState, actor: Character) -> str:
    return "learn" if actor.id == state.player_id else "learns"


def _grant_made(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    done: Practice,
    power_settled: stop.Settlements,
) -> Progress:
    """A9, A4. An idea earned: a technique on the sheet, the power's new setting, and a ruling of
    its own, so the power's first ruling stands."""
    training = step.training
    assert training is not None
    power = stop_power(actor, training.power_id)
    assert power is not None
    technique = _technique(actor, step, power.id)
    setting = GRANT_SETTINGS[training.grants]
    power_settled.put(power, setting.key, setting.value)
    topic = f"technique:{slug(training.what)}"
    ruling = Ruling(
        id=f"ruling-{power.id}-{topic}",
        topic=topic,
        power_id=power.id,
        question=step.text,
        answer=GRANT_WORDS[training.grants],
        holds=True,
        source=RulingSource.GROWTH,
    )
    gain = Gain(
        what=technique.name,
        change=f"a new way to use {power.name}",
        source=f"training ({training.teacher.value})",
        reason=step.text,
    )
    change = CharacterChange(
        id=actor.id,
        techniques=[technique],
        gains=[gain],
        practice=[done],
        rulings=[ruling],
        powers=[PowerChange(id=power.id, settings=[setting])],
    )
    who = name(state, actor.id)
    reason = (
        f"{cap(who)} {_find(state, actor)} it: {technique.name}. {GRANT_WORDS[training.grants]}"
    )
    return Progress(reason, StateDelta(characters=[change]), 0.0, made=True)


def _find(state: WorldState, actor: Character) -> str:
    return "find" if actor.id == state.player_id else "finds"


# --- moves pulled off in play (A4, G25) -----------------------------------------------------


def proven(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    moves: list[Move],
    earlier: list[Technique],
    start: Mastery = Mastery.LEARNING,
) -> tuple[str, list[Technique], StateDelta]:
    """A4, G25. The moves a step pulled off cleanly become techniques of the actor's own, so the
    next use finds them on the sheet and counts them like any technique: a move made with a
    power of theirs, a technique they were still learning, or a move made of the world's energy
    they hold. Each starts at `start`, where their skill puts a new move (`engine.levels`). One
    a technique of theirs already names, on the sheet or learned `earlier` in this plan, is that
    technique, and one that names a technique someone else knows is that person's school's
    (G25), unless they are learning it: neither is recorded. A technique they were learning is
    theirs from here, so the effort put in toward it is cleared. The reason in the world's
    words, the new techniques, and the engine's change."""
    known = [*actor.sheet.techniques, *earlier]
    others = [c for c in state.characters.values() if c.id != actor.id]
    taken = {t.id for t in known}
    techniques: list[Technique] = []
    gains: list[Gain] = []
    learned: list[Practice] = []
    for move in moves:
        if any(same_way(t.name, move.name) for t in [*known, *techniques]):
            continue
        teachers = [
            c.id for c in others if any(mentions(t.name, move.name) for t in c.sheet.techniques)
        ]
        if teachers and move.practice is None:
            continue
        new_id = technique_id(move.name, taken)
        taken.add(new_id)
        techniques.append(
            Technique(
                id=new_id,
                name=move.name,
                style=move.style,
                learned_from=min(teachers) if teachers else "their own",
                power_id=move.power.id if move.power is not None else None,
                mastery=start,
            )
        )
        gains.append(
            Gain(what=move.name, change="learned", source="pulled off in play", reason=step.text)
        )
        if move.practice is not None:
            learned.append(move.practice.model_copy(update={"effort_s": 0}))
    if not techniques:
        return "", [], StateDelta()
    whose = "yours" if actor.id == state.player_id else possessive(state, actor.id)
    named = " and ".join(t.name for t in techniques)
    which = "techniques" if len(techniques) > 1 else "a technique"
    reason = f"{named} {'are' if len(techniques) > 1 else 'is'} {which} of {whose} now."
    change = CharacterChange(id=actor.id, techniques=techniques, gains=gains, practice=learned)
    return reason, techniques, StateDelta(characters=[change])


# --- mastery (A4) ---------------------------------------------------------------------------

# A4. What an hour of practising a move they know counts for, in uses, at an ordinary pace.
USES_PER_HOUR = 1.0
PRACTICE_KEY = "mastery:"
MASTERY_WORDS = {
    Mastery.LEARNING: "learning",
    Mastery.PRACTICED: "practiced",
    Mastery.SKILLED: "skilled",
    Mastery.SECOND_NATURE: "second nature",
    Mastery.OWN: "their own",
}


@dataclass
class Moves:
    """A4. The actor's techniques as a plan has changed them so far, by id: the ones it made
    theirs and the ones whose count of uses it raised. `counted` is how much each has counted
    for from being used this turn, since a turn counts once for a move, at its best step."""

    now: dict[str, Technique] = field(default_factory=dict)
    counted: dict[str, int] = field(default_factory=dict)

    def latest(self, technique: Technique) -> Technique:
        return self.now.get(technique.id, technique)


def used_in(
    actor: Character, techniques: list[Technique], moves: list[Move], earlier: list[Technique]
) -> list[Technique]:
    """A4. The techniques of the actor's a step used: those it drew on, and those its moves
    name, on the sheet or made theirs `earlier` in this plan. Each once."""
    theirs = [*actor.sheet.techniques, *earlier]
    named = [t for move in moves for t in theirs if same_way(t.name, move.name)]
    found: dict[str, Technique] = {}
    for technique in [*techniques, *named]:
        found.setdefault(technique.id, technique)
    return list(found.values())


def used(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    techniques: list[Technique],
    rolled: bool,
    moves: Moves,
) -> tuple[str, StateDelta]:
    """A4. Using a move is how it grows. Each technique the step used counts one use, or two
    when a roll decided the step, which is use against real resistance. A turn counts once for
    a move, at its best step, however many steps of the plan use it. The reason for any that
    rose, in the world's words, and the engine's change."""
    count = levels.RESISTED_USE if rolled else levels.PLAIN_USE
    gift = talent(actor)
    changed: list[Technique] = []
    gains: list[Gain] = []
    risen: list[str] = []
    for technique in techniques:
        more = count - moves.counted.get(technique.id, 0)
        if more <= 0:
            continue
        moves.counted[technique.id] = count
        before = moves.latest(technique)
        after = _with_uses(before, more, gift)
        if after == before:
            continue
        moves.now[technique.id] = after
        changed.append(after)
        if after.mastery is not before.mastery:
            gains.append(_mastery_gain(before, after, "use in play", step.text))
            risen.append(_risen(state, actor, before, after))
    if not changed:
        return "", StateDelta()
    change = CharacterChange(id=actor.id, techniques=changed, gains=gains)
    return " ".join(risen), StateDelta(characters=[change])


def practice_uses(lived_s: int, rate: float) -> int:
    """A4. What a stretch of practising a move they know counts for, in uses: one for each hour
    of effort at the pace they keep (`effort_s`, `pace`), and one at least."""
    return max(1, int(effort_s(lived_s) * rate * USES_PER_HOUR // HOUR))


def practised(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    technique: Technique,
    lived_s: int,
    moves: Moves,
) -> tuple[str, StateDelta, TrainingSoFar]:
    """A4. A stretch spent practising a technique they know counts toward its mastery, an hour
    of effort for a use, more with a teacher (`pace`). The reason for a rise, the engine's
    change, and where the stretch started, so one cut short counts the time it ran
    (`practice_cut`)."""
    rate = pace(actor, teacher_of(state, actor, step))
    so_far = TrainingSoFar(
        key=f"{PRACTICE_KEY}{technique.id}", what=technique.name, rate=rate, practising=True
    )
    before = moves.latest(technique)
    after = _with_uses(before, practice_uses(lived_s, rate), talent(actor))
    if after == before:
        return "", StateDelta(), so_far
    moves.now[technique.id] = after
    gains, reason = [], ""
    if after.mastery is not before.mastery:
        gains = [_mastery_gain(before, after, "practice", step.text)]
        reason = _risen(state, actor, before, after)
    change = CharacterChange(id=actor.id, techniques=[after], gains=gains)
    return reason, StateDelta(characters=[change]), so_far


def practice_cut(actor: Character, so_far: TrainingSoFar, lived_s: int, why: str) -> StateDelta:
    """A4. Practice that an event cut short counts the time it ran, on the technique as the
    sheet has it now."""
    technique = actor.sheet.technique(so_far.key.removeprefix(PRACTICE_KEY))
    if technique is None or lived_s <= 0:
        return StateDelta()
    after = _with_uses(technique, practice_uses(lived_s, so_far.rate), talent(actor))
    if after == technique:
        return StateDelta()
    gains = []
    if after.mastery is not technique.mastery:
        gains = [_mastery_gain(technique, after, "practice", why)]
    return StateDelta(characters=[CharacterChange(id=actor.id, techniques=[after], gains=gains)])


def _with_uses(technique: Technique, more: int, gift: float) -> Technique:
    mastery, uses = levels.grown(technique.mastery, technique.uses, more, gift)
    return technique.model_copy(update={"mastery": mastery, "uses": uses})


def _mastery_gain(before: Technique, after: Technique, source: str, reason: str) -> Gain:
    change = f"{MASTERY_WORDS[before.mastery]} to {MASTERY_WORDS[after.mastery]}"
    return Gain(what=after.name, change=change, source=source, reason=reason)


def _risen(state: WorldState, actor: Character, before: Technique, after: Technique) -> str:
    whose = cap(possessive(state, actor.id))
    was, now = MASTERY_WORDS[before.mastery], MASTERY_WORDS[after.mastery]
    return f"{whose} {after.name} has grown from {was} to {now}."
