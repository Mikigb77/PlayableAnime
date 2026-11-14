"""A story played by hand, a few steps at a time (`evals.play`): offline here, on the stock draft
and the offline model's scenes, as the Evals workflow plays it on the real models."""

import asyncio
import json

import pytest

from evals import play, worlds
from evals.__main__ import main
from evals.runner import Eval, Models
from evals.scenario import Mode

PREMISE = "A farm boy who wants to become the strongest swordsman alive."
CREATE = {"create": {"premise": PREMISE}}


def played(root, plays) -> dict[str, bool]:
    return asyncio.run(play.play_all(root, plays, Models()))


def transcript(root, name: str) -> str:
    return (root / name / play.TRANSCRIPT_FILE).read_text(encoding="utf-8")


def kept(root, name: str) -> dict:
    return json.loads((root / name / play.STATE_FILE).read_text(encoding="utf-8"))


def test_a_draft_tells_what_its_screen_shows_and_what_the_record_made_of_the_character(tmp_path):
    assert played(tmp_path, {"farmer": [CREATE]}) == {"farmer": True}

    told = transcript(tmp_path, "farmer")
    assert f"> {PREMISE}" in told
    screen, record = told.split("### On record (the player never sees this)")
    assert "### What the draft's screen shows" in screen and "Lin Feng, 16." in screen
    on_record = json.loads(record[record.index("{") : record.rindex("}") + 1])
    # A4, G13, G18: the level a short description became, beside the world it stands in.
    assert on_record["sheet"]["attributes"] == {
        "strength": 2,
        "toughness": 2,
        "wits": 5,
        "willpower": 5,
    }
    assert on_record["gift"] == "overpowered"
    assert on_record["sheet"]["ladders"][0]["rung"] == 0
    assert on_record["ladders"][0]["rungs"][0] == "0: Qi Condensation (tier 2, lives 120)"
    assert on_record["others"][0].startswith("Elder Mo, 212, realms rung 2")
    assert on_record["years"] == {
        "age": 16.0,
        "lives_about": 120,
        "the_record_says_so": True,
        "old": False,
        "told_the_end_is_close": False,
    }
    assert "record_check" not in on_record  # nothing the record's own check found
    assert kept(tmp_path, "farmer")["state"] is None


def test_a_play_goes_on_from_where_the_last_call_left_it(tmp_path):
    assert played(tmp_path, {"farmer": [CREATE, {"start": {}}]}) == {"farmer": True}
    first = kept(tmp_path, "farmer")
    assert first["state"]["turn"] == 1 and [s["turn"] for s in first["scenes"]] == [1]

    steps = [
        {"act": "I draw water from the well."},
        {"wait": True},
        {"observe": True},
        {"show": ["sheet", "memory"]},
    ]
    assert played(tmp_path, {"farmer": steps}) == {"farmer": True}

    second = kept(tmp_path, "farmer")
    assert second["state"]["turn"] == 4
    assert [s["turn"] for s in second["scenes"]] == [1, 2, 3, 4]
    assert second["scenes"][1]["player_action"] == "I draw water from the well."
    assert second["cost_usd"] > first["cost_usd"] > 0
    told = transcript(tmp_path, "farmer")
    headings = [line for line in told.splitlines() if line.startswith("## ")]
    assert headings[0] == "## The draft (en, teen)"
    assert [h.split(",")[0] for h in headings[1:5]] == [
        "## Turn 1 (opening)",
        "## Turn 2 (action)",
        "## Turn 3 (standing)",
        "## Turn 4 (standing)",
    ]
    assert headings[5] == "## What the screens show (turn 4)"
    assert "> I draw water from the well." in told
    assert "- read as instant, 'act', 5 s: I draw water from the well." in told
    assert "- wait [certain, success]: Nothing stands in the way." in told
    assert "- observe [certain, success]: Nothing stands in the way." in told
    assert "### The Character screen" in told and '"16 years old"' in told
    assert "### Memory" in told and "On record" not in told.split("## What the screens show")[1]


def test_several_plays_are_played_in_one_call_each_in_its_own_folder_and_language(tmp_path):
    spanish = {"create": {"premise": PREMISE, "language": "es", "rating": "mature"}}
    plays = {"one": [CREATE, {"start": {}}], "dos": [spanish, {"show": "record"}]}

    assert played(tmp_path, plays) == {"one": True, "dos": True}

    assert kept(tmp_path, "one")["state"]["turn"] == 1
    dos = kept(tmp_path, "dos")
    assert (dos["language"], dos["rating"], dos["state"]) == ("es", "mature", None)
    assert dos["settings"]["language"] == "es" and dos["seed"] == "play/dos"
    assert "## The draft (es, mature)" in transcript(tmp_path, "dos")
    # Before it starts, the screens are the draft's.
    assert "## What the screens show (turn 0)" in transcript(tmp_path, "dos")


