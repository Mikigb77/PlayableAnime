"""S4, through a turn: a scene that closes on the player's move ends before it, the player
never reads it while the scene streams, and only that it happened is logged. A scene that ends
the character's story, and the one that tells them the end of their life is close, keep their
last lines."""

from engine.context import Language, StorySettings
from engine.world import last_years
from engine.world.scheduling import Kind
from graph.llm import Fail, Node, Reply
from graph.turn import NarrationDelta, NarrationReset, TurnKind, last_lines
from graph.turn.outputs import PARAGRAPH
from tests.engine.test_world import pending_of
from tests.engine.test_world_last_years import until_old_age
from tests.graph import test_turn_ending as endings
from tests.graph.test_turn_context import brief
from tests.graph.test_turn_graph import (
    CLIMB,
    FARMING,
    QUIET_SCENE,
    play,
    quiet_farm,
    streamed,
    turn_input,
)
from tests.graph.test_turn_last_years import SCENE as YEARS_SCENE
from tests.graph.test_turn_last_years import a_turn, said
from tests.graph.test_turn_saying import says

SHOWN = "The first winter storm is only weeks away, and your firewood stack is low."
TOLD = (
    "You must decide whether to secure your high home for the long freeze or walk down the "
    "winding mountain path to the village below."
)
ACTION = "You set the hoe against the wall and look over the fields."


def farmed(fake, make_client, scene: dict, **more):
    fake.script(Node.INTERPRET, Reply(json=FARMING))
    # In the order the narrator writes them: the action, the narration, then the rest.
    fake.script(Node.NARRATOR, Reply(json={**scene, "suggestions": []}))
    return play(make_client(), turn_input(quiet_farm(), action="I work the fields", **more))


def told_endings(result) -> list[str]:
    return [i.detail for i in result.issues if i.code == last_lines.ENDING_TOLD]


def test_a_scene_that_closes_on_the_players_move_ends_before_it(fake, make_client, log_lines):
    events, result = farmed(fake, make_client, {"action": ACTION, "narration": f"{SHOWN} {TOLD}"})

    assert result.scene.narration == f"{ACTION}{PARAGRAPH}{SHOWN}"
    # The player read the scene as it was saved, and no piece of it ever held the sentence.
    assert streamed(events) == result.scene.narration
    assert not any("You must" in e.text for e in events if isinstance(e, NarrationDelta))
    assert NarrationReset("retry") not in events
    # Only that it happened is kept and logged: the sentence is story text (T6).
    assert told_endings(result) == ["the scene closed on the player's move: left out"]
    logged = [line["turn_issue"] for line in log_lines() if "turn_issue" in line]
    assert {"code": last_lines.ENDING_TOLD} in logged
    assert "decide whether" not in str(log_lines())


def test_what_the_scene_keeps_of_itself_follows_the_scene_as_it_was_cut(fake, make_client):
    """R3: a scene end that gave only the time is filled from the scene's last sentence, which
    is the one the player read."""
    end = {"ended_on": "19:30", "place_id": "farm", "present_ids": ["tomas"]}

    _, result = farmed(
        fake, make_client, {"narration": f"{SHOWN} {TOLD}", "update": {"scene_end": end}}
    )

    assert result.state.scene.ended_on == SHOWN


def test_a_scene_written_with_its_parts_out_of_order_is_held_to_it_too(fake, make_client):
    """Only the narration streams when the narrator writes it before the action
    (`JsonFieldStreamer`): what went out is still the scene's own words, less the ending."""
    scene = {"narration": f"{SHOWN} {TOLD}", "suggestions": [], "action": ACTION}
    fake.script(Node.INTERPRET, Reply(json=FARMING))
    fake.script(Node.NARRATOR, Reply(json=scene))

    events, result = play(make_client(), turn_input(quiet_farm(), action="I work the fields"))

    assert result.scene.narration == f"{ACTION}{PARAGRAPH}{SHOWN}"
    assert streamed(events) == SHOWN


def test_a_scene_that_shows_streams_and_is_saved_as_it_was_told(fake, make_client):
    scene = f"{SHOWN} {TOLD} Then the dog barks in the yard, and someone knocks at the door below."

    events, result = farmed(fake, make_client, {"narration": scene})

    assert result.scene.narration == scene and streamed(events) == scene
    assert told_endings(result) == []


