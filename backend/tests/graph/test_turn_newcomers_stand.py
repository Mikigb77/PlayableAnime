"""G18, A4: someone the story brings in comes standing where the narrator's update says,
through a turn. Nobody on record is lifted (`engine.apply`)."""

from engine import path
from graph.llm import Node, Reply
from graph.turn.outputs import NarratorOutput
from tests.graph.test_turn_context import _section, brief
from tests.graph.test_turn_graph import SCENE, play, turn_input

WAIT = {
    "summary": "Lin waits by the well.",
    "steps": [
        {"text": "wait by the well", "verb": "wait", "kind": "task", "proposed_duration_s": 600}
    ],
}
ARRIVES = "An old man in grey steps out from under the gate and looks the disciples over."


def scene(*people: dict, present: tuple[str, ...] = ()) -> dict:
    end = SCENE["update"]["scene_end"] | {"present_ids": ["lin", "zhao", *present]}
    return SCENE | {
        "narration": ARRIVES,
        "update": {"characters": list(people), "scene_end": end},
    }


def on_realms(state, who: str) -> int:
    return path.own_rung(state.characters[who], "realms")


def test_someone_a_scene_brings_in_is_on_record_where_its_update_has_them(fake, make_client):
    bai = {
        "id": "elder_bai",
        "name": "Elder Bai",
        "age": 140,
        "location_id": "well",
        "meets_player": True,
        "rung": "Core Formation",
    }
    fake.script(Node.INTERPRET, Reply(json=WAIT))
    fake.script(Node.NARRATOR, Reply(json=scene(bai, present=("elder_bai",))))

    _, result = play(make_client(), turn_input())

    state = result.state
    assert "rejected" not in [i.code for i in result.issues]
    assert on_realms(state, "elder_bai") == 2
    assert state.characters["elder_bai"].sheet.axes.might == 6
    # The next scene's narrator reads him on that rung, like anyone the world was drafted with.
    present = _section(brief(state).user, "SCENE")["present"]
    shown = next(p for p in present if p["id"] == "elder_bai")
    assert [p["rung"] for p in shown["sheet"]["ladders"]] == [2]


def test_through_a_turn_nobody_on_record_is_lifted(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=WAIT))
    fake.script(Node.NARRATOR, Reply(json=scene({"id": "zhao", "rung": "Soul Transformation"})))

    _, result = play(make_client(), turn_input())

    refused = [i for i in result.issues if i.code == "rejected"]
    assert [i.area for i in refused] == ["character.rung"]
    assert on_realms(result.state, "zhao") == 1


def test_the_narrators_form_says_when_a_character_comes_with_a_rung():
    # The narrator's standing text has no room for it (K1): the form's own field says it.
    form = NarratorOutput.model_json_schema()
    rung = form["$defs"]["CharacterChange"]["properties"]["rung"]

    assert "only for someone new" in rung["description"]
    assert "nobody is lifted" in rung["description"]
