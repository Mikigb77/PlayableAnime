"""N6: the world can kill the player character. After each step in a fight the foes still in it
strike back, and a step that meets a danger, such as a long drop, meets it, logic first and the
dice only where the facts leave it open (A2), on every difficulty (A5)."""

from collections import Counter

import pytest

from engine import pipeline
from engine.context import Difficulty
from engine.contracts import (
    ActionKind,
    Aim,
    Harm,
    Intent,
    OutcomeClass,
    StandingAction,
    StopReason,
)
from engine.invariants import check_transition
from engine.resolve.power import SUBDUED_STATE
from engine.state import (
    CharacterStatus,
    Encounter,
    EncounterKind,
    Health,
    PassingState,
    StepResult,
    WorldState,
)
from graph.turn.ending import ending_of
from graph.turn.types import TurnKind

from .worlds import (
    SEEDS,
    add,
    ctx,
    disciple,
    facts,
    resolve,
    rng,
    sect,
    step,
    stop_time,
    strike,
    wounded,
)


def fighting(state: WorldState, *foe_ids: str) -> WorldState:
    """Lin in the middle of a fight with `foe_ids`."""
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=list(foe_ids), started_turn=2, started_s=0
    )
    return state


def circle(meant: Aim | None = Aim.WOUND, **kw):
    """A step in the fight that harms nobody, so only the foes' answer can hurt."""
    return step("circle, looking for an opening", verb="circle", facts=facts(foes_mean=meant), **kw)


def jump(danger_class: OutcomeClass = OutcomeClass.CONTESTED, harm: Aim = Aim.KILL):
    return step(
        "jump off the bridge into the river",
        ActionKind.MOVE,
        3,
        verb="jump",
        facts=facts(
            danger="the long drop to the river", danger_class=danger_class, danger_harm=harm
        ),
    )


def one(state: WorldState, *steps, seed: int = 0, difficulty=Difficulty.BALANCED):
    return resolve(state, Intent(steps=list(steps)), seed, difficulty).steps[0]


def harms(state: WorldState, *steps, difficulty=Difficulty.BALANCED) -> Counter:
    return Counter(
        tuple(p.harm for p in one(state, *steps, seed=s, difficulty=difficulty).perils)
        for s in SEEDS
    )


# --- logic first ---------------------------------------------------------------------------------


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_a_far_stronger_foe_cuts_down_whoever_attacks_him_every_time_with_no_roll(difficulty):
    """Three realms up, Elder Bai can't be hurt by Lin's sword, and nothing Lin has stops his."""
    state = add(sect(), disciple("bai", "Elder Bai", rung=3))

    for seed in range(40):
        settled = one(state, strike("bai"), seed=seed, difficulty=difficulty)
        assert settled.outcome_class is OutcomeClass.RULED_OUT
        [peril] = settled.perils
        assert (peril.by_ids, peril.outcome_class, peril.roll) == (["bai"], "certain", None)
        assert peril.harm is Harm.DEAD and peril.aim is Aim.KILL  # in kind
        assert "can't stop it" in peril.reason
        [death] = [c for c in settled.effects.characters if c.id == "lin"]
        assert death.status is CharacterStatus.DEAD
        # His blow is his deed against Lin (W1).
        assert [(d.actor_id, d.victim_ids) for d in settled.deeds if d.actor_id == "bai"] == [
            ("bai", ["lin"])
        ]


def test_a_far_weaker_foe_cant_get_through():
    state = sect()
    lin = state.characters["lin"]
    lin.sheet.ladders[0].rung, lin.sheet.axes.might = 3, 8
    state = fighting(add(state, disciple("zhou", "Zhou")), "zhou")

    for seed in range(40):
        [peril] = one(state, circle(Aim.KILL), seed=seed).perils
        assert (peril.outcome_class, peril.roll, peril.harm) == ("ruled_out", None, Harm.NONE)
        assert peril.reason == "Zhou strikes back, but you are far beyond them."


def test_a_helpless_character_cant_stop_a_blow():
    state = fighting(add(sect(), disciple("zhou", "Zhou")), "zhou")
    state.characters["lin"].sheet.condition.states.append(PassingState(name="bound"))

    [peril] = one(state, circle()).perils

    assert (peril.outcome_class, peril.roll, peril.harm) == ("certain", None, Harm.WOUNDED)
    assert "bound" in peril.reason


def test_killing_the_only_foe_leaves_nobody_to_strike_back():
    state = sect()
    lin = state.characters["lin"]
    lin.sheet.ladders[0].rung, lin.sheet.axes.might = 3, 8
    state = add(state, disciple("zhou", "Zhou"))

    settled = one(state, strike("zhou"))

    assert settled.result is StepResult.SUCCESS
    assert settled.perils == []


