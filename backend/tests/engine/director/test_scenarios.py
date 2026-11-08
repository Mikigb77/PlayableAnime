"""T17's openness scenarios that the director decides, as unit tests over many seeds: quiet life,
long fight, ignored event, themes off, time skip and goal ownership (W16, E4, E6, E7, N1, N2, M1).
"""

import math

import pytest

from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.context import ContentPrefs, EventFrequency
from engine.contracts import (
    ActionKind,
    Aim,
    CharacterChange,
    EventSource,
    Intent,
    PictureKind,
    PictureTrigger,
    StateDelta,
    Theme,
)
from engine.director import rules
from engine.director.deck import CARDS
from engine.director.montage import montage_steps
from engine.samples import cultivation_world, farm_world, grounded_world
from engine.state import (
    Character,
    CharacterSheet,
    DeathCertainty,
    Encounter,
    EncounterKind,
    EventSize,
    EventStatus,
    GoalStatus,
    PendingEvent,
    PowerAxes,
    Prominence,
    ThreadStatus,
)
from tests.engine.director.helpers import act, farming, fence, full_day, play_turn, supper

SEEDS = [f"seed-{i}" for i in range(12)]
LIFE = (farming, supper, fence)


def quiet_life(story: str, frequency: EventFrequency, turns: int = 30, prefs=None):
    """30 turns of farming with a spouse and no ambitions. When an event needs a decision, the
    player deals with it on the next turn, then goes back to the farm."""
    state = farm_world()
    plans = []
    answer: list[str] = []
    for turn in range(1, turns + 1):
        intent = LIFE[turn % len(LIFE)](responds_to=answer)
        played = play_turn(state, turn, intent, story=story, event_frequency=frequency, prefs=prefs)
        state, plan = played.state, played.plan
        plans.append(plan)
        event = plan.event
        answer = [event.thread_id] if event and event.needs_decision and event.thread_id else []
    return state, plans


def quiet_runs(plans) -> list[int]:
    """Runs of turns with no decision to make: no event that needs one, and not answering one."""
    runs, run, answering = [], 0, False
    for plan in plans[1:]:  # the opening plays the premise's own situation
        event = plan.event
        decision = event is not None and event.needs_decision
        if decision:
            runs.append(run)
            run = 0
        elif not answering:
            run += 1
        answering = decision
    return runs


@pytest.mark.parametrize("frequency", [EventFrequency.CALM, EventFrequency.NORMAL])
def test_quiet_life_events_come_at_least_as_often_as_the_threshold_and_stay_farm_sized(
    frequency,
):
    band = math.ceil(rules.THRESHOLDS[frequency] * (1 + rules.DRIFT_SPAN))
    for story in SEEDS:
        state, plans = quiet_life(story, frequency)
        events = [p.event for p in plans if p.event is not None and p.event.needs_decision]
        runs = quiet_runs(plans)

        # Events with stakes arrive at least as often as W16's threshold, drift included.
        assert events, story
        assert max(runs) <= band, (story, runs)
        assert len(events) >= 30 // (band + 1)
        # Farm-sized: a private life never draws a world event.
        assert all(e.size is not EventSize.WORLD for e in events), story
        # Calm returns after each one: never two events back to back.
        assert min(runs) >= 2, (story, runs)
        assert state.director.turns_without_stakes <= band


def test_quiet_life_comes_faster_on_normal_than_on_calm():
    calm = sum(sum(1 for p in quiet_life(s, EventFrequency.CALM)[1] if p.event) for s in SEEDS)
    normal = sum(sum(1 for p in quiet_life(s, EventFrequency.NORMAL)[1] if p.event) for s in SEEDS)
    assert normal > calm


def test_quiet_life_holds_good_things_as_well_as_trouble():
    from engine.director.deck import Tone

    tones = {
        CARDS[p.event.card_id].tone
        for s in SEEDS
        for p in quiet_life(s, EventFrequency.CALM)[1]
        if p.event is not None and p.event.card_id
    }
    assert Tone.GOOD in tones


