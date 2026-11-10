"""A3: a thing keeps the level it was first judged at, on its place, so the same lock is the same
lock tomorrow however the interpret step judges it the next time."""

import pytest

from engine import pipeline
from engine.contracts import ActionKind, Challenge, Intent
from engine.rng import SeededRng
from engine.state import Judged, WorldState

from .worlds import add, ctx, disciple, facts, resolve, rng, sect, step

KEPT = Judged(key="archiv door lock pick", what="the archive door's lock", level=3)


def pick(challenge: Challenge | None, what: str = "the archive door"):
    return step(
        f"pick the lock on {what}",
        ActionKind.TASK,
        600,
        verb="pick",
        facts=facts(opposition=f"{what}'s lock", challenge=challenge),
    )


def after_a_hard_lock() -> WorldState:
    """The well once Lin has tried the archive door's lock, judged a hard task."""
    state = sect()
    stream = rng()
    resolution = pipeline.resolve(state, Intent(steps=[pick(Challenge.HARD)]), ctx(), stream)
    [place] = resolution.steps[0].effects.places
    assert (place.id, place.judged) == ("well", [KEPT])
    return pipeline.play_out(state, resolution, ctx(), stream).state


def number_of(state: WorldState, attempt) -> tuple[str, int]:
    stream = SeededRng.for_turn("seed-1", "main", 4)
    (settled,) = pipeline.resolve(state, Intent(steps=[attempt]), ctx(turn=4), stream).steps
    assert settled.effects.places == []  # nothing new to keep
    level = settled.roll.throw.made_of[0]
    return level.text, level.points


def test_the_place_keeps_the_level_a_thing_was_first_judged_at():
    assert after_a_hard_lock().places["well"].judged == [KEPT]


@pytest.mark.parametrize("judged_now", [Challenge.TRIVIAL, Challenge.EASY, None, Challenge.EXTREME])
def test_the_same_lock_is_the_same_lock_however_it_is_judged_the_next_time(judged_now):
    state = after_a_hard_lock()
    assert number_of(state, pick(judged_now)) == (
        "the archive door's lock, a hard task, level 3",
        27,
    )


def test_another_thing_in_the_same_place_is_judged_on_its_own():
    state = after_a_hard_lock()
    stream = SeededRng.for_turn("seed-1", "main", 4)
    gate = pick(Challenge.EASY, "the garden gate")
    (settled,) = pipeline.resolve(state, Intent(steps=[gate]), ctx(turn=4), stream).steps
    assert settled.roll.throw.made_of[0].text == "the garden gate's lock, an easy task, level 1"
    [place] = settled.effects.places
    assert [(j.what, j.level) for j in place.judged] == [("the garden gate's lock", 1)]


@pytest.mark.parametrize("challenge", [Challenge.TRIVIAL, None])
def test_nothing_is_kept_for_a_thing_judged_trivial_or_not_judged_at_all(challenge):
    (settled,) = resolve(sect(), Intent(steps=[pick(challenge)])).steps
    assert settled.effects.places == []


def test_nobodys_own_level_is_kept_as_a_thing_of_the_place():
    state = add(sect(), disciple("wei", "Wei"))
    ask = step(
        "talk my way past Wei",
        ActionKind.CONVERSATION,
        30,
        verb="persuade",
        target_ids=["wei"],
        facts=facts(opposition_ids=["wei"], can_respond=True, challenge=Challenge.HARD),
    )
    (settled,) = resolve(state, Intent(steps=[ask])).steps
    assert settled.roll is not None and settled.effects.places == []
