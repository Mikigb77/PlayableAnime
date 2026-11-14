"""N6, W6, W10: the player character's own old age. Nothing when it begins, a stop when the end
is close, then a real end.

Old age takes everyone else under the tick's dice. The player character's day is drawn once,
by the same odds, and kept where nobody reads it. Some way before it, a part of their span
drawn with it, the years stop once so a scene can let them feel the end is close, with no
number. Going on, it takes them on the day, never within a season of the stop. A longer life
is another span, with a stop of its own, and where the record can't say how long they live,
nothing comes.
"""

import math
import re

import pytest

from engine import bonds, pipeline
from engine.apply import apply_delta
from engine.base import DAY, YEAR
from engine.context import Language
from engine.contracts import CharacterChange, StateDelta
from engine.director import titles
from engine.director.due import world_event
from engine.invariants import check_state
from engine.state import (
    BondStage,
    Creature,
    DeathCertainty,
    EventStatus,
    LadderPosition,
    PendingEvent,
    People,
    PowerLadder,
    Rung,
    WorldState,
)
from engine.state.world import EventSize
from engine.visibility import status_view
from engine.world import last_years, lives, old_age
from engine.world.last_years import ASKED_TITLE, NEAR, NEAR_TITLE, TAKES, TAKES_TITLE
from engine.world.scheduling import Kind
from engine.world.tuning import AGELESS_YEARS, LAST_YEARS, LIFE_QUIET_S, OLD_AGE_FROM

from .test_world import ctx, idle, pending_of, rng
from .test_world_lives import NARRATOR, YOU, couple, valley

OLD_AGE = Kind.OLD_AGE
SEASON = LIFE_QUIET_S


def aged(age: int | None, **more) -> WorldState:
    """The valley, with Tomas at an age."""
    state = valley()
    state.characters[YOU] = state.characters[YOU].model_copy(update={"age": age, **more})
    return state


def realms(state: WorldState, rung: int, *spans: int | None) -> WorldState:
    """The world has a ladder whose rungs live `spans` years, and Tomas stands on `rung`."""
    rungs = [
        Rung(name=f"Realm {i + 1}", tier=2 * (i + 1), lifespan_years=s) for i, s in enumerate(spans)
    ]
    state.bible.ladders = [PowerLadder(id="realms", name="Realms", rungs=rungs)]
    state.characters[YOU].sheet.ladders = [LadderPosition(ladder_id="realms", rung=rung)]
    return state


def looked(state: WorldState, turn: int = 3) -> WorldState:
    """The world looks, with no time passing: what it keeps pending is pending."""
    return pipeline.catch_up(state, state.world_s, ctx(turn), rng(turn)).state


def until_old_age(state: WorldState, years: float = 300, *, turn: int = 3):
    """Let the years pass until old age stops them: the state there and the event, or the
    state those years on and None."""
    until = state.world_s + int(years * YEAR)
    while state.world_s < until:
        passage = pipeline.catch_up(state, until, ctx(turn), rng(turn))
        state, turn = passage.state, turn + 1
        stopped = passage.interrupted_by
        if stopped is not None and stopped.kind == OLD_AGE:
            return state, stopped
    return state, None


def waiting(state: WorldState) -> list[tuple[str, int]]:
    """What is pending of the player character's old age: each stage, and the span it is for."""
    return [(e.payload["phase"], e.payload["span"]) for e in pending_of(state, OLD_AGE)]


def age_now(state: WorldState) -> float:
    return old_age.age_at(state, state.characters[YOU], state.world_s)


def about(state: WorldState, language: Language = Language.EN) -> str:
    return status_view(state, language).sheet.about[-1]


# --- nothing when it begins, a stop when the end is close --------------------------------------


