"""Growth (A4), breakthroughs (G19) and new ways to use a power (A9, W10a).

Code decides every gain, from the character's traits, the effort and time they put in, what they
learn from and the world's rules (A4). Effort is lived time, so training in a time stop or a
haste counts on the trainer's own clock (W10a), and it adds up across sessions on the sheet's
`practice` until the gain is made.

- **Effort.** The first twelve hours of a stretch count in full and the rest at a third, since
  nobody trains every waking hour of a year. A master doubles the pace, and a manual, a rival
  or watching someone helps less. Talent sets the rest (`engine.talent`): each thing grows at
  the pace of the best talent that covers it, twice as fast for a knack, four times for a
  genius and eight for someone one of a kind, and at half the pace under a weakness. Someone
  whose one of a kind talent covers a technique learns it at once by watching it done.
- **Skills** climb the one ladder of words, novice to master, each rank taking longer.
- **Techniques** take about 150 hours with a teacher's pace, three times that when the character
  invents one that no genius of theirs covers.
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
  grows with use: each turn the character uses it counts once, twice when their own throw
  decided the step, and three times for an insight, and each hour of practising it counts
  once, more with a teacher. Hours never stand between a character and a move the story
  already let them do. Talent sets the pace (`engine.talent`): a move a genius's talent covers
  takes a quarter of the uses, an hour of practice counts four, and it starts at practiced;
  one of a kind's takes an eighth and starts at skilled; a slow learner needs twice the uses.
- **Ranks** (G19) are earned, then thrown for. The sheet keeps the effort put toward the next
  rung of a ladder (`Rank`, under the key `ladder:<id>`). It fills with use in play, two hours
  of effort for a turn that used what the ladder measures, four where their own throw decided
  the step and six for an insight, and with training aimed at the rank, all at the pace their
  talent gives that ladder. How full it is reads as a stage: early, middle, late, and its peak
  once it is full. The first rung above the lowest takes about 100 hours and each rung above
  it twice the last.
- **Breakthroughs** (G19) are events. Before the peak an attempt is training toward the rung.
  At the peak it is thrown for, three dice against a level of 3 (A3): a talent that covers the
  climb adds a green die, two when it is one of a kind, a master's teaching adds one and so
  does each thing the rung lists that the character has (a pill, a beast core), none of which
  is required; a weakness throws one die fewer. Passed climbs the rung, so close keeps nine
  tenths of the rank and a miss three quarters, and they are hurt only when the way they went
  about it was risky. How long it takes is drawn too, so the world can interrupt it (W10). A
  loud rung's breakthrough is seen from afar (W1).
- **Which talent covers what** is ruled once and kept (`engine.resolve.powers.talents`).

A world with nothing extraordinary never grows a power (G6, G8).
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

from engine import levels
from engine import talent as talent_mod
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
from engine.resolve import throw as dice
from engine.resolve.checks import Move, Settled, same_way
from engine.resolve.powers import time_stop as stop
from engine.resolve.words import cap, mentions, name, possessive, stems
from engine.rng import SeededRng
from engine.state.bible import PowerLadder, Rung
from engine.state.cast import Character
from engine.state.records import StepResult, Trace, TraceKind, Visibility
from engine.state.sheet import (
    Gain,
    Health,
    LadderPosition,
    Mastery,
    Power,
    PowerAxis,
    Practice,
    RankStage,
    Ruling,
    RulingSource,
    Skill,
    SkillLevel,
    Technique,
    stage_named,
)
from engine.state.world import WorldState

# The words a gain is recorded in (`Gain.change`, `Gain.source`). A screen that shows how the
# character grew reads the record back through `read_gain`, so it never repeats them.
LEARNED = "learned"
NEW_USE = "a new way to use "
TO = " to "
WATCHING = "watching"
IN_PLAY = "pulled off in play"
BY_USE = "use in play"
PRACTICE = "practice"


def _trained(teacher: Teacher) -> str:
    return f"training ({teacher.value})"


FULL_EFFORT_S = 12 * HOUR
LONG_STRETCH_RATE = 1 / 3
TEACHER_RATE = {
    Teacher.SELF: 1.0,
    Teacher.MASTER: 2.0,
    Teacher.BOOK: 1.3,
    Teacher.RIVAL: 1.5,
    Teacher.WATCHING: 1.2,
}
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
# G19, A3. A breakthrough is three dice against a level of 3, whoever tries it.
BREAKTHROUGH_DICE = 3
BREAKTHROUGH_LEVEL = 3
MAX_HINDRANCES = 2
LOUD_STRENGTH = 90
# G19. Why a talent adds a green die to a breakthrough, and why one of a kind adds a second.
TALENT_DIE = "a talent for the climb"
ONE_OF_A_KIND_DIE = "being one of a kind at it"
MASTER_DIE = "a master's teaching"
# G19. Hours of ordinary effort a rung takes to fill: stepping onto a ladder from below it, the
# first rung above its lowest, and each rung above that twice the last.
FIRST_RUNG_HOURS = 50
RUNG_HOURS = 100
# G19. What a use in play is worth toward a rank, in hours of effort (`engine.levels`: one use
# where nothing resisted, two where their own throw decided the step, three for an insight).
RANK_HOURS_PER_USE = 2
# G19. What is left of a full rank after an attempt that fell just short, and after a miss.
CLOSE_KEEPS = 0.9
MISS_KEEPS = 0.75
RANK_KEY = talent_mod.ladder_key("")

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
    if training.kind is GrowthKind.BREAKTHROUGH:
        return talent_mod.ladder_key(training.ladder_id)
    if training.kind is GrowthKind.POWER:
        return f"power:{training.power_id or ''}:{training.grants.value}:{slug(training.what)}"
    return f"technique:{slug(training.what)}"


def effort_s(lived_s: int) -> float:
    """A4. How much of a stretch of lived time counts as training effort."""
    lived = max(0, lived_s)
    return min(lived, FULL_EFFORT_S) + max(0, lived - FULL_EFFORT_S) * LONG_STRETCH_RATE


def pace(actor: Character, teacher: Teacher, key: str) -> float:
    """A4. How much an hour of effort toward the thing `key` names counts for: what the teacher
    adds, times the pace their talent gives that thing (`engine.talent.standing`)."""
    return TEACHER_RATE[teacher] * talent_mod.standing(actor, key).pace


def talent_key(state: WorldState, actor: Character, step: IntentStep) -> str:
    """The thing a training step learns, as the rulings on talent name it. A breakthrough is
    the ladder it climbs, the one the step names or the only one there is."""
    training = step.training
    assert training is not None
    if training.kind is GrowthKind.BREAKTHROUGH:
        ladder, _ = _ladder(state, actor, training.ladder_id)
        return talent_mod.ladder_key(ladder.id if ladder is not None else training.ladder_id)
    return talent_mod.training_key(training)


def technique_pace(actor: Character, technique: Technique) -> float:
    """A4. How fast a technique of theirs grows with use: 1 for an ordinary character."""
    return talent_mod.standing(actor, talent_mod.technique_key(technique.name)).pace


def move_start(actor: Character, move: str, start: Mastery) -> Mastery:
    """A4. Where a new move by this name starts: at `start`, where their skill puts it, or
    where the talent that covers it does if that is higher (`engine.levels.TALENT_START`)."""
    steps = talent_mod.standing(actor, talent_mod.technique_key(move)).steps
    return max(start, levels.starting_mastery(None, steps), key=lambda m: m.rank)


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
    growing where the world has none, a teacher who isn't there, or the top of a ladder.
    Practising a technique they already know is never refused (`already_known`), and nothing a
    rung lists is ever a bottleneck (G19)."""
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
            return _ruled_out(f"{cap(who)} {_have(state, actor)} no power like that.", not_own=True)
    if training.kind is GrowthKind.SKILL:
        skill = actor.sheet.skill(training.what)
        if skill is not None and skill.level is SkillLevel.MASTER:
            return _ruled_out(f"{cap(who)} {_have(state, actor)} mastered {skill.name} already.")
    if training.kind is GrowthKind.BREAKTHROUGH:
        return _breakthrough_check(state, actor, step)
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


