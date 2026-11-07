"""Hurt bodies come only from the record (N6, A8, `engine.injuries`).

On 2026-11-07 Miki's character, unhurt from the first scene to the last, "reopened an old wound"
and fought on with broken ribs in a small fight. Nothing the engine settled had hurt them: the
words came from the models. These hold the three ways that can happen shut: the narrator's
update hurting the player character, an edge or hindrance leaning on an injury nobody has, and a
healed wound left in the record to be reopened.
"""

import pytest

from engine.apply import DeltaSource, apply_delta
from engine.context import TurnContext
from engine.contracts import CharacterChange, IntentStep, StateDelta
from engine.contracts.delta import ConditionChange
from engine.contracts.intent import ActionKind, StepFacts
from engine.injuries import is_hurt, names_injury, unrecorded_harm
from engine.samples import grounded_world
from engine.state import WorldState
from engine.state.sheet import Condition, Health, PassingState, Trait, TraitKind, Wound

ENGINE = DeltaSource.ENGINE
NARRATOR = DeltaSource.NARRATOR


def harm(state: WorldState, who: str, source: DeltaSource, **condition):
    change = CharacterChange(id=who, condition=ConditionChange(**condition))
    return apply_delta(
        state, StateDelta(characters=[change]), TurnContext(story_id="s1", turn=3), source=source
    )


def step(*, hindrances=(), edges=(), targets=(), opposition=()) -> IntentStep:
    return IntentStep(
        text="punch him",
        verb="attack",
        kind=ActionKind.EXCHANGE,
        proposed_duration_s=3,
        target_ids=list(targets),
        facts=StepFacts(
            hindrances=list(hindrances), edges=list(edges), opposition_ids=list(opposition)
        ),
    )


# --- Spotting an injury in a model's words, in each story language (S10) ---


@pytest.mark.parametrize(
    "text",
    [
        "the old wound in your side reopening",
        "your broken ribs",
        "a twisted ankle",
        "his injured shoulder",
        "pain in your chest",
        "the fever still on you",
        "you are limping",
        "las costillas rotas",
        "una herida antigua que se reabre",
        "el dolor del costado",
        "el tobillo torcido",
        "la ferida del costat",
        "la cama trencada",
        "una lesión en la rodilla",
        "la lesio al genoll",
    ],
)
def test_words_that_speak_of_an_injury_are_spotted(text):
    assert names_injury(text)


@pytest.mark.parametrize(
    "text",
    [
        "slippery cobbles",
        "a broken lock",
        "the swollen river",
        "a treasure chest broken open",
        "twenty feet of broken ground",
        "three of them, and they know the alley",
        "de pie sobre la roca rota",
        "la puerta rota",
        "el riu crescut",
        "his hot temper",
        "the dark",
        "",
    ],
)
def test_words_about_the_situation_are_not_an_injury(text):
    assert not names_injury(text)


# --- Edges and hindrances (A8, N6) ---


def test_a_hindrance_about_an_injury_the_character_never_had_is_left_out():
    state = grounded_world()
    facts, dropped = unrecorded_harm(
        state,
        state.player,
        step(hindrances=["the old wound in your ribs reopening", "slick cobbles"]),
    )
    assert facts.hindrances == ["slick cobbles"]
    assert dropped == 1


def test_a_hindrance_about_a_real_wound_is_left_out_because_code_weighs_it():
    # A8: a wounded character's odds already carry "your wounds", so the hindrance would count
    # them twice, and its words may not be the record's.
    state = grounded_world()
    state.player.sheet.condition = Condition(
        health=Health.WOUNDED, wounds=[Wound(text="a wound from Carmine's knife")]
    )
    facts, dropped = unrecorded_harm(state, state.player, step(hindrances=["your cracked ribs"]))
    assert facts.hindrances == [] and dropped == 1


def test_a_hindrance_naming_a_flaw_or_a_passing_state_on_the_sheet_stands():
    state = grounded_world()
    sheet = state.player.sheet
    sheet.traits.append(Trait(name="bad knee", kind=TraitKind.FLAW))
    sheet.condition.states.append(PassingState(name="fever"))
    hindrances = ["your bad knee aching on the stairs", "the fever still on you"]
    facts, dropped = unrecorded_harm(state, state.player, step(hindrances=hindrances))
    assert facts.hindrances == hindrances and dropped == 0