def test_a_foe_frozen_in_a_time_stop_cant_answer():
    state = fighting(add(sect(), disciple("zhou", "Zhou")), "zhou")

    for seed in range(20):
        steps = resolve(state, Intent(steps=[stop_time(), circle()]), seed).steps
        assert all(s.perils == [] for s in steps)


# --- the dice, only between ----------------------------------------------------------------------


def test_a_fair_fight_is_rolled_and_harder_the_harder_the_difficulty():
    state = fighting(add(sect(), disciple("zhou", "Zhou")), "zhou")
    landed = {}
    for difficulty in Difficulty:
        found = harms(state, circle(), difficulty=difficulty)
        assert set(found) == {(Harm.NONE,), (Harm.HURT,), (Harm.WOUNDED,)}
        landed[difficulty] = SEEDS.stop - found[(Harm.NONE,)]
    assert all(p.roll is not None for p in one(state, circle()).perils)
    # A5: the difficulty works for the player against foes too.
    assert landed[Difficulty.STORY] < landed[Difficulty.BALANCED] < landed[Difficulty.BRUTAL]


def test_numbers_tell():
    alone = fighting(add(sect(), disciple("zhou", "Zhou")), "zhou")
    three = fighting(
        add(sect(), *(disciple(f"thug-{n}", f"Thug {n}") for n in range(3))),
        "thug-0",
        "thug-1",
        "thug-2",
    )

    assert harms(three, circle())[(Harm.NONE,)] < harms(alone, circle())[(Harm.NONE,)]
    assert one(three, circle()).perils[0].by == "Thug 0, Thug 1 and Thug 2"


def test_a_missed_blow_leaves_the_character_open_and_a_clean_one_keeps_them_on_top():
    state = add(sect(), disciple("zhou", "Zhou"))
    wound = strike("zhou").model_copy(update={"aim": Aim.WOUND})
    after: dict[StepResult, Counter] = {r: Counter() for r in StepResult}
    for seed in SEEDS:
        settled = one(state, wound, seed=seed)
        [peril] = settled.perils
        after[settled.result][peril.harm is not Harm.NONE] += 1

    def rate(result):
        return after[result][True] / max(1, sum(after[result].values()))

    assert rate(StepResult.FAILURE) > rate(StepResult.PARTIAL) > rate(StepResult.SUCCESS)


def test_the_same_moment_strikes_the_same_way():
    state = fighting(add(sect(), disciple("zhou", "Zhou")), "zhou")

    for seed in range(20):
        assert one(state, circle(), seed=seed).perils == one(state, circle(), seed=seed).perils


# --- what they mean --------------------------------------------------------------------------


def test_a_sparring_partner_holds_back():
    state = fighting(add(sect(), disciple("bai", "Elder Bai", rung=3)), "bai")

    settled = one(state, circle(Aim.SUBDUE))

    [peril] = settled.perils
    assert peril.harm is Harm.SUBDUED and peril.outcome_class is OutcomeClass.CERTAIN
    [change] = [c for c in settled.effects.characters if c.id == "lin"]
    assert change.status is None and change.condition.states == [SUBDUED_STATE]


def test_foes_who_wont_strike_back_dont():
    state = fighting(add(sect(), disciple("bai", "Elder Bai", rung=3)), "bai")

    assert one(state, circle(Aim.NONE)).perils == []


def test_unless_told_otherwise_foes_answer_in_kind_and_at_least_mean_to_wound():
    state = add(sect(), disciple("zhou", "Zhou"))

    def meant(attack) -> set[Aim]:
        return {p.aim for s in range(40) for p in one(state, attack, seed=s).perils}

    assert meant(strike("zhou")) == {Aim.KILL}
    assert meant(strike("zhou").model_copy(update={"aim": Aim.SUBDUE})) == {Aim.SUBDUE}
    assert one(fighting(state, "zhou"), circle(None)).perils[0].aim is Aim.WOUND


def test_waiting_in_a_fight_the_foes_strike_all_the_same():
    fight = fighting(add(sect(), disciple("zhou", "Zhou")), "zhou")
    wait = Intent(standing=StandingAction.WAIT)

    found = Counter(
        tuple(p.harm for p in resolve(fight, wait, seed).steps[0].perils) for seed in SEEDS
    )

    assert (Harm.WOUNDED,) in found and (Harm.NONE,) in found
    assert resolve(add(sect(), disciple("zhou", "Zhou")), wait).steps[0].perils == []


# --- getting away -------------------------------------------------------------------------------


