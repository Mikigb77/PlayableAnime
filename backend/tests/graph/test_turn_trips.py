"""W10, W7: a trip through a whole turn. The first model says where the step goes, code takes
the time from the map and moves the character, and the narrator is told the trip and ends its
scene there (Miki's review, 2026-11-11)."""

import json

from engine.base import DAY, HOUR, MINUTE
from engine.contracts import ActionKind, Intent, IntentStep, StandingAction
from engine.director import rules
from engine.samples import farm_world
from engine.state import Journey, Place, Route, Rumor
from engine.tally import turn_tally
from engine.visibility import memory_view
from graph.drafting import prompts as drafting_prompts
from graph.drafting.schema import DraftProposal
from graph.llm import Block, Node, Reply
from graph.turn import TurnKind, prompts
from graph.turn.context import _known_view, _scene_view, interpret_prompt
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


LOOK_AROUND = {
    "summary": "Tomas looks around.",
    "steps": [{"text": "look around", "verb": "look", "kind": "task", "proposed_duration_s": 30}],
}


def scene(place_id: str | None, present=("tomas", "bram"), told_talk=False, **update) -> dict:
    end = {"ended_on": "Old Bram looks up from his fence.", "present_ids": list(present)}
    if place_id is not None:
        end["place_id"] = place_id
    return {
        "action": "You shoulder your pack and take the valley road.",
        "narration": "The road runs between the fields, and Millbrook's roofs come up at last.",
        "told_talk": told_talk,
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


# A week of work on the farm as the real model once read "the next week" (2026-11-13): the
# right length, and no mark that the player timed it.
A_WEEK_OF_WORK = {
    "summary": "Tomas works the farm for a week.",
    "steps": [
        {
            "text": "work the farm for a week",
            "verb": "work",
            "kind": "work",
            "proposed_duration_s": 7 * DAY,
        }
    ],
}


def test_a_week_the_player_asked_for_is_a_week_in_the_storys_own_language(fake, make_client):
    """W10, S10: the player's own words say how long, so the time stands whether or not the
    reading marked it. Held to what work lasts, the week stopped at eighteen hours."""
    from engine.context import Language, StorySettings

    def worked(action: str, language: Language) -> int:
        fake.script(Node.INTERPRET, Reply(json=A_WEEK_OF_WORK))
        fake.script(Node.NARRATOR, Reply(json=scene(None, present=("tomas",))))
        settings = StorySettings(language=language)
        turn = turn_input(valley(), action=action, settings=settings)
        result = play(make_client(), turn)[1]
        return result.state.world_s - turn.state.world_s

    assert worked("Trabajo en la granja toda la próxima semana", Language.ES) == 7 * DAY
    assert worked("Treballo a la granja tota la setmana vinent", Language.CA) == 7 * DAY
    assert worked("I work the farm all of next week", Language.EN) == 7 * DAY
    # Words that give no time leave the model's own guess held to what work lasts.
    assert worked("Trabajo en la granja", Language.ES) == 18 * HOUR


BARN = "The miller's barn burned down in the night."


def talking(state):
    """The same valley, with Millbrook talking about the miller's barn (W2)."""
    state.rumors["barn"] = Rumor(
        id="barn", text=BARN, is_true=True, reached_place_ids=["village"], started_s=state.world_s
    )
    return state


def test_arriving_somewhere_brings_no_news(fake, make_client):
    """W2 (Miki, 2026-11-11: "don't force it, like arriving at a place, immediately hearing
    stuff"): word that reached Millbrook before Tomas is not told to him as he gets there."""
    _, result = walk(fake, make_client, scene("village", told_talk=True), state=talking(valley()))

    brief = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    (step,) = json.loads(section(brief, "OUTCOME"))["steps"]
    assert step["trip"] == {"to": "Millbrook", "to_id": "village", "arrived": True}
    assert "## TALK" not in brief
    # Nothing was on offer, so nothing is heard whatever the narrator says it told.
    assert result.state.rumors["barn"].heard_at == {}


def look_on(fake, make_client, **told):
    """Tomas in Millbrook, looking on: the one scene that is always offered the talk there is."""
    state = talking(valley())
    state.player.location_id = "village"
    state.scene.place_id = "village"
    fake.script(Node.NARRATOR, Reply(json=scene("village", present=("tomas",), **told)))
    turn = turn_input(state, kind=TurnKind.STANDING, standing=StandingAction.OBSERVE)
    result = play(make_client(), turn)[1]
    # T5: what the turn's log line counts, from the state the turn started on.
    tally = turn_tally(turn.state, result.state, result.resolution, result.plan)
    return fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text, result, tally


def test_a_quiet_scene_is_offered_the_talk_of_the_place_and_what_it_told_is_heard(
    fake, make_client
):
    brief, result, tally = look_on(fake, make_client, told_talk=True)

    assert json.loads(section(brief, "TALK")) == {"saying": BARN}
    heard = result.state.rumors["barn"].heard_at
    assert heard == {"tomas": result.state.world_s}
    assert [r.text for r in memory_view(result.state).rumors] == [BARN]  # C6
    # T5: it is heard because the scene told it, so the turn's log counts none as unvoiced.
    assert (tally["rumors_heard"], tally["rumors_unvoiced"]) == (1, 0)


def test_talk_the_scene_left_out_is_not_heard(fake, make_client):
    """They can miss it: it stays the talk of the place, and Memory never lists it."""
    brief, result, tally = look_on(fake, make_client)  # the narrator answers no told_talk

    assert json.loads(section(brief, "TALK")) == {"saying": BARN}
    assert result.state.rumors["barn"].heard_at == {}
    assert memory_view(result.state).rumors == []
    assert (tally["rumors_heard"], tally["rumors_unvoiced"]) == (0, 0)


def test_a_place_never_seen_is_shown_for_the_first_time(fake, make_client, monkeypatch):
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
    }
    assert "## TALK" not in brief


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


