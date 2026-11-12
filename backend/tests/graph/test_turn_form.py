"""The form the interpret step fills for one turn: only what can apply to it (B5)."""

import itertools
import json
from dataclasses import fields, replace

import pytest

from engine.contracts import Intent
from engine.samples import cultivation_world, farm_world, grounded_world
from engine.state.records import Goal, GoalStatus, Lead, LeadStatus
from engine.state.sheet import Talent, TalentStrength
from graph.llm.fake import fill_schema
from graph.llm.gemini import gemini_schema
from graph.turn import prompts
from graph.turn.context import asks, interpret_prompt
from graph.turn.form import WHOLE, Asks, intent_form, left_out

EVERY = [
    Asks(**dict(zip((f.name for f in fields(Asks)), flags, strict=True)))
    for flags in itertools.product((False, True), repeat=len(fields(Asks)))
]


def _fields(form: dict, model: str) -> set[str]:
    where = form if model == "Intent" else form["$defs"][model]
    return set(where["properties"])


def test_a_plain_turn_is_asked_nothing_that_cannot_apply():
    form = intent_form(Asks())
    step = _fields(form, "IntentStep")
    # W10a: nothing about stopped time.
    assert not step & {"contact", "mass_kg", "range_m", "full_force", "proposed_personal_s"}
    assert "grants" not in _fields(form, "Training")
    assert not _fields(form, "PowerTheory") & {"about", "claims_hit_mode"}
    # G18, G20: no ladder to climb, and no strength on one to hide.
    assert "show_strength" not in step
    assert "ladder_id" not in _fields(form, "Training")
    assert "breakthrough" not in form["$defs"]["GrowthKind"]["enum"]
    # A4: no talent to rule on.
    assert not step & {"talent_cases", "bridge"}
    # N2, W16: no goal to give up, and nothing open to take up.
    assert not _fields(form, "Intent") & {"dropped_goals", "responds_to"}
    # What is left is what every turn is asked.
    assert {"text", "verb", "target_ids", "aim", "uses", "beats", "facts", "kind"} <= step
    assert {"destination", "proposed_duration_s", "until", "timed", "training"} <= step
    assert len(step) == 21
    # Nothing is required that isn't asked, and no definition is kept that nothing uses.
    assert set(form["$defs"]["IntentStep"]["required"]) <= step
    gone = {"Contact", "PowerGrant", "TheoryAbout", "HitMode", "ShowStrength", "TalentCase"}
    assert not gone & set(form["$defs"])
    assert "Bridge" not in form["$defs"] and "TalentFit" not in form["$defs"]


def test_no_form_asks_who_acts_or_for_a_strangers_crowd():
    for asked in EVERY:
        form = intent_form(asked)
        # A6: the player plays only their own character, and code sets the actor.
        assert "actor_id" not in _fields(form, "Intent")
        # W2: the step's own facts say whether a crowd is around.
        assert "crowd" not in _fields(form, "Stranger")
        assert "crowd" in _fields(form, "StepFacts")


def test_the_whole_form_is_the_contract_but_for_what_no_turn_is_asked():
    form = intent_form(WHOLE)
    contract = Intent.model_json_schema()
    assert _fields(form, "Intent") == set(contract["properties"]) - {"actor_id"}
    for model, definition in contract["$defs"].items():
        if "properties" not in definition:
            continue
        never = {"crowd"} if model == "Stranger" else set()
        assert _fields(form, model) == set(definition["properties"]) - never
    assert form["$defs"]["IntentStep"]["required"] == contract["$defs"]["IntentStep"]["required"]


@pytest.mark.parametrize("asked", EVERY, ids=str)
def test_every_form_is_whole_and_reads_as_an_intent(asked):
    form = intent_form(asked)
    text = json.dumps(form)
    # Every definition a form points at is in it, and Gemini's part of the schema still is one.
    for name in {ref.rsplit("/", 1)[-1] for ref in _refs(form)}:
        assert name in form["$defs"], name
    assert json.dumps(gemini_schema(form))
    for model, names in left_out(asked).items():
        assert not _fields(form, model) & set(names)
    # An answer to the form is an `Intent`, with the contract's defaults for what wasn't asked.
    intent = Intent.model_validate(fill_schema(form))
    assert intent.actor_id is None
    if not asked.time:
        assert all(step.proposed_personal_s is None for step in intent.steps)
    if not asked.talents:
        assert all(step.talent_cases == [] and step.bridge is None for step in intent.steps)
    if not asked.ladders:
        assert all(step.show_strength is None for step in intent.steps)
    # The form handed out is the caller's own copy.
    form["properties"].clear()
    assert json.dumps(intent_form(asked)) == text


