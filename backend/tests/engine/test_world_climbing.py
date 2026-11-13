"""W6, G19: others climb the world's ladders over the years, and nobody is lifted.

Whoever stands on a ladder goes on climbing it at the pace their own record shows, how far
they have come for their age, by the rule the player character climbs by: a rank fills, and
at its peak the climb is thrown for. So the next rung takes about as long again as someone
has been climbing: the young who stand high keep rising and an elder on a low rung dies on it.
Nothing reads the player character's sheet, nobody steps onto a ladder, and every rise is on
record with its reason. Rarely a stroke of fortune lifts one named person a rung. The player
character hears of a rise as of anything else in a life (C6).
"""

import pytest

from engine import levels, pipeline
from engine import talent as talent_mod
from engine.apply import DeltaSource, apply_delta
from engine.base import DAY, HOUR, YEAR
from engine.context import Difficulty, Language
from engine.contracts import CharacterChange, StateDelta
from engine.contracts.intent import GrowthKind
from engine.invariants import check_state
from engine.resolve import throw as dice
from engine.resolve.powers import growth
from engine.state import (
    Character,
    CharacterStatus,
    Creature,
    DeathCertainty,
    LadderPosition,
    LifeKind,
    People,
    WorldState,
)
from engine.state.sheet import Talent, TalentCover, TalentFit, TalentRuling, TalentStrength
from engine.visibility import memory_view
from engine.world import climbing, lives
from engine.world.scheduling import World
from engine.world.tuning import FORTUNE_RATE, LIFE_QUIET_S

from .test_world import ctx, rng
from .test_world_lives import YOU, a_year, news, quiet, valley, villager
from .test_world_old_age import far, realms

ROSE = LifeKind.ROSE
KEY = "ladder:realms"
# The season after the world first counts someone the player character knows is the story's:
# nobody climbs in it, so the first stretch of a test is this much shorter, in years.
QUIET = LIFE_QUIET_S / YEAR


def climbers(*people: Character, lifespans: tuple[int | None, ...] = (0, 0, 0, 0, 0)) -> WorldState:
    """The valley with a ladder of five realms, which lengthen no life unless a test says."""
    state = valley(*people)
    state.bible.ladders = [realms(*lifespans)]
    return state


def on(state: WorldState, who: str, rung: int, stage: str = "", **more) -> LadderPosition:
    position = LadderPosition(ladder_id="realms", rung=rung, stage=stage, **more)
    state.characters[who].sheet.ladders = [position]
    return position


def stands(state: WorldState, who: str) -> LadderPosition:
    (position,) = state.characters[who].sheet.ladders
    return position


def toward(state: WorldState, who: str) -> float:
    """The hours someone's sheet holds toward their next rung."""
    kept = state.characters[who].sheet.practiced(KEY)
    return kept.effort_s / HOUR if kept is not None else 0.0


def gifted(state: WorldState, who: str, strength: TalentStrength) -> None:
    """A talent of theirs that the record has covering the climb."""
    sheet = state.characters[who].sheet
    sheet.talents = [Talent(id="gift", name="a gift for the realms", strength=strength)]
    cover = TalentCover(talent_id="gift", fit=TalentFit.INSIDE)
    sheet.talent_rulings = [TalentRuling(key=KEY, covers=[cover])]


def no_luck(monkeypatch) -> None:
    """No stroke of fortune comes to anyone, so a test reads the years of work alone."""
    monkeypatch.setattr(lives, "FORTUNE_RATE", 0.0)


def throws(monkeypatch, passed: float, close: float = 0.0) -> None:
    """Every attempt at a rung comes out one way, so a test reads what follows from it."""
    shares = dice.Shares(passed, close, 1 - passed - close, 0.0)
    monkeypatch.setattr(climbing, "odds", lambda person, ladder: shares)


def at_once(monkeypatch) -> None:
    """Whoever's rank is full tries the next rung there and then."""
    monkeypatch.setattr(lives, "CLIMB_TRY_AFTER", 0.0)


def plain(monkeypatch, passed: float = 1.0, close: float = 0.0) -> None:
    """Nothing else comes to anyone, no fortune, every attempt made at once and settled."""
    quiet(monkeypatch)
    no_luck(monkeypatch)
    at_once(monkeypatch)
    throws(monkeypatch, passed, close)


# --- The pace ----------------------------------------------------------------------------------


