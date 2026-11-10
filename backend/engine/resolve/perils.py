"""N6: what strikes back at the player character.

A fight goes both ways. After each step the player character takes in a fight, the foes still in
it answer, and a step that faces a danger nobody embodies, such as a long drop or a burning roof,
meets that danger. Both are settled like any step, logic first and the dice only where the facts
leave it open (A2, A3), and recorded before anything is narrated (F4). Every die is the player
character's own: they throw their defence, and how far it falls short says what the blow does.

- **Who answers.** The foes of the fight the scene is in, or that this plan started, who are still
  in it: alive, able to act, with the player character, and not frozen in their time stop
  (W10a). One the step killed or subdued doesn't answer, and a move that got cleanly away from
  those it faced, such as a run or a leap, without harming anyone, leaves them behind. A foe the
  step just got the better of has no answer to it: they answer a miss, a throw that fell just
  short, and any step that ignored them.
- **What they are out to do.** What the interpret step says they mean (`StepFacts.foes_mean`): a
  sparring partner holds back, guards take them alive, an assassin kills. Otherwise they answer
  a step aimed at them in kind, and anyone fighting the character means at least to wound them.
- **The defence throw.** The character throws the skill their step drew on, or their speed if
  that serves them better (`engine.resolve.capability.defence_hand`), against the level of the
  strongest foe at what they strike with, plus the rungs that foe stands above them, since a
  blow meets them head-on (G18). Each other foe near the strongest adds 5, 10 at most; a step
  of theirs that just missed adds 5; wounds and exhaustion count on both sides (A8). Foes two
  levels or more under the hand can't touch them, with no throw, and neither can foes as far
  below as the world's ladder says a rung shrugs off. A character who can't fend them off (bound,
  asleep, dying) takes it, with no throw. A step that is itself the defence, such as a parry,
  is that one throw: where it fell short, no second one is thrown.
- **Deadly.** When they mean to kill and can, the throw is marked Deadly before the dice land:
  a miss by more than 5 kills, and one that falls just short leaves the character badly wounded,
  maimed with a wound that lasts when it was short by 4 or 5. A wound falls to a hurt, and
  being taken falls to a hurt, the same way. How far the throw fell short decides it all:
  nothing hidden is drawn afterwards.
- **A danger** is the interpret step's (`StepFacts.danger`): how surely it hurts an ordinary
  person sets its level, and whether it kills or wounds says what a miss costs. A body above a
  person's peak takes it better, one level for each step of power above it. One that is certain
  to hurt a person needs no throw against a body no tougher than a person's.
- **Harm builds up**: a blow no worse than what they already carry makes it one step worse, and
  anything harmful on top of dying kills.

A throw over the top turns the blow: the character holds an opening on those foes, and their next
step against them throws a green die. A peril that hurts the player character stops the plan
there, so the player decides what to do next (R6). Each foe's blow is their deed against the
player character (W1).
"""

from dataclasses import dataclass, field

from engine import levels
from engine.context import Difficulty
from engine.contracts.delta import CharacterChange, ConditionChange, StateDelta
from engine.contracts.intent import ActionKind, Aim, IntentStep, OutcomeClass
from engine.contracts.resolution import Harm, Peril, ProposedDeed
from engine.resolve import capability
from engine.resolve import throw as dice
from engine.resolve.checks import Drawn
from engine.resolve.effects import proposed_deed
from engine.resolve.power import (
    SUBDUED_STATE,
    Scale,
    helpless_state,
    in_the_fray,
    rung_levels,
    rung_words,
    rungs_above,
    scale,
    shrugs_off,
    true_tier,
)
from engine.resolve.powers import time_stop as stop
from engine.resolve.strangers import PEAK_PERSON_TIER
from engine.resolve.words import cap, is_are, name, names
from engine.rng import SeededRng
from engine.state.cast import Character, CharacterStatus, DeathCertainty
from engine.state.records import Mark, RollRecord, StepResult
from engine.state.scene import EncounterKind
from engine.state.sheet import Health, PowerAxis
from engine.state.world import WorldState

# Steps too long to be part of a fight: the encounter ends before they play (W10).
_OUT_OF_THE_FIGHT = {ActionKind.REST, ActionKind.WORK, ActionKind.TRAVEL, ActionKind.TIME_SKIP}

