"""N6: who is whose child, and children on the way. The narrator proposes a parentage or a
pregnancy, the engine decides, and the world has the child born when it is due if the one who
carries them lives (W10)."""

import pytest

from engine import world
from engine.apply import DeltaSource, apply_delta
from engine.base import DAY
from engine.context import TurnContext
from engine.contracts import CharacterChange, Expecting, StateDelta
from engine.invariants import check_state, check_transition
from engine.kin import ancestors, descendants, related
from engine.rng import SeededRng
from engine.samples import grounded_world
from engine.state import (
    Character,
    CharacterStatus,
    DeathCertainty,
    EventStatus,
    OriginKind,
    Pregnancy,
    WorldState,
)
from engine.visibility import memory_view, status_view
from engine.world import Kind
from engine.world.knowledge import FAMILY, closeness
from engine.world.tuning import GESTATION_S

NARRATOR = DeltaSource.NARRATOR
ENGINE = DeltaSource.ENGINE


def ctx(turn: int = 3) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn)


def rng(turn: int = 3) -> SeededRng:
    return SeededRng.for_turn("s1", "main", turn)


def apply(state: WorldState, *changes: CharacterChange, source=NARRATOR):
    return apply_delta(state, StateDelta(characters=list(changes)), ctx(), source=source)


def reasons(applied) -> list[str]:
    return [r.reason for r in applied.rejected]


def family() -> WorldState:
    """Naples, with Sofia (Luca's age) at the bar and her son Nino, Carmine's grandson."""
    state = grounded_world()
    state.characters["sofia"] = Character(
        id="sofia", name="Sofia Russo", age=24, location_id="bar", parent_ids=["carmine"]
    )
    state.characters["nino"] = Character(
        id="nino", name="Nino", age=3, location_id="bar", parent_ids=["sofia"]
    )
    return state


# --- Lineage --------------------------------------------------------------------------------


def test_lineage_runs_up_and_down_the_generations():
    state = family()

    assert ancestors(state.characters, "nino") == {"sofia", "carmine"}
    assert descendants(state, "carmine") == {"sofia": 1, "nino": 2}
    assert descendants(state, "nino") == {}
    assert related(state, "sofia", "nino") and related(state, "nino", "sofia")
    assert not related(state, "carmine", "nino")  # a grandparent isn't a parent


def test_a_parent_and_child_are_family_to_the_world():
    state = family()

    assert closeness(state, state.characters["sofia"], "nino") == FAMILY
    assert closeness(state, state.characters["nino"], "sofia") == FAMILY
    # Word of a death reaches family, so killing Nino reaches his mother (W4).
    assert ("sofia", FAMILY) in world.knowledge.ties_of(state, "nino")
    # Little Nino is family too, but too young to carry word on or avenge her.
    assert "nino" not in dict(world.knowledge.ties_of(state, "sofia"))
    state.characters["nino"].age = 20
    assert ("nino", FAMILY) in world.knowledge.ties_of(state, "sofia")


# --- Parentage, as the narrator proposes it -------------------------------------------------


def test_the_narrator_records_a_parentage_the_scene_shows():
    state = grounded_world()

    applied = apply(
        state,
        CharacterChange(id="gennaro", name="Gennaro Jr", age=9, parent_ids=["bartender"]),
    )

    assert not applied.rejected
    assert applied.state.characters["gennaro"].parent_ids == ["bartender"]
    assert check_transition(state, applied.state) == []


def test_parents_are_added_never_more_than_two_and_never_a_descendant():
    state = family()

    applied = apply(
        state,
        CharacterChange(id="nino", parent_ids=["sofia", "bartender"]),  # adds Gennaro
        CharacterChange(id="sofia", parent_ids=["nino"]),  # her own son
        CharacterChange(id="carmine", parent_ids=["carmine", "ghost"]),
    )

    assert applied.state.characters["nino"].parent_ids == ["sofia", "bartender"]
    assert applied.state.characters["sofia"].parent_ids == ["carmine"]
    assert reasons(applied) == [
        "'nino' descends from them",
        "no one else called 'carmine'",
        "no one else called 'ghost'",
    ]
    third = apply(applied.state, CharacterChange(id="nino", parent_ids=["carmine"]))
    assert reasons(third) == ["two parents at most"]


def test_the_player_characters_family_isnt_the_narrators_to_make_up():
    """N4: their family is drafted, claimed by the player or born in play."""
    state = grounded_world()
    parent = CharacterChange(id="luca", parent_ids=["carmine"])
    child = CharacterChange(id="bartender", parent_ids=["luca"])

    applied = apply(state, parent, child)

    assert reasons(applied) == [
        "the player character's parents aren't the narrator's",
        "the player character's children aren't the narrator's",
    ]
    engine = apply(state, parent, child, source=ENGINE).state
    assert engine.player.parent_ids == ["carmine"]
    assert engine.characters["bartender"].parent_ids == ["luca"]


