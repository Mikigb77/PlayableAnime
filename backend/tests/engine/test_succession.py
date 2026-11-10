"""N6: someone else carries the story on after its ending, drawn by the world's population odds,
and the old player character stays in the world, remembered."""

from collections import Counter

import pytest

from engine.rng import SeededRng
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    Activity,
    Character,
    CharacterStatus,
    DeathCertainty,
    Extraordinary,
    Goal,
    GoalStatus,
    Lead,
    LeadStatus,
    Place,
    PlaceStatus,
    Prevalence,
    Reputation,
    StatusChange,
)
from engine.succession import STATION_ODDS, Station, carry_on, draw

DRAWS = 20_000


def draws(state, n=DRAWS):
    return [draw(state, SeededRng(f"test/{i}")) for i in range(n)]


@pytest.fixture(scope="module")
def grounded_lots():
    return draws(grounded_world())


def test_most_people_are_common_folk_and_royalty_is_rare(grounded_lots):
    stations = Counter(lot.station for lot in grounded_lots)
    assert stations[Station.COMMON] / DRAWS == pytest.approx(STATION_ODDS[Station.COMMON], abs=0.02)
    assert stations[Station.SKILLED] / DRAWS == pytest.approx(1 / 5, abs=0.02)
    assert stations[Station.NOTABLE] / DRAWS == pytest.approx(1 / 40, abs=0.006)
    assert stations[Station.NOBLE] <= 60  # about 20 in 20,000
    assert stations[Station.ROYAL] <= 3  # about 1 in 50,000


def test_a_person_is_an_adult_of_working_age(grounded_lots):
    ages = [lot.age for lot in grounded_lots]
    assert min(ages) >= 16 and max(ages) <= 60


def test_how_rare_a_person_is_follows_the_draw(grounded_lots):
    common = next(lot for lot in grounded_lots if lot.station is Station.COMMON and lot.might == 1)
    notable = next(lot for lot in grounded_lots if lot.station is Station.NOTABLE)
    assert common.one_in == 1
    assert notable.one_in >= 40


def test_a_hidden_master_is_rarer_in_a_grounded_world(grounded_lots):
    common_powers = cultivation_world()
    common_powers.bible.extraordinary = [
        Extraordinary(id="qi", kind="qi", prevalence=Prevalence.COMMON)
    ]
    grounded = sum(lot.master for lot in grounded_lots)
    powered = sum(lot.master for lot in draws(common_powers))
    assert grounded <= 45  # about 20 in 20,000
    assert 60 <= powered <= 150  # about 100 in 20,000
    tough = sum(lot.might == 2 and not lot.master for lot in grounded_lots)
    assert tough / DRAWS == pytest.approx(1 / 15, abs=0.01)


def test_a_hidden_master_is_at_least_the_best_a_person_can_be(grounded_lots):
    masters = [lot for lot in grounded_lots if lot.master]
    assert masters and all(lot.might >= 4 for lot in masters)


@pytest.mark.parametrize(
    ("kind", "lived_in"),
    [
        ("seaport", True),
        ("city in the underworld", True),
        ("sect", True),
        ("forest", False),
        ("mountain pass", False),
        ("cave", False),
        ("wilds", False),
    ],
)
def test_where_people_make_a_home(kind, lived_in):
    state = grounded_world()
    state.places = {"here": Place(id="here", name="Here", kind=kind)}
    assert (draw(state, SeededRng("home")).place_id == "here") is lived_in


def test_people_live_in_cities_more_than_villages_and_never_in_ruins():
    state = grounded_world()
    state.places = {
        "city": Place(id="city", name="Marrow", kind="city"),
        "village": Place(id="village", name="Fenn", kind="village"),
        "ruin": Place(id="ruin", name="Old Keep", kind="castle", status=PlaceStatus.RUINED),
        "wilds": Place(id="wilds", name="The Reach", kind="wilds"),
    }
    places = Counter(lot.place_id for lot in draws(state, 3000))
    assert set(places) == {"city", "village"}
    assert places["city"] > 3 * places["village"]


def dead_and_carried(state=None, **extra):
    state = state or grounded_world()
    state.turn = 7
    state.player.status = CharacterStatus.DEAD
    state.player.death_certainty = DeathCertainty.CONFIRMED
    newcomer = Character(id="pc-2", name="Mara Venn", location_id="naples", **extra)
    return state, carry_on(state, newcomer, "Dawn at the docks.", ending="death", turn=7)


def test_carrying_on_makes_the_newcomer_the_player_character():
    before, after = dead_and_carried()

    assert after.player_id == "pc-2" and after.player.name == "Mara Venn"
    assert after.opening_due
    assert after.scene.place_id == "naples" and after.scene.present_ids == ["pc-2"]
    assert after.scene.ended_on == "Dawn at the docks."
    [fallen] = after.fallen
    assert (fallen.character_id, fallen.ending, fallen.turn) == ("luca", "death", 7)
    assert fallen.successor_id == "pc-2"
    assert not after.characters["luca"].alive  # the dead stay dead (C1)
    assert before.player_id == "luca"  # the state carried on from is untouched


def test_the_newcomer_holds_none_of_the_openings_the_fallen_won():
    # A3: an opening won by a throw over the top was the old player character's, not theirs.
    state = grounded_world()
    state.openings = ["carmine"]
    _, after = dead_and_carried(state)
    assert after.openings == []


def test_whoever_was_there_saw_how_they_died():
    state = grounded_world()
    state.player.status_history.append(
        StatusChange(status="dead", from_status="alive", turn=7, world_s=0, known_by=["luca"])
    )
    state.scene.present_ids = ["luca", "bartender"]

    _, after = dead_and_carried(state)

    [death] = [s for s in after.characters["luca"].status_history if s.status == "dead"]
    assert death.known_by == ["luca", "bartender"]


def test_what_was_the_old_player_characters_alone_stays_theirs():
    state = grounded_world()
    state.goals = {"goal-1": Goal(id="goal-1", text="Find who killed father")}
    state.leads = {"lead-1": Lead(id="lead-1", text="A job at the docks")}
    for faction in state.factions.values():
        faction.player_reputation = Reputation(esteem=40, fear=60)

    _, after = dead_and_carried(state)

    assert after.goals["goal-1"].status is GoalStatus.ABANDONED
    assert after.leads["lead-1"].status is LeadStatus.EXPIRED
    assert all(f.player_reputation == Reputation() for f in after.factions.values())
    assert all(p.player_reputation == Reputation() for p in after.places.values())


def test_the_newcomer_knows_where_they_live_and_nobody_else():
    _, after = dead_and_carried()

    newcomer = after.player
    assert newcomer.known_by == ["pc-2"] and newcomer.met_by == ["pc-2"]
    assert "pc-2" in after.places["naples"].known_by
    assert all("pc-2" not in c.known_by for c in after.npcs())


def test_someone_who_ended_their_story_alive_lives_on_in_the_world():
    state = grounded_world()
    newcomer = Character(id="pc-2", name="Mara Venn", location_id="naples")

    after = carry_on(state, newcomer, "Dawn.", ending="chosen", turn=3)

    luca = after.characters["luca"]
    assert luca.alive and luca.activity is Activity.DORMANT
    assert after.fallen[0].ending == "chosen"


def test_the_newcomer_is_never_the_player_character_already():
    state = grounded_world()
    with pytest.raises(ValueError):
        carry_on(state, state.player, "Dawn.", ending="death", turn=3)