def mage_fight_world():
    state = cultivation_world()
    state.characters["mage"] = Character(
        id="mage",
        name="the grey mage",
        prominence=Prominence.KEY,
        age=60,
        location_id="well",
        sheet=CharacterSheet(axes=PowerAxes(might=4)),
    )
    state.scene.present_ids.append("mage")
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["mage"], started_turn=2, started_s=0, key=True
    )
    return state


def strike(turn: int) -> Intent:
    intent = act(f"Strike at the mage ({turn})", "strike", ActionKind.EXCHANGE, 10)
    # The mage only parries, so thirty exchanges leave the player character standing (N6).
    intent.steps[0].facts.foes_mean = Aim.NONE
    return intent


def test_long_fight_takes_minutes_brings_nothing_unrelated_and_pictures_its_start_and_blow():
    from engine import pipeline
    from tests.engine.director.helpers import ctx as make_ctx
    from tests.engine.director.helpers import rng as make_rng

    for story in SEEDS[:4]:
        state = mage_fight_world()
        state.director.turns_without_stakes = 20  # pressure was high before the fight
        state.director.pictured = ["portrait:lin", "cover", "place:well", "portrait:zhao"]
        start_s = state.world_s
        pictures, events = [], []
        for turn in range(2, 32):
            intent = strike(turn)
            resolution = None
            if turn == 31:
                # The last exchange kills the mage: the engine's own effect (F4).
                context = make_ctx(turn, story=story)
                resolution = pipeline.resolve(state, intent, context, make_rng(story, turn))
                killing = StateDelta(
                    characters=[
                        CharacterChange(
                            id="mage", status="dead", death_certainty=DeathCertainty.CONFIRMED
                        )
                    ]
                )
                steps = [resolution.steps[0].model_copy(update={"effects": killing})]
                resolution = resolution.model_copy(update={"steps": steps})
            # The scripted strikes name no one, so the fight's own encounter is what keeps those
            # turns from counting as quiet. The engine ends it once the mage is dead, before the
            # director looks, so turn 31 says what a real killing blow aimed at the mage would
            # carry: stakes (W16).
            played = play_turn(
                state, turn, intent, story=story, resolution=resolution, stakes=turn == 31
            )
            state = played.state
            if played.plan.event is not None:
                events.append(played.plan.event)
            if played.plan.picture is not None:
                pictures.append(played.plan.picture)
            assert played.plan.stall_pressure == 0
            assert state.director.turns_without_stakes == 0
            # The engine ends the fight once its only opponent is dead (W10).
            assert (state.scene.encounter is None) == (turn == 31)

        # Thirty exchanges are a few in-world minutes, and the world barely moves (W10).
        assert state.world_s - start_s <= 10 * MINUTE
        assert state.clocks["tournament"].filled == 0  # its first step is hours away
        assert not [e for e in state.pending_events.values() if e.kind.startswith("director.")]
        # No unrelated W16 event interrupts it.
        assert events == []
        # Its start and its decisive blow, and no other key scene.
        scenes = [p.trigger for p in pictures if p.kind is PictureKind.SCENE]
        assert scenes == [PictureTrigger.FIGHT_START, PictureTrigger.DEATH], scenes


def test_long_fight_lets_in_a_pending_event_that_falls_due_within_its_minutes():
    state = mage_fight_world()
    state.pending_events["ally"] = PendingEvent(
        id="ally",
        kind="arrival",
        title="The mage's apprentice arrives",
        due_s=25,
        needs_player=True,
        subject_ids=["zhao"],
    )
    seen = []
    for turn in range(2, 6):
        played = play_turn(state, turn, strike(turn))
        state = played.state
        seen.append(played.plan.event)

    arrived = [e for e in seen if e is not None]
    assert len(arrived) == 1
    assert arrived[0].source is EventSource.DUE and arrived[0].title.startswith("The mage's")