def test_a_child_and_their_parent_can_arrive_in_the_same_scene_in_either_order():
    applied = apply(
        grounded_world(),
        CharacterChange(id="pia", name="Pia", age=6, parent_ids=["rosa"]),
        CharacterChange(id="rosa", name="Rosa Bianchi", age=31),
    )

    assert not applied.rejected
    assert applied.state.characters["pia"].parent_ids == ["rosa"]


# --- A child on the way ---------------------------------------------------------------------


def test_a_pregnancy_is_due_a_gestation_from_now():
    state = family()
    state.world_s = 5 * DAY

    applied = apply(state, CharacterChange(id="sofia", expecting=Expecting(other_parent_id="luca")))

    assert not applied.rejected
    assert applied.state.characters["sofia"].expecting == Pregnancy(
        other_parent_id="luca", conceived_s=5 * DAY, due_s=5 * DAY + GESTATION_S
    )
    assert check_transition(state, applied.state) == []


@pytest.mark.parametrize(
    ("who", "other", "reason"),
    [
        ("nino", None, "only adults have children here (aged 3)"),
        ("sofia", "nino", "only adults have children here (aged 3)"),
        ("bartender", None, "only adults have children here (no age recorded)"),
        ("sofia", "ghost", "no other parent called 'ghost'"),
        ("sofia", "sofia", "no other parent called 'sofia'"),
    ],
)
def test_only_adults_with_a_real_other_parent_have_children(who, other, reason):
    applied = apply(family(), CharacterChange(id=who, expecting=Expecting(other_parent_id=other)))

    assert reasons(applied) == [reason]
    assert applied.state.characters[who].expecting is None


def test_the_dead_carry_no_child_and_no_one_carries_two_at_once():
    state = family()
    state.characters["sofia"].expecting = Pregnancy(conceived_s=0, due_s=GESTATION_S)
    dead = state.characters["carmine"]
    dead.status, dead.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED

    applied = apply(
        state,
        CharacterChange(id="sofia", expecting=Expecting()),
        CharacterChange(id="carmine", expecting=Expecting()),
    )

    assert reasons(applied) == ["they already carry a child", "the dead carry no child"]


def test_a_pregnancy_can_end_without_a_birth():
    state = expecting(family(), "sofia")
    world.catch_up(state, DAY, ctx(), rng(), copy=False)  # the birth is pending

    applied = apply(
        state,
        CharacterChange(id="sofia", expecting=Expecting(ended=True)),
        CharacterChange(id="carmine", expecting=Expecting(ended=True)),
    )
    after = world.catch_up(applied.state, 8 * DAY, ctx(), rng())

    assert reasons(applied) == ["they carry no child"]
    assert applied.state.characters["sofia"].expecting is None
    assert born(after.state) == []
    # Its birth came to nothing, so nobody is told of it.
    (birth,) = [e for e in after.fired if e.kind == Kind.BIRTH]
    assert birth.status is EventStatus.CANCELLED


def test_the_state_never_has_a_missing_parent_or_a_loop():
    state = family()
    state.characters["sofia"].parent_ids = ["nino"]
    state.characters["luca"].parent_ids = ["ghost"]
    state.characters["carmine"].expecting = Pregnancy(
        other_parent_id="nobody", conceived_s=0, due_s=GESTATION_S
    )

    found = {(v.subject, v.detail) for v in check_state(state)}

    assert ("character luca", "unknown parent ghost") in found
    assert ("character carmine", "unknown other parent nobody") in found
    assert ("character sofia", "they are their own ancestor") in found
    assert ("character nino", "they are their own ancestor") in found


# --- Birth ----------------------------------------------------------------------------------


def expecting(state: WorldState, who: str, other: str | None = None, due_s: int = 6 * DAY):
    state.characters[who].expecting = Pregnancy(other_parent_id=other, conceived_s=0, due_s=due_s)
    return state


def born(state: WorldState) -> list[Character]:
    return [c for c in state.characters.values() if c.origin and c.origin.kind is OriginKind.BIRTH]