def test_nothing_announces_that_old_age_has_begun():
    state = looked(aged(60, lifespan_years=80))
    (stop,) = pending_of(state, OLD_AGE)

    # Sixty-eight comes and goes: the years run on until the end is close.
    state, fired = idle(state, stop.due_s - DAY)

    assert [e for e in fired if e.kind == OLD_AGE] == []
    you = state.characters[YOU]
    assert you.alive and you.old_age_span is None
    years = last_years.years_of(state, state.world_s)
    assert years.old and not years.told and waiting(state) == [(NEAR, 80)]


def test_the_years_stop_once_when_the_end_is_close():
    state = looked(aged(34))
    start = state.world_s
    (stop,) = pending_of(state, OLD_AGE)
    day_s = stop.payload["day_s"]
    assert stop.payload == {"phase": NEAR, "who": YOU, "span": 80, "day_s": day_s}

    state, event = until_old_age(state, 100)

    # However long the stretch was meant to be, it stops there, some way before the day.
    assert event.payload["phase"] == NEAR and event.needs_player
    assert state.world_s == stop.due_s > start + 30 * YEAR
    low, high = LAST_YEARS
    assert low * 80 * YEAR <= day_s - stop.due_s <= high * 80 * YEAR + 1
    you = state.characters[YOU]
    assert you.alive and you.old_age_span == 80
    # The day was drawn from the first, at an age old age takes people at, and waits there.
    (takes,) = pending_of(state, OLD_AGE)
    assert takes.payload == {"phase": TAKES, "who": YOU, "span": 80}
    assert takes.due_s == day_s >= start + (OLD_AGE_FROM * 80 - 34) * YEAR and takes.needs_player
    # Nothing stops them twice.
    later, fired = idle(state, takes.due_s - DAY)
    assert [e for e in fired if e.kind == OLD_AGE] == []
    assert later.characters[YOU].alive and waiting(later) == [(TAKES, 80)]
    assert check_state(later) == []


def test_the_scene_it_opens_is_told_the_end_is_close_and_no_number():
    state, event = until_old_age(aged(34, lifespan_years=80), 100)
    age = state.characters[YOU].age

    told = world_event(event)

    assert told.title == NEAR_TITLE == "Your years run short"
    assert told.size is EventSize.PERSONAL and told.kind.value == "loss"
    assert told.cast_ids == [YOU]
    assert told.brief.startswith(
        f"Tomas Weller is {age}, of the about 80 years someone like them lives, and the end "
        "of their life is close. The years stop here."
    )
    assert "sense it in their own body" in told.brief and "foresee" in told.brief
    assert "Nobody knows the day: give no number of years or days left." in told.brief
    assert "lengthen their life" in told.brief and "meet the end in peace" in told.brief
    # Their age and how long someone like them lives are the only numbers it holds.
    assert re.findall(r"\d+", told.brief) == [str(age), "80"]


def test_where_the_span_is_only_assumed_the_stop_asks_before_it_tells():
    # The valley's record gives no people a lifespan: eighty years is the world's assumption.
    state, event = until_old_age(aged(34), 100)
    age = state.characters[YOU].age

    asked = world_event(event)

    # Neither its title nor its kind claims a loss: the scene decides what they are.
    assert asked.title == ASKED_TITLE == "The weight of your years"
    assert asked.size is EventSize.PERSONAL and asked.kind.value == "discovery"
    assert asked.brief.startswith(
        "The record doesn't say how long Tomas Weller lives, and takes it for a human life of "
        f"about 80 years, of which they are {age}. Decide first, from WORLD and the story so "
        "far, whether that is what they are. If the story has made them someone who lives far "
        "longer, or whom old age never takes, nothing happens to them here: show no old age,"
    )
    assert "in the update (lifespan_years, 1000000 for never). Only otherwise is the end" in (
        asked.brief
    )
    # What a human is told follows, word for word, with no number of years left.
    assert asked.brief.endswith(last_years._TELLING)
    assert re.findall(r"\d+", asked.brief) == ["80", str(age), "1000000"]
    # They are told for the span the world assumed, until the record says another.
    assert state.characters[YOU].old_age_span == 80 and waiting(state) == [(TAKES, 80)]

    # Where the record says it, of them or of their people or their rung, nothing is asked.
    for said in (aged(34, lifespan_years=80), humans(aged(34), 80), realms(aged(34), 0, 80)):
        _, event = until_old_age(said, 100)
        told = world_event(event)
        assert (told.title, told.kind.value) == (NEAR_TITLE, "loss")
        assert told.brief.endswith(last_years._TELLING) and "record doesn't say" not in told.brief


