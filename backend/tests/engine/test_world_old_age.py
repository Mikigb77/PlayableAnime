"""W6, W10: old age takes people over the years.

Nothing is made to happen. From 85% of how long someone lives the years may take them, the
likelier the older: a month takes next to nobody and a hundred years every mortal, with the
same odds however the world cuts the years. How long someone lives is on record: their
people's span, their rung's where climbing lengthens life, or a span of their own for someone
the record already has older than that. The player character is never taken by the dice, and
hears of a death when they live near, from the partner the dead left, or in a scene where the
dead lived (C6).
"""

import math

import pytest

from engine import bonds, pipeline
from engine.apply import apply_delta
from engine.base import DAY, YEAR
from engine.context import Language
from engine.contracts import CharacterChange, StateDelta
from engine.invariants import check_state
from engine.state import (
    BondEnd,
    BondStage,
    Character,
    CharacterStatus,
    Creature,
    DeathCertainty,
    LadderPosition,
    LifeKind,
    People,
    PowerLadder,
    Rung,
    StatusChange,
    WorldState,
)
from engine.succession import carry_on
from engine.visibility import memory_view
from engine.world import lives, old_age
from engine.world.scheduling import World
from engine.world.tuning import AGELESS_YEARS, LIFE_QUIET_S, LIVES_KEPT

from .test_world import ctx, idle, rng
from .test_world_lives import NARRATOR, YOU, a_year, couple, news, quiet, valley, villager

DIED = LifeKind.DIED


def sure(monkeypatch) -> None:
    """Old age takes whoever it can in any stretch, so a test reads whom, not how often."""
    monkeypatch.setattr(old_age, "chance", lambda lives, from_age, to_age: 1.0)


def dead(state: WorldState) -> list[str]:
    return sorted(c.id for c in state.characters.values() if not c.alive)


def far(state: WorldState) -> WorldState:
    """Tomas lives in the city now, five days from the village, alone."""
    state.characters[YOU].location_id = "city"
    state.scene.place_id, state.scene.present_ids = "city", [YOU]
    return state


def on(state: WorldState, who: str, rung: int) -> None:
    state.characters[who].sheet.ladders = [LadderPosition(ladder_id="realms", rung=rung)]


def realms(*lifespans: int | None) -> PowerLadder:
    rungs = [
        Rung(name=f"Realm {i}", tier=2 * (i + 1), lifespan_years=y) for i, y in enumerate(lifespans)
    ]
    return PowerLadder(id="realms", name="realms", rungs=rungs)


# --- The odds ----------------------------------------------------------------------------------


def test_nothing_takes_anyone_before_old_age_and_half_are_gone_at_the_full_span():
    assert old_age.chance(80, 0, 68) == 0
    assert old_age.chance(80, 0, 80) == pytest.approx(0.5)
    assert old_age.chance(80, 0, 72) < 0.03
    assert old_age.chance(80, 0, 96) > 0.99
    # A long-lived people ages on the same curve, stretched: nothing in it counts in years.
    assert old_age.chance(600, 0, 600) == pytest.approx(0.5)
    assert old_age.chance(600, 0, 500) == 0


def test_a_month_takes_next_to_nobody_and_the_years_take_more_the_older_someone_is():
    assert old_age.chance(80, 80, 80 + 1 / 12) < 0.02
    assert old_age.chance(80, 80, 81) == pytest.approx(0.17, abs=0.01)
    assert old_age.chance(80, 70, 71) < old_age.chance(80, 80, 81) < old_age.chance(80, 90, 91)


def test_the_odds_are_the_same_however_the_years_are_cut():
    whole = old_age.chance(80, 60, 95)
    cut = 1.0
    for start in range(60, 95):
        cut *= 1 - old_age.chance(80, start, start + 1)

    assert 1 - cut == pytest.approx(whole)