def ignore_event(story: str):
    """An event arrives, then the player farms and sleeps for five days without taking it up."""
    state = farm_world()
    state.director.turns_without_stakes = 9
    first = play_turn(state, 2, full_day(), story=story)
    event = first.plan.event
    assert event is not None and event.needs_decision and event.plays_out_s is not None
    state, later = first.state, []
    for turn in range(3, 8):
        played = play_turn(state, turn, full_day(), story=story)
        state = played.state
        later.append(played.plan)
    return event, state, later


def test_an_ignored_event_plays_out_with_its_consequence_instead_of_repeating():
    for story in SEEDS:
        event, state, later = ignore_event(story)
        outcomes = [
            planned
            for plan in later
            for planned in ([plan.event] if plan.event else []) + plan.happenings
            if planned.thread_id == event.thread_id
        ]

        # It plays out once, with its consequence, needing no decision.
        assert len(outcomes) == 1, story
        played_out = outcomes[0]
        assert played_out.source is EventSource.DUE
        assert not played_out.needs_decision
        assert played_out.brief == event.consequence
        # It never comes back as a fresh event in those turns.
        fresh = [p.event for p in later if p.event and p.event.needs_decision]
        assert all(e.thread_id != event.thread_id for e in fresh)
        assert all(e.card_id is None or e.card_id != event.card_id for e in fresh)
        # Its thread is settled: dormant if the matter lingers, else over without the player.
        thread = state.threads[event.thread_id]
        lingers = CARDS[event.card_id].lingers if event.card_id else True
        assert thread.status is (
            ThreadStatus.DORMANT if lingers else ThreadStatus.RESOLVED_WITHOUT_PLAYER
        )


def test_a_taken_up_event_stops_waiting_and_never_plays_out():
    state = farm_world()
    state.director.turns_without_stakes = 9
    first = play_turn(state, 2, farming())
    event = first.plan.event
    answered = play_turn(first.state, 3, full_day(responds_to=[event.thread_id]))
    state = answered.state
    for turn in range(4, 9):
        played = play_turn(state, turn, full_day())
        state = played.state
        assert all(p.thread_id != event.thread_id for p in played.plan.happenings)
        assert played.plan.event is None or played.plan.event.thread_id != event.thread_id

    waiting = [
        e for e in state.pending_events.values() if e.payload.get("thread_id") == event.thread_id
    ]
    assert [e.status for e in waiting] == [EventStatus.CANCELLED]
    assert state.threads[event.thread_id].taken_up_turn == 3


ROMANCE_OR_DARK = {Theme.ROMANCE, Theme.DARK}


def test_themes_off_never_draws_romance_or_dark_events():
    off = ContentPrefs(romance=False, dark_themes=False)
    drawn = []
    for story in SEEDS * 2:
        _, plans = quiet_life(f"{story}-off", EventFrequency.DRAMATIC, prefs=off)
        drawn += [p.event for p in plans if p.event is not None]
    assert drawn
    assert not [e for e in drawn if ROMANCE_OR_DARK.intersection(e.themes)]


def test_themes_on_do_draw_romance_and_dark_events_so_the_filter_matters():
    drawn = []
    for story in SEEDS * 2:
        _, plans = quiet_life(f"{story}-on", EventFrequency.DRAMATIC)
        drawn += [p.event for p in plans if p.event is not None]
    themes = {t for e in drawn for t in e.themes}
    assert Theme.ROMANCE in themes and Theme.DARK in themes


def a_year_of_farming() -> Intent:
    return act("Farm here for a year", "farm", ActionKind.TIME_SKIP, YEAR)


