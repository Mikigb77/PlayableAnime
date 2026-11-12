"""Whole turns on the scripted fake for the actions Miki tried on 2026-11-05 (F1, F4, F5, W1):
stabbing yourself and killing a random stranger. Each one is read, resolved and told, and the
state the turn hands back passes every C1 invariant."""

import json

import pytest

from engine.context import Rating, TurnContext
from engine.contracts import DirectorPlan, Resolution, StepResolution
from engine.contracts.delta import CharacterChange, StateDelta
from engine.resolve import strangers
from engine.samples import cultivation_world, grounded_world
from engine.state import Attitude, Bout, StepResult, Terms
from engine.state.cast import CharacterStatus
from engine.state.sheet import Health
from graph.llm import Node, Reply
from graph.turn import TurnCompleted, TurnInput, TurnKind, run_turn
from graph.turn.context import narration_brief
from tests.graph.conftest import collect, run
from tests.graph.test_turn_graph import section


def turn_input(state, action: str, rating=Rating.MATURE) -> TurnInput:
    ctx = TurnContext(story_id="story-1", turn=state.turn + 1, rating=rating)
    return TurnInput(state=state, ctx=ctx, kind=TurnKind.ACTION, action=action)


def play(client, turn):
    events = run(collect(run_turn(turn, client)))
    assert isinstance(events[-1], TurnCompleted)
    return events[-1].result


def stab(**step) -> dict:
    return {
        "summary": "stab",
        "steps": [
            {
                "text": "drive the knife into my own chest",
                "verb": "stab",
                "kind": "exchange",
                "proposed_duration_s": 3,
                "aim": "kill",
                "uses": [{"part": "item", "ref": "knife"}],
                "facts": {"means": "clearly_enough"},
                **step,
            }
        ],
    }


@pytest.mark.parametrize("rating", [Rating.TEEN, Rating.MATURE])
def test_stabbing_yourself_is_read_resolved_and_told(fake, make_client, rating):
    fake.script(Node.INTERPRET, Reply(json=stab(target_ids=["luca"])))
    fake.script(Node.NARRATOR, Reply(json={"narration": "Your hand shakes, then it doesn't."}))

    result = play(make_client(rating=rating), turn_input(grounded_world(), "I stab myself"))

    assert result.state.player.status is CharacterStatus.DEAD
    assert result.scene.narration == "Your hand shakes, then it doesn't."
    assert result.state.deeds == {}  # harm to yourself wrongs nobody else (W1)
    assert result.state.scene.encounter is None


def test_a_random_stranger_in_the_street_is_killed_and_remembered(fake, make_client, monkeypatch):
    monkeypatch.setattr(strangers, "TOUGH_ODDS", 0.0)
    monkeypatch.setattr(strangers, "MASTER_ODDS", dict.fromkeys(strangers.MASTER_ODDS, 0.0))
    state = grounded_world()
    state.characters["luca"].location_id = "naples"
    state.scene.place_id = "naples"
    state.scene.present_ids = ["luca"]
    stranger = {
        "who": "a man buying cigarettes",
        "plausibility": "plausible",
        "crowd": True,
    }
    unaware = {"can_respond": False, "why_not": "unaware", "means": "clearly_enough"}
    fake.script(
        Node.INTERPRET,
        Reply(json=stab(text="stab some random guy", stranger=stranger, facts=unaware)),
    )
    fake.script(Node.NARRATOR, Reply(json={"narration": "He never sees the blade."}))

    result = play(make_client(), turn_input(state, "I grab my knife and kill some random guy"))

    (step,) = result.resolution.steps
    victim_id, onlooker_id = step.strangers
    after = result.state
    assert after.characters[victim_id].status is CharacterStatus.DEAD
    assert after.characters[victim_id].name == "a man buying cigarettes"
    (deed,) = after.deeds.values()
    assert deed.victim_ids == [victim_id] and deed.witness_ids == [onlooker_id]
    # The narrator met them under the ids the engine gave them.
    [request] = [r for r in fake.requests if r.node is Node.NARRATOR]
    assert victim_id in request.prompt.messages[-1].text


