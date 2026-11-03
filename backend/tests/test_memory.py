from app.domain import (
    Character,
    CharacterStatus,
    Fact,
    Faction,
    FactionStance,
    WorldState,
)
from app.engine.memory import apply_update, continuity_rules
from app.engine.schemas import CharacterChange, FactionChange, NewFact, StateUpdate


def test_new_character_is_added():
    update = StateUpdate(characters=[CharacterChange(id="kaede", name="Kaede", affinity_delta=10)])

    state = apply_update(WorldState(), update, turn=1)

    assert state.turn == 1
    assert state.characters == [Character(id="kaede", name="Kaede", affinity=10)]


def test_unknown_character_without_name_is_ignored():
    update = StateUpdate(characters=[CharacterChange(id="ghost", affinity_delta=5)])

    assert apply_update(WorldState(), update, turn=1).characters == []


def test_dead_characters_stay_dead():
    state = WorldState(characters=[Character(id="kaede", name="Kaede", status="dead")])
    update = StateUpdate(characters=[CharacterChange(id="kaede", status=CharacterStatus.ALIVE)])

    state = apply_update(state, update, turn=2)

    assert state.characters[0].status is CharacterStatus.DEAD


def test_destroyed_factions_stay_destroyed():
    state = WorldState(factions=[Faction(id="iron_lotus", name="Iron Lotus", stance="destroyed")])
    update = StateUpdate(factions=[FactionChange(id="iron_lotus", stance=FactionStance.ALLIED)])

    state = apply_update(state, update, turn=2)

    assert state.factions[0].stance is FactionStance.DESTROYED


def test_affinity_is_clamped():
    state = WorldState(characters=[Character(id="ren", name="Ren", affinity=95)])
    update = StateUpdate(characters=[CharacterChange(id="ren", affinity_delta=20)])

    assert apply_update(state, update, turn=2).characters[0].affinity == 100


def test_goals_and_summary_are_kept_when_not_updated():
    state = WorldState(goals=["Pass the exam"], summary="So far...")

    state = apply_update(state, StateUpdate(new_facts=[NewFact(text="It rained.")]), turn=2)

    assert state.goals == ["Pass the exam"]
    assert state.summary == "So far..."
    assert state.facts == [Fact(text="It rained.", turn=2, importance=3)]


def test_update_does_not_mutate_the_previous_state():
    before = WorldState(characters=[Character(id="ren", name="Ren")])

    apply_update(before, StateUpdate(characters=[CharacterChange(id="ren", status="dead")]), turn=1)

    assert before.characters[0].status is CharacterStatus.ALIVE


def test_continuity_rules_cover_the_dead_the_destroyed_and_pinned_facts():
    state = WorldState(
        characters=[
            Character(id="kaede", name="Kaede", status="dead"),
            Character(id="ren", name="Ren"),
        ],
        factions=[Faction(id="iron_lotus", name="Iron Lotus", stance="destroyed")],
        facts=[
            Fact(text="You swore an oath to the sea witch.", turn=1, importance=5),
            Fact(text="It rained.", turn=1, importance=1),
        ],
    )

    rules = continuity_rules(state)

    assert len(rules) == 3
    assert "Kaede (kaede) is dead" in rules[0]
    assert "Iron Lotus (iron_lotus) has been destroyed" in rules[1]
    assert rules[2] == "You swore an oath to the sea witch."
