"""W11, W2, C6: a witness through whole turns. The scene that tells a deed is told who runs to
tell of it, the next action can go after them, and code decides who runs whatever the
narrator's update listed: until they set off they are in the scene, and once they have they are
out of it (Miki, 2026-11-11)."""

import json

from engine.base import HOUR
from engine.samples import cultivation_world
from engine.state import Character
from engine.world import Kind, carriers
from graph.llm import Node, Reply
from tests.graph.test_turn_graph import play, section, turn_input

SECT = "the Azure Cloud Sect"


def well():
    """Lin and Zhao at the well, with Wei looking on. The sect sits in the inner court, forty
    minutes away on foot."""
    state = cultivation_world()
    state.places["inner-court"].controller_id = "azure-cloud"
    state.characters["zhao"].memberships = []
    state.characters["wei"] = Character(id="wei", name="Wei", location_id="well")
    state.scene.present_ids.append("wei")
    return state


STONE = {
    "summary": "Lin throws a stone at Zhao.",
    "steps": [
        {
            "text": "throw a stone at Zhao",
            "verb": "throw",
            "target_ids": ["zhao"],
            "kind": "exchange",
            "aim": "wound",
            "proposed_duration_s": 2,
            "facts": {"foes_mean": "none"},
        }
    ],
}


AT_WEI = {
    "summary": "Lin throws a stone at Wei.",
    "steps": [
        {
            "text": "throw a stone at Wei",
            "verb": "throw",
            "target_ids": ["wei"],
            "kind": "exchange",
            "aim": "wound",
            "proposed_duration_s": 2,
            "facts": {"foes_mean": "none"},
        }
    ],
}


def stand(seconds: int) -> dict:
    return {
        "summary": "Lin stands over Zhao.",
        "steps": [
            {
                "text": "stand over Zhao",
                "verb": "stand",
                "kind": "task",
                "proposed_duration_s": seconds,
            }
        ],
    }


def told(*present: str) -> dict:
    return {
        "action": "You do it.",
        "narration": "The yard holds its breath.",
        "suggestions": [],
        "update": {
            "scene_end": {
                "ended_on": "Zhao glares up at you.",
                "place_id": "well",
                "present_ids": list(present),
            }
        },
    }


def turn(fake, make_client, state, reading: dict, *present: str):
    fake.script(Node.INTERPRET, Reply(json=reading))
    fake.script(Node.NARRATOR, Reply(json=told(*present)))
    result = play(make_client(), turn_input(state, action=reading["summary"]))[1]
    brief = fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text
    asked = fake.calls(Node.INTERPRET)[-1].prompt.messages[-1].text
    return result, brief, json.loads(section(asked, "SCENE"))


def witnesses(brief: str):
    return json.loads(section(brief, "WITNESSES")) if "## WITNESSES" in brief else None


def test_a_witness_runs_the_scene_shows_it_and_code_takes_them_out_of_it(fake, make_client):
    first, brief, scene = turn(fake, make_client, well(), STONE, "lin", "zhao", "wei")

    # The scene that tells the stone is told Wei is off to the sect, still within reach.
    assert "leaving" not in scene
    assert witnesses(brief) == [{"id": "wei", "who": "Wei", "to_tell": SECT, "gone": False}]
    assert "wei" in first.state.scene.present_ids
    assert "witness_left" not in [i.code for i in first.issues]
    (runner,) = carriers.runners(first.state)
    assert runner.sets_off_s > first.state.world_s

    # Five minutes of doing nothing about him: the next reading sees him leaving, the scene is
    # told he got away, and he is out of it though its end still lists him.
    second, brief, scene = turn(fake, make_client, first.state, stand(300), "lin", "zhao", "wei")
    assert scene["leaving"] == [{"id": "wei", "to_tell": SECT}]
    assert witnesses(brief) == [{"id": "wei", "who": "Wei", "to_tell": SECT, "gone": True}]
    assert second.state.scene.present_ids == ["lin", "zhao"]
    assert [i.code for i in second.issues if i.code == "witness_left"] == ["witness_left"]
    stone = second.state.deeds["deed-1"]
    assert "azure-cloud" not in stone.known_by_factions
    # Gone, he saw nothing of what came after he left.
    assert all("wei" not in d.witness_ids for d in second.state.deeds.values() if d is not stone)

    # An hour on he has told the sect, forty minutes away. Nothing of that shows at the well.
    third, brief, scene = turn(fake, make_client, second.state, stand(HOUR), "lin", "zhao")
    assert "azure-cloud" in third.state.deeds["deed-1"].known_by_factions
    assert third.state.characters["wei"].location_id == "inner-court"
    assert "leaving" not in scene
    assert witnesses(brief) is None
    assert "Wei tells" not in brief and "Word of a deed" not in brief
    landed = [e for e in third.state.pending_events.values() if e.kind == Kind.REPORT]
    assert landed and all(e.applied_turn == third.state.turn for e in landed)


def test_a_scene_that_ends_without_a_witness_who_hasnt_run_still_has_them(fake, make_client):
    """On the real model (2026-11-11) the scene of a killing ended without the witness, and
    Memory never had the character see him go."""
    first, _, _ = turn(fake, make_client, well(), STONE, "lin", "zhao")

    # Wei is yet to set off, so he is in the scene whatever its end listed.
    assert first.state.scene.present_ids == ["lin", "zhao", "wei"]
    assert [i.subject for i in first.issues if i.code == "witness_kept"] == ["wei"]
    assert first.state.deeds["deed-1"].went_to_tell == {}

    # Five minutes on he has gone. The scene leaves him out, as it was told to, and the
    # character saw him go.
    second, brief, scene = turn(fake, make_client, first.state, stand(300), "lin", "zhao")
    assert scene["leaving"] == [{"id": "wei", "to_tell": SECT}]
    assert witnesses(brief) == [{"id": "wei", "who": "Wei", "to_tell": SECT, "gone": True}]
    assert second.state.scene.present_ids == ["lin", "zhao"]
    assert second.state.deeds["deed-1"].went_to_tell == {"wei": "azure-cloud"}
    assert not [i for i in second.issues if i.code in ("witness_left", "witness_kept")]


def test_a_witness_the_character_goes_after_is_held_by_the_fight(fake, make_client):
    first, _, _ = turn(fake, make_client, well(), STONE, "lin", "zhao", "wei")

    # A stone at Wei starts a fight with him. The scene is told the fight holds him, and its
    # end, which has him get away, doesn't take him out of it.
    second, brief, _ = turn(fake, make_client, first.state, AT_WEI, "lin", "zhao")
    assert "wei" in second.state.scene.encounter.opponent_ids
    assert witnesses(brief) == [
        {"id": "wei", "who": "Wei", "to_tell": SECT, "gone": False, "held": True}
    ]
    assert second.state.scene.present_ids == ["lin", "zhao", "wei"]
    assert [i.subject for i in second.issues if i.code == "witness_kept"] == ["wei"]

    # An hour of something else ends the fight: he gets away, in front of the character, and
    # tells the sect.
    third, brief, _ = turn(fake, make_client, second.state, stand(HOUR), "lin", "zhao")
    assert third.state.scene.encounter is None
    assert third.state.scene.present_ids == ["lin", "zhao"]
    assert third.state.deeds["deed-1"].went_to_tell == {"wei": "azure-cloud"}
    assert "azure-cloud" in third.state.deeds["deed-1"].known_by_factions