_HEALTH = list(Health)
# N6, A3. What a blow does by how far the defence fell short: just short, and by more.
_FELL_SHORT = {
    Aim.KILL: {Mark.SO_CLOSE: Harm.BADLY_WOUNDED, Mark.MISSED: Harm.DEAD},
    Aim.WOUND: {Mark.SO_CLOSE: Harm.HURT, Mark.MISSED: Harm.WOUNDED},
    Aim.SUBDUE: {Mark.SO_CLOSE: Harm.HURT, Mark.MISSED: Harm.SUBDUED},
}
# N6. A killing blow that fell short by this much or more, and still within "so close", leaves
# a wound that lasts, such as a lost hand or eye.
MAIMS_SHORT_BY = 4
# What a miss costs, in a line, for a throw the interpret step wrote none for.
MISS_COSTS = {
    Aim.KILL: "A miss by more than 5 kills. Just short leaves a bad wound.",
    Aim.WOUND: "A miss by more than 5 is a wound. Just short is a hurt.",
    Aim.SUBDUE: "A miss by more than 5 and they are brought down. Just short is a hurt.",
}
# A3. What a step of the character's that missed adds to the defence that follows.
EXPOSED = levels.STEP
# N6. The level of a danger nobody embodies, from how surely it hurts an ordinary person.
_DANGER_LEVEL = {
    OutcomeClass.LONG_SHOT: 1,
    OutcomeClass.CONTESTED: 2,
    OutcomeClass.CERTAIN: 4,
}
_HARM_HEALTH = {
    Harm.HURT: Health.HURT,
    Harm.WOUNDED: Health.WOUNDED,
    Harm.BADLY_WOUNDED: Health.BADLY_WOUNDED,
    Harm.MAIMED: Health.BADLY_WOUNDED,
    Harm.DYING: Health.DYING,
}
_HARM_WORDS = {
    Harm.NONE: "it doesn't hurt {you}",
    Harm.HURT: "{you} {are} hurt",
    Harm.WOUNDED: "{you} {are} wounded",
    Harm.SUBDUED: "{you} {are} brought down",
    Harm.BADLY_WOUNDED: "{you} {are} badly wounded",
    Harm.MAIMED: "{you} {are} maimed, with a wound that will last",
    Harm.DYING: "{you} {are} dying",
    Harm.DEAD: "it kills {you}",
}


@dataclass
class Struck:
    """What struck back in one step: the perils, their changes to the state, the foes' deeds,
    the foes still fighting the character afterwards, and those a defence thrown over the top
    won them an opening on."""

    perils: list[Peril] = field(default_factory=list)
    effects: StateDelta = field(default_factory=StateDelta)
    deeds: list[ProposedDeed] = field(default_factory=list)
    fighting: list[str] = field(default_factory=list)
    escaped: list[str] = field(default_factory=list)  # foes the step got cleanly away from
    openings: list[str] = field(default_factory=list)

    @property
    def dead(self) -> bool:
        return any(a.harm is Harm.DEAD for a in self.perils)