def test_a_change_asked_in_plain_words_is_drafted_again_until_the_story_starts(tmp_path):
    change = {"revise": {"target": "character", "instruction": "Make him a little older."}}
    assert played(tmp_path, {"farmer": [CREATE, change, {"start": {}}]}) == {"farmer": True}
    assert "## The draft, after asking of the character: “Make him a little older.”" in transcript(
        tmp_path, "farmer"
    )

    assert played(tmp_path, {"farmer": [change]}) == {"farmer": False}
    assert "its draft can't change" in transcript(tmp_path, "farmer")


def test_a_suggestion_is_played_by_its_words(tmp_path):
    played(tmp_path, {"farmer": [CREATE, {"start": {}}]})
    # The offline model suggests nothing, so the last scene's suggestions are put on file.
    data = kept(tmp_path, "farmer")
    data["choices"] = ["Look around the well.", "Go back to the dormitory."]
    (tmp_path / "farmer" / play.STATE_FILE).write_text(json.dumps(data), encoding="utf-8")

    assert played(tmp_path, {"farmer": [{"choose": 2}]}) == {"farmer": True}

    assert "## Turn 2 (choice)" in transcript(tmp_path, "farmer")
    assert kept(tmp_path, "farmer")["scenes"][1]["player_action"] == "Go back to the dormitory."


@pytest.mark.parametrize(
    ("steps", "says"),
    [
        ([{"start": {}}], "This play has no draft yet"),
        ([CREATE, {"act": "I look around."}], "This play hasn't started"),
        ([CREATE, {"start": {}}, {"start": {}}], "This play has already started."),
        ([CREATE, {"start": {}}, CREATE], "a new world is a new play"),
        ([CREATE, {"start": {}}, {"choose": 1}], "one of the last scene's 0 suggestions"),
        ([CREATE, {"start": {}}, {"choose": True}], "one of the last scene's 0 suggestions"),
        ([CREATE, {"start": {}}, {"act": "  "}], "act takes the action"),
        ([CREATE, {"dance": 1}], "No such step: 'dance'"),
        ([CREATE, {"act": "I look.", "wait": True}], "A step is one key and its value"),
        ([CREATE, {"show": ["sheet", "dice"]}], "show takes any of sheet, memory, record"),
        ([{"create": {"premise": " "}}], "create takes the premise"),
        ([CREATE, {"revise": {"target": "plot", "instruction": "More."}}], "revise takes a target"),
        ("start", "A play's steps are a list"),
    ],
)
def test_a_step_that_cant_be_played_stops_the_play_where_it_stood(tmp_path, steps, says):
    assert played(tmp_path, {"farmer": steps}) == {"farmer": False}

    told = transcript(tmp_path, "farmer")
    assert says in told
    if isinstance(steps, list) and len(steps) > 1:
        # What played before it is kept, and nothing of the step that failed.
        before = tmp_path / "before"
        assert played(before, {"farmer": steps[:-1]}) == {"farmer": True}
        after, expected = kept(tmp_path, "farmer"), kept(before, "farmer")
        assert after["state"] == expected["state"] and after["scenes"] == expected["scenes"]
    else:
        assert not (tmp_path / "farmer" / play.STATE_FILE).exists()


def test_an_opening_that_was_stopped_is_asked_for_again(tmp_path, monkeypatch):
    """The model's own filter can stop an opening (F4): the play then holds its opening state
    and no scene, and starting again plays the opening."""
    from graph.turn import UnreadableAction

    async def stopped(turn, client):
        raise UnreadableAction(categories=("violence",), stage="prompt")
        yield  # an async generator, as `run_turn` is

    with monkeypatch.context() as patched:
        patched.setattr("evals.runner.run_turn", stopped)
        assert played(tmp_path, {"farmer": [CREATE, {"start": {}}]}) == {"farmer": True}
    data = kept(tmp_path, "farmer")
    assert data["state"]["turn"] == 0 and data["scenes"] == []
    assert "**Refused:**" in transcript(tmp_path, "farmer")

    assert played(tmp_path, {"farmer": [{"wait": True}]}) == {"farmer": False}
    assert played(tmp_path, {"farmer": [{"start": {}}, {"wait": True}]}) == {"farmer": True}
    assert kept(tmp_path, "farmer")["state"]["turn"] == 2


def test_a_story_that_ended_takes_no_more_turns_but_still_shows_its_screens(tmp_path):
    played(tmp_path, {"farmer": [CREATE, {"start": {}}]})
    data = kept(tmp_path, "farmer")
    data["ended"] = {"kind": "death", "character_id": "player", "self_inflicted": False}
    (tmp_path / "farmer" / play.STATE_FILE).write_text(json.dumps(data), encoding="utf-8")

    assert played(tmp_path, {"farmer": [{"wait": True}]}) == {"farmer": False}
    assert "This story has ended" in transcript(tmp_path, "farmer")
    assert played(tmp_path, {"farmer": [{"show": "record"}]}) == {"farmer": True}


