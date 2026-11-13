"""G18, G7: a ladder gains a rung above its top through a turn.

The narrator names the rung and code decides whether it holds (`engine.apply`,
`engine.path.beyond_problem`). The scene's own words have to name it (`check_update`), and
from that scene on the character has heard of it. While a ladder is open above its top, the
narrator's form asks first what the scene calls the rung above it (`form.narrator_form`), and
the narrator is told that the ladder can grow on the ladder itself, in WORLD, and beside a
step that stopped at its top, however the model that reads the player's words filed it. The
open rule that held the ladder there is struck once a rung above is told (G7).
"""

import json

from engine import path
from engine.base import HOUR
from engine.contracts import NewRung, OutcomeClass, Resolution, StateDelta, StepResolution
from engine.resolve.powers import growth
from engine.samples import cultivation_world
from engine.state import LadderPosition, RuleTopic, StepResult
from engine.visibility import status_view
from graph.llm import Node, Reply
from graph.turn.check import RUNG_UNTOLD, check_update, with_rung_above
from graph.turn.context import interpret_prompt, open_above
from graph.turn.form import Above, narrator_form
from graph.turn.outputs import NarratorOutput
from tests.graph.test_turn_context import _section, brief
from tests.graph.test_turn_graph import SCENE, play, section, turn_input

TOP = 4
VOID = "Void Refinement"
# "I sit in seclusion and reach for whatever lies above my realm."
REACH = {
    "summary": "Lin reaches for what lies above Soul Transformation.",
    "steps": [
        {
            "text": "reach past Soul Transformation in seclusion",
            "verb": "cultivate",
            "kind": "task",
            "proposed_duration_s": 12 * HOUR,
            "training": {
                "kind": "breakthrough",
                "what": "the realm above",
                "ladder_id": "realms",
                "attempt": True,
            },
        }
    ],
}
TOLD = (
    "The barrier does not give. Yet for a breath you feel it: a realm past your own, vast and "
    "still. The old texts had a name for it. Void Refinement."
)


def at_the_top():
    state = cultivation_world()
    state.player.sheet.ladders = [LadderPosition(ladder_id="realms", rung=TOP)]
    return state


def scene(narration: str = TOLD, **update) -> dict:
    return SCENE | {
        "narration": narration,
        "update": {"scene_end": SCENE["update"]["scene_end"]} | update,
    }


def rungs(state) -> list[str]:
    return [rung.name for rung in state.bible.ladder("realms").rungs]


def stopped_at_the_top(state) -> Resolution:
    ladder = state.bible.ladder("realms")
    return Resolution(
        steps=[
            StepResolution(
                index=0,
                text="reach past Soul Transformation",
                outcome_class=OutcomeClass.RULED_OUT,
                reason=growth.no_rung_above(ladder),
                result=StepResult.FAILURE,
                duration_s=2,
            )
        ]
    )


def test_a_scene_that_names_a_rung_above_the_top_widens_the_ladder(fake, make_client, log_lines):
    fake.script(Node.INTERPRET, Reply(json=REACH))
    fake.script(
        Node.NARRATOR,
        Reply(json=scene(rungs=[{"ladder_id": "realms", "name": VOID, "description": "Past it."}])),
    )

    _, result = play(make_client(), turn_input(at_the_top()))

    state = result.state
    assert rungs(state)[-2:] == ["Soul Transformation", VOID]
    assert "rejected" not in [i.code for i in result.issues]
    # The climb stopped at the top, and the narrator was told beside it that the ladder is open.
    told = json.loads(section(fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text, "OUTCOME"))
    (step,) = told["steps"]
    assert (step["class"], step["result"]) == ("ruled_out", "failure")
    assert step["why"] == "Nothing anyone knows of lies above Soul Transformation."
    assert "rung_above" in step["beyond"] and "Soul Transformation" in step["beyond"]
    # C6: heard of from this scene, and his rank now fills toward it. He still stands where
    # he stood: the rung is to climb.
    assert ("rung_heard", "realms") in [(i.code, i.subject) for i in result.issues]
    assert [p.rung for p in state.player.sheet.ladders] == [TOP]
    (shown,) = status_view(state).sheet.paths
    assert [(rung.name, rung.known) for rung in shown.above] == [(VOID, False)]
    assert shown.rungs[-1].stage  # a stage again, where the top had none
    # T6: the log holds no word of the scene, the rung's name included.
    assert not any(VOID in str(line) for line in log_lines())


