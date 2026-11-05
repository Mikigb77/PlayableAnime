"""N6: what strikes back at the player character.

A fight goes both ways. After each step the player character takes in a fight, the foes still in
it answer, and a step that faces a danger nobody embodies, such as a long drop or a burning roof,
meets that danger. Both are settled like any step, logic first and the dice only where the facts
leave it open (A2, A3), and recorded before anything is narrated (F4):

- **Who answers.** The foes of the fight the scene is in, or that this plan started, who are still
  in it: alive, able to act, with the player character, and not frozen in their time stop
  (W10a). One the step killed or subdued doesn't answer, and a move that got cleanly away from
  those it faced, such as a run or a leap, without harming anyone, leaves them behind.
- **What they are out to do.** What the interpret step says they mean (`StepFacts.foes_mean`): a
  sparring partner holds back, guards take them alive, an assassin kills. Otherwise they answer
  in kind, and anyone fighting the character means at least to wound them.
- **How it lands.** The foes are measured against the character on might, the strongest of them
  with those close behind them adding numbers (A8), the same way the character is measured
  against them. Far stronger foes land it with no roll, and so does anyone against a character
  who can't fend them off (bound, asleep, dying); far weaker foes can't get through. Only what
  lies between is rolled. The character's own step moves those odds: one that failed
  or was ruled out leaves them open, and one that cleanly succeeded keeps them on top. The
  difficulty works for the player here too, so foes roll worse on Story and better on Brutal
  (A5).
- **A danger** is the interpret step's (`StepFacts.danger`): how surely it hurts an ordinary
  person, and whether it kills or wounds. A body above a person's peak takes it better, one class
  for each step of power above it, and the step itself moves the odds as above.
- **What it does.** A killing blow the character couldn't stop kills them: cut in half,
  beheaded. One that lands in a fight that was open kills outright on a roll, and otherwise
  leaves them badly wounded, or maimed with a wound that lasts; one that only partly lands wounds
  them. A wound wounds, a partial one hurts, and subduing brings them down. Harm builds up: a blow
  no worse than what they already carry makes it one step worse, and anything harmful on top of
  dying kills.

A peril that hurts the player character stops the plan there, so the player decides what to do
next (R6). Each foe's blow is their deed against the player character (W1).
"""

from dataclasses import dataclass, field

from engine.context import Difficulty
from engine.contracts.delta import CharacterChange, ConditionChange, StateDelta
from engine.contracts.intent import ActionKind, Aim, IntentStep, OutcomeClass
from engine.contracts.resolution import Harm, Peril, ProposedDeed
from engine.invariants import ancestry
from engine.resolve import odds as odds_mod
from engine.resolve.effects import proposed_deed
from engine.resolve.power import SUBDUED_STATE, helpless_state, scale, standing
from engine.resolve.powers import time_stop as stop
from engine.resolve.strangers import PEAK_PERSON_TIER
from engine.resolve.words import cap, name
from engine.rng import SeededRng
from engine.state.cast import Character, CharacterStatus, DeathCertainty
from engine.state.records import StepResult
from engine.state.scene import EncounterKind
from engine.state.sheet import Health, PowerAxis
from engine.state.world import WorldState

# How much the character's own step moves the odds of what strikes back, in log-odds: a step that
# failed leaves them open, and one that cleanly succeeded keeps them on top.
EXPOSED_SHIFT = 0.7
# How likely a killing blow that lands in a fight that was open, rather than one the character
# couldn't stop, kills outright; otherwise it leaves a grave wound.
FATAL_ODDS = 0.5
# How likely such a grave wound lasts: a lost hand, an eye.
MAIM_ODDS = 0.35
# Steps too long to be part of a fight: the encounter ends before they play (W10).
_OUT_OF_THE_FIGHT = {ActionKind.REST, ActionKind.WORK, ActionKind.TRAVEL, ActionKind.TIME_SKIP}