def test_a_step_that_breaks_says_where_and_the_other_plays_go_on(tmp_path, monkeypatch):
    async def broken(play_, given, models):
        raise RuntimeError("the model went away")

    monkeypatch.setitem(play._STEPS, "wait", broken)

    plays = {"one": [CREATE, {"start": {}}, {"wait": True}], "two": [CREATE, {"start": {}}]}
    assert played(tmp_path, plays) == {"one": False, "two": True}

    told = transcript(tmp_path, "one")
    assert "## Step 3 failed" in told and "RuntimeError('the model went away')" in told
    assert "Traceback" in told
    assert kept(tmp_path, "one")["state"]["turn"] == 1


def test_a_copy_goes_another_way_from_the_same_point_and_leaves_the_first_alone(tmp_path):
    assert played(tmp_path, {"farmer": [CREATE, {"start": {}}]}) == {"farmer": True}
    first = kept(tmp_path, "farmer")

    steps = [{"copy": "farmer"}, {"act": "I walk away from the well."}]
    assert played(tmp_path, {"other": steps}) == {"other": True}

    other = kept(tmp_path, "other")
    assert other["seed"] == first["seed"] and other["premise"] == first["premise"]
    assert [s["turn"] for s in other["scenes"]] == [1, 2]
    assert other["scenes"][0] == first["scenes"][0]
    assert kept(tmp_path, "farmer") == first
    told = transcript(tmp_path, "other")
    assert told.startswith("## Copied from `farmer`, after 1 scenes\n")
    assert "> I walk away from the well." in told


def test_a_copy_of_a_draft_can_be_changed_and_started_on_its_own(tmp_path):
    assert played(tmp_path, {"farmer": [CREATE]}) == {"farmer": True}

    assert played(tmp_path, {"other": [{"copy": "farmer"}, {"start": {}}]}) == {"other": True}

    assert transcript(tmp_path, "other").startswith("## Copied from `farmer`, as a draft\n")
    assert kept(tmp_path, "other")["state"]["turn"] == 1
    assert kept(tmp_path, "farmer")["state"] is None


@pytest.mark.parametrize(
    ("steps", "says"),
    [
        ([{"copy": "nobody"}], "There is no play named 'nobody' to copy."),
        ([{"copy": "../farmer"}], "copy takes the name of another play."),
        ([{"copy": 3}], "copy takes the name of another play."),
        ([CREATE, {"copy": "farmer"}], "This play already holds a story"),
    ],
)
def test_a_copy_that_cant_be_made_stops_the_play(tmp_path, steps, says):
    assert played(tmp_path, {"farmer": [CREATE]}) == {"farmer": True}

    assert played(tmp_path, {"other": steps}) == {"other": False}

    assert says in transcript(tmp_path, "other")
    assert kept(tmp_path, "farmer")["state"] is None


def test_a_play_isnt_copied_in_the_call_that_plays_it(tmp_path):
    # Plays run side by side, so the copy would be of wherever the other had got to.
    with pytest.raises(play.PlayError, match="'farmer' is played in this call too"):
        played(tmp_path, {"farmer": [CREATE], "other": [{"copy": "farmer"}]})
    with pytest.raises(play.PlayError, match="'other' is played in this call too"):
        played(tmp_path, {"other": [{"copy": "other"}]})

    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("name", ["../elsewhere", "Farmer", "a b", "", "-x", "x" * 41, 7])
def test_a_plays_name_is_its_folder_so_it_holds_nothing_a_path_could_misread(tmp_path, name):
    with pytest.raises(play.PlayError, match="small letters, digits and dashes"):
        played(tmp_path, {"good": [CREATE], name: [CREATE]})
    assert list(tmp_path.iterdir()) == []


def test_a_draft_whose_record_doesnt_hold_is_still_played_and_says_what_was_found(tmp_path):
    """The app plays whatever world a draft gave it: a scenario's world must hold (C1), a hand
    play's may not, and its record says what the check found."""
    world = worlds.sect()
    world.player.location_id = "nowhere"
    ev = Eval(play.SCENARIO, Mode.DETERMINISTIC)
    with pytest.raises(ValueError, match="breaks C1"):
        ev.story(world)

    assert ev.story(world, checked=False).state is world
    assert play._record(world)["record_check"]


def test_the_command_line_plays_and_says_which_plays_stopped(tmp_path, capsys):
    plays = {"one": [CREATE, {"start": {}}], "two": [{"start": {}}]}
    assert main(["play", "--root", str(tmp_path), "--plays", json.dumps(plays)]) == 1
    out = capsys.readouterr().out
    assert " played  one" in out and "stopped  two" in out
    # The transcript is printed too: a run's log is read where its files can't be.
    assert "## Turn 1 (opening)" in out

    assert main(["play", "--root", str(tmp_path), "--plays", json.dumps({"one": []})]) == 0


@pytest.mark.parametrize("given", ["[", "[]", "{}", '{"../x": []}'])
def test_the_command_line_refuses_what_it_cant_read(tmp_path, capsys, given):
    assert main(["play", "--root", str(tmp_path), "--plays", given]) == 2
    assert capsys.readouterr().err.strip()
    assert list(tmp_path.iterdir()) == []