def test_the_world_counts_ages_to_the_day():
    """So two ticks in one year don't count the same part of it twice."""
    state = valley()
    state.aged_s = 2 * YEAR
    bram, child = state.characters["bram"], villager("lena", "Lena", 3, born_s=YEAR)

    assert old_age.age_at(state, bram, 2 * YEAR + YEAR // 2) == pytest.approx(71.5)
    assert old_age.age_at(state, child, 4 * YEAR + YEAR // 4) == pytest.approx(3.25)
    assert old_age.age_at(state, villager("wren", "Wren", None), YEAR) is None


def test_ticks_take_as_many_as_one_long_stretch_would():
    """W10: nothing is timed in ticks. Ten years in one pass, a year at a time or in
    thirty-seven uneven pieces, about as many of three hundred people of seventy-one are gone
    at the end: as many as the odds between the two ages say, less the quiet season."""

    def gone_after(passes: int) -> int:
        taken = 0
        for seed in range(300):
            state = valley(villager("old", "Old One", 71))
            end = state.world_s + 10 * YEAR
            for n in range(passes):
                since = state.world_s
                state.world_s = end if n == passes - 1 else since + 10 * YEAR // passes
                w = World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng(1000 * seed + n))
                lives.live_on(w, since)
            taken += not state.characters["old"].alive
        return taken

    expected = 300 * old_age.chance(80, 71 + LIFE_QUIET_S / YEAR, 81)

    assert 150 < expected < 200  # a little over half: neither nobody nor everybody
    for passes in (1, 10, 37):
        assert abs(gone_after(passes) - expected) <= 20, passes


# --- How long someone lives -----------------------------------------------------------------------


def test_someone_lives_as_long_as_their_people_or_a_human_span_where_the_world_does_not_say():
    state = valley(villager("elf", "Sael", 100, people_id="elves"))
    state.bible.peoples = [People(id="elves", name="elves", lifespan_years=600)]

    assert old_age.span(state, state.characters["elf"]) == 600
    assert old_age.span(state, state.characters["bram"]) == 80

    state, _ = idle(state, 100 * YEAR)

    assert state.characters["elf"].alive and state.characters["elf"].age == 200
    assert not state.characters["bram"].alive


def test_old_age_never_takes_one_of_a_people_the_record_calls_ageless():
    """G23: a lifespan of 0 on record. Before, the dice read it as a human one, and one of
    the undead died of old age at eighty."""
    state = valley(
        villager("lich", "Varn", 40, people_id="undead"),
        villager("elder", "Old Varn", 3000, people_id="undead"),
        villager("ghoul", "Mok", 40, people_id="ghouls"),
    )
    state.bible.peoples = [
        People(id="undead", name="the undead", lifespan_years=0),
        People(id="ghouls", name="ghouls"),
    ]
    lich, elder, ghoul = (state.characters[i] for i in ("lich", "elder", "ghoul"))

    assert old_age.ageless(state, lich) and not old_age.ageless(state, ghoul)
    assert not old_age.ageless(state, state.characters["bram"])  # of no people on record
    assert old_age.span(state, lich) == AGELESS_YEARS
    # A people the record says nothing of lives a human span, as before.
    assert old_age.span(state, ghoul) == 80
    # However old, they are within their span: none of their own, and never past their prime.
    assert old_age.own_span(state, elder, 3000) == 0
    assert lives._prime(state, elder) and not lives._spent(state, elder)

    state, _ = idle(state, 1000 * YEAR)

    assert state.characters["lich"].alive and state.characters["lich"].age == 1040
    assert state.characters["elder"].alive and state.characters["elder"].lifespan_years == 0
    assert not state.characters["ghoul"].alive and not state.characters["bram"].alive
    assert check_state(state) == []


def test_whoever_reached_a_higher_rung_outlives_those_who_never_did():
    """Miki, 2026-11-13: after a hundred years of training "either they are dead of old age
    or some of them might actually successfully improved"."""
    state = valley(villager("low", "Wen", 60), villager("high", "Lin", 60))
    state.bible.ladders = [realms(0, 120, 500)]
    on(state, "low", 1)
    on(state, "high", 2)

    assert old_age.span(state, state.characters["low"]) == 120
    assert old_age.span(state, state.characters["high"]) == 500
    assert old_age.span(state, state.characters["bram"]) == 80

    state, _ = idle(state, 100 * YEAR)

    assert not state.characters["low"].alive and not state.characters["bram"].alive
    assert state.characters["high"].alive and state.characters["high"].age == 160


def test_a_higher_rung_never_shortens_a_life():
    state = valley(villager("elf", "Sael", 100, people_id="elves"))
    state.bible.peoples = [People(id="elves", name="elves", lifespan_years=600)]
    state.bible.ladders = [realms(120, 0, 250)]
    on(state, "elf", 2)
    on(state, "bram", 1)

    assert old_age.span(state, state.characters["elf"]) == 600
    assert old_age.span(state, state.characters["bram"]) == 120  # the rung below still counts


def test_where_a_ladder_says_nothing_of_lifespans_the_dice_take_nobody_who_stands_on_it():
    """A2: a story drafted before rungs carried a lifespan. Better a cultivator who lives
    too long than one dead at eighty by a rule their world never had."""
    state = valley(villager("climbed", "Lin", 60), villager("lowest", "Wen", 60))
    state.bible.ladders = [realms(None, None, None)]
    on(state, "climbed", 1)
    on(state, "lowest", 0)

    assert old_age.open_ended(state, state.characters["climbed"])
    assert old_age.open_ended(state, state.characters["lowest"])
    assert not old_age.open_ended(state, state.characters["bram"])  # on no ladder: a mortal

    state, _ = idle(state, 100 * YEAR)

    assert state.characters["climbed"].alive and state.characters["climbed"].age == 160
    assert state.characters["lowest"].alive and not state.characters["bram"].alive


def test_a_ladder_that_lengthens_no_life_leaves_everyone_on_it_mortal():
    """Ranks that only measure skill or standing: the record says so, and the dice read it."""
    state = valley(villager("ranked", "Lin", 60))
    state.bible.ladders = [realms(0, 0, 0)]
    on(state, "ranked", 2)

    assert not old_age.open_ended(state, state.characters["ranked"])
    assert old_age.span(state, state.characters["ranked"]) == 80

    state, _ = idle(state, 100 * YEAR)

    assert not state.characters["ranked"].alive


def test_someone_first_found_older_than_they_would_live_gets_a_span_of_their_own():
    """An elder of three hundred among people who live eighty neither drops dead the day the
    world first counts their years nor lives for ever: they have half as long again past
    their span as they have had."""
    state = valley(villager("elder", "Elder Shan", 300))

    assert old_age.own_span(state, state.characters["elder"], 300) == 410
    assert old_age.own_span(state, state.characters["bram"], 71) == 0
    # Just past their span it changes next to nothing.
    assert old_age.own_span(state, state.characters["bram"], 81) == 82

    state, _ = idle(state, 30 * YEAR)
    elder = state.characters["elder"]

    assert elder.alive and elder.age == 330 and elder.lifespan_years == 410
    assert old_age.span(state, elder) == 410

    state, _ = idle(state, 230 * YEAR)

    assert not state.characters["elder"].alive
    assert state.characters["elder"].lifespan_years == 410


def test_whoever_outlives_their_span_under_the_dice_gets_no_more_years_for_it(monkeypatch):
    """The world settles it once, by the age it first found someone at. Someone who was
    seventy-nine then and is ninety now has only been lucky: were they given a span of their
    own for it, the odds would turn on how the years were cut (W10)."""
    monkeypatch.setattr(old_age, "chance", lambda lives, from_age, to_age: 0.0)
    state = valley(villager("old", "Edda", 79))

    state = a_year(state, 1)

    assert state.characters["old"].lifespan_years == 0

    state = a_year(state, 10)
    old = state.characters["old"]

    assert old.age == 90 and old.lifespan_years == 0 and old_age.span(state, old) == 80


def test_a_span_of_their_own_goes_by_the_age_a_long_stretch_found_them_at():
    """Thirty years in one pass: someone who was sixty-two when it began has no span of their
    own for being ninety-two when it ends."""
    state = valley(villager("old", "Edda", 62), villager("elder", "Elder Shan", 300))
    since = state.world_s
    state.world_s += 30 * YEAR

    lives.live_on(World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng()), since)

    assert state.characters["old"].lifespan_years == 0
    assert state.characters["elder"].lifespan_years == 410