def _breakthrough_check(state: WorldState, actor: Character, step: IntentStep) -> Settled | None:
    """G19. A ladder that isn't there and a rung with none above it are the only things that
    stop work toward a rung. What the rung lists is a way there, never a requirement."""
    training = step.training
    assert training is not None
    ladder, position = _ladder(state, actor, training.ladder_id)
    if ladder is None:
        return _ruled_out("There is no such ladder to climb here.")
    current = position.rung if position is not None else -1
    if current + 1 >= len(ladder.rungs):
        return _ruled_out(no_rung_above(ladder))
    return None


def no_rung_above(ladder: PowerLadder) -> str:
    """G19, G18. Why a climb stops on a ladder's highest rung: the world holds nothing above
    it that anyone has told of. It stops there until the story reaches past the top and the
    ladder gains a rung (`engine.path.beyond_problem`)."""
    return f"Nothing anyone knows of lies above {ladder.rungs[-1].name}."


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
    """G19. A way the rung lists is theirs when the state holds it: something carried, a
    technique, a true fact the character knows, this turn's canon, or a master's guidance."""
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
    """Whether the one being watched knows the technique, so someone whose talent takes in a
    move on sight can have it at once."""
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


def _rule_text(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _ruled_out(reason: str, *, not_own: bool = False) -> Settled:
    return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason, not_own=not_own)