def test_the_narrator_is_told_who_a_step_made_real():
    state = grounded_world()
    made = CharacterChange(id="stranger-1-0", name="a dockhand", description="A dockhand.")
    killed = CharacterChange(id="stranger-1-0", status=CharacterStatus.DEAD)
    step = StepResolution(
        index=0,
        text="stab a dockhand",
        outcome_class="certain",
        reason="",
        result=StepResult.SUCCESS,
        duration_s=2,
        strangers=["stranger-1-0"],
        effects=StateDelta(characters=[made, killed]),
    )
    brief = narration_brief(
        before=state,
        after=state,
        ctx=TurnContext(story_id="s", turn=2),
        intent=None,
        resolution=Resolution(steps=[step]),
        plan=DirectorPlan(),
        fired=[],
        scenes=[],
    )
    # Who they were comes from the change that made them, not the one that killed them.
    assert '"met"' in brief.user and "stranger-1-0" in brief.user and "a dockhand" in brief.user


def test_a_fight_never_reopens_a_wound_the_character_never_had(fake, make_client):
    # 2026-11-07: Miki's character, unhurt all story, "reopened an old wound" with broken ribs in
    # a small fight. The interpret step leaned on an injury nobody had, and the narrator's update
    # tried to keep it: code leaves both out, so the odds, the scene and the record stay true (N6).
    state = grounded_world()
    shove = {
        "summary": "shove past Carmine",
        "steps": [
            {
                "text": "shove past Carmine to the door",
                "verb": "shove",
                "kind": "exchange",
                "proposed_duration_s": 3,
                "target_ids": ["carmine"],
                "facts": {
                    "challenge": "hard",
                    "opposition": "Carmine blocking the door",
                    "opposition_ids": ["carmine"],
                    "can_respond": True,
                    "foes_mean": "none",
                    "hindrances": ["the old wound in your ribs reopening", "the crowded bar"],
                },
            }
        ],
    }
    update = {
        "characters": [
            {"id": "luca", "condition": {"health": "hurt", "wounds": ["broken ribs, reopened"]}}
        ]
    }
    fake.script(Node.INTERPRET, Reply(json=shove))
    fake.script(Node.NARRATOR, Reply(json={"narration": "You shoulder past.", "update": update}))

    result = play(make_client(), turn_input(state, "I shove past Carmine"))

    condition = result.state.player.sheet.condition
    assert condition.health is Health.UNHURT and condition.wounds == []
    codes = [issue.code for issue in result.issues]
    assert "unrecorded_harm" in codes and "rejected" in codes
    (step,) = result.resolution.steps
    # The number names what is really against them, and nothing the record doesn't hold.
    assert step.outcome_class == "contested" and "; the crowded bar (+5): " in step.reason
    assert "wound" not in step.reason and "ribs" not in step.reason
    [request] = fake.calls(Node.NARRATOR)
    brief = request.prompt.messages[-1].text
    assert "old wound" not in brief
    assert '"condition":{"health":"unhurt","wounds":[]}' in brief


def test_a_lesson_s_blows_are_a_bout_whatever_the_interpret_step_made_of_them(fake, make_client):
    # 2026-11: in Miki's long story every blow of a lesson with a mentor was recorded as an
    # attack on him, and he ended afraid, bearing grudges and due to come for revenge. The
    # interpret step proposes the terms once; code keeps them, holds each blow to them and
    # records one bout, however a later blow is read (W1).
    state = cultivation_world()
    state.characters["zhao"].sheet.disposition.attitudes["lin"] = Attitude(affinity=20)

    def blow(aim: str, **facts) -> dict:
        facts = {"opposition_ids": ["zhao"], "can_respond": True, "foes_mean": "none", **facts}
        strike = {
            "text": "strike at Zhao with the practice sword",
            "verb": "strike",
            "kind": "exchange",
            "proposed_duration_s": 3,
            "aim": aim,
            "target_ids": ["zhao"],
            "facts": facts,
        }
        return {"summary": "spar with Zhao", "steps": [strike]}

    client = make_client()
    told = Reply(json={"narration": "Wood cracks on wood."})
    for proposed in (blow("subdue", terms="no_harm"), blow("wound"), blow("kill")):
        fake.script(Node.INTERPRET, Reply(json=proposed))
        fake.script(Node.NARRATOR, told)
        result = play(client, turn_input(state, "I come at Zhao again"))
        state = result.state
        (step,) = result.resolution.steps
        assert step.bout is not None and step.bout.terms is Terms.NO_HARM
        brief = fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text
        assert '"bout":"no_harm"' in brief

    zhao = state.characters["zhao"]
    condition = zhao.sheet.condition
    assert zhao.alive and (condition.health, condition.states) == (Health.UNHURT, [])
    assert [deed.kind for deed in state.deeds.values()] == ["bout"]
    attitude = zhao.attitude_toward("lin")
    assert (attitude.fear, attitude.grudges) == (0, []) and attitude.affinity > 20
    assert state.scene.encounter.bout == Bout(terms=Terms.NO_HARM, with_ids=["zhao"])
    # The interpret step saw the bout under way before each later blow.
    later = fake.calls(Node.INTERPRET)[-1].prompt.messages[-1].text
    assert '"bout":{"terms":"no_harm","with_ids":["zhao"]}' in later