def strike_back(
    state: WorldState,
    player: Character,
    step: IntentStep,
    *,
    outcome_class: OutcomeClass,
    result: StepResult,
    faced: list[Character],
    out: set[str],
    fighting: list[str],
    frozen: bool,
    health: Health,
    difficulty: Difficulty,
    rng: SeededRng,
    drawn: Drawn | None = None,
    defence: RollRecord | None = None,
) -> Struck:
    """What strikes back at the player character for `step`, settled with its `outcome_class` and
    `result`: the foes of the fight first, then a danger the step faced. `faced` are the living
    characters who could respond to the step, `out` those this plan already took out of the fight
    (killed, subdued or got away from, this step's kills included), and `fighting` the foes this
    plan already fought. `frozen` means the player character holds the world in a time stop,
    `health` is theirs once the step's own changes are in, `drawn` what the step drew on, and
    `defence` the step's own throw when the step was itself the defence."""
    struck = Struck()
    drawn = drawn or Drawn()
    before = health
    missed = outcome_class is OutcomeClass.RULED_OUT or result is StepResult.FAILURE
    foes, aim, escaped = _foes(state, player, step, result, faced, out, fighting, frozen)
    struck.fighting, struck.escaped = [f.id for f in foes], escaped
    # A3. A foe the step just got the better of has no answer to it.
    bested = {c.id for c in faced} if result is StepResult.SUCCESS and not missed else set()
    answering = [f for f in foes if f.id not in bested]
    if answering and aim.harmful:
        peril = _blow(
            state,
            player,
            answering,
            aim,
            step,
            drawn,
            missed=missed,
            health=health,
            difficulty=difficulty,
            rng=rng,
            defence=defence,
        )
        struck.perils.append(peril)
        health = _health_after(health, peril.harm)
        struck.deeds.append(_deed(player, peril))
        if _turned(peril):
            struck.openings = list(peril.by_ids)
    own_harm = step.aim.harmful and player.id in step.target_ids  # its danger is its means (F1)
    if outcome_class is not OutcomeClass.RULED_OUT and not struck.dead and not own_harm:
        danger = _danger(
            state, player, step, drawn, missed, health, difficulty, rng.child("danger")
        )
        if danger is not None:
            health = _health_after(health, danger.harm)
            struck.perils.append(danger)
    struck.effects = _effects(player, struck.perils, before)
    return struck


def _turned(peril: Peril) -> bool:
    """A3. A defence thrown over the top turns the blow."""
    thrown = peril.roll.throw if peril.roll is not None else None
    return thrown is not None and thrown.mark is Mark.OVER_THE_TOP


def _foes(
    state: WorldState,
    player: Character,
    step: IntentStep,
    result: StepResult,
    faced: list[Character],
    out: set[str],
    fighting: list[str],
    frozen: bool,
) -> tuple[list[Character], Aim, list[str]]:
    """The foes still in the fight after the step, in a stable order, what they mean to do, and
    those the step got cleanly away from."""
    if step.kind in _OUT_OF_THE_FIGHT:
        return [], Aim.NONE, []
    ids = list(fighting)
    encounter = state.scene.encounter
    if encounter is not None and encounter.kind is EncounterKind.FIGHT:
        ids += encounter.opponent_ids
    faced_ids = [c.id for c in faced]
    if step.aim.harmful or step.encounter is EncounterKind.FIGHT:
        ids += faced_ids  # the step starts a fight with whoever it faces
    # A move that harms no one and cleanly works, such as a run or a leap, gets away from them.
    away = step.kind is ActionKind.MOVE and not step.aim.harmful and result is StepResult.SUCCESS
    foes, escaped = [], []
    for foe_id in dict.fromkeys(ids):
        foe = state.characters.get(foe_id)
        if foe is None or foe_id in out or not in_the_fray(state, foe):
            continue
        if frozen and not stop.immune(foe):
            continue  # W10a: frozen in the character's time stop
        if away and foe_id in faced_ids:
            escaped.append(foe_id)  # the step got cleanly away from them
            continue
        foes.append(foe)
    meant = step.facts.foes_mean
    if meant is None:
        # In kind when the step aimed at them, so a sparring bout stays one; otherwise anyone
        # fighting the character means at least to wound them.
        at_them = step.aim.harmful and any(f.id in step.target_ids for f in foes)
        meant = step.aim if at_them else Aim.WOUND
    return foes, meant, escaped


@dataclass(frozen=True)
class _Attacker:
    """A foe's blow: their level at what they strike with, and the whole rungs they stand above
    the player character, since a blow meets them head-on (G18)."""

    foe: Character
    level: capability.Level
    rungs: int
    measure: Scale

    @property
    def per(self) -> int:
        return rung_levels(self.measure)

    @property
    def limit(self) -> int:
        """From how many rungs below their harm can't get through by ordinary means."""
        return shrugs_off(self.measure)

    @property
    def total(self) -> int:
        return self.level.level + self.rungs * self.per


def _attacker(
    state: WorldState, player: Character, foe: Character, step: IntentStep, drawn: Drawn
) -> _Attacker:
    level = capability.level_of(state, foe, step.facts.answers_with, drawn.skills, PowerAxis.MIGHT)
    rungs, measure = rungs_above(state, PowerAxis.MIGHT, player, foe)
    return _Attacker(foe, level, rungs, measure)


