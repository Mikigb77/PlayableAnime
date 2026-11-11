"""W10, W7: a trip through a whole turn. The first model says where the step goes, code takes
the time from the map and moves the character, and the narrator is told the trip and ends its
scene there (Miki's review, 2026-11-11)."""

import json

from engine.base import DAY, HOUR, MINUTE
from engine.contracts import ActionKind, Intent, IntentStep
from engine.director import rules
from engine.samples import farm_world
from engine.state import Journey, Place, Route, Rumor
from graph.drafting import prompts as drafting_prompts
from graph.drafting.schema import DraftProposal
from graph.llm import Block, Node, Reply
from graph.turn import TurnKind, prompts
from graph.turn.context import _known_view, _scene_view
from tests.graph.test_turn_graph import play, section, turn_input

WALK = 40 * MINUTE


def valley():
    """Tomas at his farm: the village is forty minutes off by the map and the city three days
    beyond it."""
    state = farm_world()
    state.turn = 4
    state.places["city"] = Place(
        id="city",
        name="Harrowgate",
        kind="city",
        routes=[Route(to_id="village", travel_s=3 * DAY, mode="by cart")],
        known_by=["tomas"],
    )
    return state


# The first model's reading, with its usual mistake: a walk to the village is a two-minute move.
TO_THE_VILLAGE = {
    "summary": "Tomas walks to the village.",
    "steps": [
        {
            "text": "walk to the village",
            "verb": "walk",
            "kind": "move",
            "destination": "Millbrook",
            "proposed_duration_s": 120,
        }
    ],
}


def scene(place_id: str | None, present=("tomas", "bram"), **update) -> dict:
    end = {"ended_on": "Old Bram looks up from his fence.", "present_ids": list(present)}
    if place_id is not None:
        end["place_id"] = place_id
    return {
        "action": "You shoulder your pack and take the valley road.",
        "narration": "The road runs between the fields, and Millbrook's roofs come up at last.",
        "suggestions": [],
        "update": {"scene_end": end, **update},
    }


def walk(fake, make_client, narrator: dict, state=None, **extra):
    fake.script(Node.INTERPRET, Reply(json=TO_THE_VILLAGE))
    fake.script(Node.NARRATOR, Reply(json=narrator))
    turn = turn_input(state or valley(), action="I walk to the village", **extra)
    return turn, play(make_client(), turn)[1]


def test_a_trip_takes_the_maps_time_and_the_scene_ends_there(fake, make_client):
    turn, result = walk(fake, make_client, scene("village"))

    assert result.state.world_s == turn.state.world_s + WALK
    assert result.state.scene.place_id == "village"
    assert result.state.player.location_id == "village"
    assert result.scene.world_end_s - result.scene.world_start_s == WALK
    assert "trip_place" not in [i.code for i in result.issues]
    # The narrator is told where the step took them, and how long it was.
    brief = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    (step,) = json.loads(section(brief, "OUTCOME"))["steps"]
    assert step["trip"] == {"to": "Millbrook", "to_id": "village", "arrived": True}
    assert json.loads(section(brief, "TIME"))["world_seconds_passed"] == WALK


def test_the_narrator_is_told_what_the_place_they_reach_is_saying(fake, make_client):
    """W2, C6: word that reached Millbrook before Tomas is what he hears as he gets there."""
    state = valley()
    state.rumors["barn"] = Rumor(
        id="barn",
        text="The miller's barn burned down in the night.",
        is_true=True,
        reached_place_ids=["village"],
        started_s=state.world_s,
    )

    _, result = walk(fake, make_client, scene("village"), state=state)

    brief = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    (step,) = json.loads(section(brief, "OUTCOME"))["steps"]
    assert step["trip"]["heard"] == ["The miller's barn burned down in the night."]
    assert "first_visit" not in step["trip"]  # he knows Millbrook well
    assert "tomas" in result.state.rumors["barn"].heard_at


def test_a_place_never_seen_owes_the_scene_some_talk_of_its_own(fake, make_client, monkeypatch):
    monkeypatch.setattr(rules, "ROAD_MIN_S", 10**12)  # a quiet road: this is about arriving
    reading = {
        "summary": "Tomas rides to Harrowgate.",
        "steps": [
            {
                "text": "ride to Harrowgate",
                "verb": "ride",
                "kind": "travel",
                "destination": "city",
                "proposed_duration_s": HOUR,
            }
        ],
    }
    fake.script(Node.INTERPRET, Reply(json=reading))
    fake.script(Node.NARRATOR, Reply(json=scene("city", present=("tomas",))))

    play(make_client(), turn_input(valley(), action="I ride to Harrowgate"))

    brief = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    (step,) = json.loads(section(brief, "OUTCOME"))["steps"]
    assert step["trip"] == {
        "to": "Harrowgate",
        "to_id": "city",
        "arrived": True,
        "first_visit": True,
        "talk": True,
    }


def test_the_first_model_sees_how_far_the_places_it_knows_are(fake, make_client):
    walk(fake, make_client, scene("village"))

    asked = fake.calls(Node.INTERPRET)[0].prompt.messages[-1].text
    places = {p["id"]: p for p in json.loads(section(asked, "KNOWN"))["places"]}
    assert places["village"]["travel_s"] == WALK
    assert places["city"]["travel_s"] == WALK + 3 * DAY
    assert "travel_s" not in places["valley"]  # no route says how far "the valley" is