def test_a_lesson_the_telling_ends_on_its_own_is_still_on(fake, make_client):
    """W10. On the real model (2026-11-12) a scene had the mentor walk away from a lesson the
    engine still had going, and the next blow was read as aimed at the bystander. Code ends a
    bout, never the telling: the narrator is told it is still on, and he is still in the scene."""
    spar = {
        "summary": "spar with Zhao",
        "steps": [
            {
                "text": "strike at Zhao with the practice sword",
                "verb": "strike",
                "kind": "exchange",
                "proposed_duration_s": 3,
                "aim": "subdue",
                "target_ids": ["zhao"],
                "facts": {
                    "opposition_ids": ["zhao"],
                    "can_respond": True,
                    "foes_mean": "none",
                    "terms": "no_harm",
                },
            }
        ],
    }
    end = {"ended_on": "Zhao walks away.", "place_id": "well", "present_ids": ["lin"]}
    walks_off = {"narration": "Zhao walks away.", "update": {"scene_end": end}}
    client = make_client()
    fake.script(Node.INTERPRET, Reply(json=spar))
    fake.script(Node.NARRATOR, Reply(json=walks_off))
    result = play(client, turn_input(cultivation_world(), "I come at Zhao"))

    brief = fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text
    outcome = json.loads(section(brief, "OUTCOME"))
    assert outcome["still_on"] == {"kind": "fight", "with": ["zhao"], "bout": "no_harm"}
    state = result.state
    assert state.scene.present_ids == ["lin", "zhao"] and state.scene.encounter is not None
    assert [i.subject for i in result.issues if i.code == "encounter_kept"] == ["zhao"]

    # An hour of something else ends it before it plays: the scene is told of no fight still
    # on, and its end stands.
    rest = {"text": "sit by the well", "verb": "sit", "kind": "task", "proposed_duration_s": 3600}
    fake.script(Node.INTERPRET, Reply(json={"summary": "sit by the well", "steps": [rest]}))
    fake.script(Node.NARRATOR, Reply(json=walks_off))
    result = play(client, turn_input(state, "I sit by the well for an hour"))

    brief = fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text
    assert "still_on" not in json.loads(section(brief, "OUTCOME"))
    assert result.state.scene.present_ids == ["lin"] and result.state.scene.encounter is None
    assert not [i for i in result.issues if i.code == "encounter_kept"]


def test_the_first_opening_records_a_wound_the_premise_starts_with(fake, make_client):
    # N6: the premise is the player's own words, so "you wake up wounded" is recorded on the
    # first opening. Any later scene would be refused (see the test above).
    state = grounded_world()
    update = {
        "characters": [
            {"id": "luca", "condition": {"health": "wounded", "wounds": ["a knife wound"]}}
        ]
    }
    fake.script(Node.NARRATOR, Reply(json={"narration": "You wake in a ditch.", "update": update}))
    ctx = TurnContext(story_id="story-1", turn=1)
    turn = TurnInput(
        state=state,
        ctx=ctx,
        kind=TurnKind.OPENING,
        premise="I wake up in a ditch with a knife wound.",
    )

    result = play(make_client(), turn)

    condition = result.state.player.sheet.condition
    assert condition.health is Health.WOUNDED
    assert [w.text for w in condition.wounds] == ["a knife wound"]