def _ordinary(foe: Character) -> bool:
    """G18. Whether a foe strikes by ordinary means: no power, no technique, no weapon with a
    history."""
    sheet = foe.sheet
    if sheet.powers or sheet.techniques:
        return False
    return not any(i.carried and i.history.strip() for i in sheet.resources.items)


def _blow(
    state: WorldState,
    player: Character,
    foes: list[Character],
    aim: Aim,
    step: IntentStep,
    drawn: Drawn,
    *,
    missed: bool,
    health: Health,
    difficulty: Difficulty,
    rng: SeededRng,
    defence: RollRecord | None,
) -> Peril:
    """The foes' blow, which the player character throws their defence against (A3, A8)."""
    ranked = sorted(
        (_attacker(state, player, f, step, drawn) for f in foes),
        key=lambda a: (-a.total, a.foe.id),
    )
    who = names(state, [a.foe for a in ranked])
    strike = f"{cap(who)} {'strike' if len(foes) > 1 else 'strikes'} back"
    you, are = name(state, player.id), is_are(state, player.id)
    # G18. Harm from as far below as the ladder says a rung shrugs off can't get through by
    # ordinary means: those foes can't hurt them, awake or asleep.
    able = [a for a in ranked if not (_ordinary(a.foe) and -a.rungs >= a.limit)]
    helpless = helpless_state(player)
    roll: RollRecord | None = None
    mark: Mark | None = None
    short_by = 0
    if not able:
        outcome, words = OutcomeClass.RULED_OUT, f"{you} {are} far beyond what they can hurt"
    elif helpless is not None:
        # Whoever they are, a character who can't fend them off can't stop it (A2).
        outcome, words, mark = OutcomeClass.CERTAIN, f"{you} {are} {helpless}", Mark.MISSED
    elif defence is not None and defence.throw is not None:
        # The step was itself the defence, and its throw fell short: that one throw decides.
        mark, short_by = defence.throw.mark, defence.throw.short_by
        outcome = dice.class_of(1 - defence.odds)
        held = "holds" if mark.passed else "fell short"
        words = f"{_your(state, player)} defence {held}, with no second throw"
    else:
        strongest = able[0]
        near = sum(1 for a in able[1:] if strongest.total - a.total <= capability.NEAR_LEVELS)
        hand = capability.defence_hand(state, player, step, drawn)
        number = dice.level_number(strongest.level.level, strongest.level.why, difficulty)
        number = number.raised(
            strongest.rungs * strongest.per,
            rung_words(state, player, strongest.foe, strongest.rungs, strongest.measure),
        )
        if not dice.open_against(hand, number.level):
            outcome = OutcomeClass.RULED_OUT
            words = f"they can't get past {_your(state, player)} guard"
        else:
            more = min(capability.MAX_NUMBERS, near)
            if more:
                count = {1: "one more", 2: "two more"}[more]
                number = number.plus(f"{count} at their side", levels.STEP * more)
            them = name(state, strongest.foe.id)
            for word, points in capability.condition_points(strongest.foe):
                number = number.plus(f"{them} {is_are(state, strongest.foe.id)} {word}", -points)
            for word, points in capability.condition_points(player, health):
                number = number.plus(f"{you} {are} {word}", points)
            if missed:
                number = number.plus(f"{_your(state, player)} own step missed", EXPOSED)
            deadly = aim is Aim.KILL
            means = {Aim.KILL: "meaning to kill", Aim.SUBDUE: f"meaning to take {you} down"}
            against = f"{strike}, {means[aim]}." if aim in means else f"{strike}."
            roll = dice.throw(
                rng.child("outcome"),
                hand,
                number,
                label=f"defend against {who}",
                allowed=dice.ALL_RESULTS,
                difficulty=difficulty,
                against=against,
                deadly=deadly,
                miss_costs=step.facts.miss_costs.strip() or MISS_COSTS[aim],
            )
            mark, short_by = roll.throw.mark, roll.throw.short_by
            outcome = dice.class_of(1 - roll.odds)
            words = dice.told(roll)
    peril = Peril(
        by_ids=[a.foe.id for a in ranked],  # the strongest first
        by=who,
        aim=aim,
        outcome_class=outcome,
        reason="",
        roll=roll,
        result=_landed(mark),
        harm=_harm(aim, mark, short_by),
    )
    peril = _worse(peril, health, player)
    return peril.model_copy(update={"reason": _reason(state, player, strike, words, peril)})