def test_a_spot_the_scene_adds_at_the_end_of_the_trip_lies_where_the_trip_went(fake, make_client):
    """R8. The narrator ends the scene at an inn it adds, and says neither where it lies nor
    what kind of place it is: it is in the village the walk reached, so whoever is in the
    village is around and whoever comes there finds the character."""
    inn = {"id": "the_plough", "name": "the Plough"}
    _, result = walk(fake, make_client, scene("the_plough", present=("tomas",), places=[inn]))

    after = result.state
    assert after.scene.place_id == after.player.location_id == "the_plough"
    assert after.places["the_plough"].parent_id == "village"
    assert [i.code for i in result.issues if i.code == "trip_place"] == ["trip_place"]
    assert "the_plough" not in [r.to_id for r in after.places["farm"].routes]

    # The next brief has the village's people as here.
    fake.script(Node.INTERPRET, Reply(json=LOOK_AROUND))
    fake.script(Node.NARRATOR, Reply(json=scene("the_plough", present=("tomas",))))
    play(make_client(), turn_input(after, action="I look around"))
    brief = fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text
    here = {c["id"]: c.get("here") for c in json.loads(section(brief, "WHO ELSE"))}
    assert here == {"bram": True}
    assert json.loads(section(brief, "SCENE"))["place"]["within"][0]["id"] == "village"


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
    # The first model's guide says what on_the_way means only while the scene shows it (B5).
    told = "on_the_way under SCENE is a trip that stopped before its end"
    assert told in interpret_prompt(state, "I ride on").system
    state.scene.place_id = "village"  # the scene has gone somewhere else since
    assert "on_the_way" not in _scene_view(state)
    assert told not in interpret_prompt(state, "I ride on").system
    assert told in prompts.INTERPRET_SYSTEM


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
    assert "- Arriving (W10)." in telling and "Arriving is no moment for news" in telling
    assert "- Talk of the place (W2)." in telling
    assert "It is an offer and never a task" in telling
    assert "never a list of things heard" in telling and "they can miss it" in telling
    assert "Set told_talk true only when the scene told it" in telling
    assert "- TALK: something the place is saying" in prompts.BRIEF_GUIDE
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