# --- Whom the years take --------------------------------------------------------------------------


def test_a_month_takes_nobody_and_a_hundred_years_every_mortal():
    people = [villager(f"v{i}", f"Villager {i}", 20 + 6 * i) for i in range(10)]
    month = [idle(valley(*people), 30 * DAY, turn=seed)[0] for seed in range(3, 13)]
    century, _ = idle(valley(*people), 100 * YEAR)

    assert all(dead(state) == [] for state in month)
    # Tomas among them: his own old age came for him too (`engine.world.last_years`).
    assert dead(century) == sorted(century.characters)
    assert check_state(century) == []


def test_ten_years_take_some_of_the_old_and_none_of_the_young():
    taken = []
    for seed in range(3, 23):
        state = valley(villager("young", "Wil", 30), villager("old", "Edda", 72))
        state, _ = idle(state, 10 * YEAR, turn=seed)
        taken.extend(dead(state))

    assert "young" not in taken and YOU not in taken and "ilse" not in taken
    assert 4 <= taken.count("old") <= 16 and 4 <= taken.count("bram") <= 16


def test_the_player_character_is_never_taken_and_neither_is_anyone_without_an_age_or_a_beast(
    monkeypatch,
):
    sure(monkeypatch)
    state = valley(villager("wren", "Wren", None), villager("ox", "the ox", 90, people_id="oxen"))
    state.bible.creatures = [Creature(id="oxen", name="oxen")]
    state.characters[YOU].age = 99

    state = a_year(state, 5)

    assert dead(state) == ["bram", "ilse"]