def test_the_pace_of_a_climb_is_how_far_someone_has_come_for_their_age():
    """Every rung behind them, by the player character's own count of what a rung takes, over
    the years since they took the climb up at twelve."""
    state = climbers(villager("peer", "Peer", 30), villager("kid", "Kid", 16))
    ladder = state.bible.ladders[0]

    def yearly(who: str, age: float, rung: int, stage: str = "") -> float:
        position = on(state, who, rung, stage)
        return climbing.yearly_s(state, state.characters[who], ladder, position, age) / HOUR

    assert yearly("peer", 30, 1) == pytest.approx(150 / 18, abs=0.01)
    assert yearly("kid", 16, 0) == pytest.approx(50 / 4, abs=0.01)
    assert yearly("kid", 20, 2) == pytest.approx(350 / 8, abs=0.01)
    # What their stage adds toward the next rung counts as work behind them too.
    assert yearly("peer", 30, 1, "late") == pytest.approx((150 + 200 * 2 / 3) / 18, abs=0.01)
    # A child found on a rung is a quick climber, and not an endlessly quick one.
    assert yearly("kid", 12.5, 0) == yearly("kid", 9, 0) == pytest.approx(50 / 2, abs=0.01)


def test_the_next_rung_takes_about_as_long_again_as_they_have_been_climbing():
    state = climbers(villager("peer", "Peer", 52))
    ladder = state.bible.ladders[0]
    peer = state.characters["peer"]

    def years_to_next(rung: int) -> float:
        position = on(state, "peer", rung)
        return growth.rung_need_s(rung + 1) / climbing.yearly_s(state, peer, ladder, position, 52)

    assert years_to_next(0) == pytest.approx(80, abs=0.1)  # forty years to stand on the lowest
    assert years_to_next(1) == pytest.approx(40 * 4 / 3, abs=0.1)
    assert 40 < years_to_next(3) < years_to_next(2) < 46


def test_a_long_lived_people_take_the_climb_up_later_by_the_same_measure():
    state = climbers(villager("elf", "Elf", 100, people_id="elves"))
    state.bible.peoples = [People(id="elves", name="elves", lifespan_years=600)]
    position = on(state, "elf", 0)
    elf, ladder = state.characters["elf"], state.bible.ladders[0]

    assert climbing.years_at_it(state, elf, 110) == pytest.approx(20)  # since ninety
    assert climbing.years_at_it(state, elf, 91) == pytest.approx(15)  # never under a fortieth
    assert climbing.yearly_s(state, elf, ladder, position, 110) == 2.5 * HOUR


def test_a_people_old_age_never_takes_take_the_climb_up_at_the_age_humans_do():
    """G23: an endless life is no measure of when a climb begins, or of how fast it goes."""
    state = climbers(villager("lich", "Varn", 32, people_id="undead"))
    state.bible.peoples = [People(id="undead", name="the undead", lifespan_years=0)]
    lich = state.characters["lich"]

    assert climbing.years_at_it(state, lich, 32) == pytest.approx(20)  # since twelve
    assert climbing.years_at_it(state, lich, 13) == pytest.approx(2)


def test_on_the_lowest_rung_talent_sets_the_pace_and_above_it_the_record_already_shows_it():
    state = climbers(villager("kid", "Kid", 16))
    kid, ladder = state.characters["kid"], state.bible.ladders[0]

    def yearly(rung: int, strength: TalentStrength | None) -> float:
        kid.sheet.talents, kid.sheet.talent_rulings = [], []
        if strength is not None:
            gifted(state, "kid", strength)
        return climbing.yearly_s(state, kid, ladder, on(state, "kid", rung), 16) / HOUR

    ordinary = yearly(0, None)
    assert yearly(0, TalentStrength.KNACK) == pytest.approx(2 * ordinary)
    assert yearly(0, TalentStrength.GENIUS) == pytest.approx(4 * ordinary)
    assert yearly(0, TalentStrength.ONE_OF_A_KIND) == pytest.approx(8 * ordinary)
    assert yearly(0, TalentStrength.SLOW) == pytest.approx(ordinary / 2)
    assert yearly(2, TalentStrength.ONE_OF_A_KIND) == yearly(2, None) == pytest.approx(350 / 4)