def test_a_reach_filed_against_the_worlds_open_rule_is_told_the_same(fake, make_client):
    # The model that reads the player's words may file the reach as a plain step against the
    # rule that nobody is known to have passed the top: the world check stops it with the
    # rule's own words, and the narrator is still told that the ladder is open.
    filed = {
        "summary": REACH["summary"],
        "steps": [
            {
                "text": "reach past Soul Transformation in seclusion",
                "verb": "cultivate",
                "kind": "task",
                "proposed_duration_s": 12 * HOUR,
                "facts": {"against_rule_ids": ["realm-ceiling"]},
            }
        ],
    }
    fake.script(Node.INTERPRET, Reply(json=filed))
    fake.script(Node.NARRATOR, Reply(json=scene(rungs=[{"ladder_id": "realms", "name": VOID}])))

    _, result = play(make_client(), turn_input(at_the_top()))

    told = json.loads(section(fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text, "OUTCOME"))
    (step,) = told["steps"]
    assert step["why"] == "Nobody is known to have passed Soul Transformation."
    assert "rung_above" in step["beyond"]
    state = result.state
    assert rungs(state)[-1] == VOID
    # G7: the discovery broke the rule, so nothing reads it any more.
    assert "realm-ceiling" not in [rule.id for rule in state.bible.rules]
    assert (
        "Nobody is known to have passed" not in interpret_prompt(state, "I train").messages[-1].text
    )
    assert "Nobody is known to have passed" not in brief(state).user


def test_a_step_another_rule_stopped_says_nothing_of_the_ladder():
    # An open rule about something else that names the top rung is no word on how far it goes.
    state = at_the_top()
    law = next(rule for rule in state.bible.rules if rule.id == "realm-ceiling")
    stopped = stopped_at_the_top(state)
    stopped.steps[0].reason = law.text

    (step,) = _section(brief(state, resolution=stopped).user, "OUTCOME")["steps"]
    assert "beyond" in step

    law.topic = RuleTopic.LAW
    (step,) = _section(brief(state, resolution=stopped).user, "OUTCOME")["steps"]
    assert "beyond" not in step


def test_the_narrator_reads_on_the_ladder_itself_that_it_is_open():
    # Beings from above the top can come into a scene with no climb to stop beside, so WORLD
    # says it too, for the narrator alone and only where the story can pass the top.
    state = at_the_top()

    (seen,) = _section(brief(state).user, "WORLD")["ladders"]

    assert seen["above"] == (
        "Open: nobody on record stands above Soul Transformation. When beings stronger than "
        "Soul Transformation come into the story, or someone finds what lies beyond it, the "
        "scene gives the rung above a name: rung_above asks for it."
    )
    assert "rung_above" not in interpret_prompt(state, "I wait").messages[-1].text
    # Lin on the lowest realm has not been told of the top: the world's own rungs come first.
    (low,) = _section(brief(cultivation_world()).user, "WORLD")["ladders"]
    assert "above" not in low
    # G7: nor under a rule that never changes.
    next(rule for rule in state.bible.rules if rule.id == "realm-ceiling").fixed = True
    (fixed,) = _section(brief(state).user, "WORLD")["ladders"]
    assert "above" not in fixed


def test_a_rung_the_scenes_words_never_named_is_left_out():
    # What the player read is what the record holds: a rung only the update lists isn't one.
    state = at_the_top()
    delta = StateDelta(
        rungs=[
            NewRung(ladder_id="realms", name=VOID),
            NewRung(ladder_id="realms", name="Body Integration"),
        ]
    )

    checked, issues = check_update(delta, state, told=TOLD)

    assert [rung.name for rung in checked.rungs] == [VOID]
    assert [i.code for i in issues] == [RUNG_UNTOLD]
    assert len(delta.rungs) == 2  # never mutated
    # With every rung named, nothing is said.
    checked, issues = check_update(StateDelta(rungs=delta.rungs[:1]), state, told=TOLD)
    assert (len(checked.rungs), issues) == (1, [])


def test_through_a_turn_a_rung_the_scene_never_named_changes_nothing(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=REACH))
    fake.script(
        Node.NARRATOR,
        Reply(
            json=scene("The barrier does not give.", rungs=[{"ladder_id": "realms", "name": VOID}])
        ),
    )

    _, result = play(make_client(), turn_input(at_the_top()))

    assert len(rungs(result.state)) == TOP + 1
    assert RUNG_UNTOLD in [i.code for i in result.issues]


def test_a_rung_told_before_the_story_reached_the_top_is_refused(fake, make_client):
    # Lin stands on the lowest realm and has heard of nothing above it.
    fake.script(Node.INTERPRET, Reply(json=REACH))
    fake.script(Node.NARRATOR, Reply(json=scene(rungs=[{"ladder_id": "realms", "name": VOID}])))

    _, result = play(make_client(), turn_input())

    assert len(rungs(result.state)) == TOP + 1
    refused = [i for i in result.issues if i.code == "rejected"]
    assert [i.area for i in refused] == ["ladder.rung"]
    assert result.state.player.sheet.rungs_heard == []


