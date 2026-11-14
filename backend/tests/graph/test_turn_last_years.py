"""N6, W6: the player character's own old age, through a turn.

Nothing announces that old age has begun: once they are old a scene reads them old, where the
record says how long they live. The years stop once when the end is close, and the scene that
opens there is told so, with no number. Going on past the day old age takes them ends their
story on a last scene of its own, and a scene that lengthens their life puts it off. No scene
is ever handed the day.
"""

from engine.base import DAY, YEAR
from engine.context import Language, StorySettings
from engine.state import EventStatus, PendingEvent, WorldState
from engine.world import last_years, lives, old_age
from engine.world.last_years import NEAR_TITLE, TAKES, TAKES_TITLE
from engine.world.scheduling import Kind
from graph.llm import Node, Reply
from graph.turn import prompts
from graph.turn.outputs import NarratorOutput
from tests.engine.test_world_last_years import aged, until_old_age, waiting
from tests.engine.test_world_lives import YOU
from tests.graph.test_turn_context import _section, brief
from tests.graph.test_turn_graph import play, turn_input

SCENE = {
    "narration": "The seasons turn over the valley, one much like the last.",
    "suggestions": [],
    "update": {
        "scene_end": {
            "ended_on": "Tomas looks at his hands.",
            "place_id": "farm",
            "present_ids": ["tomas", "ilse"],
        },
        "summary": "Years went by on the farm.",
    },
}


def works(years: int) -> dict:
    step = {
        "text": f"work the farm for {years} years",
        "verb": "work",
        "kind": "time_skip",
        "proposed_duration_s": years * YEAR,
    }
    return {"summary": "Tomas works the farm.", "steps": [step]}


def a_turn(fake, make_client, state: WorldState, years: int, scene: dict = SCENE, **more):
    """Tomas sets out to work the farm for `years`: the turn's result, and what its narrator
    was told."""
    fake.script(Node.INTERPRET, Reply(json=works(years)))
    fake.script(Node.NARRATOR, Reply(json=scene))
    _, result = play(make_client(), turn_input(state, action="I work the farm", **more))
    return result, fake.calls(Node.NARRATOR)[-1].prompt.messages[-1].text


def task(told: str) -> str:
    return told.split("## TASK\n", 1)[1].split("\n\n## ", 1)[0]


def said(age: int) -> WorldState:
    """Tomas at an age, in a world whose record gives him eighty years."""
    return aged(age, lifespan_years=80)


def near_the_end() -> WorldState:
    """Tomas the day a scene told him the end is close, with the day it comes still ahead."""
    state, _ = until_old_age(said(60), 40)
    return state


def the_day(state: WorldState) -> PendingEvent:
    (takes,) = [
        e
        for e in state.pending_events.values()
        if e.status is EventStatus.PENDING and e.kind == Kind.OLD_AGE
    ]
    return takes


def test_the_years_stop_once_when_the_end_is_close_and_the_scene_is_told(fake, make_client):
    result, told = a_turn(fake, make_client, said(60), 40)

    # Some of the forty years: the rest is theirs to decide on, knowing.
    (step,) = result.resolution.steps
    assert step.interrupted and 4 * YEAR < step.duration_s < 40 * YEAR
    you = result.state.characters[YOU]
    assert result.ending is None and you.alive and you.old_age_span == 80
    assert result.scene.event.title == NEAR_TITLE
    event = _section(told, "EVENT")
    assert event["title"] == NEAR_TITLE and event["kind"] == "loss"
    assert event["brief"].startswith(f"Tomas Weller is {you.age}, of the about 80 years")
    assert "the end of their life is close" in event["brief"]
    assert "give no number of years or days left" in event["brief"]
    # From this scene on they read as near the end, and the record's own counter never shows.
    view = _section(told, "PLAYER CHARACTER")
    assert view["age"] == you.age and "old_age_span" not in view
    assert view["old_age"].startswith(
        f"{you.age} of the about 80 years someone like them lives: the end of their life is "
        "close, they know it"
    )
    assert "lifespan_years" in view["old_age"]


def test_no_scene_is_handed_the_day_or_how_long_is_left(fake, make_client):
    result, told = a_turn(fake, make_client, said(60), 40)

    takes = the_day(result.state)
    assert takes.due_s > result.state.world_s  # the day is on record, still ahead
    # Neither the scene of the stop nor the one after it reads it.
    for read in (told, brief(result.state).user):
        assert "day_s" not in read and str(takes.due_s) not in read
    assert "Nobody knows how long they have" in _section(told, "PLAYER CHARACTER")["old_age"]


def test_the_title_over_the_scene_is_in_the_storys_language(fake, make_client):
    settings = StorySettings(language=Language.ES)

    result, _ = a_turn(fake, make_client, said(60), 40, settings=settings)

    assert result.scene.event.title == "Te quedan pocos años"


def test_nothing_is_said_of_old_age_before_they_are_old():
    told = brief(said(60))

    you = _section(told.user, "PLAYER CHARACTER")
    assert you["age"] == 60 and "old_age" not in you and "old_age_span" not in you


def test_once_old_a_scene_reads_them_old_where_the_record_says_how_long_they_live():
    you = _section(brief(said(70)).user, "PLAYER CHARACTER")

    assert you["old_age"].startswith(
        "70 of the about 80 years someone like them lives: they are old, and it shows in "
        "their body. Nobody knows how long they have, so no scene gives a number."
    )
    # Where eighty years is only the world's assumption, the narrator is not given it.
    assert "old_age" not in _section(brief(aged(70)).user, "PLAYER CHARACTER")