@dataclass(frozen=True)
class Progress:
    """What a stretch of training did: the reason in words, the engine's changes, and the effort
    now recorded toward the gain (zero once it is made)."""

    reason: str
    effects: StateDelta
    effort_s: float
    made: bool


# --- ranks (G19) -----------------------------------------------------------------------------


_STAGE_TOLD = {
    RankStage.EARLY: "in its early stage",
    RankStage.MIDDLE: "in its middle stage",
    RankStage.LATE: "in its late stage",
    RankStage.PEAK: "at its peak",
}


@dataclass(frozen=True)
class Rank:
    """G19. How far a character is toward the next rung of a ladder: that rung, the effort it
    takes to fill and the effort put in so far. `position` is where they stand now, or None
    below the ladder's first rung."""

    ladder: PowerLadder
    position: LadderPosition | None
    rung: Rung
    need_s: float
    effort_s: float

    @property
    def key(self) -> str:
        return talent_mod.ladder_key(self.ladder.id)

    @property
    def full(self) -> bool:
        return self.effort_s >= self.need_s

    @property
    def filled(self) -> float:
        """How full it is, from 0 to 1."""
        return min(1.0, self.effort_s / self.need_s)

    @property
    def stage(self) -> RankStage:
        if self.full:
            return RankStage.PEAK
        if 3 * self.effort_s >= 2 * self.need_s:
            return RankStage.LATE
        return RankStage.MIDDLE if 3 * self.effort_s >= self.need_s else RankStage.EARLY

    @property
    def own(self) -> Rung | None:
        """The rung they stand on."""
        return self.ladder.rungs[self.position.rung] if self.position is not None else None


def rung_need_s(index: int) -> float:
    """G19. The effort it takes to fill the way to the rung at `index`, in seconds."""
    hours = FIRST_RUNG_HOURS if index <= 0 else RUNG_HOURS * 2 ** (index - 1)
    return float(hours * HOUR)


def rank_of(actor: Character, ladder: PowerLadder, effort_s: float | None = None) -> Rank | None:
    """G19. Where the actor stands toward the next rung of `ladder`, or None on its last rung.
    The effort is what their sheet holds toward that rung, and never less than the stage the
    story put them on their rung at (`LadderPosition.stage`); a plan that has added to it
    passes what it holds now as `effort_s`."""
    position = next((p for p in actor.sheet.ladders if p.ladder_id == ladder.id), None)
    index = position.rung + 1 if position is not None else 0
    if index >= len(ladder.rungs):
        return None
    rung = ladder.rungs[index]
    need = rung_need_s(index)
    if effort_s is None:
        kept = actor.sheet.practiced(talent_mod.ladder_key(ladder.id))
        effort_s = float(kept.effort_s) if kept is not None and kept.what == rung.name else 0.0
        started = stage_named(position.stage) if position is not None else None
        if started is not None:
            effort_s = max(effort_s, started.starts * need)
    return Rank(ladder, position, rung, need, min(effort_s, need))