def test_a_scene_that_stays_behind_is_put_where_the_trip_went(fake, make_client, log_lines):
    _, result = walk(fake, make_client, scene("farm", present=("tomas", "ilse")))

    assert result.state.scene.place_id == "village"
    assert result.state.player.location_id == "village"
    assert [i.code for i in result.issues if i.code == "trip_place"] == ["trip_place"]
    # T6: the issue is logged by its code; what it says stays at DEBUG.
    above_debug = [line for line in log_lines() if line["severity"] != "DEBUG"]
    assert any(line.get("turn_issue") == {"code": "trip_place"} for line in above_debug)


def test_a_scene_with_no_end_is_put_where_the_trip_went(fake, make_client):
    untold = scene("village")
    del untold["update"]["scene_end"]

    _, result = walk(fake, make_client, untold)

    assert result.state.scene.place_id == "village"
    assert result.state.scene.present_ids == ["tomas"]  # nobody said who came along
    assert result.state.characters["ilse"].location_id == "farm"


def test_a_template_line_still_leaves_the_character_where_the_trip_went(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=TO_THE_VILLAGE))
    fake.script(Node.NARRATOR, Block(), Block())
    turn = turn_input(valley(), action="I walk to the village")

    result = play(make_client(), turn)[1]

    assert result.narration_mode == "template"
    assert result.state.world_s == turn.state.world_s + WALK
    assert result.state.scene.place_id == "village"


def test_a_trip_over_new_ground_is_on_the_map_from_then_on(fake, make_client, monkeypatch):
    monkeypatch.setattr(rules, "ROAD_MIN_S", 10**12)  # a quiet road: this is about the map
    marsh = {"id": "marsh", "name": "the salt marshes", "kind": "wilds", "setting": "outdoors"}
    reading = {
        "summary": "Tomas rides out to the salt marshes.",
        "steps": [
            {
                "text": "ride out to the salt marshes",
                "verb": "ride",
                "kind": "travel",
                "destination": "the salt marshes",
                "proposed_duration_s": 5 * HOUR,
            }
        ],
    }
    fake.script(Node.INTERPRET, Reply(json=reading))
    fake.script(Node.NARRATOR, Reply(json=scene("marsh", present=("tomas",), places=[marsh])))
    turn = turn_input(valley(), action="I ride out to the salt marshes")

    result = play(make_client(), turn)[1]

    assert result.state.world_s == turn.state.world_s + 5 * HOUR
    (route,) = result.state.places["farm"].routes[1:]
    assert (route.to_id, route.travel_s) == ("marsh", 5 * HOUR)
    # The next turn's first model reads the way home off the map.
    assert _known_view(result.state)["places"][0]["id"] == "city"
    home = {p["id"]: p for p in _known_view(result.state)["places"]}["farm"]
    assert home["travel_s"] == 5 * HOUR


def test_the_scene_shows_a_trip_that_stopped_on_the_way():
    state = valley()
    state.journey = Journey(from_id="farm", to_id="city", total_s=3 * DAY, done_s=DAY, at_id="farm")

    assert _scene_view(state)["on_the_way"] == {
        "to": "city",
        "name": "Harrowgate",
        "travel_s": 2 * DAY,
        "left": "2 d",
    }
    state.scene.place_id = "village"  # the scene has gone somewhere else since
    assert "on_the_way" not in _scene_view(state)


def test_the_models_are_told_how_trips_work():
    reading, telling = prompts.INTERPRET_SYSTEM, prompts.NARRATOR_SYSTEM

    assert "- destination, always:" in reading
    assert "Code takes the trip's time from the map" in reading
    assert "never split a trip into legs the player didn't choose" in reading
    assert "- timed: true when the player says how long the step lasts" in reading
    assert "- A trip (W10)." in telling
    assert "never in the place they were going to" in telling
    assert "never the place the character left" in telling
    assert "the way is alive" in telling and "come only with an EVENT" in telling
    assert "- Arriving (W2)." in telling and "never leave one out" in telling
    assert "of your own making" in telling and "record it under leads" in telling
    assert "travel_s by a place is the seconds the way there takes" in prompts.BRIEF_GUIDE
    assert "on_the_way is a trip that stopped before its end" in prompts.BRIEF_GUIDE


def test_the_first_model_is_always_asked_where_a_step_goes():
    """Gemini leaves out what a schema doesn't require as often as not, and a trip nobody
    names is a trip code can't time."""
    step = Intent.model_json_schema()["$defs"]["IntentStep"]

    assert "destination" in step["required"]
    assert "timed" not in step["required"]
    plain = IntentStep(text="wait", verb="wait", kind=ActionKind.WAIT, proposed_duration_s=5)
    assert plain.destination == "" and plain.timed is False


def test_a_new_world_is_drafted_with_its_map():
    assert "Draw the map between them (W7, W10)" in drafting_prompts.SYSTEM
    place = DraftProposal.model_json_schema()["$defs"]["PlaceP"]
    assert (
        "every place can be reached from the others" in place["properties"]["routes"]["description"]
    )


def test_an_opening_has_no_trip_to_settle(fake, make_client):
    fake.script(Node.NARRATOR, Reply(json=scene("farm", present=("tomas", "ilse"))))
    state = valley()
    state.turn = 0

    result = play(make_client(), turn_input(state, kind=TurnKind.OPENING))[1]

    assert result.state.scene.place_id == "farm" and result.state.journey is None