def test_its_titles_are_said_in_spanish_and_catalan():
    assert titles.said(NEAR_TITLE, Language.ES) == "Te quedan pocos años"
    assert titles.said(NEAR_TITLE, Language.CA) == "Et queden pocs anys"
    assert titles.said(TAKES_TITLE, Language.ES) == "Se te acaban los años"
    assert titles.said(TAKES_TITLE, Language.CA) == "Se t'acaben els anys"
    assert titles.said(ASKED_TITLE, Language.ES) == "El peso de tus años"
    assert titles.said(ASKED_TITLE, Language.CA) == "El pes dels teus anys"
    assert all(titles.written(title) for title in (NEAR_TITLE, TAKES_TITLE, ASKED_TITLE))


def test_a_month_or_ten_years_bring_the_young_nothing():
    for years in (1 / 12, 10):
        state = looked(aged(34))
        (stop,) = pending_of(state, OLD_AGE)

        state, event = until_old_age(state, years)

        assert event is None and state.characters[YOU].old_age_span is None
        assert pending_of(state, OLD_AGE) == [stop]


def test_someone_already_that_close_when_the_story_starts_is_told_a_day_in(monkeypatch):
    monkeypatch.setattr(old_age, "taken_at", lambda lives_years, reached, luck: reached + 0.3)
    state = aged(79)
    start = state.world_s

    first = pipeline.catch_up(state, start, ctx(), rng())  # the opening scene: no time yet
    state, event = until_old_age(first.state, 1)

    assert first.fired == () and first.state.characters[YOU].old_age_span is None
    assert event.payload["phase"] == NEAR and state.world_s == start + DAY
    assert state.characters[YOU].old_age_span == 80 and waiting(state) == [(TAKES, 80)]


def test_how_far_before_the_day_the_years_stop_tells_nobody_the_day():
    parts = []
    for seed in range(3, 27):
        (stop,) = pending_of(looked(aged(34), seed), OLD_AGE)
        parts.append((stop.payload["day_s"] - stop.due_s) / (80 * YEAR))

    low, high = LAST_YEARS
    assert all(low <= part <= high + 1e-9 for part in parts)
    assert len({round(part, 4) for part in parts}) >= 20
    assert min(parts) < 0.02 and max(parts) > 0.03


def test_someone_first_found_older_than_their_kind_lives_is_left_alone():
    # Three hundred among people who live eighty, by means the record doesn't give. Anyone
    # else is given a guessed span (`old_age.own_span`): no guess ends the player's story.
    state = looked(aged(300))

    assert state.characters[YOU].lifespan_years == AGELESS_YEARS
    assert pending_of(state, OLD_AGE) == [] and last_years.years_of(state, 0) is None
    state, event = until_old_age(state, 200)
    assert event is None and state.characters[YOU].alive
    # Someone within the span of their kind has none of their own.
    assert looked(aged(34)).characters[YOU].lifespan_years == 0


# --- it takes them -----------------------------------------------------------------------------


