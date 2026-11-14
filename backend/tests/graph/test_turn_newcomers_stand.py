"""G18, A4: someone the story brings in comes standing where the narrator's update says,
through a turn. Nobody on record is lifted (`engine.apply`)."""

import pytest

from engine import path
from engine.contracts import CharacterChange
from engine.contracts.intent import ActionKind, Intent, IntentStep
from engine.samples import cultivation_world
from graph.llm import Node, Reply
from graph.turn.check import NAMED_BY_SCENE, REAL_ENTITY, called_in
from graph.turn.context import interpret_prompt
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
    assert [p["rung"] for p in shown["sheet"]["ladders"]] == ["Core Formation"]


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
    # Gemini answers only what a form requires as often as not, so it is always asked: a
    # string, empty for whoever stands on no rung.
    assert "rung" in form["$defs"]["CharacterChange"]["required"]
    assert rung["type"] == "string"


def test_the_narrators_form_always_asks_how_old_a_character_is():
    # F3: the first live play to bring someone in left her age out, and the kiss the next
    # turn was refused. The form asks a number of everyone, as it asks the rung.
    form = NarratorOutput.model_json_schema()
    change = form["$defs"]["CharacterChange"]

    assert "age" in change["required"]
    assert change["properties"]["age"]["type"] == "integer"
    assert "their age in years" in change["properties"]["age"]["description"]
    # Code may still leave it out.
    assert CharacterChange(id="zhao").age is None


def test_a_change_that_leaves_the_rung_empty_puts_nobody_anywhere(fake, make_client):
    tao = {"id": "gate_boy", "name": "Little Tao", "age": 9, "location_id": "well", "rung": ""}
    fake.script(Node.INTERPRET, Reply(json=WAIT))
    fake.script(
        Node.NARRATOR, Reply(json=scene(tao, {"id": "zhao", "rung": ""}, present=("gate_boy",)))
    )

    _, result = play(make_client(), turn_input())

    assert "rejected" not in [i.code for i in result.issues]
    assert result.state.characters["gate_boy"].sheet.ladders == []
    assert on_realms(result.state, "zhao") == 1


def test_the_narrator_reads_where_everyone_stands_by_the_rungs_name():
    """A place counted from 0 was read one rung low: in the first live story that brought in an
    elder on Core Formation, he said he had reached Foundation Establishment (2026-11-13)."""
    state = cultivation_world()
    state.characters["zhao"].sheet.ladders[0].shown_rung = 0
    calls_on = IntentStep(
        text="call on Elder Mo",
        verb="greet",
        kind=ActionKind.CONVERSATION,
        proposed_duration_s=300,
        target_ids=["elder-mo"],
    )

    text = brief(state, intent=Intent(steps=[calls_on])).user

    def stands(view: dict) -> list[dict]:
        return view["sheet"]["ladders"]

    assert stands(_section(text, "PLAYER CHARACTER")) == [
        {"ladder_id": "realms", "rung": "Qi Condensation", "stage": "early"}
    ]
    zhao = next(p for p in _section(text, "SCENE")["present"] if p["id"] == "zhao")
    assert stands(zhao) == [
        {
            "ladder_id": "realms",
            "rung": "Foundation Establishment",
            "stage": "early",
            # G20: the rung he passes for, by its name too.
            "shown_rung": "Qi Condensation",
        }
    ]
    (mo,) = _section(text, "WHO ELSE")
    assert mo["id"] == "elder-mo"
    assert stands(mo) == [{"ladder_id": "realms", "rung": "Core Formation", "stage": "late"}]


def test_the_interpret_step_keeps_the_number_its_form_answers_with():
    state = cultivation_world()
    state.characters["zhao"].sheet.ladders[0].shown_rung = 0

    text = interpret_prompt(state, "I hide my cultivation").messages[-1].text

    assert _section(text, "PLAYER CHARACTER")["sheet"]["ladders"][0]["rung"] == 0
    zhao = next(p for p in _section(text, "SCENE")["present"] if p["id"] == "zhao")
    assert (zhao["sheet"]["ladders"][0]["rung"], zhao["sheet"]["ladders"][0]["shown_rung"]) == (
        1,
        0,
    )


NAMED = "An old man in grey steps out from under the gate. “Elder Song,” Zhao Kun breathes."


def codes(result, code: str) -> list[str | None]:
    return [issue.subject for issue in result.issues if issue.code == code]


def test_someone_new_the_update_leaves_nameless_takes_the_name_the_scene_calls_them_by(
    fake, make_client
):
    """The narrator's form doesn't require a name, and in a live story it called an elder by
    name all through the scene and left the name out of its update: he was refused for want
    of one, and the record never had him (2026-11-13)."""
    song = {"id": "elder-song", "age": 140, "location_id": "well", "rung": "Core Formation"}
    told = scene(song, present=("elder-song",)) | {"narration": NAMED}
    fake.script(Node.INTERPRET, Reply(json=WAIT))
    fake.script(Node.NARRATOR, Reply(json=told))

    _, result = play(make_client(), turn_input())

    state = result.state
    assert state.characters["elder-song"].name == "Elder Song"
    assert on_realms(state, "elder-song") == 2
    assert codes(result, NAMED_BY_SCENE) == ["elder-song"]
    assert codes(result, "rejected") == []