def test_the_climb_is_thrown_for_as_the_player_characters_own_is():
    """Three dice against a level of 3: a talent for the climb adds a green die, one of a kind
    a second, and a weakness throws a die fewer (G19)."""
    state = climbers(villager("kid", "Kid", 16))
    kid, ladder = state.characters["kid"], state.bible.ladders[0]
    number = levels.number(growth.BREAKTHROUGH_LEVEL, Difficulty.BALANCED)

    def passed(strength: TalentStrength | None) -> float:
        kid.sheet.talents, kid.sheet.talent_rulings = [], []
        if strength is not None:
            gifted(state, "kid", strength)
        return climbing.odds(kid, ladder).passed

    assert passed(None) == pytest.approx(dice.chance(dice.Hand(3), 0, number))
    assert passed(TalentStrength.KNACK) == pytest.approx(dice.chance(dice.Hand(3), 1, number))
    assert passed(TalentStrength.ONE_OF_A_KIND) == pytest.approx(
        dice.chance(dice.Hand(3), 2, number)
    )
    assert passed(TalentStrength.SLOW) == pytest.approx(dice.chance(dice.Hand(2), 0, number))
    assert (
        passed(TalentStrength.SLOW) < 0.3 < 0.68 < passed(None) < 0.7 < passed(TalentStrength.KNACK)
    )


# --- What the years do -------------------------------------------------------------------------


def test_a_month_moves_nobody_and_the_years_fill_a_rank(monkeypatch):
    """Miki, 2026-11-13: "If a month went by, obviously there is no time for such things"."""
    plain(monkeypatch)
    state = climbers(villager("peer", "Peer", 30))
    on(state, "peer", 1)

    state = a_year(state, QUIET + 1 / 12)
    assert stands(state, "peer").rung == 1 and stands(state, "peer").stage == ""
    assert toward(state, "peer") == pytest.approx(150 / 18 / 12, abs=0.1)

    state = a_year(state, 10)
    # Eight hours and a third a year: ten years are 84 of the 200 hours the next rung takes.
    assert stands(state, "peer").rung == 1 and stands(state, "peer").stage == "middle"
    assert toward(state, "peer") == pytest.approx(150 / 18 * (10 + 1 / 12), abs=0.1)
    assert state.characters["peer"].sheet.growth == [] and news(state, ROSE) == []


def test_a_full_rank_is_thrown_for_and_a_pass_stands_them_on_the_next_rung(monkeypatch):
    plain(monkeypatch)
    state = climbers(villager("kid", "Kid", 16))
    on(state, "kid", 0)

    state = a_year(state, QUIET + 7)
    assert stands(state, "kid").rung == 0 and stands(state, "kid").stage == "late"

    state = a_year(state, 2)
    kid = state.characters["kid"]
    assert stands(state, "kid").rung == 1 and stands(state, "kid").stage == ""
    # A year past the eight the rung took, at twelve hours and a half a year.
    assert toward(state, "kid") == pytest.approx(12.5, abs=0.2)
    assert kid.sheet.practiced(KEY).what == "Realm 2"
    (gain,) = kid.sheet.growth
    assert (gain.what, gain.source) == ("Realm 1", GrowthKind.BREAKTHROUGH.value)
    assert gain.change == "broke through to Realm 1" and "work" in gain.reason
    assert gain.world_s == state.world_s


def test_a_miss_costs_years_and_a_throw_that_fell_just_short_fewer(monkeypatch):
    """G19: a miss keeps three quarters of the rank and so close nine tenths, as for the player
    character, so whoever fails is at it again only after more work."""
    plain(monkeypatch, passed=0.0)
    missed = climbers(villager("kid", "Kid", 16))
    on(missed, "kid", 0)
    missed = a_year(missed, QUIET + 8.5)

    assert stands(missed, "kid").rung == 0 and stands(missed, "kid").stage == "late"
    assert toward(missed, "kid") == pytest.approx(75 + 12.5 / 2, abs=0.2)
    assert missed.characters["kid"].sheet.growth == []

    throws(monkeypatch, passed=0.0, close=1.0)
    close = climbers(villager("kid", "Kid", 16))
    on(close, "kid", 0)
    close = a_year(close, QUIET + 8.5)

    assert toward(close, "kid") == pytest.approx(90 + 12.5 / 2, abs=0.2)


