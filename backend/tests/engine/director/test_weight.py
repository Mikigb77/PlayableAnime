"""R3: a scene's length follows its weight. In Miki's long story, read on 2026-11-10, the typical
scene came to 258 words whether one question was asked or a duel was fought, so code weighs
each scene from what the engine recorded: a passing moment is told short, a turning point gets
room, and anything else gets the length the player's setting gives."""

from engine import pipeline
from engine.base import MINUTE
from engine.context import ImageSetting
from engine.contracts import (
    ActionKind,
    Beat,
    DirectorPlan,
    Intent,
    LinkResolution,
    OutcomeClass,
    PictureTrigger,
    Resolution,
    SceneWeight,
    StopReason,
)
from engine.director.due import in_sight
from engine.director.pictures import key_moment
from engine.director.pressure import Pressure
from engine.director.weight import PASSING_BEATS, PASSING_S, PASSING_WORDS, told, weigh
from engine.samples import farm_world
from engine.state import Deed, EventStatus, Gain, Journey, PendingEvent, StepResult, WorldState
from tests.engine.director.helpers import act, ctx, fence, play_turn, rng
from tests.engine.director.test_pictures import big_deed, died, key_fight, quiet_farm
from tests.engine.director.test_threads import facts

LIGHT, ORDINARY, HEAVY = SceneWeight.LIGHT, SceneWeight.ORDINARY, SceneWeight.HEAVY


def chat(**intent) -> Intent:
    return act("Pass the time of day", "chat", ActionKind.CONVERSATION, 10 * MINUTE, **intent)


def quiet(**kw) -> Pressure:
    """A turn with nothing at stake and no encounter under way."""
    base = dict(
        value=0.0,
        threshold=5.0,
        stakes=False,
        encounter=False,
        turns_without_stakes=1,
        low_stakes_streak=0,
        action_key=None,
    )
    return Pressure(**(base | kw))


def settled(intent: Intent) -> Resolution:
    """The plan as the engine settles it and plays it out on the farm."""
    return play_turn(farm_world(), 2, intent).play.resolution


def weighed(
    resolution: Resolution, *, state=None, intent=None, key=False, planned=False, **kw
) -> SceneWeight:
    pressure = {k: kw.pop(k) for k in ("stakes", "encounter") if k in kw}
    return weigh(
        state or farm_world(),
        resolution,
        facts(2, **kw),
        quiet(**pressure),
        intent,
        key=key,
        planned=planned,
    )


def test_one_small_step_with_nothing_at_stake_is_a_passing_moment():
    resolution = settled(chat())

    assert len(resolution.steps) == 1 and resolution.steps[0].roll is None
    assert weighed(resolution) is LIGHT


def test_something_at_stake_or_more_than_one_small_step_is_an_ordinary_scene():
    resolution = settled(chat())

    assert weighed(resolution, stakes=True) is ORDINARY
    assert weighed(resolution, encounter=True) is ORDINARY
    # Hours of work, and a plan of two steps.
    assert weighed(settled(fence())) is ORDINARY
    twice = Intent(steps=[*chat().steps, *chat().steps])
    assert weighed(settled(twice)) is ORDINARY
    # An opening scene, or a turn that only waits, has no step to call a passing moment.
    assert weighed(Resolution()) is ORDINARY


def changed(resolution: Resolution, **update) -> Resolution:
    step = resolution.steps[0].model_copy(update=update)
    return resolution.model_copy(update={"steps": [step]})


def test_a_step_that_didnt_simply_go_through_is_an_ordinary_scene():
    resolution = settled(chat())

    assert weighed(changed(resolution, outcome_class=OutcomeClass.CONTESTED)) is ORDINARY
    assert weighed(changed(resolution, outcome_class=OutcomeClass.RULED_OUT)) is ORDINARY
    assert weighed(changed(resolution, result=StepResult.PARTIAL)) is ORDINARY
    assert weighed(changed(resolution, interrupted=True)) is ORDINARY
    assert weighed(changed(resolution, duration_s=PASSING_S)) is ORDINARY
    assert weighed(changed(resolution, duration_s=PASSING_S - 1)) is LIGHT
    # Someone met for the first time, and a chain of cause and effect, take telling.
    assert weighed(changed(resolution, strangers=["stranger-1"])) is ORDINARY
    link = LinkResolution(
        text="The lamp tips", outcome_class=OutcomeClass.CERTAIN, reason="It was full", holds=True
    )
    assert weighed(changed(resolution, chain=[link])) is ORDINARY
    stopped = resolution.model_copy(
        update={"stop_reason": StopReason.INTERRUPTED, "unplayed": ["Walk home"]}
    )
    assert weighed(stopped) is ORDINARY


def test_a_long_action_is_an_ordinary_scene():
    """The scene tells each thing the player described and says their lines word for word (R1,
    R7), so an action of many beats or a long speech keeps the setting's own length."""
    resolution = settled(chat())

    def read(**step) -> Intent:
        return Intent(steps=[chat().steps[0].model_copy(update=step)])

    few = [Beat(text=f"Beat {n}") for n in range(PASSING_BEATS)]
    speech = " ".join(["word"] * PASSING_WORDS)
    assert weighed(resolution, intent=read(beats=few, lines=[speech])) is LIGHT
    assert weighed(resolution, intent=read(beats=[*few, Beat(text="One more")])) is ORDINARY
    assert weighed(resolution, intent=read(lines=[speech, "More."])) is ORDINARY


