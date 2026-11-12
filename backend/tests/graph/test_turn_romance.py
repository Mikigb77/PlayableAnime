"""W17: a move in a romance through a whole turn, on the scripted fake model.

The reading names the move, code rules on it from the bond on record and the other's own heart,
the narrator is told what came of it, and nothing the narrator says moves the bond or a heart.
"""

import json

from engine import bonds
from engine.context import Rating, StorySettings, TurnContext
from engine.contracts import OutcomeClass
from engine.samples import farm_world
from engine.state.cast import Character
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