def test_nobody_dies_in_the_season_after_the_player_character_was_with_them(monkeypatch):
    """Those days are the story's to tell, which also keeps a short scene from losing someone
    in it to the dice."""
    sure(monkeypatch)
    state = valley()
    state.characters["bram"].seen_s = state.world_s

    since = state.world_s
    state.world_s += 60 * DAY
    lives.live_on(World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng()), since)

    assert dead(state) == []

    since = state.world_s
    state.world_s += 60 * DAY
    lives.live_on(World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng()), since)

    assert dead(state) == ["bram", "ilse"]


def test_someone_in_a_scene_that_no_scene_has_ended_on_is_the_storys(monkeypatch):
    """A stranger in the opening scene: the record has no day yet on which the player
    character was with them, so the dice leave them to the story for now."""
    sure(monkeypatch)
    stranger = Character(id="hale", name="Hale", age=90, location_id="farm")
    state = valley(stranger)
    state.scene.present_ids.append("hale")

    state = a_year(state, 2)

    assert "hale" not in dead(state) and state.characters["hale"].seen_s is None


def test_a_long_stretch_may_take_someone_in_the_scene_and_they_know():
    """Thirty years lived beside someone are not a scene: the years take them too, and the
    player character was there."""
    state = valley()
    state.characters["ilse"].age = 75

    state, _ = idle(state, 30 * YEAR)

    ilse = state.characters["ilse"]
    assert not ilse.alive and "ilse" not in state.scene.present_ids
    (event,) = [e for e in news(state, DIED) if e.subject_ids[0] == "ilse"]
    assert YOU in event.known_by and YOU in ilse.status_history[-1].known_by


# --- What a death leaves on record ----------------------------------------------------------------


