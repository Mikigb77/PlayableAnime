"""Someone the story brings in comes standing where their change says (G18, A4): on a rung the
world's ladders have, and only someone the same update created. Nobody on record is lifted
(`engine.apply`)."""

from engine import path
from engine.apply import DeltaSource, apply_delta
from engine.context import TurnContext
from engine.contracts import CharacterChange, NewRung, StateDelta
from engine.resolve.power import base_tier, rungs_above
from engine.samples import cultivation_world, grounded_world
from engine.state import LadderPosition, PowerAxis
from engine.visibility import status_view

TOP = 4  # Soul Transformation
VOID = "Void Refinement"
LIFTED = "only someone this scene brought in comes standing on it: nobody is lifted"


def brought_in(state, *people, rungs=(), source=DeltaSource.NARRATOR):
    delta = StateDelta(characters=list(people), rungs=list(rungs))
    return apply_delta(state, delta, TurnContext(story_id="s1", turn=9), source=source)


def elder(rung: str | None = "Core Formation", **kw) -> CharacterChange:
    return CharacterChange(id="elder-bai", name="Elder Bai", age=140, rung=rung, **kw)


def on_realms(state, who: str) -> int:
    return path.own_rung(state.characters[who], "realms")


def reasons(applied) -> list[str]:
    return [r.reason for r in applied.rejected]


def at_the_top():
    state = cultivation_world()
    state.player.sheet.ladders = [LadderPosition(ladder_id="realms", rung=TOP)]
    return state


def test_someone_the_story_brings_in_stands_on_the_rung_their_change_names():
    state = cultivation_world()

    applied = brought_in(state, elder())

    assert not applied.rejected
    bai = applied.state.characters["elder-bai"]
    (position,) = bai.sheet.ladders
    # On the rung, with nothing toward the next and no pace read yet: the world's years take
    # them on from here like anyone (W6).
    assert (position.ladder_id, position.rung, position.stage, position.yearly_s) == (
        "realms",
        2,
        "",
        None,
    )
    # A rung is the world's name for a tier on its axis, so the engine measures them by it.
    assert bai.sheet.axes.might == base_tier(applied.state, bai, PowerAxis.MIGHT) == 6
    assert rungs_above(applied.state, PowerAxis.MIGHT, applied.state.player, bai)[0] == 2


def test_a_rungs_name_is_read_whatever_its_case():
    applied = brought_in(cultivation_world(), elder("nascent soul"))

    assert not applied.rejected
    assert on_realms(applied.state, "elder-bai") == 3


def test_a_few_words_that_hold_one_rungs_name_are_read_as_that_rung():
    # A scene's update may say where on the rung they are: the record keeps the rung.
    applied = brought_in(cultivation_world(), elder("late Core Formation"))

    assert not applied.rejected
    assert on_realms(applied.state, "elder-bai") == 2


def test_words_that_hold_two_rungs_names_put_them_on_none():
    applied = brought_in(cultivation_world(), elder("between Core Formation and Nascent Soul"))

    assert reasons(applied) == ["no ladder has that rung"]
    assert applied.state.characters["elder-bai"].sheet.ladders == []


def test_a_new_rung_may_hold_an_old_ones_name_in_its_own():
    # Only a rung called exactly that is taken (`path.beyond_problem`), so the story can tell
    # of Greater Soul Transformation, and someone can come standing on it.
    greater = "Greater Soul Transformation"

    applied = brought_in(
        at_the_top(),
        CharacterChange(id="envoy", name="Envoy Shen", rung=greater),
        rungs=[NewRung(ladder_id="realms", name=greater)],
    )

    assert not applied.rejected
    assert on_realms(applied.state, "envoy") == TOP + 1


def test_someone_whose_change_names_no_rung_stands_on_none():
    # Most people a story brings in are ordinary on record, as before.
    applied = brought_in(cultivation_world(), elder(None))

    bai = applied.state.characters["elder-bai"]
    assert bai.sheet.ladders == [] and bai.sheet.axes.might == 1


def test_nobody_on_record_is_lifted():
    # A4: someone the story already has climbs. Their rung is never a scene's to raise.
    state = cultivation_world()

    applied = brought_in(
        state,
        CharacterChange(id="zhao", rung="Soul Transformation"),
        CharacterChange(id="lin", rung="Foundation Establishment"),
    )

    assert reasons(applied) == [LIFTED, LIFTED]
    assert (on_realms(applied.state, "zhao"), on_realms(applied.state, "lin")) == (1, 0)
    assert applied.state.characters["zhao"].sheet.axes.might == 4


