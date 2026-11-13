"""W17: a move in a romance through a whole turn, on the scripted fake model.

The reading names the move, code rules on it from the bond on record and the other's own heart,
the narrator is told what came of it, and nothing the narrator says moves the bond or a heart.
"""

import json

from engine import bonds
from engine.context import Rating, StorySettings, TurnContext
from engine.contracts import OutcomeClass
from engine.samples import farm_world
from engine.state.cast import Character, Place, Route
from engine.state.records import Bond, BondStage, BondStep, StepResult
from engine.state.sheet import Attitude
from engine.state.world import WorldState
from graph.llm import Node, Reply
from graph.turn import TurnCompleted, TurnInput, TurnKind, prompts, run_turn
from graph.turn.context import asks, interpret_prompt
from graph.turn.form import intent_form
from tests.graph.conftest import collect, run


def farm(attraction: int, stage: BondStage | None = None) -> WorldState:
    """Tomas at his gate with Mara, a neighbour he is or isn't courting."""
    state = farm_world()
    felt = Attitude(affinity=30, trust=30, attraction=attraction)
    mara = Character(id="mara", name="Mara", age=29, location_id="farm", known_by=["tomas"])
    mara.met_by = ["tomas"]
    mara.sheet.disposition.attitudes["tomas"] = felt
    state.characters["mara"] = mara
    state.scene.present_ids = ["tomas", "mara"]
    if stage is not None:
        state.bonds["bond-2"] = Bond(
            id="bond-2", a_id="tomas", b_id="mara", stage=stage, steps=[BondStep(stage=stage)]
        )
    return state


def asked(move: str | None, text: str = "ask Mara to be with me", verb: str = "ask") -> dict:
    return {
        "summary": "Tomas asks Mara.",
        "steps": [
            {
                "text": text,
                "verb": verb,
                "target_ids": ["mara"],
                "axis": "influence",
                "kind": "conversation",
                "proposed_duration_s": 300,
                "romance": move,
                "facts": {"opposition_ids": ["mara"], "can_respond": True},
            }
        ],
    }


def scene(**update) -> dict:
    """A scene whose narrator says yes to everything, whatever the engine decided."""
    return {
        "narration": "Mara laughs, takes your hands and says yes.",
        "suggestions": [{"label": "Walk her home", "kind": "personal"}],
        "update": {
            "scene_end": {
                "ended_on": "Mara's hands are in yours.",
                "place_id": "farm",
                "present_ids": ["tomas", "mara"],
            },
            **update,
        },
    }


def play(fake, make_client, state: WorldState, reading: dict, told: dict, action: str):
    fake.script(Node.INTERPRET, Reply(json=reading))
    fake.script(Node.NARRATOR, Reply(json=told))
    ctx = TurnContext(
        story_id="story-1", turn=state.turn + 1, settings=StorySettings(), rating=Rating.TEEN
    )
    turn = TurnInput(state=state, ctx=ctx, kind=TurnKind.ACTION, action=action)
    events = run(collect(run_turn(turn, make_client())))
    assert isinstance(events[-1], TurnCompleted)
    return events[-1].result


def section(text: str, name: str) -> str:
    return text.split(f"## {name}\n", 1)[1].split("\n## ", 1)[0]


