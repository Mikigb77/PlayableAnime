"""N6 on the turn graph: a death ends the player character's story, and `/end` tells an epilogue
with only what the world allows of the player's note on how it should end."""

import pytest

from engine.context import Rating, TurnContext
from engine.contracts import (
    ActionKind,
    Aim,
    Intent,
    IntentStep,
    OutcomeClass,
    Resolution,
    StepResolution,
)
from engine.samples import grounded_world
from engine.state.cast import CharacterStatus
from engine.state.records import StepResult
from graph.llm import Node, Reply
from graph.turn import (
    Ending,
    EndingRefused,
    TurnCompleted,
    TurnInput,
    TurnKind,
    prompts,
    run_turn,
)
from graph.turn.ending import ending_of
from tests.graph.conftest import collect, run

EPILOGUE = {"narration": "The bar empties; you leave the city to the sea.", "suggestions": []}


def opened():
    state = grounded_world()
    state.turn = 3
    return state


def turn_input(state, kind, action=None, *, drop_refused=False) -> TurnInput:
    ctx = TurnContext(story_id="story-1", turn=state.turn + 1, rating=Rating.MATURE)
    return TurnInput(state=state, ctx=ctx, kind=kind, action=action, drop_refused=drop_refused)


def play(client, turn):
    events = run(collect(run_turn(turn, client)))
    assert isinstance(events[-1], TurnCompleted)
    return events[-1].result


def step(text, verb, means="clearly_enough", **extra) -> dict:
    return {
        "text": text,
        "verb": verb,
        "kind": "move",
        "proposed_duration_s": 600,
        "facts": {"means": means},
        **extra,
    }


def told(fake) -> str:
    [request] = fake.calls(Node.NARRATOR)
    return request.prompt.messages[-1].text


def test_a_death_ends_the_story_on_its_last_scene(fake, make_client):
    stab = step("drive the knife into my own heart", "stab", aim="kill", target_ids=["luca"])
    stab |= {
        "kind": "exchange",
        "proposed_duration_s": 3,
        "uses": [{"part": "item", "ref": "knife"}],
    }
    fake.script(Node.INTERPRET, Reply(json={"summary": "stab", "steps": [stab]}))
    fake.script(
        Node.NARRATOR,
        Reply(
            json={
                "narration": "Your hand stops shaking.",
                "suggestions": [{"label": "Run", "kind": "personal"}],
            }
        ),
    )

    result = play(make_client(), turn_input(opened(), TurnKind.ACTION, "I stab myself"))

    assert result.ending == Ending(kind="death", character_id="luca", self_inflicted=True)
    assert result.scene.choices == []  # nothing left for them to act on
    prompt = told(fake)
    assert '"kind":"death"' in prompt and prompts.DEATH_TASK in prompt
    assert '"count":0' in prompt


def test_an_ending_with_no_note_is_told_from_things_as_they_stand(fake, make_client):
    fake.script(Node.NARRATOR, Reply(json=EPILOGUE))

    result = play(make_client(), turn_input(opened(), TurnKind.END))

    assert fake.calls(Node.INTERPRET) == []
    assert result.ending == Ending(kind="chosen", character_id="luca")
    assert result.state.player.status is CharacterStatus.ALIVE
    assert result.scene.kind is TurnKind.END and result.scene.choices == []
    prompt = told(fake)
    assert prompts.EPILOGUE_TASK in prompt and prompts.OPENING_TASK not in prompt


def test_a_note_the_world_allows_plays_in_the_epilogue(fake, make_client):
    leave = step("walk out of the bar for the last time", "walk")
    fake.script(Node.INTERPRET, Reply(json={"summary": "leave", "steps": [leave]}))
    fake.script(Node.NARRATOR, Reply(json=EPILOGUE))
    note = "I walk out of the bar and leave the family business behind"

    result = play(make_client(), turn_input(opened(), TurnKind.END, note))

    assert result.ending == Ending(kind="chosen", character_id="luca")
    assert [s.text for s in result.resolution.steps] == ["walk out of the bar for the last time"]
    prompt = told(fake)
    assert note in prompt and prompts.EPILOGUE_TASK in prompt


def crowned():
    leave = step("walk out of the bar for the last time", "walk")
    crown = step("become the king of Italy", "rule", means="clearly_not")
    return {"summary": "end", "steps": [crown, leave]}


def test_a_note_asking_for_what_the_world_rules_out_is_refused(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=crowned()))

    with pytest.raises(EndingRefused) as refusal:
        run(collect(run_turn(turn_input(opened(), TurnKind.END, "I become king"), make_client())))

    # Every refused part at once, though the plan would stop at the first (R6).
    [refused] = refusal.value.refused
    assert refused.text == "become the king of Italy"
    assert refused.outcome_class == "ruled_out" and refused.reason
    assert fake.calls(Node.NARRATOR) == []  # nothing is told or saved