@pytest.mark.parametrize("lives_years", [80, 600])
@pytest.mark.parametrize("part", [0.3, 0.85, 0.95, 1.0, 1.1])
def test_the_day_is_drawn_by_the_odds_of_everyones_old_age(lives_years, part):
    reached = part * lives_years
    for luck in (0.0, 0.01, 0.25, 0.5, 0.9, 0.999, 1.0):
        at = old_age.taken_at(lives_years, reached, luck)

        # The chance of being taken before that age is the luck that was drawn.
        assert old_age.chance(lives_years, reached, at) == pytest.approx(min(luck, 1 - 1e-12))
        assert at >= reached and at >= OLD_AGE_FROM * lives_years
    drawn = [old_age.taken_at(lives_years, reached, n / 50) for n in range(51)]
    assert drawn == sorted(drawn)
    assert drawn[-1] < 1.4 * lives_years  # next to nobody sees a fifth more than their span


def test_the_day_is_never_before_the_age_they_have_reached_whatever_the_rounding():
    # With no luck at all the day is the one they stand on: 80.2 comes out a hair under it.
    ages = [tenths / 10 for tenths in range(690, 1000)]

    assert all(old_age.taken_at(80, age, 0.0) >= age for age in ages)


def test_going_on_past_the_day_ends_their_life():
    state = aged(34)
    start = state.world_s
    couple(state, YOU, "ilse", BondStage.MARRIED)
    state.characters["ilse"].age = None  # she is there to the end
    state, _ = until_old_age(state, 100)
    (takes,) = pending_of(state, OLD_AGE)

    state, event = until_old_age(state, 100)

    assert event.payload["phase"] == TAKES and event.needs_player
    assert state.world_s == takes.due_s  # the years stop there, whatever was meant
    you = state.characters[YOU]
    assert not you.alive and you.death_certainty is DeathCertainty.CONFIRMED
    assert lives.of_old_age(you)
    death = you.status_history[-1]
    assert (death.note, death.known_by, death.world_s) == ("Died of old age.", [YOU], state.world_s)
    # The record has the age they died at, to the year, whenever the world last counted.
    assert you.age == int(34 + (takes.due_s - start) / YEAR)
    assert bonds.partners(state, YOU) == []  # W17: the death ended their marriage
    assert world_event(event).brief == f"Old age takes Tomas Weller, at {you.age}."
    assert check_state(state) == []
    # Nothing more is pending for the dead, and the years leave them the age they died at.
    later, fired = idle(state, state.world_s + 20 * YEAR)
    assert [e for e in fired if e.kind == OLD_AGE] == [] and waiting(later) == []
    assert later.characters[YOU].age == you.age


def test_the_day_never_comes_within_a_season_of_the_stop(monkeypatch):
    monkeypatch.setattr(old_age, "taken_at", lambda lives_years, reached, luck: reached)
    state = looked(aged(79))
    (stop,) = pending_of(state, OLD_AGE)
    # The day on record is the day it comes: a season after a stop made a day in.
    assert stop.due_s == state.world_s + DAY and stop.payload["day_s"] == stop.due_s + SEASON
    state, _ = until_old_age(state, 1)
    told_s = state.world_s

    state, event = until_old_age(state, 1)

    assert event.payload["phase"] == TAKES
    assert state.world_s == told_s + SEASON


def test_a_stop_that_comes_late_still_leaves_a_season():
    """A stretch the event cap cut short leaves the stop overdue. The season runs from the
    scene that tells them, not from when it was due."""
    state = looked(aged(60, lifespan_years=80))
    (stop,) = pending_of(state, OLD_AGE)
    at = state.world_s
    stop.due_s, stop.payload["day_s"] = at - YEAR, at + DAY

    state, event = until_old_age(state, 1)

    assert event.payload["phase"] == NEAR and state.world_s == at
    (takes,) = pending_of(state, OLD_AGE)
    assert takes.payload["phase"] == TAKES and takes.due_s == at + SEASON