def test_a_hindrance_stands_for_a_wound_that_lasts():
    # No odds weigh a lost eye, so a hindrance may.
    state = grounded_world()
    state.player.sheet.condition.wounds = [Wound(text="a lost eye", lasting=True)]
    facts, dropped = unrecorded_harm(
        state, state.player, step(hindrances=["your blind left eye, an old injury"])
    )
    assert dropped == 0 and len(facts.hindrances) == 1


def test_an_edge_about_a_foes_wound_stands_only_when_the_foe_is_hurt():
    state = grounded_world()
    edges = ["Carmine is already wounded", "the bar is dark"]
    facts, dropped = unrecorded_harm(state, state.player, step(edges=edges, targets=["carmine"]))
    assert facts.edges == ["the bar is dark"] and dropped == 1

    state.characters["carmine"].sheet.condition = Condition(
        health=Health.HURT, wounds=[Wound(text="a cut on the arm")]
    )
    facts, dropped = unrecorded_harm(state, state.player, step(edges=edges, opposition=["carmine"]))
    assert facts.edges == edges and dropped == 0


def test_a_step_with_nothing_to_leave_out_keeps_its_facts_as_they_are():
    state = grounded_world()
    original = step(hindrances=["two of them"], edges=["surprise"])
    facts, dropped = unrecorded_harm(state, state.player, original)
    assert facts is original.facts and dropped == 0


# --- The narrator's update never hurts the player character (N6) ---


def test_the_narrator_cannot_wound_the_player_character():
    state = grounded_world()
    applied = harm(
        state,
        "luca",
        NARRATOR,
        health=Health.HURT,
        wounds=["broken ribs"],
        states=["bruised ribs", "drunk"],
    )
    condition = applied.state.player.sheet.condition
    assert condition.health is Health.UNHURT
    assert condition.wounds == []
    assert [s.name for s in condition.states] == ["drunk"]  # a passing state that isn't harm
    assert sorted(r.change for r in applied.rejected) == ["harm", "injury", "wound"]
    assert not is_hurt(applied.state.player)


def test_the_narrator_can_show_the_player_character_heal():
    state = grounded_world()
    state.player.sheet.condition = Condition(
        health=Health.WOUNDED,
        wounds=[Wound(text="a wound from Carmine's knife"), Wound(text="a lost eye", lasting=True)],
    )
    applied = harm(state, "luca", NARRATOR, health=Health.HURT)
    assert not applied.rejected
    assert applied.state.player.sheet.condition.health is Health.HURT
    assert len(applied.state.player.sheet.condition.wounds) == 2

    healed = harm(applied.state, "luca", NARRATOR, health=Health.UNHURT)
    condition = healed.state.player.sheet.condition
    assert condition.health is Health.UNHURT
    # Healed wounds are gone, so none is there to "reopen"; a lost eye stays lost.
    assert condition.wounds == [Wound(text="a lost eye", lasting=True)]


def test_the_engine_still_wounds_the_player_character():
    state = grounded_world()
    applied = harm(state, "luca", ENGINE, health=Health.WOUNDED, wounds=["a wound from Carmine"])
    condition = applied.state.player.sheet.condition
    assert not applied.rejected
    assert condition.health is Health.WOUNDED
    assert [w.text for w in condition.wounds] == ["a wound from Carmine"]


def test_the_narrator_can_still_show_others_hurt():
    # An event or someone else's fight can hurt the people around the player character.
    state = grounded_world()
    applied = harm(state, "carmine", NARRATOR, health=Health.HURT, wounds=["a split lip"])
    assert not applied.rejected
    assert applied.state.characters["carmine"].sheet.condition.health is Health.HURT


# --- A healed wound never lingers in the record ---


def test_a_state_saved_with_a_healed_wound_still_listed_loads_without_it():
    data = grounded_world().model_dump(mode="json")
    data["characters"]["luca"]["sheet"]["condition"] = {
        "health": "unhurt",
        "wounds": [{"text": "a wound from a fall"}, {"text": "a lost hand", "lasting": True}],
    }
    loaded = WorldState.model_validate(data)
    assert [w.text for w in loaded.player.sheet.condition.wounds] == ["a lost hand"]


def test_a_hurt_body_keeps_its_wounds_when_loaded():
    condition = Condition(health=Health.HURT, wounds=[Wound(text="a cut")])
    assert Condition.model_validate(condition.model_dump()).wounds == [Wound(text="a cut")]
