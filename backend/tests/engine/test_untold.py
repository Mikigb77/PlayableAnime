"""G1, C6: what the story has yet to tell the player of its own start (`engine.untold`)."""

from engine import pipeline, untold
from engine.samples import cultivation_world, grounded_world
from engine.state import Fact, GoalStatus
from engine.visibility import memory_view, status_view

HELD = ["goal:find-killer", "person:carmine", "thread:revenge"]


def holding(*keys: str):
    return grounded_world().model_copy(update={"untold": list(keys or HELD)})


def test_what_is_held_back_is_read_by_kind():
    held = untold.held(holding(*HELD, "place:naples", "nonsense"))

    assert (held.people, held.goals, held.threads) == ({"carmine"}, {"find-killer"}, {"revenge"})
    assert untold.held(grounded_world()) == untold.Untold()
    assert untold.key(untold.PERSON, "carmine") == "person:carmine"


def test_memory_holds_back_who_and_what_the_start_kept_a_surprise():
    plain = memory_view(grounded_world())
    assert [p.name for p in plain.people] == ["Carmine Russo"]
    assert [g.id for g in plain.goals] == ["find-killer"]
    assert [t.id for t in plain.threads] == ["revenge"]

    view = memory_view(holding())

    assert (view.people, view.goals, view.threads) == ([], [], [])
    # The world the draft showed stays: its places and factions are no surprise.
    assert [p.name for p in view.places] == [p.name for p in plain.places]
    assert [f.name for f in view.factions] == [f.name for f in plain.factions]
    # One at a time: each key holds back its own record and nothing else.
    only = memory_view(holding("person:carmine"))
    assert (only.people, [g.id for g in only.goals], [t.id for t in only.threads]) == (
        [],
        ["find-killer"],
        ["revenge"],
    )


def test_what_the_character_knows_about_someone_held_back_waits_for_them():
    state = holding("person:carmine")
    about = "Carmine was the last to see my father alive."
    state.facts["f1"] = Fact(
        id="f1",
        text=about,
        subject_ids=["carmine", "carmines-bar"],
        known_by=["luca"],
        importance=5,
    )
    own = "My father was shot dead outside his own club."
    state.facts["f2"] = Fact(id="f2", text=own, known_by=["luca"], importance=5)

    assert about not in str(memory_view(state).model_dump())
    assert [entry.text for entry in status_view(state).since] == [own]

    told = untold.tell(state, ["person:carmine"])
    (carmine,) = memory_view(told).people
    assert about in carmine.lines
    assert {entry.text for entry in status_view(told).since} == {own, about}


def test_telling_takes_a_key_off_the_list_for_good_and_leaves_the_rest():
    state = holding()

    told = untold.tell(state, ["person:carmine", "person:nobody"])

    assert told.untold == ["goal:find-killer", "thread:revenge"]
    assert state.untold == HELD
    assert [p.name for p in memory_view(told).people] == ["Carmine Russo"]
    # Nothing on the list is named: the same state comes back.
    assert untold.tell(state, ["person:nobody"]) is state
    assert untold.tell(state, []) is state


def test_play_reaches_a_goal_it_moves_or_closes_and_a_thread_the_player_takes_up():
    state = holding()
    assert untold.reached(state) == []

    moved = holding()
    moved.goals["find-killer"].moved_turn = 3
    assert untold.reached(moved) == ["goal:find-killer"]

    noted = holding()
    noted.goals["find-killer"].progress = "Carmine was at the club that night."
    assert untold.reached(noted) == ["goal:find-killer"]

    closed = holding()
    closed.goals["find-killer"].status = GoalStatus.ABANDONED
    assert untold.reached(closed) == ["goal:find-killer"]

    taken = holding()
    taken.threads["revenge"].taken_up_turn = 2
    assert untold.reached(taken) == ["thread:revenge"]

    # N6: someone who carries the story on is nobody the player has yet to meet.
    heir = holding()
    heir.player_id = "carmine"
    assert untold.reached(heir) == ["person:carmine"]

    # A key whose record is gone, or of a kind nobody holds back, holds nothing back.
    gone = holding("person:nobody", "goal:none", "thread:none", "place:naples", *HELD)
    assert untold.reached(gone) == ["person:nobody", "goal:none", "thread:none", "place:naples"]


def test_settling_tells_what_the_scene_named_and_what_play_reached():
    state = holding()
    state.threads["revenge"].taken_up_turn = 2

    settled, told = pipeline.settle_untold(state, ["person:carmine", "person:nobody"])

    assert told == ["person:carmine", "thread:revenge"]
    assert settled.untold == ["goal:find-killer"]
    assert state.untold == HELD

    # Nothing told: the same state, and a story that holds nothing back is never touched.
    assert pipeline.settle_untold(holding(), []) == (holding(), [])
    quiet = holding()
    assert pipeline.settle_untold(quiet)[0] is quiet
    plain = cultivation_world()
    assert pipeline.settle_untold(plain, ["person:zhao"]) == (plain, [])