def test_an_ask_their_heart_is_there_for_makes_a_couple_on_record(fake, make_client):
    state = farm(bonds.DECLARE_SURE, BondStage.COURTING)
    result = play(fake, make_client, state, asked("declare"), scene(), "I ask Mara to be mine")

    [step] = result.resolution.steps
    assert (step.outcome_class, step.result) == (OutcomeClass.CERTAIN, StepResult.SUCCESS)
    assert step.reason == "Mara wants this too. You and Mara are together now."
    bond = bonds.live(result.state, "tomas", "mara")
    assert bond.stage is BondStage.TOGETHER
    assert bond.steps[-1].turn == 1

    # The form asked for the move, and the guide explained it.
    [read] = fake.calls(Node.INTERPRET)
    assert asks(state).romance
    assert read.json_schema == intent_form(asks(state))
    assert "- romance, always (W17)" in read.prompt.system
    assert read.prompt.system == prompts.interpret_system(asks(state))
    # The narrator reads the scene as it began, with the two still courting, and is told what
    # came of the ask. The next scene begins with a couple.
    [narration] = fake.calls(Node.NARRATOR)
    told = narration.prompt.messages[-1].text
    assert "You and Mara are together now." in section(told, "OUTCOME")
    assert "A romance is on record, and only the engine moves it (W17)" in narration.prompt.system
    mara = next(p for p in json.loads(section(told, "SCENE"))["present"] if p["id"] == "mara")
    assert mara["bond_with_you"]["stage"] == "courting"
    after = interpret_prompt(result.state, "I kiss Mara").messages[-1].text
    assert '"bond_with_you":{"stage":"together","since":"moments ago"' in after


def test_the_scene_cannot_make_a_couple_of_two_whose_hearts_arent_there(fake, make_client):
    """The narrator's yes changes nothing: the ask was turned down, and so the record says."""
    state = farm(10)
    sweet = scene(
        characters=[{"id": "mara", "attitudes": [{"toward_id": "tomas", "affinity": 10}]}]
    )
    # A scene that tries to move her heart itself is refused that part.
    sweet["update"]["characters"][0]["attitudes"][0]["attraction"] = 60
    sweet["update"]["bonds"] = [{"a_id": "tomas", "b_id": "mara", "stage": "together"}]
    result = play(fake, make_client, state, asked("declare"), sweet, "I ask Mara to be mine")

    [step] = result.resolution.steps
    assert (step.outcome_class, step.result) == (OutcomeClass.RULED_OUT, StepResult.FAILURE)
    assert step.reason == "Mara's heart isn't there yet."
    assert bonds.live(result.state, "tomas", "mara").stage is BondStage.INTEREST
    felt = result.state.characters["mara"].attitude_toward("tomas")
    assert (felt.attraction, felt.affinity) == (10, 40)
    [narration] = fake.calls(Node.NARRATOR)
    assert "Mara's heart isn't there yet." in section(narration.prompt.messages[-1].text, "OUTCOME")


def test_a_kiss_the_reading_left_unnamed_is_still_an_advance(fake, make_client):
    """The step's own words count beside the reading: a kiss with a partner is one, and sure."""
    state = farm(60, BondStage.TOGETHER)
    reading = asked(None, "kiss Mara", "kiss")
    result = play(fake, make_client, state, reading, scene(), "I kiss Mara")

    [step] = result.resolution.steps
    assert (step.outcome_class, step.roll) == (OutcomeClass.CERTAIN, None)
    assert step.reason.startswith("You and Mara are together: nothing stands in the way.")
    assert result.state.characters["mara"].attitude_toward("tomas").attraction == 70


def test_a_step_that_is_no_move_reads_and_plays_as_before(fake, make_client):
    state = farm(60, BondStage.COURTING)
    reading = asked(None, "ask Mara about the harvest")
    result = play(fake, make_client, state, reading, scene(), "I ask Mara about the harvest")

    assert bonds.live(result.state, "tomas", "mara").stage is BondStage.COURTING
    assert result.state.characters["mara"].attitude_toward("tomas").attraction == 60


# --- the world reacting: a partner who is wronged ---------------------------------------------


def outcome(fake) -> dict:
    """The OUTCOME section the narrator was last given."""
    return json.loads(section(fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text, "OUTCOME"))


def feels(state: WorldState, who: str = "ilse") -> tuple[int, int, int]:
    toward = state.characters[who].attitude_toward("tomas")
    return toward.affinity, toward.trust, toward.attraction