def test_someone_on_record_whose_change_says_their_own_rung_or_a_lower_one_stays_put():
    # Said again, or said of who they were, it is nothing new: nobody moves and nothing is
    # refused.
    state = cultivation_world()

    applied = brought_in(
        state,
        CharacterChange(id="elder-mo", rung="Core Formation"),
        CharacterChange(id="zhao", rung="Qi Condensation"),
    )

    assert not applied.rejected
    assert (on_realms(applied.state, "elder-mo"), on_realms(applied.state, "zhao")) == (2, 1)


def test_someone_on_record_who_stands_on_no_ladder_steps_onto_none():
    state = brought_in(cultivation_world(), elder(None)).state

    applied = brought_in(state, elder("Qi Condensation"))

    assert reasons(applied) == [LIFTED]
    assert applied.state.characters["elder-bai"].sheet.ladders == []


def test_a_rung_no_ladder_has_puts_them_on_none():
    applied = brought_in(cultivation_world(), elder("Golden Immortal"))

    assert reasons(applied) == ["no ladder has that rung"]
    assert applied.state.characters["elder-bai"].sheet.ladders == []


def test_in_a_world_with_no_ladder_nobody_stands_on_one():
    applied = brought_in(grounded_world(), CharacterChange(id="sal", name="Sal", rung="Capo"))

    assert reasons(applied) == ["no ladder has that rung"]
    assert applied.state.characters["sal"].sheet.ladders == []


def test_someone_can_come_standing_on_a_rung_the_same_scene_told():
    # The update names the new rung on the newcomer's own change, with nothing under `stands`.
    state = at_the_top()

    applied = brought_in(
        state,
        CharacterChange(id="envoy", name="Envoy Shen", age=3000, rung=VOID),
        rungs=[NewRung(ladder_id="realms", name=VOID)],
    )

    assert not applied.rejected
    assert on_realms(applied.state, "envoy") == TOP + 1
    assert applied.state.characters["envoy"].sheet.axes.might == 12


def test_three_come_with_a_new_rung_however_the_update_lists_them():
    state = at_the_top()
    people = [
        CharacterChange(id=f"new-{n}", name=f"Sovereign {'ABCD'[n]}", rung=VOID if n > 1 else None)
        for n in range(4)
    ]

    applied = brought_in(
        state,
        *people,
        rungs=[NewRung(ladder_id="realms", name=VOID, stands=["new-0", "new-1", "new-2"])],
    )

    # The three under `stands` took the places; the one named there and on their own change
    # counts once, and the fourth stays on no rung.
    assert reasons(applied) == ["three come with a rung at most"]
    assert [on_realms(applied.state, f"new-{n}") for n in range(4)] == [5, 5, 5, -1]


def test_where_the_new_rung_was_refused_whoever_named_it_stands_on_none():
    state = cultivation_world()  # Lin Feng on the lowest rung: the top is not his to pass yet

    applied = brought_in(
        state,
        CharacterChange(id="envoy", name="Envoy Shen", rung=VOID),
        rungs=[NewRung(ladder_id="realms", name=VOID)],
    )

    assert len(applied.rejected) == 2
    assert applied.state.characters["envoy"].sheet.ladders == []


def test_any_number_come_standing_on_a_rung_the_world_started_with():
    people = [
        CharacterChange(id=f"new-{n}", name=f"Disciple {'ABCDE'[n]}", rung="Qi Condensation")
        for n in range(5)
    ]

    applied = brought_in(cultivation_world(), *people)

    assert not applied.rejected
    assert [on_realms(applied.state, f"new-{n}") for n in range(5)] == [0] * 5


def test_the_engine_too_lifts_nobody_this_way():
    applied = brought_in(
        cultivation_world(),
        CharacterChange(id="zhao", rung="Nascent Soul"),
        source=DeltaSource.ENGINE,
    )

    assert reasons(applied) == [LIFTED]


def test_someone_the_engine_makes_with_a_place_on_a_ladder_holds_one_place_on_it():
    # The engine can make someone with a place on a ladder already (`ladders`). A higher rung
    # said of them too leaves them one place on that ladder.
    change = elder("Core Formation", ladders=[LadderPosition(ladder_id="realms", rung=0)])

    applied = brought_in(cultivation_world(), change, source=DeltaSource.ENGINE)

    assert not applied.rejected
    (position,) = applied.state.characters["elder-bai"].sheet.ladders
    assert position.rung == 2


def test_where_someone_new_stands_is_the_records_until_the_story_shows_it():
    # C6: the record holds it, and the character's own path says nothing of someone they
    # have not stood before.
    state = cultivation_world()
    before = status_view(state).sheet.paths

    applied = brought_in(state, elder("Nascent Soul", location_id="inner-court"))

    assert on_realms(applied.state, "elder-bai") == 3
    assert status_view(applied.state).sheet.paths == before