def test_a_child_is_born_when_it_is_due():
    state = expecting(family(), "sofia", other="carmine")
    state.characters["carmine"].location_id = "questura"  # elsewhere

    early = world.catch_up(state, 5 * DAY, ctx(), rng()).state
    assert born(early) == []
    assert early.characters["sofia"].expecting is not None

    later = world.catch_up(early, 7 * DAY, ctx(), rng()).state
    (child,) = born(later)
    assert (child.name, child.age, child.location_id) == ("Sofia Russo's child", 0, "bar")
    assert child.parent_ids == ["sofia", "carmine"]
    assert child.description == "A newborn, the child of Sofia Russo and Carmine Russo."
    # The mother meets the child; a father elsewhere learns of it as the story has him (C6).
    assert child.met_by == ["sofia"] and child.known_by == ["sofia"]
    assert later.characters["sofia"].expecting is None
    assert descendants(later, "carmine") == {"sofia": 1, "nino": 2, child.id: 1}
    birth = next(e for e in later.pending_events.values() if e.kind == Kind.BIRTH)
    assert birth.status is EventStatus.APPLIED and child.id in birth.subject_ids
    assert not birth.needs_player  # it happened to someone else, off-screen
    assert check_state(later) == []


def test_a_birth_is_scheduled_once_and_plays_the_same_however_time_is_split():
    state = expecting(family(), "sofia")

    in_one = world.catch_up(state, 8 * DAY, ctx(), rng()).state
    stepped = state
    for day in (2, 5, 6, 7, 8):
        stepped = world.catch_up(stepped, day * DAY, ctx(), rng()).state

    for result in (in_one, stepped):
        births = [e for e in result.pending_events.values() if e.kind == Kind.BIRTH]
        assert len(births) == 1
        assert [c.parent_ids for c in born(result)] == [["sofia"]]


def test_a_child_whose_carrier_dies_first_is_never_born():
    state = expecting(family(), "sofia")
    world.catch_up(state, DAY, ctx(), rng(), copy=False)  # the birth is pending
    sofia = state.characters["sofia"]
    sofia.status, sofia.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED

    after = world.catch_up(state, 8 * DAY, ctx(), rng())

    assert born(after.state) == []
    assert after.state.characters["sofia"].expecting is None
    (birth,) = [e for e in after.fired if e.kind == Kind.BIRTH]
    assert birth.status is EventStatus.CANCELLED


def test_a_presumed_death_holds_the_birth_until_they_come_back():
    """C1: a presumed death can turn out false, and the child is born when they return."""
    state = expecting(family(), "sofia")
    world.catch_up(state, DAY, ctx(), rng(), copy=False)
    sofia = state.characters["sofia"]
    sofia.status, sofia.death_certainty = CharacterStatus.DEAD, DeathCertainty.PRESUMED

    world.catch_up(state, 8 * DAY, ctx(), rng(), copy=False)
    assert born(state) == [] and sofia.expecting is not None

    sofia.status, sofia.death_certainty = CharacterStatus.ALIVE, None
    world.catch_up(state, 8 * DAY + 1, ctx(), rng(), copy=False)
    assert [c.parent_ids for c in born(state)] == [["sofia"]]


def test_a_newborns_placeholder_name_is_a_name_and_never_taken():
    state = family()
    state.characters["sofia"].name = "S" * 200
    state.characters["nina"] = Character(id="nina", name="Nina")
    expecting(state, "sofia")
    state = world.catch_up(state, 7 * DAY, ctx(), rng()).state
    expecting(state, "sofia", due_s=8 * DAY)
    state = world.catch_up(state, 9 * DAY, ctx(), rng()).state

    first, second = sorted((c.name for c in born(state)), key=len)
    assert first == "S" * 180 + "'s child" and second == first + " 2"


def test_a_birth_to_the_player_character_stops_the_clock_for_them():
    state = expecting(family(), "luca", other="sofia")

    passage = world.catch_up(state, 9 * DAY, ctx(), rng())

    assert passage.ended_s == 6 * DAY  # the clock stops at the birth (W10)
    (child,) = born(passage.state)
    assert child.parent_ids == ["luca", "sofia"]
    # Both parents are at the bar, so both meet the child, the player character among them.
    assert child.met_by == ["luca", "sofia"]
    birth = next(e for e in passage.state.pending_events.values() if e.kind == Kind.BIRTH)
    assert birth.needs_player


def test_the_player_character_sees_their_family_and_a_child_on_the_way():
    state = expecting(family(), "luca", due_s=40 * DAY)
    state.world_s = 10 * DAY
    state.characters["nino"].parent_ids = ["sofia", "luca"]
    state.characters["nino"].known_by = ["luca"]
    state.characters["carmine"].known_by = ["luca"]
    state.characters["luca"].parent_ids = ["carmine"]

    people = {p.id: p for p in memory_view(state).people}
    assert people["nino"].lines[0] == "Your child."
    assert people["carmine"].lines[0] == "Your parent."
    assert "Expecting a child, due in 4 weeks" in status_view(state).character.lines