def test_someone_told_before_they_are_old_reads_as_near_the_end(monkeypatch):
    # A day that falls as old age begins: the stop before it comes while they are not yet old.
    monkeypatch.setattr(old_age, "taken_at", lambda lives_years, reached, luck: 68.5)
    state, event = until_old_age(said(60), 40)

    years = last_years.years_of(state, state.world_s)
    assert event is not None and years.told and not years.old
    you = _section(brief(state).user, "PLAYER CHARACTER")
    assert "the end of their life is close, they know it" in you["old_age"]


def test_going_on_past_the_day_ends_the_story_on_a_scene_of_its_own(fake, make_client):
    start = near_the_end()
    takes = the_day(start)

    result, told = a_turn(fake, make_client, start, 40)

    you = result.state.characters[YOU]
    assert not you.alive and lives.of_old_age(you)
    assert result.state.world_s == takes.due_s  # the years stop on the day
    ending = result.ending
    assert (ending.kind, ending.character_id, ending.self_inflicted) == ("death", YOU, False)
    # N6: their last scene ends on them, with no event of its own and nothing to act on.
    assert result.plan.event is None and result.scene.event is None
    assert result.plan.suggestions.count == 0
    assert _section(told, "ENDING") == {"kind": "death"}
    assert task(told) == prompts.OLD_AGE_TASK.strip()
    assert prompts.DEATH_TASK.strip() not in told
    fired = _section(told, "FIRED")
    assert {"title": TAKES_TITLE, "kind": "world.old_age", "needs_you": True} in fired


def test_someone_whose_day_was_left_overdue_dies_before_they_act(fake, make_client):
    """A stretch the event cap cut short leaves what was due pending, and the next turn
    applies it as it begins: their years ran out, and nothing they set out to do happens."""
    start = near_the_end()
    the_day(start).due_s = start.world_s - DAY

    result, told = a_turn(fake, make_client, start, 1)

    assert not result.state.characters[YOU].alive
    assert result.ending.kind == "death" and not result.ending.self_inflicted
    assert result.resolution.steps == [] and result.state.world_s == start.world_s
    assert "died_first" in [issue.code for issue in result.issues]
    assert task(told) == prompts.OLD_AGE_TASK.strip()
    assert "## ACTION" not in told


def test_a_scene_that_lengthens_their_life_puts_old_age_off(fake, make_client):
    start = near_the_end()
    scene = SCENE | {
        "narration": "The peach is cold and sweet, and the years fall from Tomas like a coat.",
        "update": SCENE["update"] | {"characters": [{"id": YOU, "lifespan_years": 300}]},
    }

    result, _ = a_turn(fake, make_client, start, 0, scene=scene)

    state = result.state
    assert "rejected" not in [issue.code for issue in result.issues]
    assert state.characters[YOU].lifespan_years == 300
    # The next time the world looks, the day that was drawn is gone and old age is years off.
    state = until_old_age(state, 1)[0]
    assert waiting(state) == [("near", 300)]
    assert last_years.years_of(state, state.world_s).told is False
    assert "old_age" not in _section(brief(state).user, "PLAYER CHARACTER")


def test_the_scene_of_the_stop_can_answer_that_the_story_has_them_living_far_longer(
    fake, make_client
):
    """A world drafted before peoples said how long they live: eighty years is the world's
    assumption, the scene is told so, and its update can put the real span on record."""
    scene = SCENE | {
        "narration": "Tomas is an elf, and his winters sit on him like one.",
        "update": SCENE["update"] | {"characters": [{"id": YOU, "lifespan_years": 800}]},
    }

    result, told = a_turn(fake, make_client, aged(60), 40, scene=scene)

    asked = _section(told, "EVENT")["brief"]
    assert "The record doesn't say how long they live" in asked and "lifespan_years" in asked
    state = result.state
    assert "rejected" not in [issue.code for issue in result.issues]
    assert state.characters[YOU].lifespan_years == 800
    # The day drawn for eighty years is gone, and old age is centuries off.
    state = until_old_age(state, 1)[0]
    assert waiting(state) == [("near", 800)]
    assert "old_age" not in _section(brief(state).user, "PLAYER CHARACTER")


def test_the_narrators_form_says_when_a_scene_gives_a_lifespan():
    form = NarratorOutput.model_json_schema()["$defs"]["CharacterChange"]
    asked = form["properties"]["lifespan_years"]["description"]

    assert "only when this scene itself lengthened their life" in asked
    assert "or when EVENT asks how long they live" in asked
    assert "1000000 for someone old age can no longer take" in asked
    assert "Never to shorten a life" in asked
    assert "lifespan_years" not in form["required"]


def test_an_old_age_event_of_another_story_line_is_left_alone():
    # A pending event on another timeline is not this one's to cancel or to fire.
    state = near_the_end()
    other = PendingEvent(
        id="elsewhere",
        kind=str(Kind.OLD_AGE),
        title=TAKES_TITLE,
        due_s=state.world_s + DAY,
        timeline_id="other",
        needs_player=True,
        payload={"phase": TAKES, "who": YOU, "span": 80},
    )
    state.pending_events[other.id] = other

    state, event = until_old_age(state, 1 / 12)

    assert event is None and state.characters[YOU].alive
    assert state.pending_events["elsewhere"].status is EventStatus.PENDING