def test_a_clean_escape_leaves_the_foes_behind():
    state = fighting(add(sect(), disciple("zhou", "Zhou")), "zhou")
    flee = step(
        "run for the tunnel",
        ActionKind.MOVE,
        20,
        verb="run",
        facts=facts(opposition_ids=["zhou"], can_respond=True, foes_mean=Aim.KILL),
    )
    then = circle(Aim.KILL)
    seen = set()
    for seed in SEEDS:
        first, *rest = resolve(state, Intent(steps=[flee, then]), seed).steps
        seen.add(first.result)
        if first.result is StepResult.SUCCESS:
            assert first.perils == []
            assert all(s.perils == [] for s in rest)  # he is behind them now
        else:
            assert [p.by_ids for p in first.perils] == [["zhou"]]
    assert StepResult.SUCCESS in seen and StepResult.FAILURE in seen


# --- dangers ------------------------------------------------------------------------------------


def test_a_long_drop_can_kill_a_person():
    found = harms(sect(), jump())

    assert {(Harm.NONE,), (Harm.DEAD,), (Harm.BADLY_WOUNDED,), (Harm.MAIMED,)} <= set(found)
    assert one(sect(), jump()).perils[0].by == "the long drop to the river"


def test_a_body_far_above_a_persons_peak_takes_it_better():
    state = sect()
    state.characters["lin"].sheet.axes.might = 14

    for seed in range(40):
        [peril] = one(state, jump(), seed=seed).perils
        assert (peril.outcome_class, peril.roll, peril.harm) == ("ruled_out", None, Harm.NONE)
        assert peril.reason == "The long drop to the river, but you are too tough for it."


def test_a_certain_death_needs_no_roll():
    for seed in range(20):
        [peril] = one(sect(), jump(OutcomeClass.CERTAIN), seed=seed).perils
        assert (peril.roll, peril.harm) == (None, Harm.DEAD)


def test_harm_turned_on_oneself_meets_no_second_danger():
    leap = jump().model_copy(update={"aim": Aim.KILL, "target_ids": ["lin"]})

    assert all(not one(sect(), leap, seed=s).perils for s in range(20))


# --- harm builds up -------------------------------------------------------------------------------


def test_dying_the_character_cant_fend_anything_off_and_any_harm_kills():
    state = wounded(fighting(add(sect(), disciple("zhou", "Zhou")), "zhou"), "lin", Health.DYING)

    assert set(harms(state, circle())) == {(Harm.DEAD,)}
    # A sparring partner only holds them down.
    assert set(harms(state, circle(Aim.SUBDUE))) == {(Harm.SUBDUED,)}


def test_a_blow_no_worse_than_what_they_carry_makes_it_worse():
    state = wounded(
        fighting(add(sect(), disciple("zhou", "Zhou")), "zhou"), "lin", Health.BADLY_WOUNDED
    )

    assert set(harms(state, circle())) == {(Harm.NONE,), (Harm.DYING,)}


def test_a_maiming_wound_lasts():
    state = add(sect(), disciple("zhou", "Zhou"))
    kill = strike("zhou")
    seed = next(
        s for s in SEEDS if any(p.harm is Harm.MAIMED for p in one(state, kill, seed=s).perils)
    )
    resolution = resolve(state, Intent(steps=[kill]), seed)

    played = pipeline.play_out(state, resolution, ctx(), rng(seed))

    assert check_transition(state, played.state) == []
    lin = played.state.characters["lin"]
    assert lin.sheet.condition.health is Health.BADLY_WOUNDED
    assert [(w.text, w.lasting) for w in lin.sheet.condition.wounds if w.lasting] == [
        ("a maiming wound from Zhou", True)
    ]


# --- what follows --------------------------------------------------------------------------------


def test_a_blow_that_lands_stops_the_plan_so_the_player_can_react():
    state = fighting(add(sect(), disciple("zhou", "Zhou")), "zhou")
    plan = Intent(steps=[circle(), step("run for the tunnel", ActionKind.MOVE, 20, verb="run")])

    stopped = 0
    for seed in SEEDS:
        resolution = resolve(state, plan, seed)
        if resolution.steps[0].hurt_by_peril:
            stopped += 1
            assert resolution.stop_reason is StopReason.STRUCK
            assert resolution.unplayed == ["run for the tunnel"]
    assert stopped


def test_struck_down_the_character_does_nothing_more_and_their_death_is_no_suicide():
    state = add(sect(), disciple("bai", "Elder Bai", rung=3))
    plan = Intent(
        steps=[
            strike("bai").model_copy(update={"target_ids": ["bai", "lin"]}),
            step("run for the tunnel", ActionKind.MOVE, 20, verb="run"),
        ]
    )
    resolution = resolve(state, plan)
    played = pipeline.play_out(state, resolution, ctx(), rng())

    assert not played.state.player.alive
    assert resolution.steps[-1].perils[-1].harm is Harm.DEAD
    ending = ending_of(state, played.state, plan, played.resolution, TurnKind.ACTION)
    assert ending is not None and ending.kind == "death" and not ending.self_inflicted