def test_a_scene_with_something_else_to_tell_is_an_ordinary_scene():
    resolution = settled(chat())
    theft = Deed(id="d1", actor_id="tomas", kind="theft", text="", turn=2, world_s=0, severity=1)
    grown = Gain(what="Farming", change="novice to adept", source="practice", reason="")

    # What the director planned for it: an event, a small thing of the moment, talk.
    assert weighed(resolution, planned=True) is ORDINARY
    assert weighed(resolution, deeds=(theft,)) is ORDINARY
    assert weighed(resolution, gains=(("tomas", grown),)) is ORDINARY
    assert weighed(resolution, subdued=frozenset({"bram"})) is ORDINARY
    on_the_road = farm_world()
    on_the_road.journey = Journey(from_id="farm", to_id="village", total_s=3600, done_s=600)
    assert weighed(resolution, state=on_the_road) is ORDINARY
    # Someone else's deed or growth is not this scene's to tell.
    theirs = theft.model_copy(update={"actor_id": "bram"})
    assert weighed(resolution, deeds=(theirs,), gains=(("ilse", grown),)) is LIGHT


def test_what_the_world_did_within_sight_is_something_else_to_tell():
    def farm(place: str | None, *, turn: int = 2) -> WorldState:
        state = farm_world()
        if place is not None:
            state.pending_events["bell"] = PendingEvent(
                id="bell",
                kind="world.clock_step",
                title="The village bell rings",
                due_s=state.world_s,
                place_id=place,
                status=EventStatus.APPLIED,
                applied_turn=turn,
            )
        return state

    assert [e.id for e in in_sight(farm("farm"), ctx(2))] == ["bell"]
    assert in_sight(farm("village"), ctx(2)) == ()  # somewhere else
    assert in_sight(farm("farm", turn=1), ctx(2)) == ()  # another turn's

    light = 0
    for i in range(20):
        story = f"sight-{i}"
        if play_turn(farm(None), 2, chat(), story=story).plan.weight is not LIGHT:
            continue
        light += 1
        assert play_turn(farm("farm"), 2, chat(), story=story).plan.weight is ORDINARY
        assert play_turn(farm("village"), 2, chat(), story=story).plan.weight is LIGHT
    assert light > 5


def test_a_key_scene_is_a_turning_point_whether_or_not_it_gets_a_picture():
    state = quiet_farm()
    died(state, "ilse", 2)
    turn = facts(2, died=frozenset({"ilse"}))
    before = state.director.model_dump()

    for images in ImageSetting:
        key = key_moment(
            state, ctx(2, images=images), turn, state.director, event=None, closed_threads=[]
        )
        assert key is PictureTrigger.DEATH
    assert state.director.model_dump() == before  # it only reads
    assert weighed(settled(chat()), key=True) is HEAVY

    # A key fight's start and its decisive blow, and a grave deed, are key scenes too.
    fight = quiet_farm()
    key_fight(fight, started_turn=2)
    assert _key(fight, facts(2)) is PictureTrigger.FIGHT_START
    assert _key(fight, facts(2, gravely_hurt=frozenset({"bram"}))) is PictureTrigger.DECISIVE_BLOW
    assert _key(quiet_farm(), facts(2, deeds=(big_deed(2),))) is PictureTrigger.BIG_DEED
    # A first portrait, a first visit and the cover are pictures of no turning point.
    assert _key(farm_world(), facts(2)) is None


def _key(state, turn):
    return key_moment(state, ctx(2), turn, state.director, event=None, closed_threads=[])


def test_the_player_character_badly_hurt_is_a_turning_point():
    resolution = settled(chat())

    assert weighed(resolution, gravely_hurt=frozenset({"tomas"})) is HEAVY
    assert weighed(resolution, died=frozenset({"tomas"})) is HEAVY
    # Someone else badly hurt is told, at the setting's own length, unless it is a key scene.
    assert weighed(resolution, gravely_hurt=frozenset({"bram"})) is ORDINARY


def test_a_storys_ending_is_a_turning_point_whatever_the_turn_held():
    plan = DirectorPlan(weight=LIGHT)

    assert told(plan, ending=False) is LIGHT
    assert told(plan, ending=True) is HEAVY
    assert DirectorPlan().weight is ORDINARY


def test_the_director_weighs_every_scene_it_plans():
    """Through the whole director: a quiet word is a passing moment unless the director gave
    the scene something of its own, and a key character's death is a turning point."""
    plans = [play_turn(farm_world(), 2, chat(), story=f"w-{i}").plan for i in range(60)]
    for plan in plans:
        given = plan.event or plan.moment or plan.happenings or plan.talk
        assert plan.weight is (ORDINARY if given else LIGHT)
    assert sum(plan.weight is LIGHT for plan in plans) > 30

    state = quiet_farm()
    died(state, "ilse", 2)
    hold = act("Hold her hand", "hold", ActionKind.INSTANT, 5)
    resolution = pipeline.resolve(state, hold, ctx(2), rng())
    plan = pipeline.direct(state, resolution, ctx(2), rng())
    assert plan.weight is HEAVY