_HEALTH = list(Health)
_CLASSES = [
    OutcomeClass.RULED_OUT,
    OutcomeClass.LONG_SHOT,
    OutcomeClass.CONTESTED,
    OutcomeClass.CERTAIN,
]
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
    and the foes still fighting the character afterwards."""

    perils: list[Peril] = field(default_factory=list)
    effects: StateDelta = field(default_factory=StateDelta)
    deeds: list[ProposedDeed] = field(default_factory=list)
    fighting: list[str] = field(default_factory=list)
    escaped: list[str] = field(default_factory=list)  # foes the step got cleanly away from

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
    difficulty: Difficulty,
    rng: SeededRng,
) -> Struck:
    """What strikes back at the player character for `step`, settled with its `outcome_class` and
    `result`: the foes of the fight first, then a danger the step faced. `faced` are the living
    characters who could respond to the step, `out` those this plan already took out of the fight
    (killed, subdued or got away from, this step's kills included), and `fighting` the foes this
    plan already fought. `frozen` means the player character holds the world in a time stop."""
    struck = Struck()
    health = player.sheet.condition.health
    foes, aim, escaped = _foes(state, player, step, result, faced, out, fighting, frozen)
    struck.fighting, struck.escaped = [f.id for f in foes], escaped
    if foes and aim.harmful:
        peril = _blow(state, player, step, foes, aim, faced, outcome_class, result, difficulty, rng)
        struck.perils.append(peril)
        if peril.harm is not Harm.NONE:
            health = _health_after(health, peril.harm)
        struck.deeds.append(_deed(state, player, foes, peril))
    own_harm = step.aim.harmful and player.id in step.target_ids  # its danger is its means (F1)
    if outcome_class is not OutcomeClass.RULED_OUT and not struck.dead and not own_harm:
        danger = _danger(state, player, step, result, difficulty, rng.child("danger"))
        if danger is not None:
            if danger.harm is not Harm.NONE:
                danger = _worse(danger, health, player)
                health = _health_after(health, danger.harm)
            struck.perils.append(danger)
    struck.effects = _effects(player, struck.perils)
    return struck


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
    """The foes who answer the step, in a stable order, what they mean to do, and those the step
    got cleanly away from."""
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
        if foe is None or foe_id in out or not _in_the_fight(state, player, foe):
            continue
        if frozen and not stop.immune(foe):
            continue  # W10a: frozen in the character's time stop
        if away and foe_id in faced_ids:
            escaped.append(foe_id)  # the step got cleanly away from them
            continue
        foes.append(foe)
    meant = step.facts.foes_mean
    if meant is None:
        # In kind: a sparring bout stays one, and anyone fighting the character means at least
        # to wound them.
        meant = step.aim if step.aim.harmful else Aim.WOUND
    return foes, meant, escaped


def _in_the_fight(state: WorldState, player: Character, foe: Character) -> bool:
    """Alive, able to act and with the player character, like `encounters.still_in_it`."""
    if foe.id == player.id or foe.status is not CharacterStatus.ALIVE:
        return False
    if helpless_state(foe) is not None:
        return False
    here = player.location_id or state.scene.place_id
    if foe.id in state.scene.present_ids or foe.location_id is None or here is None:
        return True
    return here in ancestry(state.places, foe.location_id) or (
        foe.location_id in ancestry(state.places, here)
    )


def _blow(
    state: WorldState,
    player: Character,
    step: IntentStep,
    foes: list[Character],
    aim: Aim,
    faced: list[Character],
    outcome_class: OutcomeClass,
    result: StepResult,
    difficulty: Difficulty,
    rng: SeededRng,
) -> Peril:
    """The foes' blow, measured like a step of theirs against the player character (A8)."""
    measure = scale(state, PowerAxis.MIGHT, player, *foes)
    mine = standing(state, player, PowerAxis.MIGHT, measure)
    theirs = sorted(
        (standing(state, f, PowerAxis.MIGHT, measure) for f in foes),
        key=lambda s: (-s.tier, s.character.id),
    )
    strongest = theirs[0]
    close = sum(1 for s in theirs[1:] if strongest.tier - s.tier < measure.step)
    numbers = min(odds_mod.MAX_NUMBERS, odds_mod.NUMBERS_STEP * close)
    # The player character stands in their way: the gap is theirs minus the foes', less numbers.
    gap = (mine.tier - strongest.tier) / measure.step - numbers
    who = _names(state, [s.character for s in theirs])
    strike = f"{cap(who)} {'strike' if len(foes) > 1 else 'strikes'} back"
    helpless = helpless_state(player)
    roll = None
    you, are = name(state, player.id), _are(state, player)
    if gap >= odds_mod.RULED_OUT_AT:
        outcome, done = OutcomeClass.RULED_OUT, StepResult.FAILURE
        words = f"{you} {are} far beyond them"
    elif gap <= odds_mod.CERTAIN_AT or helpless is not None:
        outcome, done = OutcomeClass.CERTAIN, StepResult.SUCCESS
        words = f"{you} can't stop it" if helpless is None else f"{you} {are} {helpless}"
    else:
        outcome = OutcomeClass.LONG_SHOT if gap >= odds_mod.LONG_SHOT_AT else OutcomeClass.CONTESTED
        faced_ids = {c.id for c in faced}
        shift = _exposure(result, outcome_class) if any(f.id in faced_ids for f in foes) else 0.0
        chances = odds_mod.settle(
            odds_mod.gap_logit(gap),
            shift,
            odds_mod.BANDS[outcome],
            difficulty,
            against_player=True,
        )
        roll = odds_mod.roll(
            rng.child("outcome"),
            chances,
            label=strike,
            allowed=odds_mod.ALL_RESULTS,
            difficulty=difficulty,
        )
        done = roll.result
        words = roll.odds_label
        if outcome is OutcomeClass.LONG_SHOT:
            words = f"a long shot, {words}"
    harm = _harm(aim, outcome, done, rng.child("harm"))
    peril = Peril(
        by_ids=[f.id for f in foes],
        by=who,
        aim=aim,
        outcome_class=outcome,
        reason="",
        roll=roll,
        result=done,
        harm=harm,
    )
    peril = _worse(peril, player.sheet.condition.health, player)
    return peril.model_copy(update={"reason": _reason(state, player, strike, words, peril)})


def _danger(
    state: WorldState,
    player: Character,
    step: IntentStep,
    result: StepResult,
    difficulty: Difficulty,
    rng: SeededRng,
) -> Peril | None:
    """A danger the step faced, as the interpret step proposed it, for the character's body."""
    facts = step.facts
    what = facts.danger.strip()
    if not what:
        return None
    harm_aim = facts.danger_harm if facts.danger_harm in (Aim.KILL, Aim.WOUND) else Aim.WOUND
    proposed = facts.danger_class or OutcomeClass.CONTESTED
    measure = scale(state, PowerAxis.MIGHT, player)
    tier = standing(state, player, PowerAxis.MIGHT, measure).tier
    tougher = max(0, int((tier - PEAK_PERSON_TIER) // measure.step))
    outcome = _CLASSES[max(0, _CLASSES.index(proposed) - tougher)]
    roll = None
    if outcome is OutcomeClass.RULED_OUT:
        done, words = StepResult.FAILURE, "it can't do real harm"
        if tougher and proposed is not OutcomeClass.RULED_OUT:
            words = f"{name(state, player.id)} {_are(state, player)} too tough for it"
    elif outcome is OutcomeClass.CERTAIN:
        done, words = StepResult.SUCCESS, "there's no escaping it"
    else:
        chances = odds_mod.settle(
            odds_mod.logit(odds_mod.UNMEASURED_ODDS[outcome]),
            _exposure(result, OutcomeClass.CONTESTED),
            odds_mod.BANDS[outcome],
            difficulty,
            against_player=True,
        )
        roll = odds_mod.roll(
            rng.child("outcome"),
            chances,
            label=what,
            allowed=odds_mod.ALL_RESULTS,
            difficulty=difficulty,
        )
        done, words = roll.result, roll.odds_label
        if outcome is OutcomeClass.LONG_SHOT:
            words = f"a long shot, {words}"
    peril = Peril(
        by=what,
        aim=harm_aim,
        outcome_class=outcome,
        reason="",
        roll=roll,
        result=done,
        harm=_harm(harm_aim, outcome, done, rng.child("harm")),
    )
    return peril.model_copy(update={"reason": _reason(state, player, cap(what), words, peril)})


def _exposure(result: StepResult, outcome_class: OutcomeClass) -> float:
    """How the character's own step moves the odds of what strikes back at them."""
    if outcome_class is OutcomeClass.RULED_OUT or result is StepResult.FAILURE:
        return EXPOSED_SHIFT
    if result is StepResult.SUCCESS:
        return -EXPOSED_SHIFT
    return 0.0


def _harm(aim: Aim, outcome: OutcomeClass, result: StepResult, rng: SeededRng) -> Harm:
    if result is StepResult.FAILURE or not aim.harmful:
        return Harm.NONE
    if aim is Aim.KILL:
        if result is StepResult.PARTIAL:
            return Harm.WOUNDED
        if outcome is OutcomeClass.CERTAIN or rng.child("fatal").chance(FATAL_ODDS):
            return Harm.DEAD
        return Harm.MAIMED if rng.child("maim").chance(MAIM_ODDS) else Harm.BADLY_WOUNDED
    if aim is Aim.SUBDUE:
        return Harm.SUBDUED if result is StepResult.SUCCESS else Harm.HURT
    return Harm.WOUNDED if result is StepResult.SUCCESS else Harm.HURT


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


def _effects(player: Character, perils: list[Peril]) -> StateDelta:
    """The engine's changes for what struck: one for each peril that did harm, in order."""
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
        condition = ConditionChange(health=_HARM_HEALTH.get(peril.harm))
        if peril.harm is Harm.SUBDUED:
            condition = ConditionChange(states=[SUBDUED_STATE])
        elif peril.harm is Harm.MAIMED:
            condition.lasting_wounds = [f"a maiming wound {what}"]
        else:
            condition.wounds = [f"a wound {what}"]
        changes.append(CharacterChange(id=player.id, condition=condition))
    return StateDelta(characters=changes)


def _deed(
    state: WorldState, player: Character, foes: list[Character], peril: Peril
) -> ProposedDeed:
    """W1. The strongest foe's blow at the player character is their deed, landed or not."""
    blow = IntentStep(
        text=f"{peril.by} strike back at {name(state, player.id)}",
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
        foes[0].id,
        targets=[player],
        others=[],
        in_stopped_time=False,
    )
    assert deed is not None  # an aim at someone is always a deed
    return deed


def _reason(state: WorldState, player: Character, lead: str, words: str, peril: Peril) -> str:
    """In the world's words (A8), such as "The grey mage strikes back (very likely): it kills
    you." """
    if peril.outcome_class is OutcomeClass.RULED_OUT:
        return f"{lead}, but {words}."
    you = name(state, player.id)
    outcome = _HARM_WORDS[peril.harm].format(you=you, are=_are(state, player))
    if peril.harm is Harm.NONE:
        outcome = f"it misses {you}" if peril.by_ids else f"{you} come through unhurt"
    if peril.outcome_class is OutcomeClass.CERTAIN:
        return f"{lead}, and {words}: {outcome}."
    return f"{lead} ({words}): {outcome}."


def _are(state: WorldState, player: Character) -> str:
    return "are" if player.id == state.player_id else "is"


def _names(state: WorldState, people: list[Character]) -> str:
    names = [name(state, p.id) for p in people]
    if len(names) <= 2:
        return " and ".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"