def test_the_record_has_them_dead_for_certain_at_the_age_they_died_and_their_romance_ended(
    monkeypatch,
):
    sure(monkeypatch)
    state = valley(villager("mara", "Mara", 30))
    bond = couple(state, "bram", "mara", BondStage.MARRIED)

    state = a_year(state, 2)
    bram = state.characters["bram"]

    assert bram.status is CharacterStatus.DEAD
    assert bram.death_certainty is DeathCertainty.CONFIRMED
    assert bram.age == 73 and bram.location_id == "village"
    last = bram.status_history[-1]
    assert (last.status, last.from_status, last.note) == ("dead", "alive", "Died of old age.")
    assert last.world_s == state.world_s
    assert (bond.stage, bond.end) == (BondStage.OVER, BondEnd.DEATH)
    assert bond.steps[-1].how == "Old Bram died."
    assert bonds.partners(state, "mara") == []

    monkeypatch.undo()
    state, _ = idle(state, state.world_s + 5 * YEAR)

    assert state.characters["bram"].age == 73  # the dead stay the age they died at
    assert len(state.characters["bram"].status_history) == 1


def test_someone_who_dies_while_out_on_a_trip_is_on_record_at_home(monkeypatch):
    sure(monkeypatch)
    state = valley()
    homes = lives._Homes(state)
    homes.out["bram"] = "village"
    state.characters["bram"].location_id = "city"
    w = World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng())

    lives._pass_away(w, homes, state.characters["bram"])

    assert state.characters["bram"].location_id == "village"


def test_someone_only_presumed_dead_is_dead_for_certain_once_old_age_would_have_taken_them(
    monkeypatch,
):
    """C1: a death only presumed may turn out false, so their years count on. Past their
    span it can't any more, and that is news to nobody."""
    sure(monkeypatch)
    state = valley(villager("mara", "Mara", 30))
    bram = state.characters["bram"]
    bram.status, bram.death_certainty = CharacterStatus.DEAD, DeathCertainty.PRESUMED
    bram.status_history.append(StatusChange(status="dead", presumed=True, turn=1, world_s=0))
    bond = couple(state, "bram", "mara", BondStage.MARRIED)

    state = a_year(state, 2)

    assert bram.death_certainty is DeathCertainty.CONFIRMED
    assert bram.status_history[-1].from_status == "dead" and not bram.status_history[-1].presumed
    assert [e for e in news(state, DIED) if "bram" in e.subject_ids] == []
    assert bond.end is BondEnd.DEATH


# --- Who hears of it (C6) -------------------------------------------------------------------------


def test_the_player_character_knows_at_once_when_they_live_near(monkeypatch):
    sure(monkeypatch)
    state = a_year(valley(), 2)

    (event,) = [e for e in news(state, DIED) if e.subject_ids == ["bram"]]
    assert YOU in event.known_by
    assert lives.heard_in(state, ctx().turn) == news(state, DIED)
    bram = next(p for p in memory_view(state).people if p.id == "bram")
    assert bram.status == "dead" and bram.lines[-1] == "Died of old age, day 821."


def test_far_away_it_is_news_until_a_scene_where_they_lived_tells_it(monkeypatch):
    sure(monkeypatch)
    state = far(valley())
    state.characters["ilse"].age = None
    state = a_year(state, 2)

    (event,) = news(state, DIED)
    assert event.subject_ids == ["bram"] and YOU not in event.known_by
    assert state.characters["bram"].status_history[-1].known_by == []
    bram = next(p for p in memory_view(state).people if p.id == "bram")
    assert bram.status == "alive" and not any("old age" in line for line in bram.lines)
    # Where the dead lived, or within a day of it, a scene can tell it. Nowhere else.
    assert lives.gone(state, "village") == [event]
    assert lives.gone(state, "farm") == [event]
    assert lives.gone(state, "city") == [] and lives.gone(state, None) == []

    told, heard = lives.settle(state, [event.id])

    assert heard == [event.id] and YOU in told.lives[event.id].known_by
    assert state.characters["bram"].status_history[-1].known_by == []  # a new state
    bram = next(p for p in memory_view(told).people if p.id == "bram")
    assert bram.status == "dead" and bram.lines[-1] == "Died of old age, day 821."
    assert lives.gone(told, "village") == []


