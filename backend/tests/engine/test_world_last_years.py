"""N6, W6, W10: the player character's own old age, a warning first and then a real end.

Old age takes everyone else under the tick's dice. The player character's comes as two events
of their own, at in-world times: it sets in at the age it does for anyone, stopping the years
once so a scene can tell them, and it takes them on a day drawn then by the same odds, never
within a season of the warning. A longer life is another span, with a warning of its own, and
where the record can't say how long they live, nothing comes.
"""

import math

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
from engine.world.last_years import SETS_IN, SETS_IN_TITLE, TAKES, TAKES_TITLE
from engine.world.scheduling import Kind
from engine.world.tuning import AGELESS_YEARS, LIFE_QUIET_S, OLD_AGE_FROM

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


# --- it sets in --------------------------------------------------------------------------------


def test_old_age_sets_in_at_its_age_and_stops_the_years_once():
    state = aged(34)
    start = state.world_s

    state, event = until_old_age(state, 100)

    # Sixty-eight of eighty years, to the day, however long the stretch was meant to be.
    assert event.payload["phase"] == SETS_IN and event.needs_player
    assert state.world_s - start == 34 * YEAR
    assert age_now(state) == pytest.approx(OLD_AGE_FROM * 80)
    you = state.characters[YOU]
    assert you.alive and you.old_age_span == 80
    # The day it takes them is drawn there and then, and never within a season.
    (takes,) = pending_of(state, OLD_AGE)
    assert takes.payload == {"phase": TAKES, "who": YOU, "span": 80}
    assert takes.due_s >= state.world_s + SEASON and takes.needs_player
    # Nothing warns them twice.
    later, fired = idle(state, takes.due_s - DAY)
    assert [e for e in fired if e.kind == OLD_AGE] == []
    assert later.characters[YOU].alive and waiting(later) == [(TAKES, 80)]
    assert check_state(later) == []


def test_the_scene_it_opens_is_told_what_it_means():
    state, event = until_old_age(aged(34), 100)

    told = world_event(event)

    assert told.title == SETS_IN_TITLE == "Old age sets in"
    assert told.size is EventSize.PERSONAL and told.kind.value == "loss"
    assert told.cast_ids == [YOU]
    assert told.brief.startswith("Tomas Weller has grown old: 68, of the about 80 years")
    assert "Half of those who reach this age are gone by 80" in told.brief
    assert "next to nobody sees 96" in told.brief
    assert "lengthens their life" in told.brief


def test_where_the_span_is_only_assumed_the_scene_may_answer_that_they_live_longer():
    # The valley's record gives no people a lifespan: eighty years is the world's assumption.
    _, event = until_old_age(aged(34), 100)
    unsaid = world_event(event).brief
    assert "The record doesn't say how long they live, and takes it for a human life." in unsaid
    assert unsaid.endswith("in the update (lifespan_years, 1000000 for never).")

    # Where the record says it, of them or of their people or their rung, it stands.
    for state in (aged(34, lifespan_years=80), humans(aged(34), 80), realms(aged(34), 0, 80)):
        _, event = until_old_age(state, 100)
        said = world_event(event).brief
        assert said.startswith("Tomas Weller has grown old: 68, of the about 80 years")
        assert said.endswith("puts it off.") and "The record doesn't say" not in said


def test_its_titles_are_said_in_spanish_and_catalan():
    assert titles.said(SETS_IN_TITLE, Language.ES) == "Llega la vejez"
    assert titles.said(SETS_IN_TITLE, Language.CA) == "Arriba la vellesa"
    assert titles.said(TAKES_TITLE, Language.ES) == "Se te acaban los años"
    assert titles.said(TAKES_TITLE, Language.CA) == "Se t'acaben els anys"
    assert titles.written(SETS_IN_TITLE) and titles.written(TAKES_TITLE)


def test_a_month_or_ten_years_bring_the_young_nothing():
    for years in (1 / 12, 10):
        state = aged(34)
        start = state.world_s

        state, event = until_old_age(state, years)

        assert event is None and state.characters[YOU].old_age_span is None
        (sets_in,) = pending_of(state, OLD_AGE)
        assert sets_in.payload["phase"] == SETS_IN
        assert sets_in.due_s == start + 34 * YEAR


def test_someone_who_starts_the_story_old_is_told_a_day_in():
    state = aged(75)
    start = state.world_s

    first = pipeline.catch_up(state, start, ctx(), rng())  # the opening scene: no time yet
    state, event = until_old_age(first.state, 1)

    assert first.fired == () and first.state.characters[YOU].old_age_span is None
    assert event.payload["phase"] == SETS_IN and state.world_s == start + DAY
    assert state.characters[YOU].old_age_span == 80


