"""A3: a throw over the top, and the one fixed extra effect code gives it by the kind of step.

A total past everything the hand could make without a 20 is over the top. A blow leaves those
who answered staggered, and the next step against them throws a green die, in this plan or in the
next turn of the same fight. Words move each listener a notch further. A task on a thing takes
half the time. The effect is the engine's, written on the step, so the telling can't inflate it.
"""

import pytest

from engine import pipeline
from engine.contracts import ActionKind, Aim, Challenge, Intent
from engine.rng import SeededRng
from engine.state import CharacterStatus, Mark, PowerAxis, StepResult, WorldState

from .worlds import SEEDS, add, ctx, disciple, facts, item, resolve, rng, sect, step

REMEMBERED = "Those who saw it will remember."
STAGGERED = (
    "Over the top: Wei is staggered and has no answer, and your next step against them throws a "
    f"green die. {REMEMBERED}"
)


def world() -> WorldState:
    """Lin at the well with Wei, a disciple of his own realm."""
    return add(sect(), disciple("wei", "Wei"))


def slash(aim: Aim = Aim.WOUND):
    """A cut at Wei, who only parries, so the step's own throw is all that happens."""
    return step(
        "slash at Wei",
        verb="attack",
        aim=aim,
        target_ids=["wei"],
        axis=PowerAxis.MIGHT,
        uses=[item("sword")],
        facts=facts(opposition_ids=["wei"], can_respond=True, foes_mean=Aim.NONE),
    )


def talk(text: str, verb: str):
    return step(
        text,
        ActionKind.CONVERSATION,
        30,
        verb=verb,
        axis=PowerAxis.INFLUENCE,
        target_ids=["wei"],
        facts=facts(opposition_ids=["wei"], can_respond=True),
    )


def pick_the_lock():
    return step(
        "pick the lock on the archive door",
        ActionKind.TASK,
        600,
        verb="pick",
        facts=facts(opposition="the archive door's lock", challenge=Challenge.MODERATE),
    )


def over(settled) -> bool:
    return settled.roll is not None and settled.roll.throw.mark is Mark.OVER_THE_TOP


def seeds_over_the_top(state: WorldState, first) -> list[int]:
    found = [s for s in SEEDS if over(resolve(state, Intent(steps=[first]), s).steps[0])]
    assert found  # about one throw in twenty of a two-dice hand
    return found


# --- what it is ----------------------------------------------------------------------------------


def test_over_the_top_is_a_total_past_what_the_hand_could_make_without_a_twenty():
    state = world()
    for seed in SEEDS:
        (settled,) = resolve(state, Intent(steps=[slash()]), seed).steps
        thrown = settled.roll.throw
        assert thrown.most == 20 * thrown.hand
        assert over(settled) == (thrown.total > thrown.most)
        if over(settled):
            assert settled.result is StepResult.SUCCESS
            assert any(die.sprung for die in thrown.dice)  # it takes a 20 and the die it throws
        else:
            assert (settled.extra, settled.opening_ids) == ("", [])


# --- a blow --------------------------------------------------------------------------------------


def test_a_blow_over_the_top_staggers_whoever_answered_and_the_next_step_throws_a_green_die():
    state = world()
    spent = []
    for seed in seeds_over_the_top(state, slash()):
        plan = Intent(steps=[slash(), slash(), slash()])
        first, second, *rest = resolve(state, plan, seed).steps
        assert first.extra == STAGGERED
        assert first.opening_ids == ["wei"]
        # The opening is the next step's green die, and only the next step's.
        assert second.roll.throw.greens == ["the opening on Wei"]
        assert "and a green die for the opening on Wei" in second.reason
        spent += [third.roll.throw.greens for third in rest if not over(second)]
    assert spent and not any(spent)  # a third cut, where Wei still stood for one, had none


def test_nobody_is_left_staggered_by_the_blow_that_killed_them():
    state = world()
    for seed in seeds_over_the_top(state, slash(Aim.KILL)):
        (settled,) = resolve(state, Intent(steps=[slash(Aim.KILL)]), seed).steps
        assert settled.extra == f"Over the top: {REMEMBERED}"
        assert settled.opening_ids == []


