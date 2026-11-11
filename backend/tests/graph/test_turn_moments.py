"""W16, W10: a moment through a whole turn. When the story has been quiet and too little time
has passed for one of life's events, the narrator is given a small thing of here and now to
tell, the app is shown no event, and nothing is opened or left to play out (Miki, 2026-11-11:
"100 scenes in the same hour should get events that make sense for this time lap")."""

import json

from engine.base import DAY, HOUR, MINUTE
from engine.contracts import StandingAction
from engine.director.moments import BY_ID
from engine.samples import farm_world
from engine.state import EventSize
from graph.llm import Node, Reply
from graph.turn import TurnKind, prompts
from tests.graph.test_turn_graph import play, section, turn_input

QUIET = {
    "action": "You wait by the gate.",
    "narration": "The afternoon goes on, and the valley with it.",
    "told_talk": False,
    "suggestions": [],
    "update": {"scene_end": {"ended_on": "The gate creaks.", "present_ids": ["tomas"]}},
}


def stalled(since_event_s: int, since_small_s: int | None = None):
    """Tomas on his farm on the story's second day, with the quiet past its threshold and the
    last of life's events `since_event_s` ago."""
    state = farm_world()
    state.turn = 12
    state.world_s = DAY
    state.director.turns_without_stakes = 20
    state.director.last_event_s = {EventSize.PERSONAL: DAY - since_event_s}
    if since_small_s is not None:
        state.director.last_small_s = DAY - since_small_s
    return state


def wait(fake, make_client, state):
    fake.script(Node.NARRATOR, Reply(json=QUIET))
    turn = turn_input(state, kind=TurnKind.STANDING, standing=StandingAction.WAIT)
    result = play(make_client(), turn)[1]
    return fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text, result


def test_an_hour_after_an_event_the_quiet_brings_a_moment_and_no_event(fake, make_client):
    brief, result = wait(fake, make_client, stalled(HOUR))

    moment = json.loads(section(brief, "MOMENT"))
    drawn = result.plan.moment
    assert moment["brief"] == BY_ID[drawn.id].brief and "id" not in moment
    assert "## EVENT" not in brief and "## TALK" not in brief
    # The app marks no event, and nothing waits on the player.
    assert result.scene.event is None
    assert result.state.threads.keys() == farm_world().threads.keys()
    assert not [e for e in result.state.pending_events.values() if e.kind.startswith("director.")]
    after = result.state.director
    assert after.turns_without_stakes == 0
    assert after.last_small_s == result.state.world_s and after.recent_moments == [drawn.id]
    assert after.last_event_s == {EventSize.PERSONAL: DAY - HOUR}


def test_once_the_hours_have_passed_the_quiet_brings_an_event_again(fake, make_client):
    brief, result = wait(fake, make_client, stalled(3 * HOUR))

    assert "## MOMENT" not in brief
    assert json.loads(section(brief, "EVENT"))["title"] == result.scene.event.title
    assert result.state.director.last_event_s[result.plan.event.size] == result.state.world_s


def test_minutes_after_a_small_thing_the_quiet_brings_nothing_yet(fake, make_client):
    brief, result = wait(fake, make_client, stalled(HOUR, since_small_s=3 * MINUTE))

    assert "## MOMENT" not in brief and "## EVENT" not in brief and "## TALK" not in brief
    assert result.scene.event is None
    assert result.state.director.turns_without_stakes == 21  # and the quiet goes on counting


def test_the_narrator_is_told_a_moment_stays_small():
    assert "MOMENT" in prompts.NARRATOR_SYSTEM and "- MOMENT:" in prompts.BRIEF_GUIDE
    assert "It stays small" in prompts.NARRATOR_SYSTEM