def test_a_short_life_is_stopped_a_season_before_the_day_at_the_least(monkeypatch):
    # A people of six years: the last of them is under three months, whatever is drawn.
    monkeypatch.setattr(old_age, "taken_at", lambda lives_years, reached, luck: 5.5)
    state = looked(humans(aged(3), 6))

    (stop,) = pending_of(state, OLD_AGE)

    assert LAST_YEARS[1] * 6 * YEAR < SEASON
    # The day stays the day that was drawn, and the years stop a season before it.
    day_s = stop.payload["day_s"]
    assert day_s == state.world_s + math.ceil((5.5 - age_now(state)) * YEAR)
    assert stop.due_s == day_s - SEASON


def test_the_same_story_finds_the_same_stop_and_day_however_the_years_are_cut():
    first = looked(aged(34))
    (stop,) = pending_of(first, OLD_AGE)

    at_once, _ = until_old_age(first.model_copy(deep=True), 100, turn=9)
    by_days = first.model_copy(deep=True)
    for turn in range(20, 26):  # a week of scenes, each its own turn, then the rest
        by_days = pipeline.catch_up(by_days, by_days.world_s + DAY, ctx(turn), rng(turn)).state
    by_days, _ = until_old_age(by_days, 100, turn=40)
    assert at_once.world_s == by_days.world_s == stop.due_s

    at_once, _ = until_old_age(at_once, 100, turn=10)
    by_days, _ = until_old_age(by_days, 100, turn=77)
    assert at_once.world_s == by_days.world_s == stop.payload["day_s"]
    assert not at_once.characters[YOU].alive and not by_days.characters[YOU].alive