def test_a_partner_who_is_there_sees_it_and_the_scene_is_told_so(fake, make_client):
    """Tomas kisses Mara with his wife standing by: it is a deed that wrongs her, she saw it,
    and the narrator reads both."""
    state = farm(60, BondStage.COURTING)
    state.scene.present_ids.append("ilse")
    reading = asked("advance", "kiss Mara", "kiss")
    result = play(fake, make_client, state, reading, scene(), "I kiss Mara")

    [step] = outcome(fake)["steps"]
    assert step["wrongs"] == [{"id": "ilse", "who": "Ilse Weller", "saw_it": True}]
    (deed,) = result.state.deeds.values()
    assert (deed.kind, deed.target_ids, deed.wronged_ids) == ("court", ["mara"], ["ilse"])
    assert "ilse" in deed.witness_ids and "ilse" in deed.known_by
    # Courting someone else is an affair: liking, trust and heart, by how far it went.
    assert feels(result.state) == (
        80 - bonds.WRONGED_LIKING * bonds.AFFAIR,
        80 - bonds.WRONGED_TRUST * bonds.AFFAIR,
        80 - bonds.WRONGED_HEART * bonds.AFFAIR,
    )
    (grudge,) = result.state.characters["ilse"].attitude_toward("tomas").grudges
    assert grudge.reason == "Tomas Weller courted Mara at the Weller farm."
    assert bonds.live(result.state, "tomas", "ilse").stage is BondStage.MARRIED
    system = fake.calls(Node.NARRATOR)[-1].prompt.system
    assert "A partner minds another romance" in system


def test_a_partner_who_is_elsewhere_is_named_and_knows_nothing_yet(fake, make_client):
    state = farm(60, BondStage.COURTING)  # Ilse is about the farm, and not at the gate
    reading = asked("advance", "kiss Mara", "kiss")
    result = play(fake, make_client, state, reading, scene(), "I kiss Mara")

    [step] = outcome(fake)["steps"]
    assert step["wrongs"] == [{"id": "ilse", "who": "Ilse Weller"}]
    (deed,) = result.state.deeds.values()
    assert "ilse" not in deed.known_by and feels(result.state) == (80, 80, 80)


def test_a_move_that_wrongs_nobody_names_nobody(fake, make_client):
    state = farm(60, BondStage.COURTING)
    bonds.end(state.bonds["bond-1"], by_id="ilse", how="She left.", turn=0, world_s=0)
    reading = asked("advance", "kiss Mara", "kiss")
    result = play(fake, make_client, state, reading, scene(), "I kiss Mara")

    assert "wrongs" not in outcome(fake)["steps"][0]
    assert not [d for d in result.state.deeds.values() if d.wronged_ids]


def test_a_partner_whose_heart_is_gone_comes_to_end_it_and_no_scene_mends_it(fake, make_client):
    """The whole of it over two turns: she sees the kiss, and a day later she comes to say it
    is over. The scene is given that as its event, and the record holds whatever it tells."""
    state = farm(60, BondStage.COURTING)
    state.scene.present_ids.append("ilse")
    state.characters["ilse"].sheet.disposition.attitudes["tomas"].attraction = 50
    reading = asked("advance", "kiss Mara", "kiss")
    seen = play(fake, make_client, state, reading, scene(), "I kiss Mara").state
    assert feels(seen)[2] == 30 < bonds.LEAVES_UNDER
    assert bonds.live(seen, "tomas", "ilse").stage is BondStage.MARRIED  # not in the moment

    days = {
        "summary": "Tomas works his fields.",
        "steps": [
            {
                "text": "work the fields for three days",
                "verb": "work",
                "kind": "time_skip",
                "proposed_duration_s": 3 * 86400,
                "timed": True,
            }
        ],
    }
    mended = scene(
        characters=[{"id": "ilse", "attitudes": [{"toward_id": "tomas", "affinity": 90}]}],
        bonds=[{"a_id": "tomas", "b_id": "ilse", "stage": "married"}],
    )
    result = play(fake, make_client, seen, days, mended, "I work the fields for three days")

    told = fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text
    event = json.loads(section(told, "EVENT"))
    assert event["title"] == (
        "Ilse Weller comes to tell Tomas Weller it is over between them: Tomas Weller courted "
        "Mara at the Weller farm."
    )
    assert outcome(fake)["stop_reason"] == "interrupted"  # she found him on the second day
    [ilse] = [p for p in json.loads(section(told, "WHO ELSE")) if p["id"] == "ilse"]
    assert ilse["bond_with_you"]["stage"] == "over"
    assert ilse["bond_with_you"]["ended"].startswith("Ilse Weller ended it: ")
    bond = result.state.bonds["bond-1"]
    assert (bond.stage, bond.steps[-1].by_id, bond.steps[-1].turn) == (BondStage.OVER, "ilse", 2)
    assert bonds.partners(result.state, "tomas") == []
    assert feels(result.state)[2] == 30