def test_someone_at_their_peak_tries_in_their_own_time_and_not_overnight(monkeypatch):
    """The story has them ready to try the next rung. A week brings next to none of them to
    it, and a few years bring most."""
    quiet(monkeypatch)
    no_luck(monkeypatch)
    throws(monkeypatch, passed=1.0)

    def risen(years: float) -> int:
        count = 0
        for seed in range(100):
            state = climbers(villager("star", "Star", 20))
            on(state, "star", 2, "peak")
            count += stands(a_year(state, years, seed=seed), "star").rung == 3
        return count

    assert risen(7 / 365) <= 5
    assert risen(3) >= 85


def test_ticks_bring_as_many_up_as_one_long_stretch_would(monkeypatch):
    """W10: nothing is timed in ticks. Ten years in one pass, a year at a time or in
    thirty-seven uneven pieces, about as many of three hundred sixteen-year-olds have left the
    lowest rung, and their pace is the one the first count read."""
    quiet(monkeypatch)
    no_luck(monkeypatch)

    def risen_after(passes: int) -> int:
        risen = 0
        for seed in range(300):
            state = climbers(villager("kid", "Kid", 16))
            on(state, "kid", 0)
            end = state.world_s + 10 * YEAR
            for n in range(passes):
                since = state.world_s
                state.world_s = end if n == passes - 1 else since + 10 * YEAR // passes
                w = World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng(1000 * seed + n))
                lives.live_on(w, since)
            assert stands(state, "kid").yearly_s == pytest.approx(12.5 * HOUR, rel=0.02)
            risen += stands(state, "kid").rung >= 1
        return risen

    whole = risen_after(1)

    assert 90 < whole < 210  # neither nobody nor everybody
    for passes in (10, 37):
        assert abs(risen_after(passes) - whole) <= 30, passes


def test_the_pace_is_read_once_by_the_age_the_stretch_found_them_at(monkeypatch):
    plain(monkeypatch, passed=0.0)
    state = climbers(villager("kid", "Kid", 16))
    on(state, "kid", 0)

    state = a_year(state, 6)
    first = stands(state, "kid").yearly_s
    state = a_year(state, 6)

    assert first == stands(state, "kid").yearly_s == pytest.approx(12.5 * HOUR, rel=0.02)


def test_the_young_who_stand_high_keep_rising_and_an_elder_on_a_low_rung_dies_on_it():
    """Miki, 2026-11-13: after a hundred years "either they are dead of old age or some of
    them might actually successfully improved". Thirty years, over forty stories."""
    rose = {"kid": 0, "peer": 0, "elder": 0, "star": 0}
    for seed in range(40):
        state = far(
            climbers(
                villager("kid", "Kid", 16),
                villager("peer", "Peer", 30),
                villager("elder", "Elder", 70),
                villager("star", "Star", 20),
            )
        )
        start = {"kid": 0, "peer": 1, "elder": 1, "star": 2}
        for who, rung in start.items():
            on(state, who, rung)
        state = a_year(state, 30, seed=seed)
        for who, rung in start.items():
            rose[who] += stands(state, who).rung > rung
        assert not state.characters["elder"].alive and stands(state, "elder").rung <= 2

    assert rose["kid"] == 40 and rose["star"] >= 36
    assert 10 <= rose["peer"] <= 34  # some of them
    assert rose["elder"] <= 2


def test_whoever_broke_through_lives_the_longer_for_it(monkeypatch):
    """Where a rung lengthens life (G19), the climb is ahead of old age in a stretch: an
    elder of ninety-seven on a rung that lives a hundred, at their peak, is dead in ten years
    more often than not if the climb fails, and alive for sure if it comes off."""
    no_luck(monkeypatch)
    at_once(monkeypatch)

    def alive(passed: float) -> int:
        throws(monkeypatch, passed)
        count = 0
        for seed in range(30):
            state = far(climbers(villager("elder", "Elder", 97), lifespans=(100, 300, 600)))
            for person in state.characters.values():
                person.age = 97 if person.id == "elder" else None
            on(state, "elder", 0, "peak")
            count += a_year(state, 10, seed=seed).characters["elder"].alive
        return count

    assert alive(1.0) == 30
    assert alive(0.0) <= 12


# --- Who climbs --------------------------------------------------------------------------------