def _refs(node) -> list[str]:
    if isinstance(node, dict):
        found = [node["$ref"]] if isinstance(node.get("$ref"), str) else []
        return found + [ref for value in node.values() for ref in _refs(value)]
    if isinstance(node, list):
        return [ref for value in node for ref in _refs(value)]
    return []


# What the guide says about a field only some turns are asked, by what has to hold.
TOLD = {
    "time": ["proposed_personal_s", "- contact:", "mass_kg", "full_force", "hit_force", "grants"],
    "ladders": ["show_strength", "breakthrough", "ladder_id"],
    "talents": ["- TALENTS", "talent_cases", "- bridge, always"],
    "goals": ["dropped_goals"],
    "threads": ["responds_to"],
}


def test_the_guide_explains_only_what_the_form_holds():
    plain = prompts.interpret_system(Asks())
    assert "<<" not in plain and "<<" not in prompts.INTERPRET_SYSTEM
    for needs, said in TOLD.items():
        with_it = prompts.interpret_system(replace(Asks(), **{needs: True}))
        for words in said:
            assert words not in plain, words
            assert words in with_it, words
            assert words in prompts.INTERPRET_SYSTEM, words
        # Only its own part is added.
        others = [w for other, told in TOLD.items() if other != needs for w in told]
        assert not [words for words in others if words in with_it]
    # Training is still explained to a turn with no ladder, without the rung to break through to.
    assert "studying a manual). kind skill, technique or power (a new way" in plain
    assert "or breakthrough (the next rung of a ladder" in prompts.INTERPRET_SYSTEM
    assert prompts.interpret_system(WHOLE) == prompts.INTERPRET_SYSTEM
    assert len(plain) < 0.85 * len(prompts.INTERPRET_SYSTEM)


def test_what_a_turn_is_asked_is_read_from_the_state():
    # A cultivation story: a time stop on the sheet, the sect's realms, a tournament to answer.
    lin = cultivation_world()
    assert asks(lin) == Asks(time=True, ladders=True, talents=False, goals=False, threads=True)
    # A4: a talent that covers everything needs no ruling; one that reaches some things does.
    lin.player.sheet.talents = [
        Talent(id="gift", name="Gifted", strength=TalentStrength.GENIUS, general=True)
    ]
    assert not asks(lin).talents
    lin.player.sheet.talents = [
        Talent(id="sword", name="Sword heart", covers="the sword", strength=TalentStrength.GENIUS)
    ]
    assert asks(lin).talents
    # N2: only a goal still active can be given up.
    lin.goals["goal-1"] = Goal(id="goal-1", text="Win the outer tournament.")
    assert asks(lin).goals
    lin.goals["goal-1"].status = GoalStatus.ACHIEVED
    assert not asks(lin).goals
    # W10a: without the power, only a stop still at work asks about time.
    stop = next(power for power in lin.player.sheet.powers if power.time is not None)
    lin.player.sheet.powers.remove(stop)
    assert not asks(lin).time

    # A grounded story has no ladder, and its hero no power over time.
    luca = grounded_world()
    asked = asks(luca)
    assert not asked.time and not asked.ladders and not asked.talents
    # W16, N1: a lead on offer is something to take up, like a thread they know of.
    farm = farm_world()
    farm.threads.clear()
    farm.leads.clear()
    assert not asks(farm).threads
    farm.leads["lead-1"] = Lead(id="lead-1", text="A stranger asks after the old mill.")
    assert asks(farm).threads
    farm.leads["lead-1"].status = LeadStatus.TAKEN
    assert not asks(farm).threads


def test_the_interpret_prompt_explains_only_what_its_turn_is_asked():
    luca = grounded_world()
    prompt = interpret_prompt(luca, "I order a coffee")
    assert prompt.system == prompts.interpret_system(asks(luca))
    assert "show_strength" not in prompt.system and "proposed_personal_s" not in prompt.system
    # A caller that already worked it out hands it in, so the form and the guide can't differ.
    assert interpret_prompt(luca, "I order a coffee", asked=WHOLE).system == (
        prompts.INTERPRET_SYSTEM
    )