def test_someone_first_found_older_than_their_kind_lives_is_left_alone():
    # Three hundred among people who live eighty, by means the record doesn't give. Anyone
    # else is given a guessed span (`old_age.own_span`): no guess ends the player's story.
    state = pipeline.catch_up(aged(300), 0, ctx(), rng()).state

    assert state.characters[YOU].lifespan_years == AGELESS_YEARS
    assert pending_of(state, OLD_AGE) == [] and last_years.years_of(state, 0) is None
    state, event = until_old_age(state, 200)
    assert event is None and state.characters[YOU].alive
    # Someone within the span of their kind has none of their own.
    assert pipeline.catch_up(aged(34), 0, ctx(), rng()).state.characters[YOU].lifespan_years == 0


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
    assert you.age == int(68 + (takes.due_s - takes.created_s) / YEAR)
    assert bonds.partners(state, YOU) == []  # W17: the death ended their marriage
    assert world_event(event).brief == f"Old age takes Tomas Weller, at {you.age}."
    assert check_state(state) == []
    # Nothing more is pending for the dead, and the years leave them the age they died at.
    later, fired = idle(state, state.world_s + 20 * YEAR)
    assert [e for e in fired if e.kind == OLD_AGE] == [] and waiting(later) == []
    assert later.characters[YOU].age == you.age


def test_the_day_never_comes_within_a_season_of_the_warning(monkeypatch):
    monkeypatch.setattr(old_age, "taken_at", lambda lives_years, reached, luck: reached)
    state, _ = until_old_age(aged(79), 1)
    told_s = state.world_s

    state, event = until_old_age(state, 1)

    assert event.payload["phase"] == TAKES
    assert state.world_s == told_s + SEASON


def test_the_same_story_finds_the_same_day_however_the_years_are_cut():
    told, _ = until_old_age(aged(34), 100)
    (takes,) = pending_of(told, OLD_AGE)

    at_once, _ = until_old_age(told.model_copy(deep=True), 100, turn=9)
    by_days = told.model_copy(deep=True)
    for turn in range(20, 26):  # a week of scenes, each its own turn, then the rest
        by_days = pipeline.catch_up(by_days, by_days.world_s + DAY, ctx(turn), rng(turn)).state
    by_days, _ = until_old_age(by_days, 100, turn=40)

    assert at_once.world_s == by_days.world_s == takes.due_s
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


def test_a_longer_life_is_another_span_with_a_warning_of_its_own():
    state = realms(aged(34), 0, 80, 200)
    state, _ = until_old_age(state, 100)
    (takes,) = pending_of(state, OLD_AGE)
    assert state.characters[YOU].old_age_span == 80

    # A breakthrough at seventy: the next rung lives two hundred years.
    state, _ = idle(state, state.world_s + 2 * YEAR)
    state.characters[YOU].sheet.ladders[0].rung = 1
    state = pipeline.catch_up(state, state.world_s, ctx(9), rng(9)).state

    assert waiting(state) == [(SETS_IN, 200)]
    assert state.pending_events[takes.id].status is EventStatus.CANCELLED
    assert last_years.years_of(state, state.world_s).set_in is False
    # The day that was drawn for the old span passes and takes nobody.
    state, event = until_old_age(state, 120)
    assert event.payload == {"phase": SETS_IN, "who": YOU, "span": 200} | {
        "event": event.payload["event"]
    }
    assert age_now(state) == pytest.approx(170)
    assert state.world_s > takes.due_s and state.characters[YOU].alive
    assert state.characters[YOU].old_age_span == 200 and waiting(state) == [(TAKES, 200)]


def test_someone_already_old_for_the_longer_life_is_told_again_a_day_on(monkeypatch):
    monkeypatch.setattr(old_age, "taken_at", lambda lives_years, reached, luck: reached + 40)
    state = realms(aged(34), 0, 80, 100)
    state, _ = until_old_age(state, 100)
    state, _ = idle(state, state.world_s + 20 * YEAR)  # eighty-eight, and still here
    state.characters[YOU].sheet.ladders[0].rung = 1
    at = state.world_s

    state, event = until_old_age(state, 1)

    # Eighty-five of a hundred years is where old age begins: they are past it already.
    assert event.payload["phase"] == SETS_IN and event.payload["span"] == 100
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


def test_a_warning_already_given_is_never_given_again():
    state, first = until_old_age(aged(34), 100)
    again = PendingEvent(
        id="again",
        kind=str(OLD_AGE),
        title=SETS_IN_TITLE,
        due_s=state.world_s,
        timeline_id=state.timeline_id,
        needs_player=True,
        payload={"phase": SETS_IN, "who": YOU, "span": 80},
    )
    state.pending_events[again.id] = again

    after = pipeline.apply_event(state, again, ctx(), rng())

    assert after.pending_events["again"].status is EventStatus.CANCELLED
    assert waiting(after) == [(TAKES, 80)]
    # And the world's own look cancels whatever stage is behind them.
    looked = pipeline.catch_up(state, state.world_s, ctx(), rng()).state
    assert looked.pending_events["again"].status is EventStatus.CANCELLED