def test_only_a_climb_stopped_at_an_open_top_tells_the_narrator_the_ladder_can_grow():
    state = at_the_top()
    stopped = stopped_at_the_top(state)

    (step,) = _section(brief(state, resolution=stopped).user, "OUTCOME")["steps"]

    # The reach finds that a rung lies there: the scene is asked to name it, not left to.
    assert step["beyond"] == (
        "How far cultivation realms goes is open: nobody on record stands above Soul "
        "Transformation, and nothing says nobody can. This step still fails, since no rung "
        "above Soul Transformation has a name yet, but the reach shows the character that one "
        "lies there. Never tell Soul Transformation as the end of the path. Answer rung_above "
        "with a name for that rung and say it in the scene. Reaching it will be a climb of its "
        "own."
    )
    # A step ruled out for anything else says nothing of it.
    other = stopped.model_copy(deep=True)
    other.steps[0].reason = "There is no such ladder to climb here."
    (step,) = _section(brief(state, resolution=other).user, "OUTCOME")["steps"]
    assert "beyond" not in step
    # Nor a step that wasn't ruled out, whatever its reason reads.
    thrown = stopped.model_copy(deep=True)
    thrown.steps[0].outcome_class = OutcomeClass.CONTESTED
    (step,) = _section(brief(state, resolution=thrown).user, "OUTCOME")["steps"]
    assert "beyond" not in step


def test_a_top_the_story_cant_pass_is_told_as_the_end_of_the_climb():
    # G7: a rule that never changes holds the ladder there, so the narrator is told nothing.
    state = at_the_top()
    next(rule for rule in state.bible.rules if rule.id == "realm-ceiling").fixed = True
    assert path.top_problem(state, state.bible.ladder("realms")) is not None

    (step,) = _section(brief(state, resolution=stopped_at_the_top(state)).user, "OUTCOME")["steps"]

    assert "beyond" not in step


def test_the_narrator_reads_a_rung_the_story_added_as_any_rung_of_the_world():
    state = at_the_top()
    ladder = state.bible.ladder("realms")
    ladder.rungs.append(ladder.rungs[-1].model_copy(update={"name": VOID, "added_s": 5}))

    told = brief(state)

    (seen,) = _section(told.user, "WORLD")["ladders"]
    assert [rung["name"] for rung in seen["rungs"]][-1] == VOID
    assert "added_s" not in told.user


# --- The form asks first (G18) ----------------------------------------------------------------

REALMS = Above(ladder_id="realms", ladder="cultivation realms", top="Soul Transformation")


def asked(fake) -> dict:
    """The form the narrator was last asked with."""
    return fake.calls(Node.NARRATOR)[-1].json_schema


def test_while_a_ladder_is_open_the_form_asks_first_what_the_scene_calls_the_rung_above(
    fake, make_client
):
    # The scene's own words have to name the rung, and the narrator writes its scene before its
    # update, so the question comes before the scene, and it is required: Gemini answers only
    # what a form requires as often as not.
    fake.script(Node.INTERPRET, Reply(json=REACH))
    fake.script(Node.NARRATOR, Reply(json=scene("The barrier does not give.")))

    play(make_client(), turn_input(at_the_top()))

    form = asked(fake)
    assert list(form["properties"])[:2] == ["rung_above", "action"]
    assert form["required"][0] == "rung_above"
    question = form["properties"]["rung_above"]
    assert question["type"] == "string"
    assert "answer before the scene" in question["description"]
    assert "cultivation realms is open above Soul Transformation" in question["description"]
    # Everything else is the narrator's own form.
    own = NarratorOutput.model_json_schema()
    assert {k: v for k, v in form["properties"].items() if k != "rung_above"} == own["properties"]
    assert form["$defs"] == own["$defs"]


def test_a_turn_in_which_no_ladder_is_open_asks_the_narrators_own_form(fake, make_client):
    # Almost every turn of almost every story: nothing is asked that can't apply.
    fake.script(Node.INTERPRET, Reply(json=REACH))
    fake.script(Node.NARRATOR, Reply(json=scene("The barrier does not give.")))

    play(make_client(), turn_input())  # Lin on the lowest realm

    assert asked(fake) == NarratorOutput.model_json_schema()
    assert "rung_above" not in asked(fake)["properties"]
    assert narrator_form(None) is None