def test_their_own_partner_who_died_far_from_them_is_news_to_them_too(monkeypatch):
    """Ten years away, and the one they left at home grew old and died. Nobody has told
    them: Memory still has the two together until a scene at home tells it."""
    sure(monkeypatch)
    state = far(valley())
    bond = couple(state, YOU, "ilse", BondStage.MARRIED)

    state = a_year(state, 2)

    event = next(e for e in news(state, DIED) if e.subject_ids == ["ilse", YOU])
    assert YOU not in event.known_by and bond.end is BondEnd.DEATH
    assert state.characters["ilse"].status_history[-1].known_by == []
    assert event in lives.gone(state, "farm")
    ilse = next(p for p in memory_view(state).people if p.id == "ilse")
    assert ilse.status == "alive"

    told, _ = lives.settle(state, [event.id])

    ilse = next(p for p in memory_view(told).people if p.id == "ilse")
    assert ilse.status == "dead" and "Died of old age, day 821." in ilse.lines


def test_their_own_partner_who_died_beside_them_they_know_of(monkeypatch):
    sure(monkeypatch)
    state = valley()
    couple(state, YOU, "ilse", BondStage.MARRIED)
    state.characters["ilse"].seen_s = state.world_s

    state = a_year(state, 2)

    event = next(e for e in news(state, DIED) if e.subject_ids == ["ilse", YOU])
    assert YOU in event.known_by and "ilse" not in state.scene.present_ids
    assert lives.gone(state, "farm") == []


def test_a_strangers_death_is_no_news_of_theirs(monkeypatch):
    sure(monkeypatch)
    stranger = Character(id="hale", name="Hale", age=75, location_id="city")
    state = valley(stranger)
    state.characters["bram"].age = None

    state = a_year(state, 2)

    assert dead(state) == ["hale", "ilse"]
    assert [e.subject_ids for e in news(state, DIED)] == [["ilse", YOU]]
    assert lives.gone(state, "city") == []


def test_the_partner_they_leave_has_it_as_their_news(monkeypatch):
    """When the two meet again, it is under the one left behind, who is in the scene to
    tell it."""
    sure(monkeypatch)
    state = far(valley(villager("mara", "Mara", None)))
    couple(state, "bram", "mara", BondStage.MARRIED)

    state = a_year(state, 2)

    event = next(e for e in news(state, DIED) if e.subject_ids[0] == "bram")
    assert event.subject_ids == ["bram", "mara"]
    assert lives.news_of(state, state.characters["mara"]) == [event]
    assert lives.said(event, "mara") == "lost their partner, who died of old age"
    assert lives.said(event, "bram") == "died of old age"
    assert lives.died(event) == "bram"


def test_a_death_is_told_where_the_scene_names_the_one_who_died(monkeypatch):
    sure(monkeypatch)
    state = far(valley(villager("mara", "Mara", None)))
    couple(state, "bram", "mara", BondStage.MARRIED)
    state = a_year(state, 2)
    event = next(e for e in news(state, DIED) if e.subject_ids[0] == "bram")
    state.scene.present_ids = [YOU, "mara"]

    def heard(scene: str) -> list[str]:
        return pipeline.settle_lives(state, [event.id], scene=scene)[1]

    assert heard("Mara pours the tea and says nothing of the winter.") == []
    assert heard('"Old Bram is in the ground six seasons now," Mara says.') == [event.id]


def test_their_family_in_a_scene_can_tell_it_wherever_the_scene_is(monkeypatch):
    """The dead are in no scene, so a death is told where they lived, or by their family."""
    sure(monkeypatch)
    state = far(
        valley(villager("lena", "Lena", None, parent_ids=["bram"]), villager("wil", "Wil", None))
    )
    state.characters["ilse"].age = None
    state = a_year(state, 2)
    (event,) = news(state, DIED)

    assert lives.gone(state, "city") == [] and lives.gone(state, "city", there=["wil"]) == []
    assert lives.gone(state, "city", there=["wil", "lena"]) == [event]
    assert lives.gone(state, None, there=["lena"]) == [event]