def rank_for(
    state: WorldState, actor: Character, step: IntentStep, efforts: dict[str, float]
) -> Rank | None:
    """The rank a step of training toward a rung works on, with what this plan has added to it
    so far (`efforts`, by practice key)."""
    training = step.training
    assert training is not None
    ladder, _ = _ladder(state, actor, training.ladder_id)
    if ladder is None:
        return None
    return rank_of(actor, ladder, efforts.get(talent_mod.ladder_key(ladder.id)))


def at_peak(state: WorldState, actor: Character, step: IntentStep) -> bool:
    """G19. Whether an attempt to break through would be thrown for: the rank is full."""
    rank = rank_for(state, actor, step, {})
    return rank is not None and rank.full


def _rank_words(state: WorldState, actor: Character, rank: Rank) -> str:
    """The rank as the reason names it: "your Qi Condensation", or the groundwork for a first
    rung."""
    whose = possessive(state, actor.id)
    own = rank.own
    return f"{whose} {own.name}" if own is not None else f"{whose} groundwork for {rank.rung.name}"


def _fill(
    state: WorldState, actor: Character, rank: Rank, more_s: float, source: str, why: str
) -> tuple[Rank, list[Practice], list[Gain], str]:
    """G19. Add effort to a rank, up to its peak: the rank after it, what the sheet keeps, a
    gain where the stage of a rung they stand on rose, and that rise in words."""
    after = replace(rank, effort_s=min(rank.need_s, rank.effort_s + max(0.0, more_s)))
    if after.effort_s <= rank.effort_s:
        return rank, [], [], ""
    kept = Practice(key=rank.key, what=rank.rung.name, effort_s=int(after.effort_s))
    if after.stage is rank.stage:
        return after, [kept], [], ""
    gains = []
    if rank.own is not None:
        change = f"{rank.stage.value}{TO}{after.stage.value}"
        gains = [Gain(what=rank.own.name, change=change, source=source, reason=why)]
    words = cap(_rank_words(state, actor, after))
    if after.full:
        told = f"{words} is at its peak: a breakthrough to {rank.rung.name} can be tried."
    else:
        told = f"{words} has reached its {after.stage.value} stage."
    return after, [kept], gains, told


def rank_trained(
    state: WorldState, actor: Character, step: IntentStep, rank: Rank, lived_s: int
) -> tuple[Progress, float]:
    """G19. A stretch of training aimed at the rank fills it, at the teacher's pace and the
    pace their talent gives the ladder (`pace`). At its peak nothing fills it further, and an
    attempt made before the peak is this training too. What it did, and the pace it went at."""
    training = step.training
    assert training is not None
    teacher = teacher_of(state, actor, step)
    rate = pace(actor, teacher, rank.key)
    who = name(state, actor.id)
    words = _rank_words(state, actor, rank)
    if rank.full:
        tries = "try" if actor.id == state.player_id else "tries"
        reason = (
            f"{cap(words)} is at its peak: nothing fills it further until {who} {tries} to"
            f" break through to {rank.rung.name}."
        )
        return Progress(reason, StateDelta(), rank.effort_s, made=True), rate
    after, kept, gains, risen = _fill(
        state, actor, rank, effort_s(lived_s) * rate, _trained(teacher), step.text
    )
    told = risen or (
        f"{cap(who)} {_make(state, actor)} progress toward {rank.rung.name}:"
        f" {words} is {_STAGE_TOLD[after.stage]}."
    )
    if training.attempt:
        told = (
            f"{cap(words)} is not at its peak yet, so this is training toward"
            f" {rank.rung.name}. {told}"
        )
    change = CharacterChange(id=actor.id, practice=kept, gains=gains)
    effects = StateDelta(characters=[change]) if kept else StateDelta()
    return Progress(told, effects, after.effort_s, made=after.full), rate


def rank_cut(
    state: WorldState, actor: Character, so_far: TrainingSoFar, lived_s: int, why: str
) -> StateDelta:
    """G19. Training toward a rung that an event cut short counts the time it ran, on the rank
    as the sheet has it now."""
    ladder = state.bible.ladder(so_far.key.removeprefix(RANK_KEY))
    rank = rank_of(actor, ladder) if ladder is not None else None
    if rank is None or rank.rung.name != so_far.what or lived_s <= 0:
        return StateDelta()
    effort = so_far.before_s + effort_s(lived_s) * so_far.rate
    _, kept, gains, _ = _fill(state, actor, rank, effort - rank.effort_s, PRACTICE, why)
    if not kept:
        return StateDelta()
    return StateDelta(characters=[CharacterChange(id=actor.id, practice=kept, gains=gains)])