def test_ending_without_what_was_refused_keeps_the_rest(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=crowned()))
    fake.script(Node.NARRATOR, Reply(json=EPILOGUE))
    turn = turn_input(opened(), TurnKind.END, "I become king", drop_refused=True)

    result = play(make_client(), turn)

    assert [s.text for s in result.resolution.steps] == ["walk out of the bar for the last time"]
    assert [s.text for s in result.intent.steps] == ["walk out of the bar for the last time"]
    assert result.ending == Ending(kind="chosen", character_id="luca")
    # The narrator gets what was kept and what was left out, never the note as written.
    prompt = told(fake)
    assert "I become king" not in prompt
    assert '"left_out":["become the king of Italy"]' in prompt


def test_an_ending_note_never_claims_how_others_take_it(fake, make_client):
    # A6: the player never writes outcomes or others' reactions, and an ending is no exception.
    leave = step("walk out of the bar for the last time", "walk")
    note = {"summary": "leave", "steps": [leave], "outcome_claims": ["the city mourns me"]}
    fake.script(Node.INTERPRET, Reply(json=note))

    with pytest.raises(EndingRefused) as refusal:
        run(
            collect(run_turn(turn_input(opened(), TurnKind.END, "I leave, mourned"), make_client()))
        )

    [refused] = refusal.value.refused
    assert refused.text == "the city mourns me"
    assert refused.outcome_class == "ruled_out" and refused.reason


def test_a_note_with_no_steps_keeps_what_else_it_says(fake, make_client):
    # A note read as a standing action is played, not dropped for having no steps.
    fake.script(Node.INTERPRET, Reply(json={"summary": "watch", "standing": "observe"}))
    fake.script(Node.NARRATOR, Reply(json=EPILOGUE))

    result = play(make_client(), turn_input(opened(), TurnKind.END, "I watch the sea"))

    assert result.intent is not None and result.intent.standing == "observe"
    assert result.ending == Ending(kind="chosen", character_id="luca")


def played(*steps: IntentStep) -> Resolution:
    """Every step played, cleanly."""
    return Resolution(
        steps=[
            StepResolution(
                index=i,
                text=s.text,
                outcome_class=OutcomeClass.CERTAIN,
                reason="as it stands",
                result=StepResult.SUCCESS,
                duration_s=s.proposed_duration_s,
            )
            for i, s in enumerate(steps)
        ]
    )


def died():
    before = opened()
    after = before.model_copy(deep=True)
    after.characters["luca"].status = CharacterStatus.DEAD
    return before, after


POISON = IntentStep(
    text="drink the poison",
    verb="drink",
    kind=ActionKind.INSTANT,
    proposed_duration_s=5,
    aim=Aim.KILL,
    target_ids=["luca"],
)


def test_a_note_that_kills_you_is_a_death():
    before, after = died()

    ending = ending_of(before, after, Intent(steps=[POISON]), played(POISON), TurnKind.END)
    assert ending == Ending(kind="death", character_id="luca", self_inflicted=True)


def test_harming_yourself_before_dying_of_something_else_is_no_self_inflicted_death():
    # A blood oath's cut, then a fall: the step that killed them aimed at no one.
    before, after = died()
    cut = POISON.model_copy(update={"text": "cut my palm for the oath", "aim": Aim.WOUND})
    jump = IntentStep(
        text="leap the gap between the roofs",
        verb="leap",
        kind=ActionKind.INSTANT,
        proposed_duration_s=3,
    )

    ending = ending_of(before, after, Intent(steps=[cut, jump]), played(cut, jump), TurnKind.ACTION)
    assert ending == Ending(kind="death", character_id="luca", self_inflicted=False)


def test_dying_of_something_else_is_no_self_inflicted_death():
    # Such as the blast of your own throw in stopped time (W10a): no helpline line for that.
    before = opened()
    after = before.model_copy(deep=True)
    after.characters["luca"].status = CharacterStatus.DEAD
    throw = IntentStep(
        text="throw the pebble at the army",
        verb="throw",
        kind=ActionKind.INSTANT,
        proposed_duration_s=1,
        target_ids=["carmine"],
    )

    ending = ending_of(before, after, Intent(steps=[throw]), played(throw), TurnKind.ACTION)
    assert ending == Ending(kind="death", character_id="luca", self_inflicted=False)


def test_an_ordinary_turn_reaches_no_ending():
    state = opened()
    assert ending_of(state, state, None, Resolution(), TurnKind.ACTION) is None