def test_the_rung_the_scene_named_where_the_form_asked_widens_the_ladder(fake, make_client):
    # No rung is listed under the update: the answer to the form's question is the proposal.
    fake.script(Node.INTERPRET, Reply(json=REACH))
    fake.script(Node.NARRATOR, Reply(json=scene() | {"rung_above": VOID}))

    _, result = play(make_client(), turn_input(at_the_top()))

    state = result.state
    assert rungs(state)[-2:] == ["Soul Transformation", VOID]
    assert "rejected" not in [i.code for i in result.issues]
    assert ("rung_heard", "realms") in [(i.code, i.subject) for i in result.issues]
    assert [p.rung for p in state.player.sheet.ladders] == [TOP]


def test_a_realm_the_scene_names_between_dashes_widens_the_ladder(fake, make_client):
    # As the first live scene to lose its realm wrote it (2026-11-13): the dashes ran the name
    # into the words beside it, and the rung was dropped as one the scene never named.
    told = "A blinding glimpse of a higher realm—Void Refinement—shimmers beyond your grasp."
    fake.script(Node.INTERPRET, Reply(json=REACH))
    fake.script(Node.NARRATOR, Reply(json=scene(told) | {"rung_above": VOID}))

    _, result = play(make_client(), turn_input(at_the_top()))

    assert rungs(result.state)[-2:] == ["Soul Transformation", VOID]
    assert "rung_untold" not in [i.code for i in result.issues]


def test_whoever_the_scene_brings_in_stands_on_the_rung_it_named(fake, make_client):
    envoy = {"id": "envoy", "name": "Envoy Shen", "location_id": "well", "rung": VOID}
    fake.script(Node.INTERPRET, Reply(json=REACH))
    fake.script(Node.NARRATOR, Reply(json=scene(characters=[envoy]) | {"rung_above": VOID}))

    _, result = play(make_client(), turn_input(at_the_top()))

    assert "rejected" not in [i.code for i in result.issues]
    assert path.own_rung(result.state.characters["envoy"], "realms") == TOP + 1


def test_a_name_answered_that_the_scene_never_said_changes_nothing(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=REACH))
    fake.script(
        Node.NARRATOR, Reply(json=scene("The barrier does not give.") | {"rung_above": VOID})
    )

    _, result = play(make_client(), turn_input(at_the_top()))

    assert len(rungs(result.state)) == TOP + 1
    assert RUNG_UNTOLD in [i.code for i in result.issues]


def test_an_answer_no_form_asked_for_is_nothing(fake, make_client):
    # Lin on the lowest realm: the form asked nothing, so a name it gives all the same is
    # never the story reaching past the top.
    fake.script(Node.INTERPRET, Reply(json=REACH))
    fake.script(Node.NARRATOR, Reply(json=scene() | {"rung_above": VOID}))

    _, result = play(make_client(), turn_input())

    assert len(rungs(result.state)) == TOP + 1
    assert "rejected" not in [i.code for i in result.issues]


def test_only_a_name_is_read_as_the_rung_above():
    update = StateDelta()

    for answer in ("", "   ", "none", "N/A", "A realm beyond " * 5):
        assert with_rung_above(update, answer, REALMS) is update
    assert with_rung_above(update, VOID, None) is update

    proposed = with_rung_above(update, f" {VOID} ", REALMS)
    assert [(r.ladder_id, r.name, r.stands) for r in proposed.rungs] == [("realms", VOID, [])]
    assert update.rungs == []  # never mutated


def test_a_rung_the_update_lists_already_is_not_listed_twice():
    listed = StateDelta(rungs=[NewRung(ladder_id="realms", name=VOID, stands=["envoy"])])

    assert with_rung_above(listed, "void refinement", REALMS) is listed


def test_the_form_asks_about_the_ladder_a_step_stopped_at_before_any_other():
    # Two ladders open: with nothing stopped, the first; else the one the reach was for.
    state = at_the_top()
    realms = state.bible.ladder("realms")
    ranks = realms.model_copy(deep=True, update={"id": "ranks", "name": "sect ranks"})
    for rung in ranks.rungs:
        rung.name = f"Rank {rung.name}"
    state.bible.ladders.append(ranks)
    state.player.sheet.ladders.append(LadderPosition(ladder_id="ranks", rung=TOP))

    assert open_above(state).ladder_id == "realms"
    stopped = stopped_at_the_top(state)
    stopped.steps[0].reason = growth.no_rung_above(ranks)
    assert open_above(state, stopped) == Above(
        ladder_id="ranks", ladder="sect ranks", top="Rank Soul Transformation"
    )
    # Only that ladder's cue is told beside the step.
    told = brief(state, resolution=stopped)
    assert told.above.ladder_id == "ranks"
    (step,) = _section(told.user, "OUTCOME")["steps"]
    assert "sect ranks" in step["beyond"]
    # Nothing open, nothing asked.
    assert open_above(cultivation_world()) is None
    assert brief(cultivation_world()).form is None