def test_nobody_steps_onto_a_ladder_and_nobody_passes_its_top(monkeypatch):
    plain(monkeypatch)
    monkeypatch.setattr(lives, "FORTUNE_RATE", 1.0)
    state = climbers(
        villager("farmer", "Farmer", 16),
        villager("sage", "Sage", 40),
        villager("adept", "Adept", 40),
    )
    on(state, "sage", 4)
    on(state, "adept", 3, "peak")

    state = a_year(state, 60)

    assert state.characters["farmer"].sheet.ladders == []
    assert stands(state, "sage").rung == 4 and stands(state, "sage").yearly_s is None
    assert state.characters["sage"].sheet.practice == []
    assert [e.subject_ids for e in news(state, ROSE)] == [["adept"]]
    # Their own work brought the adept to the top, and no stroke of fortune lifts them past it.
    assert stands(state, "adept").rung == 4 and len(state.characters["adept"].sheet.growth) == 1


def test_the_player_character_beasts_the_dead_and_the_ageless_are_left_alone(monkeypatch):
    plain(monkeypatch)
    monkeypatch.setattr(lives, "FORTUNE_RATE", 1.0)
    state = climbers(
        villager("wren", "Wren", None),
        villager("ox", "the ox", 16, people_id="oxen"),
        villager(
            "ghost",
            "Ghost",
            16,
            status=CharacterStatus.DEAD,
            death_certainty=DeathCertainty.CONFIRMED,
        ),
    )
    state.bible.creatures = [Creature(id="oxen", name="oxen")]
    state.characters[YOU].age = 16
    state.characters[YOU].seen_s = 0  # as someone has who took the story up from another (N6)
    for who in (YOU, "wren", "ox", "ghost"):
        on(state, who, 0, "peak")

    state = a_year(state, 30)

    for who in (YOU, "wren", "ox", "ghost"):
        assert stands(state, who) == LadderPosition(ladder_id="realms", rung=0, stage="peak"), who
        assert state.characters[who].sheet.growth == []


def test_someone_in_a_scene_that_no_scene_has_ended_on_is_the_storys(monkeypatch):
    """A stranger in the opening scene: the record has no day yet on which the player
    character was with them, so the years leave their climb to the story for now."""
    plain(monkeypatch)
    stranger = Character(id="hale", name="Hale", age=16, location_id="farm")
    state = climbers(stranger)
    on(state, "hale", 0, "peak")
    state.scene.present_ids.append("hale")

    state = a_year(state, 2)

    assert stands(state, "hale") == LadderPosition(ladder_id="realms", rung=0, stage="peak")
    assert state.characters["hale"].seen_s is None


def test_nobody_is_lifted_to_keep_up_with_the_player_character():
    """Miki, 2026-11-13: "I would feel cheated out of 100 years of training" if everyone rose
    with the character. Nothing in the climb reads the player character's sheet: the same
    years bring everyone else the same, whether they stand on the lowest rung or the top."""

    def others(rung: int) -> dict:
        state = far(
            climbers(
                villager("kid", "Kid", 16),
                villager("peer", "Peer", 30),
                villager("star", "Star", 20),
            )
        )
        for who, at in (("kid", 0), ("peer", 1), ("star", 2)):
            on(state, who, at)
        on(state, YOU, rung)
        state = a_year(state, 40, seed=7)
        return {
            c.id: (c.sheet.ladders, c.sheet.practice, c.sheet.growth)
            for c in state.characters.values()
            if c.id != YOU
        }

    assert others(0) == others(4)


def test_nobody_climbs_in_the_season_after_the_player_character_was_with_them(monkeypatch):
    """Those days are the story's, so someone met yesterday hasn't broken through by the
    world's doing today, and neither has someone in a scene that has yet to end."""
    plain(monkeypatch)
    state = climbers(villager("star", "Star", 20), villager("guest", "Guest", 20))
    on(state, "star", 2, "peak")
    on(state, "guest", 2, "peak")
    state.characters["star"].seen_s = state.world_s
    state.scene.present_ids = [YOU, "ilse", "guest"]

    since = state.world_s
    state.world_s += 30 * DAY
    lives.live_on(World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng(2)), since)

    assert stands(state, "star").rung == 2 and stands(state, "guest").rung == 2

    state = a_year(state, 1)
    assert stands(state, "star").rung == 3


