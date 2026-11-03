"""check_transition: C1 between any two states, however the second was made."""

import pytest

from engine.invariants import InvariantError, assert_valid_transition, check_state, check_transition
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    Cause,
    CauseMechanism,
    CauseRef,
    CharacterStatus,
    DeathCertainty,
    Deed,
    FactionStatus,
    LadderPosition,
    Membership,
    PlaceStatus,
    Ruling,
    RulingSource,
    StatusChange,
    WorldRule,
    WorldState,
)


def rules_hit(violations) -> list[str]:
    return [v.rule for v in violations]


def copy(state: WorldState) -> WorldState:
    return state.model_copy(deep=True)


@pytest.mark.parametrize("make", [grounded_world, cultivation_world])
def test_the_sample_worlds_hold_every_invariant(make):
    state = make()

    assert check_state(state) == []
    assert check_transition(state, copy(state)) == []


def test_check_state_finds_bounds_names_and_dangling_references():
    state = grounded_world()
    # Engine code mutates copies without validation, so bounds are checked again.
    state.characters["carmine"].sheet.disposition.attitudes["luca"].affinity = 500
    state.characters["bartender"].name = "Unknown"
    state.characters["bartender"].location_id = "moon"
    state.characters["bartender"].memberships.append(Membership(faction_id="ghosts"))
    state.player.sheet.ladders.append(LadderPosition(ladder_id="realms", rung=0))
    state.factions["police"].parent_id = "nobody"
    state.places["bar"].parent_id = "nowhere"

    found = check_state(state)

    assert rules_hit(found).count("bounds") == 1
    assert "named" in rules_hit(found)
    assert rules_hit(found).count("reference") == 5


def test_records_are_never_deleted_and_time_never_runs_backwards():
    before = grounded_world()
    before.world_s = 100
    after = copy(before)
    del after.characters["bartender"]
    del after.places["questura"]
    after.world_s = 50

    found = check_transition(before, after)

    assert [v.subject for v in found if v.rule == "C1"] == [
        "characters bartender",
        "places questura",
    ]
    assert "W10" in rules_hit(found)


def test_only_a_rewind_changes_the_timeline():
    before = grounded_world()
    after = copy(before)
    after.timeline_id = "rewound"

    assert rules_hit(check_transition(before, after)) == ["W10a"]


def dead(state: WorldState, cid: str, certainty=DeathCertainty.CONFIRMED) -> WorldState:
    state = copy(state)
    character = state.characters[cid]
    character.status = CharacterStatus.DEAD
    character.death_certainty = certainty
    character.status_history.append(StatusChange(status="dead", turn=1, world_s=state.world_s))
    return state


def test_a_death_undone_without_a_recorded_cause_is_caught():
    before = dead(grounded_world(), "carmine")
    after = copy(before)
    after.characters["carmine"].status = CharacterStatus.ALIVE
    after.characters["carmine"].death_certainty = None

    found = check_transition(before, after)

    assert [(v.subject, v.detail) for v in found] == [
        ("character carmine", "left death with no recorded cause")
    ]


def test_a_death_undone_by_a_real_cause_passes_where_the_world_allows_it():
    world = cultivation_world()
    world.bible.medicine.resurrection = world.bible.medicine.resurrection.POSSIBLE
    before = dead(world, "zhao")
    after = copy(before)
    after.deeds["rite"] = Deed(
        id="rite",
        actor_id="lin",
        kind="revive",
        text="A rite",
        turn=2,
        world_s=0,
        target_ids=["zhao"],
    )
    zhao = after.characters["zhao"]
    zhao.status = CharacterStatus.ALIVE
    zhao.death_certainty = None
    rite = Cause(
        mechanism=CauseMechanism.RESURRECTION, ref_kind=CauseRef.DEED, ref_id="rite", text=""
    )
    zhao.status_history.append(StatusChange(status="alive", turn=2, world_s=0, cause=rite))

    assert check_transition(before, after) == []
    # The same cause in a world without resurrection is caught.
    grounded_after = copy(after)
    grounded_after.bible.medicine.resurrection = grounded_after.bible.medicine.resurrection.NONE
    assert rules_hit(check_transition(before, grounded_after)) == ["C1"]


def test_a_confirmed_death_never_becomes_presumed():
    before = dead(grounded_world(), "carmine")
    after = copy(before)
    after.characters["carmine"].death_certainty = DeathCertainty.PRESUMED

    found = check_transition(before, after)

    assert [v.detail for v in found] == ["a confirmed death never becomes presumed"]


def test_destroyed_factions_and_ruined_places_stay_that_way_without_a_cause():
    before = grounded_world()
    before.factions["carmine-crew"].status = FactionStatus.DESTROYED
    before.places["bar"].status = PlaceStatus.RUINED
    after = copy(before)
    after.factions["carmine-crew"].status = FactionStatus.INTACT
    after.places["bar"].status = PlaceStatus.THRIVING

    found = check_transition(before, after)

    assert sorted(v.subject for v in found) == ["faction carmine-crew", "place bar"]


def test_fixed_rules_never_change_and_none_are_added():
    before = grounded_world()
    after = copy(before)
    after.bible.rules[0].text = "Magic is real now."
    after.bible.rules.append(WorldRule(id="new-law", text="Something new.", fixed=True))

    found = check_transition(before, after)

    assert [v.subject for v in found] == ["rule no-supernatural", "rule new-law"]
    assert set(rules_hit(found)) == {"G7"}


def test_a_ruling_is_never_flipped_or_dropped():
    before = cultivation_world()
    before.player.sheet.rulings.append(
        Ruling(
            id="r1",
            topic="stop-and-blood",
            power_id="time-stop",
            question="Does blood flow?",
            answer="No.",
            holds=True,
            source=RulingSource.TEST,
        )
    )
    flipped = copy(before)
    flipped.player.sheet.rulings[0].holds = False
    dropped = copy(before)
    dropped.player.sheet.rulings.clear()

    assert rules_hit(check_transition(before, flipped)) == ["A9"]
    assert rules_hit(check_transition(before, dropped)) == ["A9"]


def test_assert_valid_transition_raises_with_every_violation():
    before = grounded_world()
    after = copy(before)
    del after.characters["bartender"]
    after.characters["carmine"].name = "someone"

    with pytest.raises(InvariantError) as error:
        assert_valid_transition(before, after)

    assert len(error.value.violations) == 2
    assert "records are archived, never deleted" in str(error.value)
