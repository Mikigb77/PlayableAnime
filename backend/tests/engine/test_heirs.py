"""N6: heirs. After the player character's ending, their living children and grandchildren can
carry the story on, and so can a child on the way if the one who carries them lives. One too young
to act is played from the day they turn 16, once the world has run on to it."""

import pytest

from engine.base import DAY, YEAR
from engine.context import TurnContext
from engine.heirs import (
    AGE_OF_ACTION,
    UNBORN,
    born_of,
    heirs,
    time_jump,
    unborn_lost,
)
from engine.rng import SeededRng
from engine.samples import grounded_world
from engine.state import (
    Character,
    CharacterStatus,
    DeathCertainty,
    Health,
    OriginKind,
    Pregnancy,
    WorldState,
)
from engine.succession import carry_on

DUE_S = 30 * DAY


def rng() -> SeededRng:
    return SeededRng("story=s/ending=3/heirs")


def ctx() -> TurnContext:
    return TurnContext(story_id="s", turn=3)


def dead(character: Character) -> None:
    character.status, character.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED


def family() -> WorldState:
    """Luca, dead, with a son of 2, a daughter of 30 with a boy of her own, a dead son, and Sofia
    carrying his child."""
    state = grounded_world()
    dead(state.player)
    luca = state.player_id
    for character in (
        Character(id="tonio", name="Tonio", age=2, location_id="bar", parent_ids=[luca]),
        Character(id="rosa", name="Rosa", age=30, location_id="bar", parent_ids=[luca]),
        Character(id="enzo", name="Enzo", age=8, location_id="bar", parent_ids=["rosa"]),
        Character(id="paolo", name="Paolo", age=20, location_id="bar", parent_ids=[luca]),
        Character(
            id="sofia",
            name="Sofia",
            age=24,
            location_id="bar",
            expecting=Pregnancy(other_parent_id=luca, conceived_s=0, due_s=DUE_S),
        ),
    ):
        state.characters[character.id] = character
    dead(state.characters["paolo"])
    return state


def test_heirs_are_living_children_then_grandchildren_then_a_child_on_the_way():
    found = heirs(family(), rng())

    assert [(h.id, h.relation, h.age, h.years) for h in found] == [
        ("rosa", "child", 30, 0),
        ("tonio", "child", 2, AGE_OF_ACTION - 2),
        ("enzo", "grandchild", 8, AGE_OF_ACTION - 8),
        (UNBORN + "sofia", "child", None, AGE_OF_ACTION + 1),
    ]
    unborn = found[-1]
    assert unborn.unborn and unborn.carrier_id == "sofia" and unborn.due_s == DUE_S
    assert unborn.name == "Sofia's child, not yet born"
    assert unborn.jump_s == DUE_S + AGE_OF_ACTION * YEAR


def test_an_unborn_child_counts_only_if_the_one_who_carries_them_lives():
    state = family()
    dead(state.characters["sofia"])

    assert UNBORN + "sofia" not in {h.id for h in heirs(state, rng())}


def test_a_child_on_the_way_counts_when_the_player_character_carries_it_and_lives():
    """After an epilogue, the player character lives on, and so does the child they carry."""
    state = grounded_world()
    state.player.expecting = Pregnancy(conceived_s=0, due_s=DUE_S)

    [heir] = heirs(state, rng())

    assert heir.id == UNBORN + "luca" and heir.relation == "child"
    dead(state.player)
    assert heirs(state, rng()) == []


def test_only_a_dying_carrier_leaves_it_to_a_roll_settled_once_per_ending():
    state = family()
    assert unborn_lost(state, rng()) == set()  # alive and well: logic decides
    state.characters["sofia"].sheet.condition.health = Health.DYING

    outcomes = {
        seed: unborn_lost(state, SeededRng(f"story=s/ending={seed}/heirs")) for seed in range(40)
    }

    assert set(map(frozenset, outcomes.values())) == {frozenset(), frozenset({"sofia"})}
    for seed, lost in outcomes.items():
        again = unborn_lost(state, SeededRng(f"story=s/ending={seed}/heirs"))
        assert again == lost
        listed = {h.id for h in heirs(state, SeededRng(f"story=s/ending={seed}/heirs"))}
        assert (UNBORN + "sofia" in listed) is not bool(lost)


def test_the_world_runs_on_until_the_heir_can_act():
    state = family()
    [*_, unborn] = heirs(state, rng())

    later = time_jump(state, state.world_s + unborn.jump_s, ctx(), SeededRng("jump"))

    assert later.world_s == unborn.jump_s
    child = born_of(later, "sofia", DUE_S)
    assert child is not None and child.origin.kind is OriginKind.BIRTH
    assert child.parent_ids == ["sofia", "luca"]
    assert child.age == AGE_OF_ACTION  # born at the due time, sixteen years ago
    # Everyone alive grew older by the years that went by; the dead stay as they were.
    assert later.characters["tonio"].age == 2 + 16
    assert later.characters["rosa"].age == 30 + 16
    assert later.characters["paolo"].age == 20
    assert later.characters["carmine"].age == state.characters["carmine"].age + 16
    assert state.world_s == 0 and state.characters["tonio"].age == 2  # a new state


def test_a_time_jump_plays_the_same_every_time():
    state = family()
    until = state.world_s + 3 * YEAR

    first = time_jump(state, until, ctx(), SeededRng("jump"))
    second = time_jump(state, until, ctx(), SeededRng("jump"))

    assert first == second


def test_carrying_on_as_an_heir_keeps_them_as_the_world_has_them():
    state = family()
    state.characters["tonio"].known_by = ["sofia"]
    later = time_jump(state, state.world_s + 14 * YEAR, ctx(), SeededRng("jump"))
    tonio = later.characters["tonio"]

    carried = carry_on(later, tonio, "Dawn.", ending="death", turn=3, ended_s=state.world_s)

    you = carried.player
    assert carried.player_id == "tonio" and you.age == 16
    assert you.parent_ids == ["luca"] and you.prominence.value == "key"
    sibling = born_of(later, "sofia", DUE_S).id  # Sofia's child, his half-brother
    # Who knew him still does, and so do his living brothers and sisters.
    assert set(you.known_by) == {"sofia", "tonio", "rosa", sibling}
    # The fallen is remembered as of their ending, years before (N6).
    [fallen] = carried.fallen
    assert (fallen.character_id, fallen.world_s, fallen.successor_id) == ("luca", 0, "tonio")
    # They know their family: their dead father, and their sister and her son.
    assert "tonio" in carried.characters["luca"].known_by
    assert "tonio" not in carried.characters["luca"].met_by
    for kin in ("rosa", "paolo"):
        assert "tonio" in carried.characters[kin].known_by
    assert "tonio" in carried.characters["rosa"].met_by and "rosa" in you.met_by
    assert "tonio" not in carried.characters["enzo"].known_by  # a nephew isn't counted
    assert carried.opening_due


@pytest.mark.parametrize("age", [None, 16, 40])
def test_an_heir_old_enough_to_act_needs_no_jump(age):
    state = family()
    state.characters["tonio"].age = age

    [tonio] = [h for h in heirs(state, rng()) if h.id == "tonio"]

    assert tonio.jump_s == 0 and tonio.years == 0