def test_words_that_waited_go_out_when_the_text_ends_not_when_the_answer_does(fake, make_client):
    """A short last sentence waits, since nothing yet says it won't tell. The rest of the
    narrator's answer (the suggestions, the update) is written after the scene and takes
    seconds, so what waited goes out as soon as the scene's own text is whole."""
    cut_off = '{"narration": "The furrows run straight. The dog barks.", "suggestions": [{"la'
    fake.script(Node.INTERPRET, Reply(json=FARMING))
    fake.script(Node.NARRATOR, Fail(after_text=cut_off), Reply(json=QUIET_SCENE))

    events, result = play(make_client(), turn_input(quiet_farm(), action="I work the fields"))

    retry = events.index(NarrationReset("retry"))
    before = "".join(e.text for e in events[:retry] if isinstance(e, NarrationDelta))
    assert before == "The furrows run straight. The dog barks."
    assert result.scene.narration == QUIET_SCENE["narration"]


def test_an_ending_the_first_telling_would_have_closed_on_never_shows_either(fake, make_client):
    cut_off = '{"narration": "' + f"{SHOWN} {TOLD}" + '", "suggestions": [{"la'
    fake.script(Node.INTERPRET, Reply(json=FARMING))
    fake.script(Node.NARRATOR, Fail(after_text=cut_off), Reply(json=QUIET_SCENE))

    events, _ = play(make_client(), turn_input(quiet_farm(), action="I work the fields"))

    retry = events.index(NarrationReset("retry"))
    assert "".join(e.text for e in events[:retry] if isinstance(e, NarrationDelta)) == SHOWN


def test_a_story_in_spanish_is_held_to_it_too_with_its_lines_still_said(fake, make_client):
    """S10: where the turn's lines are said in the story's language beside the narrator, what
    the telling found is kept with what the saying found."""
    shown = "La primera tormenta del invierno está a pocas semanas, y queda poca leña."
    told = "Debes decidir si aseguras la casa para la helada o bajas al pueblo."
    says(fake)
    fake.script(Node.INTERPRET, Reply(json=CLIMB))
    fake.script(Node.NARRATOR, Reply(json={"narration": f"{shown} {told}", "suggestions": []}))
    settings = StorySettings(language=Language.ES)

    events, result = play(
        make_client(), turn_input(action="Trepo por el muro y me escapo", settings=settings)
    )

    assert result.scene.narration == shown == streamed(events)
    assert len(told_endings(result)) == 1


def test_a_scene_that_ends_their_story_keeps_its_last_line(fake, make_client):
    """N6: the last scene of a life leaves nothing to act on, so its last line tells nobody
    their move."""
    epilogue = "The bar empties, and the city goes on without you. It is time to rest."
    fake.script(Node.NARRATOR, Reply(json={"narration": epilogue, "suggestions": []}))

    result = endings.play(make_client(), endings.turn_input(endings.opened(), TurnKind.END))

    assert result.ending is not None and result.scene.narration == epilogue
    assert told_endings(result) == []


def test_the_scene_that_tells_them_the_end_is_close_may_say_what_is_theirs_to_do(fake, make_client):
    """N6, Miki 2026-11-13: when the years stop, the scene hands the turn back with what they
    can do with the time they have left, which is the one place a scene says so."""
    close = "Your heart beats slow, like a bell under water. The choice is yours."
    scene = YEARS_SCENE | {"narration": close}

    result, _ = a_turn(fake, make_client, said(60), 40, scene)

    assert result.scene.event.title == last_years.NEAR_TITLE
    assert result.scene.narration == close and told_endings(result) == []


def test_the_brief_says_which_scenes_are_held_to_showing():
    state = endings.opened()
    told, stop = until_old_age(said(60), 40)
    (day,) = pending_of(told, Kind.OLD_AGE)

    assert brief(state).ends_shown
    assert not brief(state, ending=endings.Ending(kind="chosen", character_id="luca")).ends_shown
    # The stop before old age is the one event whose scene says what is theirs to do.
    assert last_years.foreseen(stop) and not last_years.foreseen(day)
    assert not last_years.let_come(stop)
