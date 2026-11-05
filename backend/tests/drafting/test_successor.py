"""N6: the drafter fills in the person code drew to carry a story on, and code holds the person to
the draw."""

from engine.samples import cultivation_world, grounded_world
from engine.state import PowerAxis, Prevalence
from engine.succession import Lot, Station, carry_on
from graph.drafting.assemble import PLAYER_FALLBACK_NAME
from graph.drafting.successor import SuccessorProposal, build, successor_prompt
from graph.drafting.view import character_lines


def proposal(**changes) -> SuccessorProposal:
    fields = {
        "name": "Mara Venn",
        "description": "A broad-shouldered hauler.",
        "attributes": {"strength": 9, "wits": 4},
        "skills": [{"name": "hauling", "level": "skilled"}],
        "items": [{"name": "a hooked pole"}],
        "rank": "freight hauler",
        "title": "Lady of the Docks",
        "situation": "Before dawn, an axle starts to give.",
    }
    return SuccessorProposal.model_validate(fields | changes)


def lot(**changes) -> Lot:
    return Lot.model_validate({"place_id": "naples", "age": 34, "one_in": 1} | changes)


def test_the_person_is_held_to_the_draw():
    state = grounded_world()
    noble = lot(station=Station.NOBLE, might=2, one_in=15_000)

    character, situation = build(state, noble, proposal())

    assert character.age == 34 and character.location_id == "naples"
    axes = character.sheet.axes
    assert (axes.might, axes.influence, axes.wealth) == (2, 4, 4)
    assert character.sheet.attributes.strength == 5  # the peak of a person in a grounded world
    assert character.sheet.resources.title == "Lady of the Docks"
    assert situation == "Before dawn, an axle starts to give."
    assert character.id not in state.characters


def test_common_folk_carry_no_title():
    character, _ = build(grounded_world(), lot(), proposal())
    assert character.sheet.resources.title == ""


def test_a_name_the_story_already_has_is_not_reused():
    state = grounded_world()
    character, _ = build(state, lot(), proposal(name="Luca Esposito"))
    assert character.name == PLAYER_FALLBACK_NAME


def test_a_strong_draw_stands_on_the_worlds_ladder():
    state = cultivation_world()
    [ladder] = [lad for lad in state.bible.ladders if lad.axis is PowerAxis.MIGHT]
    tier = ladder.rungs[1].tier

    character, _ = build(state, lot(place_id="well", might=tier, master=True), proposal())

    [position] = character.sheet.ladders
    assert (position.ladder_id, position.rung) == (ladder.id, 1)
    assert character.sheet.axes.might == tier


def test_the_prompt_carries_the_draw_and_the_names_taken():
    state = grounded_world()
    prompt = successor_prompt(state, lot(station=Station.ROYAL, master=True, might=4))

    assert "ruling family, but not its ruler" in prompt
    assert "hidden master" in prompt and "Age: 34." in prompt
    assert "Naples" in prompt and "Luca Esposito" in prompt


def test_the_player_reads_the_newcomer_in_the_worlds_words():
    state = grounded_world()
    character, situation = build(state, lot(), proposal())

    lines = character_lines(carry_on(state, character, situation, ending="death", turn=0))

    assert lines[0] == "Mara Venn, 34."
    assert "Skilled: hauling." in lines
    # The old player character's goals are theirs alone.
    assert not any(line.startswith("Goal:") for line in lines)


def test_the_world_decides_whether_a_strong_body_is_possible():
    state = cultivation_world()
    for kind in state.bible.extraordinary:
        kind.prevalence = Prevalence.COMMON
    strong, _ = build(state, lot(place_id="well", might=6, master=True), proposal())
    ordinary, _ = build(state, lot(place_id="well"), proposal())
    assert strong.sheet.attributes.strength == 9
    assert ordinary.sheet.attributes.strength == 5
