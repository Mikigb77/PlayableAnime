"""N6: the drafter fills in the person code drew to carry a story on, and code holds the person to
the draw."""

from engine.samples import cultivation_world, grounded_world
from engine.state import (
    Attitude,
    Character,
    CharacterStatus,
    DeathCertainty,
    Health,
    Item,
    Origin,
    OriginKind,
    PowerAxis,
    Prevalence,
    Skill,
    SkillLevel,
    Trait,
    Wound,
)
from engine.succession import Lot, Station, carry_on
from graph.drafting.assemble import PLAYER_FALLBACK_NAME
from graph.drafting.successor import (
    SuccessorProposal,
    build,
    build_heir,
    heir_prompt,
    successor_prompt,
)
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


def test_a_second_nameless_newcomer_gets_a_name_of_their_own():
    state = grounded_world()
    first, _ = build(state, lot(), proposal(name="Luca Esposito"))
    state.characters[first.id] = first

    second, _ = build(state, lot(), proposal(name="Luca Esposito"))

    assert second.name == f"{PLAYER_FALLBACK_NAME} 2"


def test_only_a_hidden_master_goes_past_a_persons_peak():
    state = cultivation_world()
    for kind in state.bible.extraordinary:
        kind.prevalence = Prevalence.COMMON
    tough, _ = build(state, lot(place_id="well", might=2), proposal())
    assert tough.sheet.attributes.strength == 5


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


# --- Heirs ------------------------------------------------------------------------------------


def heir_world():
    """Luca, a capo with a title, dead; his newborn son grown up off-screen, still unnamed, and
    his daughter Rosa, drafted with skills of her own."""
    state = grounded_world()
    luca = state.player
    luca.sheet.resources.title = "Don of the Quartieri"
    luca.sheet.axes.influence, luca.sheet.axes.wealth = 3, 4
    luca.status, luca.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED
    state.characters["npc-1"] = Character(
        id="npc-1",
        name="Luca Esposito's child",
        age=16,
        location_id="bar",
        parent_ids=["luca"],
        description="A newborn, the child of Luca Esposito.",
        origin=Origin(kind=OriginKind.BIRTH, ref_id="event-1"),
    )
    state.characters["npc-1"].sheet.disposition.attitudes["carmine"] = Attitude(affinity=-40)
    rosa = Character(
        id="rosa", name="Rosa", age=30, location_id="bar", parent_ids=["luca"], appearance="Dark."
    )
    rosa.sheet.skills = [Skill(name="bookkeeping", level=SkillLevel.SKILLED)]
    state.characters["rosa"] = rosa
    return state


def test_an_heir_who_grew_up_off_screen_is_who_the_drafter_says_held_to_their_family():
    state = heir_world()

    heir, situation = build_heir(
        state, state.characters["npc-1"], proposal(attributes={"strength": 9}), grown=True
    )

    assert (heir.id, heir.name, heir.age, heir.parent_ids) == ("npc-1", "Mara Venn", 16, ["luca"])
    assert heir.location_id == "bar" and heir.prominence.value == "key"
    assert heir.description == "A broad-shouldered hauler."
    sheet = heir.sheet
    assert sheet.attributes.strength == 5  # a person, however strong their parent was
    assert (sheet.axes.might, sheet.axes.influence, sheet.axes.wealth) == (1, 3, 4)
    assert sheet.resources.title == "Lady of the Docks"  # a titled family
    assert [s.name for s in sheet.skills] == ["hauling"]
    # What the world already held of them stays theirs.
    assert sheet.disposition.attitudes["carmine"].affinity == -40
    assert situation == "Before dawn, an axle starts to give."
    assert state.characters["npc-1"].name == "Luca Esposito's child"  # the state is untouched


def test_an_heir_the_story_already_has_keeps_their_name_and_sheet():
    state = heir_world()

    heir, _ = build_heir(state, state.characters["rosa"], proposal(name="Mara Venn"), grown=False)

    assert heir.name == "Rosa" and heir.appearance == "Dark."
    assert heir.description == "A broad-shouldered hauler."  # she had none
    assert [s.name for s in heir.sheet.skills] == ["bookkeeping"]


def test_an_heir_drafted_anew_keeps_what_the_world_holds_of_them():
    """A son the story never filled in, wounded at the ending, with his father's ring."""
    state = heir_world()
    tonio = Character(id="tonio", name="Tonio", age=20, location_id="bar", parent_ids=["luca"])
    condition = tonio.sheet.condition
    condition.health = Health.BADLY_WOUNDED
    condition.wounds = [Wound(text="a knife in the side"), Wound(text="a lost eye", lasting=True)]
    tonio.sheet.resources.items = [Item(id="a-hooked-pole", name="His father's ring")]
    tonio.sheet.resources.money = 30
    tonio.sheet.traits = [Trait(name="Stubborn")]
    state.characters["tonio"] = tonio

    heir, _ = build_heir(state, tonio, proposal(traits=[{"name": "Patient"}]), grown=False)

    sheet = heir.sheet
    assert [s.name for s in sheet.skills] == ["hauling"]  # filled in
    assert sheet.condition.health is Health.BADLY_WOUNDED and len(sheet.condition.wounds) == 2
    assert [i.name for i in sheet.resources.items] == ["His father's ring", "a hooked pole"]
    assert len({i.id for i in sheet.resources.items}) == 2
    assert sheet.resources.money == 30
    assert [t.name for t in sheet.traits] == ["Stubborn", "Patient"]

    # Grown up years later: only the lasting wound is left.
    grown, _ = build_heir(state, tonio, proposal(), grown=True)
    assert grown.sheet.condition.health is Health.UNHURT
    assert [w.text for w in grown.sheet.condition.wounds] == ["a lost eye"]
    assert "His father's ring" in [i.name for i in grown.sheet.resources.items]


def test_the_heir_prompt_names_how_far_down_the_family_they_are():
    state = heir_world()
    state.characters["mia"] = Character(id="mia", name="Mia", age=8, parent_ids=["rosa"])
    state.characters["ugo"] = Character(id="ugo", name="Ugo", age=0, parent_ids=["mia"])

    assert "Grandchild of Luca Esposito" in heir_prompt(state, state.characters["mia"], years=8)
    great = heir_prompt(state, state.characters["ugo"], years=16)
    assert "Great-grandchild of Luca Esposito" in great and "Grandchild of" not in great


def test_the_heir_prompt_names_their_family_and_the_years_since():
    state = heir_world()

    prompt = heir_prompt(state, state.characters["npc-1"], years=17)

    assert "THE HEIR" in prompt and "Name: none yet; give them one." in prompt
    assert "Parent: Luca Esposito (the last player character, now dead), Don of the" in prompt
    assert "They grew up in the 17 years since the last story ended." in prompt
    assert "Lives in: " in prompt
    rosa = heir_prompt(state, state.characters["rosa"], years=0)
    assert "Name: Rosa." in rosa and "grew up" not in rosa