def test_the_story_putting_someone_on_a_rung_has_the_world_read_their_pace_again(monkeypatch):
    plain(monkeypatch, passed=0.0)
    state = climbers(villager("kid", "Kid", 16))
    on(state, "kid", 0)
    state = a_year(state, 2)
    assert stands(state, "kid").yearly_s == pytest.approx(12.5 * HOUR, rel=0.02)

    placed = CharacterChange(id="kid", ladders=[LadderPosition(ladder_id="realms", rung=2)])
    state = apply_delta(
        state, StateDelta(characters=[placed]), ctx(), source=DeltaSource.ENGINE
    ).state
    assert stands(state, "kid").yearly_s is None

    state = a_year(state, 1)
    # Eighteen and a bit when the year began, on the third rung: 350 hours in six years.
    assert stands(state, "kid").yearly_s == pytest.approx(350 / 6.25 * HOUR, rel=0.03)


def test_the_record_holds_together_over_a_hundred_years():
    for seed in range(5):
        state = climbers(
            villager("kid", "Kid", 16),
            villager("peer", "Peer", 30),
            villager("star", "Star", 20),
            lifespans=(120, 250, 500, 1000, 2000),
        )
        for who, rung in (("kid", 0), ("peer", 1), ("star", 2)):
            on(state, who, rung)
        for _ in range(10):
            state = a_year(state, 10, seed=seed)
            assert check_state(state) == []
        assert all(0 <= stands(state, who).rung <= 4 for who in ("kid", "peer", "star"))


# --- Who hears of it (C6) --------------------------------------------------------------------


def test_a_rise_is_known_at_once_to_a_player_character_who_lives_near(monkeypatch):
    plain(monkeypatch)
    state = climbers(villager("kid", "Kid", 16))
    on(state, "kid", 0)

    state = a_year(state, 9)

    (event,) = news(state, ROSE)
    assert (event.subject_ids, event.rung, event.fortune) == (["kid"], "Realm 1", False)
    assert YOU in event.known_by and lives.news_of(state, state.characters["kid"]) == []
    assert lives.said(event, "kid") == "rose to Realm 1"
    kid = next(p for p in memory_view(state).people if p.id == "kid")
    assert any(line.startswith("Rose to Realm 1, ") for line in kid.lines)


def test_far_away_a_rise_is_news_until_a_scene_tells_it_by_naming_them(monkeypatch):
    plain(monkeypatch)
    state = far(climbers(villager("kid", "Kid", 16)))
    on(state, "kid", 0)

    state = a_year(state, 9)

    (event,) = news(state, ROSE)
    kid = state.characters["kid"]
    assert YOU not in event.known_by and lives.news_of(state, kid) == [event]
    assert not any("Realm" in line for p in memory_view(state).people for line in p.lines)

    state.characters[YOU].location_id = "village"
    state.scene.place_id, state.scene.present_ids = "village", [YOU, "kid"]

    def heard(scene: str) -> tuple[WorldState, list[str]]:
        return pipeline.settle_lives(state, [event.id], scene=scene)

    assert heard("The lane is as it was, and nobody says a word of the realms.")[1] == []
    told, ids = heard("Kid bows, and the air about them is that of the first realm now.")
    assert ids == [event.id]
    entry = next(p for p in memory_view(told).people if p.id == "kid")
    assert any(line.startswith("Rose to Realm 1, ") for line in entry.lines)


def test_only_the_latest_rise_nobody_told_is_news(monkeypatch):
    """Thirty years away: where they stand now is the news, not every rung on the way."""
    plain(monkeypatch)
    state = far(climbers(villager("kid", "Kid", 16)))
    on(state, "kid", 0)

    for _ in range(3):
        state = a_year(state, 10)

    assert stands(state, "kid").rung == 2
    assert [(e.subject_ids, e.rung) for e in news(state, ROSE)] == [(["kid"], "Realm 2")]
    assert len(state.characters["kid"].sheet.growth) == 2


def test_a_stranger_someone_missing_and_someone_hiding_their_strength_rise_unheard(monkeypatch):
    """C6, G20: a stranger's rise is no talk of the player character's, nobody saw what
    someone missing did, and whoever hides their strength still shows the rung they showed."""
    plain(monkeypatch)
    state = climbers(
        Character(id="hermit", name="Hermit", age=16, location_id="village"),
        villager("lost", "Lost", 16, status=CharacterStatus.MISSING),
        villager("sly", "Sly", 16),
    )
    on(state, "hermit", 0)
    on(state, "lost", 0)
    on(state, "sly", 0, shown_rung=0)

    state = a_year(state, 9)

    assert news(state, ROSE) == []
    for who in ("hermit", "lost", "sly"):
        assert stands(state, who).rung == 1 and len(state.characters[who].sheet.growth) == 1
    assert stands(state, "sly").shown_rung == 0