def alone() -> dict:
    """The scripted scene, ending at the farm gate with nobody but Tomas in it."""
    told = scene()
    told["update"]["scene_end"]["present_ids"] = ["tomas"]
    return told


def test_an_ask_to_someone_a_short_walk_away_goes_to_them(fake, make_client):
    """W10: she is in Millbrook and he is at his gate. The step goes to her first, so she
    answers where she is: the scene is told the walk and that she is here, and it ends there
    whatever place the narrator gave."""
    state = farm(bonds.DECLARE_SURE, BondStage.COURTING)
    state.characters["mara"].location_id = "village"
    state.scene.present_ids = ["tomas"]
    result = play(fake, make_client, state, asked("declare"), alone(), "I ask Mara to be mine")

    [step] = result.resolution.steps
    assert (step.outcome_class, step.result) == (OutcomeClass.CERTAIN, StepResult.SUCCESS)
    assert step.trip.to_id == "village" and step.trip.arrived
    assert step.duration_s == 40 * 60  # the walk is the least it takes
    assert bonds.live(result.state, "tomas", "mara").stage is BondStage.TOGETHER
    assert result.state.characters["tomas"].location_id == "village"
    assert result.state.scene.place_id == "village"
    told = fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text
    trip = outcome(fake)["steps"][0]["trip"]
    assert trip == {"to": "Millbrook", "to_id": "village", "arrived": True}
    [mara] = [p for p in json.loads(section(told, "WHO ELSE")) if p["id"] == "mara"]
    assert mara["here"] is True


def test_an_ask_to_someone_far_off_reaches_nobody(fake, make_client):
    """W10: she is in a town three hours down the road. Her heart would say yes, and nothing
    is on record all the same: the scene is told she isn't here, and lists her as elsewhere."""
    state = farm(bonds.DECLARE_SURE, BondStage.COURTING)
    state.places["town"] = Place(id="town", name="Harrow", kind="town", known_by=["tomas"])
    state.places["farm"].routes.append(Route(to_id="town", travel_s=3 * 60 * 60))
    state.characters["mara"].location_id = "town"
    state.scene.present_ids = ["tomas"]
    result = play(fake, make_client, state, asked("declare"), alone(), "I ask Mara to be mine")

    [step] = result.resolution.steps
    assert (step.outcome_class, step.result) == (OutcomeClass.RULED_OUT, StepResult.FAILURE)
    assert step.reason == "Mara isn't here." and step.trip is None
    assert bonds.live(result.state, "tomas", "mara").stage is BondStage.COURTING
    assert result.state.characters["tomas"].location_id == "farm"
    assert not result.state.deeds  # and nothing that would wrong his wife was done
    told = fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text
    assert outcome(fake)["steps"][0]["why"] == "Mara isn't here."
    [mara] = [p for p in json.loads(section(told, "WHO ELSE")) if p["id"] == "mara"]
    assert "here" not in mara and mara["bond_with_you"]["stage"] == "courting"