def test_a_partner_the_years_took_before_the_story_named_them_is_told_by_naming_them(monkeypatch):
    """Mara found someone while Tomas was away, and lost them again, and the story never
    named them. No place tells Tomas of someone he never knew of: it is hers to tell, and the
    scene that gives them a name and says it has told it."""
    quiet(monkeypatch)
    monkeypatch.setattr(lives, "PAIR_RATE", 1.0)
    monkeypatch.setattr(lives, "PAIR_FROM_CAST", 0.0)
    state = far(valley(villager("mara", "Mara", 29)))
    state = a_year(state, 2)
    (found,) = news(state, LifeKind.PAIRED)
    partner = state.characters[found.other("mara")]
    monkeypatch.undo()
    sure(monkeypatch)
    for person in state.characters.values():
        person.age = 79 if person.id == partner.id else None

    state = a_year(state, 2)

    (event,) = news(state, DIED)
    assert event.subject_ids == [partner.id, "mara"] and lives.unnamed(partner)
    assert lives.of_old_age(partner) and not lives.of_old_age(state.characters["mara"])
    assert lives.gone(state, "village") == []
    assert event in lives.news_of(state, state.characters["mara"])
    state.characters[YOU].location_id = "village"
    state.scene.place_id, state.scene.present_ids = "village", [YOU, "mara"]

    scene = f"{partner.name} died last winter, Mara says."
    assert pipeline.settle_lives(state, [event.id], played=state, scene=scene)[1] == []

    naming = [CharacterChange(id=partner.id, name="Edrik Hale", known_to_player=True)]
    named = apply_delta(state, StateDelta(characters=naming), ctx(), source=NARRATOR).state
    shown = [found.id, event.id]

    assert lives.told_by_naming(state, named, shown) == [found.id, event.id]
    scene = "Mara looks at her hands. Edrik died last winter, she says."
    told, heard = pipeline.settle_lives(named, played=state, shown=shown, scene=scene)
    assert heard == [found.id, event.id]
    edrik = next(p for p in memory_view(told).people if p.id == partner.id)
    assert edrik.status == "dead"


def test_a_death_they_have_not_heard_of_is_kept_however_old(monkeypatch):
    """K8 keeps only the latest news. A death is the one piece that can't be let go unheard:
    the record would have the dead as dead and no scene could ever tell it."""
    sure(monkeypatch)
    state = a_year(far(valley()), 2)
    (unheard,) = [e for e in news(state, DIED) if e.subject_ids == ["bram"]]
    heard = next(e for e in news(state, DIED) if e.subject_ids[0] == "ilse")
    heard.known_by.append(YOU)
    for n in range(LIVES_KEPT + 5):
        key = state.new_id("life")
        state.lives[key] = lives.LifeEvent(
            id=key, kind=LifeKind.FRIENDS, subject_ids=["a", "b"], world_s=state.world_s + n
        )

    lives._prune(state)

    assert unheard.id in state.lives and heard.id not in state.lives
    assert len(state.lives) == LIVES_KEPT + 1


def test_someone_who_takes_the_story_up_knows_who_of_their_people_died(monkeypatch):
    """N6: they grew up in this world. Their own grandfather's death is no news to them."""
    sure(monkeypatch)
    heir = villager("lena", "Lena", 20, location_id="city")
    heir.known_by, heir.met_by = [YOU, "lena"], [YOU, "lena"]
    state = far(valley(heir))
    state.characters["bram"].met_by.append("lena")
    state.characters["bram"].known_by.append("lena")
    state = a_year(state, 2)

    after = carry_on(state, state.characters["lena"], "Lena wakes.", ending="retired", turn=5)

    bram = next(p for p in memory_view(after, Language.EN).people if p.id == "bram")
    assert bram.status == "dead"
    assert lives.gone(after, "village") == []


def test_nothing_about_old_age_breaks_the_record_over_a_lifetime():
    for seed in range(3, 9):
        state = valley(*(villager(f"v{i}", f"Villager {i}", 20 + 7 * i) for i in range(9)))
        couple(state, "v7", "v8", BondStage.MARRIED)
        state, _ = idle(state, 60 * YEAR, turn=seed)

        assert check_state(state) == []
        for person in state.characters.values():
            if not person.alive:
                assert person.age <= math.ceil(old_age.span(state, person) * 1.3)
                assert bonds.partners(state, person.id) == []