# --- A stroke of fortune -------------------------------------------------------------------------


def test_a_stroke_of_fortune_lifts_a_named_person_a_rung_with_its_reason_on_record(monkeypatch):
    """Miki, 2026-11-13: "to all power-ups there should be a reason". The record says it was
    fortune and not the years, and the scene that tells of it says what it was."""
    quiet(monkeypatch)
    monkeypatch.setattr(lives, "FORTUNE_RATE", 1.0)
    monkeypatch.setattr(lives, "PAIR_RATE", 1.0)
    monkeypatch.setattr(lives, "PAIR_FROM_CAST", 0.0)
    state = far(climbers(villager("mara", "Mara", 29)))
    state = a_year(state, 1)
    partner = next(c for c in state.characters.values() if lives.unnamed(c))
    monkeypatch.setattr(lives, "PAIR_RATE", 0.0)
    on(state, "mara", 1)
    on(state, partner.id, 1)
    partner.age, partner.known_by = 29, [YOU]

    state = a_year(state, 1 / 12)

    assert stands(state, "mara").rung == 2 and stands(state, partner.id).rung == 1
    (gain,) = state.characters["mara"].sheet.growth
    assert gain.what == "Realm 2" and "fortune" in gain.reason
    (event,) = news(state, ROSE)
    assert (event.subject_ids, event.rung, event.fortune) == (["mara"], "Realm 2", True)
    assert lives.said(event, "mara").startswith("rose to Realm 2 by a stroke of fortune")
    event.known_by.append(YOU)
    mara = next(p for p in memory_view(state).people if p.id == "mara")
    assert any(line.startswith("Rose to Realm 2 by a stroke of fortune, ") for line in mara.lines)


def test_fortune_is_rare():
    """One in a thousand years each: a month brings nobody one, and ten years bring four
    climbers one in a few stories out of a hundred."""
    assert FORTUNE_RATE == 0.001

    def strokes(years: float) -> int:
        count = 0
        for seed in range(100):
            state = far(climbers(*(villager(f"v{i}", f"Villager {i}", 50) for i in range(4))))
            for i in range(4):
                on(state, f"v{i}", 1)
            state = a_year(state, years, seed=seed)
            count += sum(len(state.characters[f"v{i}"].sheet.growth) for i in range(4))
        return count

    assert strokes(1 / 12) == 0
    assert 1 <= strokes(10) <= 12


# --- Memory, in the story's language (S10) -------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "plain_line", "fortune_line"),
    [
        (Language.EN, "Rose to Realm 1, ", "Rose to Realm 1 by a stroke of fortune, "),
        (Language.ES, "Alcanzó Realm 1, ", "Alcanzó Realm 1 por un golpe de fortuna, "),
        (Language.CA, "Va assolir Realm 1, ", "Va assolir Realm 1 per un cop de fortuna, "),
    ],
)
def test_memory_tells_a_rise_in_the_storys_language(
    monkeypatch, language, plain_line, fortune_line
):
    plain(monkeypatch)
    state = climbers(villager("kid", "Kid", 16))
    on(state, "kid", 0)
    state = a_year(state, 9)
    (event,) = news(state, ROSE)

    def lines() -> list[str]:
        return next(p for p in memory_view(state, language).people if p.id == "kid").lines

    assert any(line.startswith(plain_line) for line in lines())
    event.fortune = True
    assert any(line.startswith(fortune_line) for line in lines())


def test_a_talent_for_the_climb_reaches_it_only_where_the_record_says_so():
    """The helper above rules the talent onto the ladder, as the story does the first time
    someone sets out to climb: a talent the record never placed stays outside."""
    state = climbers(villager("kid", "Kid", 16))
    kid = state.characters["kid"]
    gifted(state, "kid", TalentStrength.GENIUS)
    assert talent_mod.standing(kid, KEY).pace == 4
    kid.sheet.talent_rulings = []
    assert talent_mod.standing(kid, KEY).pace == 1