def rank_used(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    *,
    axis: PowerAxis | None,
    own: bool,
    by_hand: bool,
    insight: bool,
    counted: dict[str, int],
    efforts: dict[str, float],
) -> tuple[str, StateDelta]:
    """G19. What a step in play adds to each rank it drew on. A ladder of might fills when the
    step used a power, a technique or a move of their own (`own`), or was a blow or a clash
    their own throw decided; any other ladder when their own throw decided a step on its axis.
    It counts one use where nothing resisted, two where their own throw decided it, however it
    went, and three for an insight, each `RANK_HOURS_PER_USE` hours of effort at the pace their
    talent gives the ladder. A turn counts once for a ladder, at its best step (`counted`), and
    `efforts` holds what the plan has added so far. The reason for a stage that rose, and the
    engine's change."""
    kept: list[Practice] = []
    gains: list[Gain] = []
    told: list[str] = []
    for position in actor.sheet.ladders:
        ladder = state.bible.ladder(position.ladder_id)
        if ladder is None:
            continue
        on_axis = by_hand and axis is ladder.axis
        if not on_axis and not (own and ladder.axis is PowerAxis.MIGHT):
            continue
        count = levels.PLAIN_USE
        if by_hand:
            count = levels.INSIGHT_USE if insight else levels.RESISTED_USE
        more = count - counted.get(ladder.id, 0)
        if more <= 0:
            continue
        counted[ladder.id] = count
        key = talent_mod.ladder_key(ladder.id)
        rank = rank_of(actor, ladder, efforts.get(key))
        if rank is None or rank.full:
            continue
        gift = talent_mod.standing(actor, key).pace
        effort = more * RANK_HOURS_PER_USE * HOUR * gift
        after, keeps, gained, risen = _fill(state, actor, rank, effort, BY_USE, step.text)
        efforts[key] = after.effort_s
        kept += keeps
        gains += gained
        told += [risen] if risen else []
    if not kept:
        return "", StateDelta()
    change = CharacterChange(id=actor.id, practice=kept, gains=gains)
    return " ".join(told), StateDelta(characters=[change])


# --- breakthroughs (G19) ---------------------------------------------------------------------


def ways(
    state: WorldState, actor: Character, step: IntentStep, rung: Rung, canon: Sequence[str]
) -> list[str]:
    """G19. The ways to the rung that the world knows and the character has, each worth a
    green die: a pill they carry, a technique, a true thing they know. None is required. A
    master's guidance is counted as the master's teaching, once."""
    return [
        need.strip().rstrip(".")
        for need in rung.needs
        if need.strip()
        and not stems(need) & _MASTER_STEMS
        and _need_met(state, actor, step, need, list(canon))
    ]