def _harm(aim: Aim, mark: Mark | None, short_by: int) -> Harm:
    """N6, A3. What a blow does, from how far the defence fell short of it. Nothing else is
    drawn: a killing blow that fell just short maims when it was short by 4 or 5."""
    harm = _FELL_SHORT[aim].get(mark, Harm.NONE) if mark is not None else Harm.NONE
    if harm is Harm.BADLY_WOUNDED and mark is Mark.SO_CLOSE and short_by >= MAIMS_SHORT_BY:
        return Harm.MAIMED
    return harm


def _landed(mark: Mark | None) -> StepResult:
    """The blow's own result, from how the defence fared: it lands where the defence missed,
    partly where it fell just short, and not at all where it held or was never needed."""
    if mark is Mark.MISSED:
        return StepResult.SUCCESS
    return StepResult.PARTIAL if mark is Mark.SO_CLOSE else StepResult.FAILURE


def _your(state: WorldState, player: Character) -> str:
    return "your" if player.id == state.player_id else f"{player.name}'s"


def _danger(
    state: WorldState,
    player: Character,
    step: IntentStep,
    drawn: Drawn,
    missed: bool,
    health: Health,
    difficulty: Difficulty,
    rng: SeededRng,
) -> Peril | None:
    """A danger the step faced, as the interpret step proposed it, which the character throws
    their defence against. How surely it hurts an ordinary person is its level, and a body
    above a person's peak takes it better, one level for each step of power above it."""
    facts = step.facts
    what = facts.danger.strip()
    if not what:
        return None
    harm_aim = facts.danger_harm if facts.danger_harm in (Aim.KILL, Aim.WOUND) else Aim.WOUND
    proposed = facts.danger_class or OutcomeClass.CONTESTED
    measure = scale(state, PowerAxis.MIGHT, player)
    tier = true_tier(state, player, PowerAxis.MIGHT)
    tougher = max(0, int((tier - PEAK_PERSON_TIER) // measure.step))
    level = _DANGER_LEVEL.get(proposed, 0) - tougher
    you, are = name(state, player.id), is_are(state, player.id)
    roll: RollRecord | None = None
    mark: Mark | None = None
    short_by = 0
    hand = capability.defence_hand(state, player, step, drawn)
    if level <= 0:
        outcome, words = OutcomeClass.RULED_OUT, "it can't do real harm"
        if tougher and proposed is not OutcomeClass.RULED_OUT:
            words = f"{you} {are} too tough for it"
    elif helpless_state(player) is not None or (proposed is OutcomeClass.CERTAIN and not tougher):
        # A2. What is certain to hurt a person is not thrown for against a person's body, and
        # nobody who can't move gets clear of anything.
        outcome, words, mark = OutcomeClass.CERTAIN, "there's no escaping it", Mark.MISSED
    elif not dice.open_against(hand, level):
        outcome, words = OutcomeClass.RULED_OUT, f"it is no match for {_your(state, player)} skill"
    else:
        number = dice.level_number(level, f"{what}, level {level}", difficulty)
        for word, points in capability.condition_points(player, health):
            number = number.plus(f"{you} {are} {word}", points)
        if missed:
            number = number.plus(f"{_your(state, player)} own step missed", EXPOSED)
        roll = dice.throw(
            rng.child("outcome"),
            hand,
            number,
            label=what,
            allowed=dice.ALL_RESULTS,
            difficulty=difficulty,
            against=f"{cap(what)}.",
            deadly=harm_aim is Aim.KILL,
            miss_costs=facts.miss_costs.strip() or MISS_COSTS[harm_aim],
        )
        mark, short_by = roll.throw.mark, roll.throw.short_by
        outcome = dice.class_of(1 - roll.odds)
        words = dice.told(roll)
    peril = Peril(
        by=what,
        aim=harm_aim,
        outcome_class=outcome,
        reason="",
        roll=roll,
        result=_landed(mark),
        harm=_harm(harm_aim, mark, short_by),
    )
    peril = _worse(peril, health, player)
    return peril.model_copy(update={"reason": _reason(state, player, cap(what), words, peril)})


def _worse(peril: Peril, health: Health, player: Character) -> Peril:
    """Harm builds up: a blow no worse than what they carry makes it a step worse, and anything
    harmful on top of dying kills."""
    harm = peril.harm
    level = _HARM_HEALTH.get(harm)
    if level is None or not player.alive:
        return peril
    if health is Health.DYING:
        harm = Harm.DEAD
    elif _HEALTH.index(level) <= _HEALTH.index(health):
        worse = _HEALTH[min(_HEALTH.index(health) + 1, _HEALTH.index(Health.DYING))]
        harm = next(h for h, hl in _HARM_HEALTH.items() if hl is worse and h is not Harm.MAIMED)
        if peril.harm is Harm.MAIMED and harm is Harm.BADLY_WOUNDED:
            harm = Harm.MAIMED
    return peril.model_copy(update={"harm": harm})


def _health_after(health: Health, harm: Harm) -> Health:
    level = _HARM_HEALTH.get(harm)
    if level is None:
        return health
    return level if _HEALTH.index(level) > _HEALTH.index(health) else health


def _effects(player: Character, perils: list[Peril], health: Health) -> StateDelta:
    """The engine's changes for what struck, from `health` after the step's own changes: one for
    each peril that did harm, in order, never leaving them better than they were."""
    changes = []
    for peril in perils:
        if peril.harm is Harm.NONE:
            continue
        if peril.harm is Harm.DEAD:
            changes.append(
                CharacterChange(
                    id=player.id,
                    status=CharacterStatus.DEAD,
                    death_certainty=DeathCertainty.CONFIRMED,
                )
            )
            break
        what = f"from {peril.by}"
        health = _health_after(health, peril.harm)
        condition = ConditionChange(health=health)
        if peril.harm is Harm.SUBDUED:
            condition = ConditionChange(states=[SUBDUED_STATE])
        elif peril.harm is Harm.MAIMED:
            condition.lasting_wounds = [f"a maiming wound {what}"]
        else:
            condition.wounds = [f"a wound {what}"]
        changes.append(CharacterChange(id=player.id, condition=condition))
    return StateDelta(characters=changes)


def _deed(player: Character, peril: Peril) -> ProposedDeed:
    """W1. The blow at the player character is the strongest foe's deed, landed or not."""
    strike = "strike" if len(peril.by_ids) > 1 else "strikes"
    blow = IntentStep(
        text=f"{cap(peril.by)} {strike} back at {player.name}",
        verb="attack",
        target_ids=[player.id],
        aim=peril.aim,
        kind=ActionKind.EXCHANGE,
        proposed_duration_s=0,
    )
    deed = proposed_deed(
        blow,
        peril.outcome_class,
        peril.result,
        peril.by_ids[0],
        targets=[player],
        others=[],
        in_stopped_time=False,
    )
    assert deed is not None  # an aim at someone is always a deed
    return deed


def _reason(state: WorldState, player: Character, lead: str, words: str, peril: Peril) -> str:
    """In the world's words (A8), such as "The grey mage strikes back. Speed, 2 dice, against
    the grey mage's spellcraft (expert), level 4: 19 against 37, missed. It kills you." """
    if peril.outcome_class is OutcomeClass.RULED_OUT:
        return f"{lead}, but {words}."
    you = name(state, player.id)
    outcome = _HARM_WORDS[peril.harm].format(you=you, are=is_are(state, player.id))
    if peril.harm is Harm.NONE:
        outcome = f"it misses {you}" if peril.by_ids else f"{you} come through unhurt"
        if peril.by_ids and _turned(peril):
            # A3. A defence thrown over the top turns the blow and wins an opening.
            whose = _your(state, player)
            outcome = f"{you} turn the blow, and {whose} next step against them throws a green die"
    if peril.roll is None:
        return f"{lead}, and {words}: {outcome}."
    return f"{lead}. {cap(words)}. {cap(outcome)}."
