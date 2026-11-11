"""W2: the talk of the place is offered softly (Miki, 2026-11-11: "it should be soft. It shouldn't
be like too forced, the part of hearing rumors. And it should also blend with the story. And you
might miss some rumors, that's also okay"). The director only decides that a quiet scene may
carry one piece of it, now and then; the narrator decides whether the scene has room."""

from engine.base import HOUR, MINUTE
from engine.contracts import (
    ActionKind,
    Intent,
    IntentStep,
    PlannedTalk,
    Resolution,
    StandingAction,
)
from engine.director import rules
from engine.director.pressure import Pressure
from engine.director.talk import plan_talk
from engine.samples import farm_world
from engine.state import ActiveTimeEffect, Journey, Rumor, TimeEffect, WorldState
from engine.timekeeping import world_stopped
from tests.engine.director.helpers import act, play_turn, rng, supper

STORIES = [f"talk-{i}" for i in range(300)]
BARN = "The miller's barn burned down in the night."


def village(*, talking: bool = True) -> WorldState:
    """Tomas in Millbrook, which is talking about the miller's barn."""
    state = farm_world()
    state.player.location_id = "village"
    state.scene.place_id = "village"
    state.scene.present_ids = ["tomas"]
    if talking:
        state.rumors["barn"] = Rumor(
            id="barn", text=BARN, is_true=True, reached_place_ids=["village"], started_s=0
        )
    return state


def chat(**intent) -> Intent:
    return act("Pass the time of day", "chat", ActionKind.CONVERSATION, 10 * MINUTE, **intent)


def offered(state: WorldState, intent: Intent, **kw) -> list[PlannedTalk | None]:
    """The talk each of many stories' directors offers the same scene."""
    return [play_turn(state, 2, intent, story=story, **kw).plan.talk for story in STORIES]


def share(talks: list[PlannedTalk | None]) -> float:
    return sum(t is not None for t in talks) / len(talks)


def test_a_quiet_scene_carries_what_the_place_is_saying_only_now_and_then():
    talks = offered(village(), chat())

    assert {t.rumor_id for t in talks if t is not None} == {"barn"}
    assert abs(share(talks) - rules.TALK_CHANCE) < 0.08  # about one scene in three
    # Seeded: the same story offers the same scene the same thing.
    assert offered(village(), chat()) == talks


def test_a_scene_where_they_only_look_on_is_always_offered_it():
    talks = offered(village(), Intent(standing=StandingAction.OBSERVE))

    assert share(talks) == 1 and {t.rumor_id for t in talks} == {"barn"}
    # Waiting is a quiet scene like any other.
    waiting = offered(village(), Intent(standing=StandingAction.WAIT))
    assert abs(share(waiting) - rules.TALK_CHANCE) < 0.08


def test_a_place_with_nothing_new_to_them_may_get_talk_of_the_storys_own_and_rarely():
    talks = offered(village(talking=False), chat())

    assert {t.rumor_id for t in talks if t is not None} == {None}
    assert abs(share(talks) - rules.OWN_TALK_CHANCE) < 0.05
    # Looking on makes it no likelier: there is nothing on record to catch.
    looking = offered(village(talking=False), Intent(standing=StandingAction.OBSERVE))
    assert abs(share(looking) - rules.OWN_TALK_CHANCE) < 0.05


def test_a_scene_that_goes_somewhere_carries_no_talk():
    state = village()
    state.player.location_id = "farm"
    state.scene.place_id = "farm"
    ride = IntentStep(
        text="Gallop to Millbrook",
        verb="ride",
        kind=ActionKind.TRAVEL,
        proposed_duration_s=20 * MINUTE,
        destination="village",
    )

    turns = [play_turn(state, 2, Intent(steps=[ride]), story=story) for story in STORIES[:60]]

    assert all(t.play.resolution.steps[0].trip.arrived for t in turns)
    assert all(t.state.player.location_id == "village" for t in turns)
    assert all(t.plan.talk is None for t in turns)


def test_a_scene_with_something_at_stake_carries_no_talk():
    assert share(offered(village(), chat(), stakes=True)) == 0


def quiet(**kw) -> Pressure:
    base = {"value": 1.0, "threshold": 5.0, "stakes": False, "encounter": False}
    return Pressure(**{**base, **kw}, turns_without_stakes=1, low_stakes_streak=1, action_key=None)


def looking_on(state: WorldState) -> Resolution:
    """A scene in which Tomas only looks on, which is always offered the talk there is."""
    return play_turn(state, 2, Intent(standing=StandingAction.OBSERVE)).play.resolution


def test_a_scene_that_is_about_something_else_carries_no_talk():
    state = village()
    scene = looking_on(state)

    assert plan_talk(state, scene, rng(), pressure=quiet(), busy=False) == PlannedTalk(
        rumor_id="barn"
    )
    # An event or a happening the director already has for the scene.
    assert plan_talk(state, scene, rng(), pressure=quiet(), busy=True) is None
    assert plan_talk(state, scene, rng(), pressure=quiet(encounter=True), busy=False) is None
    assert plan_talk(state, scene, rng(), pressure=quiet(stakes=True), busy=False) is None
    # An opening has no steps: it tells the premise's own situation.
    assert plan_talk(state, Resolution(), rng(), pressure=quiet(), busy=False) is None


def test_no_talk_while_time_stands_still():
    state = village()
    scene = looking_on(state)
    state.time_effects.append(
        ActiveTimeEffect(
            character_id="tomas", power_id="stop", effect=TimeEffect.STOP, started_personal_s=0
        )
    )

    assert world_stopped(state)
    assert plan_talk(state, scene, rng(), pressure=quiet(), busy=False) is None


def test_no_talk_on_the_way_or_off_the_map():
    on_the_way = village()
    scene = looking_on(on_the_way)
    on_the_way.journey = Journey(from_id="farm", to_id="village", total_s=HOUR, done_s=MINUTE)
    lost = village()
    lost.player.location_id = None
    lost.scene.place_id = None

    assert plan_talk(on_the_way, scene, rng(), pressure=quiet(), busy=False) is None
    assert plan_talk(lost, scene, rng(), pressure=quiet(), busy=False) is None


def test_a_scene_with_an_event_carries_no_talk():
    # A quiet life gets its event at the threshold: that scene is about the event.
    state = village()
    turn = 2
    while True:
        played = play_turn(state, turn, supper(), story="talk-event")
        if played.plan.event is not None:
            break
        state, turn = played.state, turn + 1
        assert turn < 30

    assert played.plan.talk is None