def breakthrough(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    rng: SeededRng,
    difficulty,
    *,
    greens: list[str] | tuple[str, ...] = (),
    canon: Sequence[str] = (),
) -> Settled:
    """G19, A3. An attempt at the peak of a rank is thrown for, never certain: three dice
    against a level of 3, whoever they are, since every rung is as far from the last. Green
    dice, two at most: a talent that covers the climb adds one, and a second when it is one of
    a kind (`engine.talent`); a master's teaching adds one; so does each way the rung lists
    that the character has (`ways`), and any advantage of the step that holds (`greens`). A
    weakness that covers the climb throws one die fewer, and each thing in the scene against
    them adds 5 to the number, two at most."""
    training = step.training
    assert training is not None
    ladder, position = _ladder(state, actor, training.ladder_id)
    assert ladder is not None
    rung = ladder.rungs[(position.rung if position is not None else -1) + 1]
    stands = talent_mod.standing(actor, talent_mod.ladder_key(ladder.id))
    reasons: list[str] = []
    if stands.steps >= talent_mod.ONE_OF_A_KIND_STEPS:
        reasons += [TALENT_DIE, ONE_OF_A_KIND_DIE]
    elif stands.steps > 0:
        reasons.append(TALENT_DIE)
    if teacher_of(state, actor, step) is Teacher.MASTER:
        reasons.append(MASTER_DIE)
    reasons += ways(state, actor, step, rung, canon)
    number = dice.level_number(
        BREAKTHROUGH_LEVEL,
        f"breaking through to {rung.name}, level {BREAKTHROUGH_LEVEL}",
        difficulty,
    )
    for hindrance in [h.strip() for h in step.facts.hindrances if h.strip()][:MAX_HINDRANCES]:
        number = number.plus(hindrance, levels.STEP)
    slow = stands.steps < 0
    count = BREAKTHROUGH_DICE - (1 if slow else 0)
    what = "A breakthrough against a weakness" if slow else "A breakthrough"
    roll = dice.throw(
        rng.child("outcome"),
        dice.Hand(count, f"{what}, {count} dice"),
        number,
        label=f"break through to {rung.name}",
        allowed=dice.ALL_RESULTS,
        difficulty=difficulty,
        greens=[*reasons, *greens],
        against=step.facts.up_against.strip() or f"The wall before {rung.name}.",
    )
    return Settled(dice.class_of(roll.odds), roll.result, f"{cap(dice.told(roll))}.", roll)


def breakthrough_effects(
    state: WorldState, actor: Character, step: IntentStep, result: StepResult
) -> tuple[str, StateDelta, ProposedDeed | None]:
    """G19. What an attempt at the peak did. Passed, they stand on the new rung and the rank
    starts to fill again from nothing. So close keeps nine tenths of the rank and a miss three
    quarters, so a miss costs time. They are hurt only when the way they went about it was
    risky (`Training.risky`): shaken by a throw that fell just short, wounded by a miss."""
    training = step.training
    assert training is not None
    ladder, position = _ladder(state, actor, training.ladder_id)
    assert ladder is not None
    current = position.rung if position is not None else -1
    rung = ladder.rungs[current + 1]
    key = talent_mod.ladder_key(ladder.id)
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
        emptied = Practice(key=key, what=rung.name, effort_s=0)
        change = CharacterChange(id=actor.id, ladders=[climbed], gains=[gain], practice=[emptied])
        deed = _loud_deed(state, actor, rung.name) if rung.loud else None
        return (
            f"{cap(who)} {_break(state, actor)} through to {rung.name}.",
            (StateDelta(characters=[change])),
            deed,
        )
    close = result is StepResult.PARTIAL
    keeps = CLOSE_KEEPS if close else MISS_KEEPS
    kept = Practice(key=key, what=rung.name, effort_s=int(rung_need_s(current + 1) * keeps))
    # The stage the story started them at no longer says where they are.
    stood = []
    if position is not None and position.stage:
        stood = [position.model_copy(update={"stage": ""})]
    condition = None
    how = "stalls just short" if close else "fails"
    if training.risky and close:
        condition = ConditionChange(health=Health.HURT, wounds=["a breakthrough that stalled"])
        how = f"stalls, leaving {_them(state, actor)} shaken"
    elif training.risky:
        worse = _worse(actor.sheet.condition.health, Health.WOUNDED)
        condition = ConditionChange(health=worse, wounds=["a breakthrough gone wrong"])
        how = f"goes wrong and wounds {_them(state, actor)}"
    rank = Rank(ladder, position, rung, rung_need_s(current + 1), float(kept.effort_s))
    why = (
        f"The breakthrough to {rung.name} {how}. {cap(_rank_words(state, actor, rank))} falls"
        f" back from its peak, and it takes more work before another try."
    )
    change = CharacterChange(id=actor.id, practice=[kept], ladders=stood, condition=condition)
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


def needed_hours(actor: Character, step: IntentStep) -> float:
    """A4. The hours of ordinary effort a gain takes. A technique the character invents takes
    three times as long, unless a talent covers it at a genius's pace or better."""
    training = step.training
    assert training is not None
    if training.kind is GrowthKind.SKILL:
        skill = actor.sheet.skill(training.what)
        level = skill.level if skill is not None else SkillLevel.UNTRAINED
        return SKILL_HOURS.get(level, SKILL_HOURS[SkillLevel.EXPERT])
    if training.kind is GrowthKind.POWER:
        return POWER_HOURS
    hours = TECHNIQUE_HOURS
    stands = talent_mod.standing(actor, talent_mod.training_key(training))
    if training.invents and stands.steps < talent_mod.GENIUS_STEPS:
        hours *= INVENT_FACTOR
    return hours


