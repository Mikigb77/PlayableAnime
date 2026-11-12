"""T5: what a turn's log line counts about the logic of play (`engine.tally`), in numbers only.
A change that brings back a throw for an ordinary thing, a move refused as not the character's
own, a rumor heard with no scene telling it or goals that only pile up shows as a number."""

from engine import pipeline
from engine.contracts import (
    Beat,
    BeatUse,
    DirectorPlan,
    Intent,
    PlannedTalk,
    Plausibility,
    Resolution,
    UseSource,
)
from engine.samples import cultivation_world
from engine.state import Goal, GoalStatus, Rumor, WorldState
from engine.tally import turn_tally
from tests.engine.resolve.worlds import ctx, power, resolve, rng, step

QUIET = DirectorPlan()


def tally(
    before: WorldState,
    after: WorldState | None = None,
    resolution: Resolution | None = None,
    plan: DirectorPlan = QUIET,
) -> dict[str, int]:
    return turn_tally(before, after or before, resolution or Resolution(), plan)


def reach(thing: str, plausibility: Plausibility | None = None):
    """A step that reaches for something the record doesn't hold."""
    use = BeatUse(source=UseSource.NEW, thing=thing, plausibility=plausibility)
    return step(f"take {thing}", beats=[Beat(text=f"take {thing}", uses=[use])])


def word(state: WorldState, rumor_id: str, *heard_by: str) -> None:
    state.rumors[rumor_id] = Rumor(
        id=rumor_id,
        text="The granary burned.",
        is_true=True,
        reached_place_ids=[state.scene.place_id] if state.scene.place_id else [],
        heard_at=dict.fromkeys(heard_by, state.world_s),
    )


def test_a_quiet_turn_counts_nothing_but_the_goals_still_open():
    state = cultivation_world()
    state.goals = {
        "a": Goal(id="a", text="Reach the inner sect."),
        "b": Goal(id="b", text="Find the thief."),
        "c": Goal(id="c", text="Win the trial.", status=GoalStatus.ACHIEVED),
        "d": Goal(id="d", text="Find who stole it.", status=GoalStatus.MERGED, merged_into="b"),
    }

    assert tally(state) == {
        "refused": 0,
        "moves_refused": 0,
        "searches": 0,
        "searches_empty": 0,
        "rumors_heard": 0,
        "rumors_unvoiced": 0,
        "goals_open": 2,
    }


def test_refusals_are_counted_and_those_of_a_move_as_not_their_own_apart():
    state = cultivation_world()
    state.player.sheet.powers[0].ready_at_personal_s = 5
    # A power of theirs that isn't ready, and one no record of theirs holds.
    tired = resolve(state, Intent(steps=[step("stop time", uses=[power("time-stop")])]))
    lacking = resolve(state, Intent(steps=[step("call lightning", uses=[power("lightning")])]))

    assert tally(state, resolution=tired) == tally(state) | {"refused": 1}
    assert tally(state, resolution=lacking) == tally(state) | {"refused": 1, "moves_refused": 1}


def test_only_a_throw_for_whether_a_thing_is_there_is_a_search():
    state = cultivation_world()
    # What a place of that kind would hold is there with no throw (R2).
    plain = resolve(state, Intent(steps=[reach("a fallen branch")]))
    assert tally(state, resolution=plain) == tally(state)

    hidden = Intent(steps=[reach("a key", Plausibility.UNCERTAIN)])
    counted = [tally(state, resolution=resolve(state, hidden, seed)) for seed in range(12)]
    assert {t["searches"] for t in counted} == {1}
    # Some of twelve throws find it and some don't, and only those that don't count as empty.
    assert {t["searches_empty"] for t in counted} == {0, 1}
    assert all(t["refused"] == 0 for t in counted)  # a lost throw is no refusal

    # What the place can't hold is refused with no throw, so it is no search.
    absent = resolve(state, Intent(steps=[reach("a dragon's egg", Plausibility.ABSENT)]))
    assert tally(state, resolution=absent) == tally(state) | {"refused": 1}


def test_a_rumor_a_scene_told_is_heard_and_any_other_is_unvoiced():
    before = cultivation_world()
    word(before, "granary")
    word(before, "old", before.player_id)  # heard before the turn: not this turn's
    plan = DirectorPlan(talk=PlannedTalk(rumor_id="granary"))

    # The scene had no room for the talk: nothing is heard.
    assert tally(before, plan=plan) == tally(before)

    told = pipeline.hear_talk(before, plan, ctx(), rng())
    assert tally(before, told, plan=plan) == tally(before) | {"rumors_heard": 1}

    # Marked as heard by anything but the scene's talk, it shows (C6).
    marked = before.model_copy(deep=True)
    marked.rumors["granary"].heard_at[marked.player_id] = marked.world_s
    assert tally(before, marked) == tally(before) | {"rumors_heard": 1, "rumors_unvoiced": 1}
    other = DirectorPlan(talk=PlannedTalk(rumor_id="old"))
    assert tally(before, marked, plan=other)["rumors_unvoiced"] == 1
    # What they were there to see happen is what they saw, not talk they heard.
    seen = before.model_copy(deep=True)
    seen.rumors["granary"].heard_at[seen.player_id] = seen.world_s
    seen.rumors["granary"].seen_by.append(seen.player_id)
    assert tally(before, seen) == tally(before)
    # What someone else heard is the world's business, not the scene's.
    elsewhere = before.model_copy(deep=True)
    someone = next(i for i in elsewhere.characters if i != elsewhere.player_id)
    elsewhere.rumors["granary"].heard_at[someone] = elsewhere.world_s
    assert tally(before, elsewhere) == tally(before)