def test_an_opening_is_carried_to_the_next_turn_of_the_same_fight_and_used_once():
    state = world()
    seed = seeds_over_the_top(state, slash())[0]
    stream = rng(seed)
    resolution = pipeline.resolve(state, Intent(steps=[slash()]), ctx(), stream)
    after = pipeline.play_out(state, resolution, ctx(), stream).state
    assert after.scene.encounter is not None and after.openings == ["wei"]

    # A step that doesn't face Wei leaves the opening where it is.
    stream = SeededRng.for_turn("seed-0", "main", 4)
    breather = step("catch my breath", verb="breathe", facts=facts(foes_mean=Aim.NONE))
    resolution = pipeline.resolve(after, Intent(steps=[breather]), ctx(turn=4), stream)
    assert pipeline.play_out(after, resolution, ctx(turn=4), stream).state.openings == ["wei"]

    # The next step against him throws the green die, and the opening is spent.
    for next_seed in range(20):
        stream = SeededRng.for_turn(f"seed-{next_seed}", "main", 4)
        resolution = pipeline.resolve(after, Intent(steps=[slash()]), ctx(turn=4), stream)
        (settled,) = resolution.steps
        assert settled.roll.throw.greens == ["the opening on Wei"]
        later = pipeline.play_out(after, resolution, ctx(turn=4), stream).state
        assert later.openings == (["wei"] if over(settled) else [])


def test_an_opening_doesnt_outlast_the_fight_or_the_foe():
    state = world()
    seed = seeds_over_the_top(state, slash())[0]
    stream = rng(seed)
    resolution = pipeline.resolve(state, Intent(steps=[slash()]), ctx(), stream)
    after = pipeline.play_out(state, resolution, ctx(), stream).state
    breather = step("catch my breath", verb="breathe", facts=facts(foes_mean=Aim.NONE))

    def next_turn(start: WorldState) -> WorldState:
        stream = SeededRng.for_turn("seed-0", "main", 4)
        resolution = pipeline.resolve(start, Intent(steps=[breather]), ctx(turn=4), stream)
        return pipeline.play_out(start, resolution, ctx(turn=4), stream).state

    over_now = after.model_copy(deep=True)
    over_now.scene.encounter = None
    assert next_turn(over_now).openings == []

    dead = after.model_copy(deep=True)
    dead.characters["wei"].status = CharacterStatus.DEAD
    assert next_turn(dead).openings == []


def test_an_opening_the_state_holds_on_someone_else_gives_no_die_against_this_foe():
    state = add(world(), disciple("han", "Han"))
    state.openings = ["han"]
    (settled,) = resolve(state, Intent(steps=[slash()])).steps
    assert settled.roll.throw.greens == []


# --- words ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "verb", "moved", "told"),
    [
        ("ask Wei to let me into the archive", "persuade", "trust", "trust in you"),
        ("threaten Wei: step aside or else", "threaten", "fear", "fear of you"),
    ],
)
def test_words_over_the_top_move_the_listener_one_notch_further(text, verb, moved, told):
    state = world()
    spoken = talk(text, verb)
    for seed in seeds_over_the_top(state, spoken):
        (settled,) = resolve(state, Intent(steps=[spoken]), seed).steps
        assert settled.extra == f"Over the top: Wei: {told} goes a notch further. {REMEMBERED}"
        assert settled.opening_ids == []  # words win no opening
        [shift] = [s for c in settled.effects.characters if c.id == "wei" for s in c.attitudes]
        assert shift.toward_id is None  # toward the player character
        assert {name: getattr(shift, name) for name in ("trust", "fear")} == {
            "trust": 0,
            "fear": 0,
            moved: 10,
        }


def test_words_that_only_pass_move_nobody_further():
    state = world()
    spoken = talk("ask Wei to let me into the archive", "persuade")
    for seed in SEEDS:
        (settled,) = resolve(state, Intent(steps=[spoken]), seed).steps
        if not over(settled):
            assert not any(c.attitudes for c in settled.effects.characters)


# --- a task --------------------------------------------------------------------------------------


def test_a_task_over_the_top_takes_half_the_time():
    state = world()
    took = set()
    for seed in SEEDS:
        (settled,) = resolve(state, Intent(steps=[pick_the_lock()]), seed).steps
        if over(settled):
            assert settled.duration_s == 300
            assert settled.extra == f"Over the top: It takes half the time. {REMEMBERED}"
        else:
            assert (settled.duration_s, settled.extra) == (600, "")
        took.add(settled.duration_s)
    assert took == {300, 600}


def test_a_blow_over_the_top_is_no_quicker():
    state = world()
    for seed in seeds_over_the_top(state, slash()):
        (settled,) = resolve(state, Intent(steps=[slash()]), seed).steps
        assert settled.duration_s == 2 and "half the time" not in settled.extra