def pace_and_need(state: WorldState, actor: Character, step: IntentStep) -> tuple[float, float]:
    """A4. The effective effort per hour of effort put in, and the effort the gain needs in
    seconds: none for someone watching a technique done that a one of a kind talent of theirs
    covers, who has it on sight."""
    training = step.training
    assert training is not None
    teacher = teacher_of(state, actor, step)
    key = talent_key(state, actor, step)
    covered = talent_mod.standing(actor, key).steps >= talent_mod.ONE_OF_A_KIND_STEPS
    on_sight = covered or talent_mod.copies_on_sight(actor)
    instant = (
        training.kind is GrowthKind.TECHNIQUE
        and teacher is Teacher.WATCHING
        and on_sight
        and _shows_it(state, step)
    )
    return pace(actor, teacher, key), 0.0 if instant else needed_hours(actor, step) * HOUR


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
    enough. A technique taken in on sight is learned at once. `start` is where the actor's skill
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
        change=f"{level.value}{TO}{raised.value}",
        source=_trained(training.teacher),
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
        change=LEARNED,
        source=WATCHING if instant else _trained(training.teacher),
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
        change=f"{NEW_USE}{power.name}",
        source=_trained(training.teacher),
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
    they hold. Each starts at `start`, where their skill puts a new move (`engine.levels`), or
    higher where a talent of theirs covers it (`move_start`). One
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
                mastery=move_start(actor, move.name, start),
            )
        )
        gains.append(Gain(what=move.name, change=LEARNED, source=IN_PLAY, reason=step.text))
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
    count: int,
    moves: Moves,
) -> tuple[str, StateDelta]:
    """A4. Using a move is how it grows. Each technique the step used counts `count` uses: one
    where nothing resisted, two where the actor's own throw decided the step, which is use
    against real resistance, and three for an insight (`engine.levels`). A turn counts once for
    a move, at its best step, however many steps of the plan use it. The reason for any that
    rose, in the world's words, and the engine's change."""
    changed: list[Technique] = []
    gains: list[Gain] = []
    risen: list[str] = []
    for technique in techniques:
        more = count - moves.counted.get(technique.id, 0)
        if more <= 0:
            continue
        moves.counted[technique.id] = count
        before = moves.latest(technique)
        after = _with_uses(before, more, technique_pace(actor, technique))
        if after == before:
            continue
        moves.now[technique.id] = after
        changed.append(after)
        if after.mastery is not before.mastery:
            gains.append(_mastery_gain(before, after, BY_USE, step.text))
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
    of effort for a use, more with a teacher and with talent (`pace`): an hour is worth two
    uses to a knack, four to a genius and eight to someone one of a kind, on top of the fewer
    uses each mastery takes them (`technique_pace`). The reason for a rise, the engine's
    change, and where the stretch started, so one cut short counts the time it ran
    (`practice_cut`)."""
    key = talent_mod.technique_key(technique.name)
    rate = pace(actor, teacher_of(state, actor, step), key)
    so_far = TrainingSoFar(
        key=f"{PRACTICE_KEY}{technique.id}", what=technique.name, rate=rate, practising=True
    )
    before = moves.latest(technique)
    gift = technique_pace(actor, technique)
    after = _with_uses(before, practice_uses(lived_s, rate), gift)
    if after == before:
        return "", StateDelta(), so_far
    moves.now[technique.id] = after
    gains, reason = [], ""
    if after.mastery is not before.mastery:
        gains = [_mastery_gain(before, after, PRACTICE, step.text)]
        reason = _risen(state, actor, before, after)
    change = CharacterChange(id=actor.id, techniques=[after], gains=gains)
    return reason, StateDelta(characters=[change]), so_far


def practice_cut(actor: Character, so_far: TrainingSoFar, lived_s: int, why: str) -> StateDelta:
    """A4. Practice that an event cut short counts the time it ran, on the technique as the
    sheet has it now."""
    technique = actor.sheet.technique(so_far.key.removeprefix(PRACTICE_KEY))
    if technique is None or lived_s <= 0:
        return StateDelta()
    gift = technique_pace(actor, technique)
    after = _with_uses(technique, practice_uses(lived_s, so_far.rate), gift)
    if after == technique:
        return StateDelta()
    gains = []
    if after.mastery is not technique.mastery:
        gains = [_mastery_gain(technique, after, PRACTICE, why)]
    return StateDelta(characters=[CharacterChange(id=actor.id, techniques=[after], gains=gains)])


def _with_uses(technique: Technique, more: int, gift: float) -> Technique:
    mastery, uses = levels.grown(technique.mastery, technique.uses, more, gift)
    return technique.model_copy(update={"mastery": mastery, "uses": uses})


def _mastery_gain(before: Technique, after: Technique, source: str, reason: str) -> Gain:
    change = f"{MASTERY_WORDS[before.mastery]}{TO}{MASTERY_WORDS[after.mastery]}"
    return Gain(what=after.name, change=change, source=source, reason=reason)


def _risen(state: WorldState, actor: Character, before: Technique, after: Technique) -> str:
    whose = cap(possessive(state, actor.id))
    was, now = MASTERY_WORDS[before.mastery], MASTERY_WORDS[after.mastery]
    return f"{whose} {after.name} has grown from {was} to {now}."


# --- a gain read back (A4, G17) --------------------------------------------------------------


class GainKind(StrEnum):
    """What a gain on the record was."""

    BREAKTHROUGH = "breakthrough"  # a rung of one of the world's ladders (G19)
    STAGE = "stage"  # the rank they stand on filled to its next stage (G19)
    SKILL = "skill"  # a skill rose a level
    LEARNED = "learned"  # a technique, new on the sheet
    MASTERY = "mastery"  # a technique they had, a level better
    NEW_USE = "new_use"  # a new way to use a power, earned


class GainHow(StrEnum):
    """How a gain was made, as far as its record says."""

    SELF = Teacher.SELF.value
    MASTER = Teacher.MASTER.value
    BOOK = Teacher.BOOK.value
    RIVAL = Teacher.RIVAL.value
    WATCHING = Teacher.WATCHING.value
    PLAY = "play"  # by doing it when it counted
    PRACTICE = "practice"  # hours of practising it


@dataclass(frozen=True)
class GainRead:
    """A gain as its record tells it: what kind it was, the level it reached for a skill or a
    technique, the stage for a rank, the power a new use belongs to, and how it was made."""

    kind: GainKind
    now: SkillLevel | Mastery | RankStage | None = None
    power: str = ""
    how: GainHow | None = None


def read_gain(gain: Gain) -> GainRead | None:
    """The record of a gain read back, or None for one written in words this module doesn't
    write."""
    how = _how(gain.source)
    if gain.source == GrowthKind.BREAKTHROUGH.value:
        return GainRead(GainKind.BREAKTHROUGH)
    if gain.change == LEARNED:
        return GainRead(GainKind.LEARNED, how=how)
    if gain.change.startswith(NEW_USE):
        return GainRead(GainKind.NEW_USE, power=gain.change.removeprefix(NEW_USE), how=how)
    was, _, now = gain.change.partition(TO)
    levels_ = {level.value: level for level in SkillLevel}
    if was in levels_ and now in levels_:
        return GainRead(GainKind.SKILL, now=levels_[now], how=how)
    masteries = {words: mastery for mastery, words in MASTERY_WORDS.items()}
    if was in masteries and now in masteries:
        return GainRead(GainKind.MASTERY, now=masteries[now], how=how)
    stages = {stage.value: stage for stage in RankStage}
    if was in stages and now in stages:
        return GainRead(GainKind.STAGE, now=stages[now], how=how)
    return None


def _how(source: str) -> GainHow | None:
    if source in (IN_PLAY, BY_USE):
        return GainHow.PLAY
    if source == PRACTICE:
        return GainHow.PRACTICE
    if source == WATCHING:
        return GainHow.WATCHING
    found = re.fullmatch(r"training \((\w+)\)", source)
    if found is None or found[1] not in {teacher.value for teacher in Teacher}:
        return None
    return GainHow(found[1])