def test_someone_nameless_the_scene_never_names_is_still_refused(fake, make_client):
    # C1: ARRIVES tells of an old man in grey and names nobody.
    fake.script(Node.INTERPRET, Reply(json=WAIT))
    fake.script(Node.NARRATOR, Reply(json=scene({"id": "elder-song", "location_id": "well"})))

    _, result = play(make_client(), turn_input())

    assert "elder-song" not in result.state.characters
    assert [i.area for i in result.issues if i.code == "rejected"] == ["character.create"]
    assert codes(result, NAMED_BY_SCENE) == []


def test_a_word_that_is_no_name_names_nobody_though_the_scene_says_it(fake, make_client):
    told = scene({"id": "stranger"}) | {"narration": "A stranger steps out from under the gate."}
    fake.script(Node.INTERPRET, Reply(json=WAIT))
    fake.script(Node.NARRATOR, Reply(json=told))

    _, result = play(make_client(), turn_input())

    assert "stranger" not in result.state.characters
    assert codes(result, NAMED_BY_SCENE) == []


def test_a_name_the_update_gives_stands_and_someone_on_record_keeps_theirs(fake, make_client):
    # The scene calls the newcomer Elder Song and his update says Old Grey: the update's word
    # stands. Zhao Kun's change gives no name, and the scene's "Zhao" is not a new one for him.
    grey = {"id": "elder-song", "name": "Old Grey", "location_id": "well"}
    told = scene(grey, {"id": "zhao"}) | {"narration": NAMED + " Zhao bows low."}
    fake.script(Node.INTERPRET, Reply(json=WAIT))
    fake.script(Node.NARRATOR, Reply(json=told))

    _, result = play(make_client(), turn_input())

    state = result.state
    assert state.characters["elder-song"].name == "Old Grey"
    zhao = state.characters["zhao"]
    assert (zhao.name, zhao.aliases) == ("Zhao Kun", ["Senior Brother Zhao"])
    assert codes(result, NAMED_BY_SCENE) == []


def test_an_id_whose_words_someone_on_record_goes_by_is_nobody_new(fake, make_client):
    # "zhao_kun" is Zhao Kun's id written another way, and "senior_brother_zhao" his alias: a
    # second Zhao Kun on record would be worse than a refused change.
    told = scene({"id": "zhao_kun"}, {"id": "senior_brother_zhao"}) | {
        "narration": "Zhao Kun bows low. “Senior Brother Zhao,” someone whispers."
    }
    fake.script(Node.INTERPRET, Reply(json=WAIT))
    fake.script(Node.NARRATOR, Reply(json=told))

    _, result = play(make_client(), turn_input())

    assert not {"zhao_kun", "senior_brother_zhao"} & result.state.characters.keys()
    assert codes(result, NAMED_BY_SCENE) == []
    refused = [i.area for i in result.issues if i.code == "rejected"]
    assert refused == ["character.create", "character.create"]


def test_a_name_the_scene_gives_is_held_to_what_any_new_name_is(fake, make_client):
    # G12: nobody new is named after a real person, whoever supplied the name.
    told = scene({"id": "elon_musk", "age": 55}) | {"narration": "Elon Musk waits by the well."}
    fake.script(Node.INTERPRET, Reply(json=WAIT))
    fake.script(Node.NARRATOR, Reply(json=told))

    _, result = play(make_client(), turn_input())

    assert "elon_musk" not in result.state.characters
    assert codes(result, REAL_ENTITY) == ["Elon Musk"]


@pytest.mark.parametrize(
    ("told", "character_id", "name"),
    [
        ("“Elder Song,” you say.", "elder-song", "Elder Song"),
        # As the scene writes it as a name, wherever it first says the words.
        ("An elder. Song of the peak, elder song to some: Elder Song.", "elder_song", "Elder Song"),
        ("Elder Núñez bows.", "elder_nunez", "Elder Núñez"),
        ("Then Lin de la Cruz bows.", "lin_de_la_cruz", "Lin de la Cruz"),
        # Never written as a name: each word takes a capital.
        ("The envoy—calm—waits.", "envoy", "Envoy"),
        ("The envoy waits.", "the_envoy", "The Envoy"),
        # The words in a row and in order, or nothing.
        ("An old man steps out.", "elder-song", None),
        ("Song, the elder, nods.", "elder-song", None),
        ("A song elder than the peak itself.", "elder-song", None),
        ("Elder Songbird sings.", "elder-song", None),
        ("Anything at all.", "", None),
    ],
)
def test_the_name_a_scene_gives_someone_is_their_ids_words_as_it_writes_them(
    told, character_id, name
):
    assert called_in(told, character_id) == name


def test_the_narrators_form_says_someone_new_always_comes_with_a_name():
    form = NarratorOutput.model_json_schema()
    name = form["$defs"]["CharacterChange"]["properties"]["name"]

    assert "always for someone new" in name["description"]