def test_the_days_vary_from_story_to_story_as_everyones_do():
    ages = []
    for seed in range(3, 27):
        state, _ = until_old_age(aged(34), 100, turn=seed)
        state, _ = until_old_age(state, 100, turn=seed + 100)
        ages.append(state.characters[YOU].age)

    assert all(68 <= age <= 100 for age in ages)
    assert len(set(ages)) >= 8 and 74 <= sorted(ages)[len(ages) // 2] <= 86


# --- a longer life is another span -------------------------------------------------------------


def test_a_longer_life_is_another_span_with_a_stop_of_its_own():
    state = realms(aged(34), 0, 80, 200)
    state, _ = until_old_age(state, 100)
    (takes,) = pending_of(state, OLD_AGE)
    assert state.characters[YOU].old_age_span == 80

    # A breakthrough in the time left: the next rung lives two hundred years.
    state.characters[YOU].sheet.ladders[0].rung = 1
    state = looked(state, 9)

    assert waiting(state) == [(NEAR, 200)]
    assert state.pending_events[takes.id].status is EventStatus.CANCELLED
    assert last_years.years_of(state, state.world_s).told is False
    # The day that was drawn for the old span passes and takes nobody.
    state, event = until_old_age(state, 200)
    assert (event.payload["phase"], event.payload["span"]) == (NEAR, 200)
    assert age_now(state) >= (OLD_AGE_FROM - LAST_YEARS[1]) * 200
    assert state.world_s > takes.due_s and state.characters[YOU].alive
    assert state.characters[YOU].old_age_span == 200 and waiting(state) == [(TAKES, 200)]


def test_someone_already_close_for_the_longer_life_is_told_again_a_day_on(monkeypatch):
    state = realms(aged(34), 0, 80, 100)
    state, _ = until_old_age(state, 100)
    monkeypatch.setattr(old_age, "taken_at", lambda lives_years, reached, luck: reached + 0.5)
    state.characters[YOU].sheet.ladders[0].rung = 1
    at = state.world_s

    state, event = until_old_age(state, 1)

    # Half a year from the new day is within the last of a hundred years: they are told.
    assert (event.payload["phase"], event.payload["span"]) == (NEAR, 100)
    assert state.world_s == at + DAY
    assert state.characters[YOU].old_age_span == 100 and waiting(state) == [(TAKES, 100)]


def test_an_event_for_a_span_they_no_longer_have_is_cancelled_and_tells_nobody():
    state = realms(aged(34), 0, 80, 200)
    state, _ = until_old_age(state, 100)
    (takes,) = pending_of(state, OLD_AGE)
    state.characters[YOU].sheet.ladders[0].rung = 1  # after the world last looked
    state.world_s = takes.due_s

    after = pipeline.apply_event(state, state.pending_events[takes.id], ctx(), rng())

    assert after.pending_events[takes.id].status is EventStatus.CANCELLED
    assert not after.pending_events[takes.id].needs_player
    assert after.characters[YOU].alive


def test_a_stop_already_made_is_never_made_again():
    state, _ = until_old_age(aged(34), 100)
    again = PendingEvent(
        id="again",
        kind=str(OLD_AGE),
        title=NEAR_TITLE,
        due_s=state.world_s,
        timeline_id=state.timeline_id,
        needs_player=True,
        payload={"phase": NEAR, "who": YOU, "span": 80, "day_s": state.world_s + YEAR},
    )
    state.pending_events[again.id] = again

    after = pipeline.apply_event(state, again, ctx(), rng())

    assert after.pending_events["again"].status is EventStatus.CANCELLED
    assert waiting(after) == [(TAKES, 80)]
    # And the world's own look cancels whatever stage is behind them.
    assert looked(state).pending_events["again"].status is EventStatus.CANCELLED
    # Even where it is all that is pending: what waits is the day, not a second stop.
    for event in pending_of(state, OLD_AGE):
        if event.id != "again":
            event.status = EventStatus.CANCELLED
    alone = looked(state)
    assert alone.pending_events["again"].status is EventStatus.CANCELLED
    assert waiting(alone) == [(TAKES, 80)]


def test_a_life_lengthened_before_the_stop_is_stopped_for_the_new_life_alone():
    state = looked(realms(aged(34), 0, 80, 200))
    (first,) = pending_of(state, OLD_AGE)
    assert (first.payload["phase"], first.payload["span"]) == (NEAR, 80)

    state.characters[YOU].sheet.ladders[0].rung = 1  # a breakthrough at thirty-four
    state, event = until_old_age(state, 300)

    # The stop that waited was for another life, and so was its day.
    assert state.pending_events[first.id].status is EventStatus.CANCELLED
    assert event.payload["span"] == 200 and state.world_s > first.payload["day_s"]
    assert age_now(state) >= (OLD_AGE_FROM - LAST_YEARS[1]) * 200
    assert state.characters[YOU].old_age_span == 200


def test_a_life_back_at_the_span_they_were_told_for_has_a_day_again():
    state = realms(aged(34), 0, 80, 200)
    state, _ = until_old_age(state, 100)
    state.characters[YOU].sheet.ladders[0].rung = 1
    state = looked(state, 8)
    assert waiting(state) == [(NEAR, 200)]

    state.characters[YOU].sheet.ladders[0].rung = 0  # the rung is lost again
    state = looked(state, 9)

    # They were told for eighty years already, so no second stop: only the day.
    (takes,) = pending_of(state, OLD_AGE)
    assert takes.payload == {"phase": TAKES, "who": YOU, "span": 80}
    assert takes.due_s >= state.world_s + SEASON


def test_a_day_drawn_again_is_never_within_a_season(monkeypatch):
    state = realms(aged(34), 0, 80, 200)
    state, _ = until_old_age(state, 100)
    state.characters[YOU].sheet.ladders[0].rung = 1
    state = looked(state, 8)
    monkeypatch.setattr(old_age, "taken_at", lambda lives_years, reached, luck: reached)

    state.characters[YOU].sheet.ladders[0].rung = 0  # the rung is lost again
    state = looked(state, 9)

    (takes,) = pending_of(state, OLD_AGE)
    assert takes.payload["phase"] == TAKES and takes.due_s == state.world_s + SEASON


def test_of_two_events_for_the_same_stage_one_is_kept():
    state, _ = until_old_age(aged(34), 100)
    (takes,) = pending_of(state, OLD_AGE)
    twin = takes.model_copy(update={"id": "twin", "due_s": takes.due_s + YEAR})
    state.pending_events[twin.id] = twin

    assert waiting(looked(state)) == [(TAKES, 80)]


def test_whoever_takes_the_story_up_has_an_old_age_of_their_own():
    state, _ = until_old_age(aged(34), 100)
    assert waiting(state) == [(TAKES, 80)]
    state.characters["ilse"].age = 40
    state.player_id = "ilse"

    state = looked(state, 9)

    (stop,) = pending_of(state, OLD_AGE)
    assert (stop.payload["phase"], stop.payload["who"], stop.payload["span"]) == (NEAR, "ilse", 80)
    ilse = old_age.age_at(state, state.characters["ilse"], state.world_s)
    assert stop.payload["day_s"] >= state.world_s + (68 - ilse) * YEAR
    # Tomas is one of the world's people now: the dice have him, as they have everyone.
    assert state.characters[YOU].alive and state.characters[YOU].old_age_span == 80


def test_a_stop_drawn_for_whoever_played_before_is_not_theirs():
    # Both live eighty years and neither was told: the stage and the span are the same.
    state = looked(aged(34))
    (his,) = pending_of(state, OLD_AGE)
    state.characters["ilse"].age = 40
    state.player_id = "ilse"

    state = looked(state, 9)

    (hers,) = pending_of(state, OLD_AGE)
    assert state.pending_events[his.id].status is EventStatus.CANCELLED
    assert (hers.payload["phase"], hers.payload["who"], hers.payload["span"]) == (NEAR, "ilse", 80)


# --- the story lengthens a life ----------------------------------------------------------------


def told(state: WorldState, who: str, years: int):
    """A scene's update says how long someone now lives."""
    change = CharacterChange(id=who, lifespan_years=years)
    return apply_delta(state, StateDelta(characters=[change]), ctx(), source=NARRATOR)


def test_a_scene_that_lengthens_their_life_puts_old_age_off_to_the_new_span():
    state, _ = until_old_age(aged(34), 100)
    (takes,) = pending_of(state, OLD_AGE)
    age = state.characters[YOU].age

    # An elixir, a pact: what it was is the scene's. Five hundred years, all told.
    after = told(state, YOU, 500)
    state = looked(after.state, 9)

    assert after.rejected == () and state.characters[YOU].lifespan_years == 500
    assert waiting(state) == [(NEAR, 500)]
    assert state.pending_events[takes.id].status is EventStatus.CANCELLED
    assert about(state) == f"{age} years old"
    state, event = until_old_age(state, 450)
    assert event.payload["phase"] == NEAR
    assert age_now(state) >= (OLD_AGE_FROM - LAST_YEARS[1]) * 500


def test_a_scene_that_ends_their_ageing_ends_their_old_age():
    state, _ = until_old_age(aged(34), 100)

    after = told(state, YOU, 1_000_000_000)  # as good as never, however many zeros
    state, fired = idle(after.state, after.state.world_s + 500 * YEAR)

    you = state.characters[YOU]
    assert you.lifespan_years == 1_000_000 and you.alive
    assert [e for e in fired if e.kind == OLD_AGE] == [] and waiting(state) == []
    assert about(state) == f"{you.age} years old"


def test_a_life_is_never_shortened_by_a_scene():
    state = realms(aged(34), 1, 80, 200)

    for years in (0, -5, 80, 200):
        after = told(state, YOU, years)
        assert after.rejected == () and after.state.characters[YOU].lifespan_years is None
    assert told(state, YOU, 201).state.characters[YOU].lifespan_years == 201


def test_a_scene_lengthens_the_life_of_nobody_it_does_not_reach():
    state = valley()
    state.characters["bram"].age = 72  # in the village, forty minutes from the farm's scene

    after = told(state, "bram", 500)

    assert [(r.subject, r.change) for r in after.rejected] == [("character bram", "lifespan")]
    assert after.state.characters["bram"].lifespan_years is None
    # Ilse is in the scene: what happens in it can.
    assert told(state, "ilse", 500).state.characters["ilse"].lifespan_years == 500


# --- where the record can't say, nothing comes (A2) --------------------------------------------


def humans(state: WorldState, years: int) -> WorldState:
    state.bible.peoples = [People(id="humans", name="humans", lifespan_years=years)]
    state.characters[YOU].people_id = "humans"
    return state


def unsleeping(state: WorldState) -> WorldState:
    state.bible.peoples = [People(id="unsleeping", name="the unsleeping", lifespan_years=0)]
    state.characters[YOU].people_id = "unsleeping"
    return state


def an_ox(state: WorldState) -> WorldState:
    state.bible.creatures = [Creature(id="oxen", name="oxen")]
    state.characters[YOU].people_id = "oxen"
    return state


@pytest.mark.parametrize(
    "state",
    [
        pytest.param(aged(None), id="no age on record"),
        pytest.param(unsleeping(aged(71)), id="a people old age never takes"),
        pytest.param(realms(aged(60), 0, None, None), id="a ladder that carries no lifespans"),
        pytest.param(an_ox(aged(60)), id="a beast"),
        pytest.param(aged(60, lifespan_years=1_000_000), id="a span as good as for ever"),
    ],
)
def test_nothing_comes_where_old_age_never_does_or_the_record_cannot_say(state):
    assert last_years.years_of(state, state.world_s) is None

    state, fired = idle(state, state.world_s + 300 * YEAR)

    assert [e for e in fired if e.kind == OLD_AGE] == [] and waiting(state) == []
    you = state.characters[YOU]
    assert you.alive and you.old_age_span is None


def test_a_people_that_lives_long_grows_old_at_its_own_age():
    state = aged(140, people_id="elves")
    state.bible.peoples = [People(id="elves", name="elves", lifespan_years=600)]

    state, event = until_old_age(state, 700)

    assert (event.payload["phase"], event.payload["span"]) == (NEAR, 600)
    # Never before the last of six hundred years: twenty-four years before five hundred and ten.
    assert age_now(state) >= (OLD_AGE_FROM - LAST_YEARS[1]) * 600


# --- the sheet ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state",
    [
        pytest.param(humans(aged(34), 80), id="a people whose span is on record"),
        pytest.param(aged(34, lifespan_years=90), id="a span of their own"),
        pytest.param(realms(aged(34), 1, 80, 200), id="a rung that lengthens life"),
        pytest.param(aged(34), id="a span the world only assumes"),
    ],
)
def test_the_sheet_says_their_age_and_never_how_long_they_live(state):
    # Miki, 2026-11-14, of "68 of about 80 years": "I don't want that showing in the screen."
    assert about(state) == "34 years old"
    assert about(state, Language.ES) == "34 años"
    assert about(state, Language.CA) == "34 anys"


@pytest.mark.parametrize(
    "state",
    [
        pytest.param(humans(aged(34), 80), id="a span on record"),
        pytest.param(aged(34), id="a span the world only assumes, told by the stop"),
    ],
)
def test_the_sheet_holds_their_age_and_no_other_number_once_the_years_have_stopped(state):
    state, _ = until_old_age(state, 100)
    age = state.characters[YOU].age

    shown = " ".join(status_view(state, Language.EN).sheet.about)

    assert about(state) == f"{age} years old"
    assert re.findall(r"\d+", shown) == [str(age)]


@pytest.mark.parametrize(
    "state",
    [
        pytest.param(unsleeping(aged(71)), id="a people old age never takes"),
        pytest.param(realms(aged(60), 0, None, None), id="a ladder that carries no lifespans"),
    ],
)
def test_the_sheet_says_only_their_age_where_the_record_gives_no_span(state):
    assert about(state) == f"{state.characters[YOU].age} years old"
    assert about(state, Language.ES) == f"{state.characters[YOU].age} años"