def test_a_life_lengthened_before_old_age_set_in_is_warned_at_the_new_age_alone():
    state = realms(aged(34), 0, 80, 200)
    state = pipeline.catch_up(state, state.world_s, ctx(), rng()).state
    (first,) = pending_of(state, OLD_AGE)
    assert first.payload == {"phase": SETS_IN, "who": YOU, "span": 80}

    state.characters[YOU].sheet.ladders[0].rung = 1  # a breakthrough at thirty-four
    state, event = until_old_age(state, 300)

    # Sixty-eight comes and goes: the warning that waited there was for another life.
    assert state.pending_events[first.id].status is EventStatus.CANCELLED
    assert event.payload["span"] == 200 and age_now(state) == pytest.approx(170)
    assert state.characters[YOU].old_age_span == 200


def test_a_life_back_at_the_span_they_were_told_for_has_a_day_again():
    state = realms(aged(34), 0, 80, 200)
    state, _ = until_old_age(state, 100)
    state.characters[YOU].sheet.ladders[0].rung = 1
    state = pipeline.catch_up(state, state.world_s, ctx(8), rng(8)).state
    assert waiting(state) == [(SETS_IN, 200)]

    state.characters[YOU].sheet.ladders[0].rung = 0  # the rung is lost again
    state = pipeline.catch_up(state, state.world_s, ctx(9), rng(9)).state

    # They were told for eighty years already, so no second warning: only the day.
    (takes,) = pending_of(state, OLD_AGE)
    assert takes.payload == {"phase": TAKES, "who": YOU, "span": 80}
    assert takes.due_s >= state.world_s + SEASON


def test_of_two_events_for_the_same_stage_one_is_kept():
    state, _ = until_old_age(aged(34), 100)
    (takes,) = pending_of(state, OLD_AGE)
    twin = takes.model_copy(update={"id": "twin", "due_s": takes.due_s + YEAR})
    state.pending_events[twin.id] = twin

    looked = pipeline.catch_up(state, state.world_s, ctx(), rng()).state

    assert waiting(looked) == [(TAKES, 80)]


def test_whoever_takes_the_story_up_has_an_old_age_of_their_own():
    state, _ = until_old_age(aged(34), 100)
    assert waiting(state) == [(TAKES, 80)]
    state.characters["ilse"].age = 40
    state.player_id = "ilse"

    state = pipeline.catch_up(state, state.world_s, ctx(9), rng(9)).state

    (sets_in,) = pending_of(state, OLD_AGE)
    assert sets_in.payload == {"phase": SETS_IN, "who": "ilse", "span": 80}
    ilse = old_age.age_at(state, state.characters["ilse"], state.world_s)
    assert sets_in.due_s == state.world_s + math.ceil((68 - ilse) * YEAR)
    # Tomas is one of the world's people now: the dice have him, as they have everyone.
    assert state.characters[YOU].alive and state.characters[YOU].old_age_span == 80


# --- the story lengthens a life ----------------------------------------------------------------


def told(state: WorldState, who: str, years: int):
    """A scene's update says how long someone now lives."""
    change = CharacterChange(id=who, lifespan_years=years)
    return apply_delta(state, StateDelta(characters=[change]), ctx(), source=NARRATOR)


def test_a_scene_that_lengthens_their_life_puts_old_age_off_to_the_new_span():
    state, _ = until_old_age(aged(34), 100)
    (takes,) = pending_of(state, OLD_AGE)

    # An elixir, a pact: what it was is the scene's. Five hundred years, all told.
    after = told(state, YOU, 500)
    state = pipeline.catch_up(after.state, after.state.world_s, ctx(9), rng(9)).state

    assert after.rejected == () and state.characters[YOU].lifespan_years == 500
    assert waiting(state) == [(SETS_IN, 500)]
    assert state.pending_events[takes.id].status is EventStatus.CANCELLED
    assert about(state) == "68 of about 500 years"
    state, event = until_old_age(state, 400)
    assert event.payload["phase"] == SETS_IN and age_now(state) == pytest.approx(425)


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
    start = state.world_s

    state, event = until_old_age(state, 500)

    assert event.payload == {"phase": SETS_IN, "who": YOU, "span": 600} | {
        "event": event.payload["event"]
    }
    assert state.world_s - start == 370 * YEAR  # five hundred and ten, of six hundred


# --- the sheet ---------------------------------------------------------------------------------


def about(state: WorldState, language: Language = Language.EN) -> str:
    return status_view(state, language).sheet.about[-1]


def test_the_sheet_says_their_age_of_how_many_years_where_the_record_says_how_long_they_live():
    state = humans(aged(34), 80)

    assert about(state) == "34 of about 80 years"
    assert about(state, Language.ES) == "34 años de unos 80"
    assert about(state, Language.CA) == "34 anys d'uns 80"
    # A span of their own says it too, and a rung that lengthens life shows at once.
    assert about(aged(34, lifespan_years=90)) == "34 of about 90 years"
    assert about(realms(aged(34), 1, 80, 200)) == "34 of about 200 years"


def test_a_span_the_world_only_assumes_is_on_the_sheet_once_a_scene_has_told_it():
    state = aged(34)
    assert about(state) == "34 years old" and about(state, Language.CA) == "34 anys"

    state, _ = until_old_age(state, 100)

    assert about(state) == "68 of about 80 years"


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
