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
from engine.contracts.resolution import Cost, Resolution, StepResolution
from engine.injuries import is_hurt, names_injury, pays_in_body, unrecorded_harm
from engine.samples import grounded_world
from engine.state import StepResult, WorldState
from engine.state.sheet import (
    Condition,
    CostKind,
    Health,
    PassingState,
    Trait,
    TraitKind,
    Wound,
)

ENGINE = DeltaSource.ENGINE
NARRATOR = DeltaSource.NARRATOR


def harm(state: WorldState, who: str, source: DeltaSource, *, may_hurt_player=False, **condition):
    change = CharacterChange(id=who, condition=ConditionChange(**condition))
    return apply_delta(
        state,
        StateDelta(characters=[change]),
        TurnContext(story_id="s1", turn=3),
        source=source,
        may_hurt_player=may_hurt_player,
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


def hurt(state: WorldState, who: str, health: Health, *wounds: str) -> None:
    state.characters[who].sheet.condition = Condition(
        health=health, wounds=[Wound(text=w) for w in wounds]
    )


# --- Spotting an injury in a model's words, in each story language (S10) ---


@pytest.mark.parametrize(
    "text",
    [
        "the old wound in your side reopening",
        "your broken ribs",
        "your broken left arm",
        "a twisted ankle",
        "his injured shoulder",
        "pain in your chest",
        "you're still hurt from the fight",
        "the fever still on you",
        "you are limping",
        "las costillas rotas",
        "la rodilla derecha rota",
        "una herida antigua que se reabre",
        "el dolor del costado",
        "el tobillo torcido",
        "la ferida del costat",
        "el turmell inflat",
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
        "the broken lock in his hand",
        "keeps an eye on the burned bridge",
        "the arms cache was burned",
        "the swollen river",
        "a treasure chest broken open",
        "twenty feet of broken ground",
        "three of them, and they know the alley",
        "the guard is sick of waiting",
        "a limp rope",
        "rotate the wheel by hand",
        "the hurt pride of the captain",
        "de pie sobre la roca rota",
        "la cama rota",
        "la puerta rota",
        "Ha dit que la porta està trencada",
        "el riu crescut",
        "his hot temper",
        "the dark",
        "",
    ],
)
def test_words_about_the_situation_are_not_an_injury(text):
    assert not names_injury(text)


# --- Hindrances: the actor's own body (A8, N6) ---


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
    hurt(state, "luca", Health.WOUNDED, "a wound from Carmine's knife")
    facts, dropped = unrecorded_harm(state, state.player, step(hindrances=["your cracked ribs"]))
    assert facts.hindrances == [] and dropped == 1


def test_a_hindrance_naming_a_flaw_or_a_passing_state_on_the_sheet_stands():
    state = grounded_world()
    sheet = state.player.sheet
    sheet.traits.append(Trait(name="bad knee", kind=TraitKind.FLAW))
    sheet.condition.states.append(PassingState(name="fever"))
    hindrances = ["your aching knee on the stairs", "the fever still on you"]
    facts, dropped = unrecorded_harm(state, state.player, step(hindrances=hindrances))
    assert facts.hindrances == hindrances and dropped == 0


def test_a_hindrance_stands_for_a_wound_that_lasts_but_only_for_that_part():
    # No odds weigh a lost eye, so a hindrance may; it reopens nothing else.
    state = grounded_world()
    state.player.sheet.condition.wounds = [
        Wound(text="a maiming wound from the bandit", lasting=True)
    ]
    state.player.appearance = "24, lean, dark hair, a scar where his left eye was."
    facts, dropped = unrecorded_harm(
        state,
        state.player,
        step(hindrances=["your missing left eye", "the old wound in your ribs reopening"]),
    )
    assert facts.hindrances == ["your missing left eye"] and dropped == 1


# --- About someone else: they must be hurt on the record ---


def test_an_edge_about_a_foes_wound_stands_only_when_the_foe_is_hurt():
    state = grounded_world()
    edges = ["Carmine is already wounded", "the bar is dark"]
    facts, dropped = unrecorded_harm(state, state.player, step(edges=edges, targets=["carmine"]))
    assert [e.text for e in facts.edges] == ["the bar is dark"] and dropped == 1

    hurt(state, "carmine", Health.HURT, "a cut on the arm")
    facts, dropped = unrecorded_harm(state, state.player, step(edges=edges, targets=["carmine"]))
    assert [e.text for e in facts.edges] == edges and dropped == 0


def test_an_edge_must_name_someone_hurt_and_never_a_part_the_record_says_is_whole():
    state = grounded_world()
    hurt(state, "carmine", Health.HURT, "a cut on the arm")
    edges = ["Gennaro's shattered knee", "Carmine's broken ribs", "Carmine's bleeding arm"]
    facts, dropped = unrecorded_harm(
        state, state.player, step(edges=edges, targets=["carmine", "bartender"])
    )
    # Gennaro is unhurt, and Carmine's wound is on his arm, not his ribs.
    assert [e.text for e in facts.edges] == ["Carmine's bleeding arm"] and dropped == 2


def test_a_hindrance_about_an_allys_recorded_wound_stands():
    state = grounded_world()
    hindrance = "carrying Gennaro, whose leg is broken, slows you"
    facts, dropped = unrecorded_harm(state, state.player, step(hindrances=[hindrance]))
    assert dropped == 1  # Gennaro is unhurt on the record

    hurt(state, "bartender", Health.BADLY_WOUNDED, "a bullet through the leg")
    facts, dropped = unrecorded_harm(state, state.player, step(hindrances=[hindrance]))
    assert facts.hindrances == [hindrance] and dropped == 0


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


def test_the_narrator_records_harm_something_recorded_this_turn_caused():
    # A power's toll in health or blood, or the first opening's premise (`may_hurt_player`).
    state = grounded_world()
    applied = harm(
        state,
        "luca",
        NARRATOR,
        may_hurt_player=True,
        health=Health.HURT,
        wounds=["veins burned black by the spell"],
    )
    assert not applied.rejected
    condition = applied.state.player.sheet.condition
    assert condition.health is Health.HURT
    assert [w.text for w in condition.wounds] == ["veins burned black by the spell"]


def test_a_toll_in_health_or_blood_is_paid_in_the_body():
    def toll(kind: CostKind, *, interrupted=False) -> Resolution:
        played = StepResolution(
            index=0,
            text="burn the bridge with my blood",
            outcome_class="certain",
            reason="",
            result=StepResult.SUCCESS,
            duration_s=2,
            costs=[Cost(kind=kind, text="a cut across the palm")],
            interrupted=interrupted,
        )
        return Resolution(steps=[played])

    assert pays_in_body(toll(CostKind.BLOOD))
    assert pays_in_body(toll(CostKind.HEALTH))
    assert not pays_in_body(toll(CostKind.FATIGUE))
    assert not pays_in_body(toll(CostKind.BLOOD, interrupted=True))  # it never happened
    assert not pays_in_body(Resolution())


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


def test_the_narrator_can_still_show_others_hurt_and_the_wound_outlives_a_reload():
    # An event or someone else's fight can hurt the people around the player character. A wound
    # leaves an unhurt body hurt, so it is still there when the state loads next turn.
    state = grounded_world()
    applied = harm(state, "carmine", NARRATOR, wounds=["a split lip"])
    assert not applied.rejected
    carmine = applied.state.characters["carmine"].sheet.condition
    assert carmine.health is Health.HURT
    loaded = WorldState.model_validate(applied.state.model_dump(mode="json"))
    assert [w.text for w in loaded.characters["carmine"].sheet.condition.wounds] == ["a split lip"]


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


def test_health_knows_worse_from_better():
    assert Health.WOUNDED.worse_than(Health.HURT)
    assert not Health.HURT.worse_than(Health.HURT)
    assert not Health.UNHURT.worse_than(Health.DYING)