def test_a_time_skip_stops_early_when_an_event_needs_a_decision():
    stopped = finished = 0
    for story in SEEDS * 2:
        state = farm_world()
        played = play_turn(state, 2, a_year_of_farming(), story=f"{story}-skip")
        step = played.play.resolution.steps[0]
        stop = played.play.interrupted_by
        if stop is None:
            finished += 1
            assert played.state.world_s == YEAR
            assert not step.interrupted
            continue
        stopped += 1
        # The clock stops at the event, the montage is cut there, and the scene starts on it.
        assert stop.kind == "director.event" and stop.needs_player
        assert played.state.world_s == stop.due_s < YEAR
        assert step.interrupted and step.duration_s == stop.due_s
        assert played.plan.event is not None and played.plan.event.needs_decision
        assert played.plan.event.title == stop.title
        # Nothing was rolled for the months after the stop.
        later = [
            e
            for e in played.state.pending_events.values()
            if e.kind == "director.event" and e.due_s > stop.due_s
        ]
        assert later == []
    # A year of a calm life almost always holds something that needs the player.
    assert stopped > finished


def test_a_time_skip_runs_in_a_capped_number_of_steps_however_long_it_is():
    assert len(montage_steps(0, YEAR)) == rules.MONTAGE_MAX_STEPS
    assert len(montage_steps(0, 1000 * YEAR)) == rules.MONTAGE_MAX_STEPS
    assert len(montage_steps(0, 3 * DAY)) == 3
    for story in SEEDS:
        played = play_turn(
            farm_world(),
            2,
            act("Wander for a thousand years", "wander", ActionKind.TIME_SKIP, 1000 * YEAR),
            story=story,
        )
        rolled = [e for e in played.state.pending_events.values() if e.kind == "director.event"]
        assert len(rolled) <= rules.MONTAGE_MAX_STEPS


def test_a_short_action_is_never_a_montage():
    played = play_turn(farm_world(), 2, act("Sleep", "sleep", ActionKind.REST, 8 * HOUR))
    assert not [e for e in played.state.pending_events.values() if e.kind == "director.event"]


# N2: what makes a goal the player's, which nothing ever rewrites.
WORDS = ("id", "text", "set_turn", "lead_id")


def test_goal_ownership_over_fifty_turns_of_normal_play():
    """Goals change only with the player's input (N2): through events, threads going dormant and
    closing, leads offered and expiring, and callbacks, the only new goals are the ones the player
    states or accepts, no goal is ever rewritten, and the only goal that closes is one the player
    accepted from a lead whose thread closed."""
    offered = taken = 0
    for story in SEEDS[:6]:
        state = grounded_world()
        stated = {10: "Take over the family", 30: "Get out of Naples alive"}
        answer: list[str] = []
        before = {g.id: g.model_dump() for g in state.goals.values()}
        for turn in range(1, 51):
            goals = [stated[turn]] if turn in stated else []
            open_leads = [i for i, lead in state.leads.items() if lead.status.value == "open"]
            if turn % 7 == 0 and open_leads:
                answer = [*answer, open_leads[0]]
                taken += 1
            intent = act(
                "Drink at the bar",
                "drink",
                ActionKind.TASK,
                2 * HOUR,
                goals=goals,
                responds_to=answer,
            )
            played = play_turn(state, turn, intent, story=story)
            state, plan = played.state, played.plan
            offered += len(plan.updates.new_leads)
            event = plan.event
            answer = [event.thread_id] if event and event.needs_decision and turn % 2 else []

            after = {g.id: g.model_dump() for g in state.goals.values()}
            for goal_id, goal in before.items():
                now = after[goal_id]
                assert all(now[k] == goal[k] for k in WORDS), (story, turn)  # never rewritten
                if now["status"] is not goal["status"]:
                    assert goal["status"] is GoalStatus.ACTIVE and goal["lead_id"], (story, turn)
                    lead = state.leads[goal["lead_id"]]
                    assert state.threads[lead.thread_id].status.closed, (story, turn)
            added = [after[i] for i in after if i not in before]
            for goal in added:
                assert goal["text"] in goals or goal["lead_id"] in intent.responds_to
            before = after
        texts = {g.text for g in state.goals.values()}
        assert {"Find out who killed my father.", *stated.values()} <= texts
    # The run did offer leads and the player did take some, so goals from leads were exercised.
    assert offered and taken
