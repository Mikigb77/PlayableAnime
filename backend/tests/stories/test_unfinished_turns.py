"""A3 over HTTP: the engine's decided steps go out before the telling, dice and all, and a turn
that was shown is played out as it was decided, whatever is sent next (T10, T5, T6)."""

import pytest
from asgiref.sync import async_to_sync
from django.test import Client

from billing import meter
from billing.models import CreditHold, LedgerEntry
from engine.context import Difficulty, EventFrequency, StorySettings
from engine.contracts import StandingAction
from engine.state.world import WorldState
from graph.llm import Fail, Node, Reply
from graph.turn import TurnKind
from stories import owner_export, turns, unfinished
from stories.export import export_stories
from stories.models import Scene, Story
from stories.schemas import TurnIn
from tests.conftest import auth_headers
from tests.stories.conftest import parse_events, play
from tests.stories.test_endings import EPILOGUE
from tests.stories.test_turns import AFTER, STEP_AROUND, assert_nothing_saved, opened

pytestmark = pytest.mark.django_db

# A step the dice settle (A2): a hard task with no move behind it.
CLIMB = {
    "summary": "Lin climbs the wall of the well.",
    "steps": [
        {
            "text": "climb the wet wall of the well",
            "verb": "climb",
            "kind": "task",
            "proposed_duration_s": 30,
            "facts": {"challenge": "hard"},
        }
    ],
}
CLIMBED = {
    "narration": "Moss gives under your fingers as you haul yourself up the wall.",
    "suggestions": [{"label": "Look down", "kind": "thread"}],
    "update": {
        "scene_end": {"ended_on": "Zhao watches from below.", "present_ids": ["lin", "zhao"]}
    },
}
THE_CLIMB = {
    "kind": "action",
    "action": "I climb the wall of the well",
    "input_mode": "voice",
    "expected_version": 2,
}
SOMETHING_ELSE = {"kind": "action", "action": "I step around Zhao", "expected_version": 2}


@pytest.fixture(autouse=True)
def quick_play(settings, starter_credit_for_everyone):
    """The per-minute turn limit (T9) is lifted: these stories play faster than anyone types."""
    settings.BILLING = {
        **settings.BILLING,
        "PER_MINUTE": {**settings.BILLING["PER_MINUTE"], "turn": 1000},
    }


@pytest.fixture
def client(player) -> Client:
    return Client(headers=auth_headers(player))


def cast(player, story: Story, model, body=THE_CLIMB):
    """Plays the climb until its dice are shown, and then the narrator fails twice: the turn is
    left with its dice cast and no scene saved."""
    model.backend.script(Node.INTERPRET, Reply(json=CLIMB))
    model.backend.script(Node.NARRATOR, Fail(), Fail())
    played = play(player, story, body)
    assert played.names == ["turn.started", "steps.decided", "error"], played.events
    assert played.named("error")[0]["code"] == "llm_unavailable"
    return played


def decided(played) -> dict:
    [data] = played.named("steps.decided")
    return data


def throw_of(played) -> dict:
    return decided(played)["details"]["steps"][0]["roll"]["throw"]


def shown(client, story: Story) -> dict:
    return client.get(f"/v1/stories/{story.pk}").json()


def owed(story: Story):
    return Story.objects.get(pk=story.pk).unfinished_turn


def stream(player, prepared: turns.PreparedTurn) -> list:
    async def run() -> bytes:
        ticket = await meter.astart(player, meter.TURN)
        chunks = turns.stream(prepared, ticket=ticket, byok=None)
        return b"".join([chunk async for chunk in chunks])

    return parse_events(async_to_sync(run)())


# --- the stream ----------------------------------------------------------------------------------


def test_the_decided_steps_go_out_before_the_telling_with_the_dice_the_scene_keeps(
    client, player, make_story, model
):
    story = opened(player, make_story, model)
    model.backend.script(Node.INTERPRET, Reply(json=CLIMB))
    model.backend.script(Node.NARRATOR, Reply(json=CLIMBED))

    played = play(player, story, THE_CLIMB)

    assert played.names[:2] == ["turn.started", "steps.decided"]
    assert set(played.names[2:-1]) == {"narration.delta"}
    assert played.names[-1] == "scene.completed"
    assert played.named("turn.started") == [{"turn": 2}]
    assert decided(played)["turn"] == 2
    # The scene carries exactly what was shown before a word of it was written.
    scene = played.completed["scene"]
    assert scene["details"] == decided(played)["details"]
    assert Scene.objects.get(story=story, turn=2).details == decided(played)["details"]
    thrown = throw_of(played)
    assert set(thrown) == {
        "dice",
        "hand",
        "hand_why",
        "greens",
        "number",
        "made_of",
        "total",
        "most",
        "mark",
        "against",
        "deadly",
        "miss_costs",
        "insight",
        "insight_at",
    }
    assert len(thrown["dice"]) >= thrown["hand"] >= 1
    assert all(set(die) == {"kind", "face", "sprung"} for die in thrown["dice"])
    assert thrown["total"] == sum(die["face"] for die in thrown["dice"])
    assert thrown["mark"] in {"passed", "so_close", "missed", "over_the_top"}
    assert sum(part["points"] for part in thrown["made_of"]) == thrown["number"]
    # Its scene is saved, so the story owes nothing.
    assert owed(story) is None
    assert shown(client, story)["unfinished_turn"] is None


def test_an_opening_has_no_steps_to_send(player, make_story, model):
    story = opened(player, make_story, model)

    assert Scene.objects.get(story=story, turn=1).details["steps"] == []
    assert owed(story) is None


def test_a_turn_with_no_dice_is_owed_too_once_its_steps_are_shown(
    client, player, make_story, model
):
    """A step that is certain shows how it went as well: a fall that kills, or what a search
    found. So it is played out like a throw."""
    story = opened(player, make_story, model)
    model.backend.script(Node.NARRATOR, Fail(), Fail())

    failed = play(player, story, {"kind": "standing", "standing": "wait", "expected_version": 2})

    assert failed.names == ["turn.started", "steps.decided", "error"]
    assert [step["roll"] for step in decided(failed)["details"]["steps"]] == [None]
    assert shown(client, story)["unfinished_turn"] == {
        "turn": 2,
        "kind": "standing",
        "action": "wait",
    }
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))
    played = play(player, story, SOMETHING_ELSE)
    assert played.named("turn.started") == [
        {"turn": 2, "resumed": True, "kind": "standing", "action": "wait"}
    ]
    scene = played.completed["scene"]
    assert (scene["kind"], scene["player_action"], scene["input_mode"]) == (
        "standing",
        "wait",
        "choice",
    )
    assert scene["details"] == decided(failed)["details"]
    assert model.backend.calls(Node.INTERPRET) == []
    assert owed(story) is None


# --- once the dice are cast ----------------------------------------------------------------------


def test_a_turn_whose_dice_were_cast_is_played_out_whatever_is_sent_next(
    client, player, make_story, model
):
    story = opened(player, make_story, model)

    first = cast(player, story, model)

    # No scene, no charge, and the world as it was: only the turn it owes is kept.
    assert_nothing_saved(story, player)
    assert shown(client, story)["unfinished_turn"] == {
        "turn": 2,
        "kind": "action",
        "action": "I climb the wall of the well",
    }

    # Another action is sent. The climb plays, read as it was and on the same dice.
    model.backend.script(Node.NARRATOR, Reply(json=CLIMBED))
    played = play(player, story, SOMETHING_ELSE)

    assert played.named("turn.started") == [
        {"turn": 2, "resumed": True, "kind": "action", "action": "I climb the wall of the well"}
    ]
    assert decided(played) == decided(first)
    scene = played.completed["scene"]
    assert scene["player_action"] == "I climb the wall of the well"
    assert scene["input_mode"] == "voice"
    assert scene["details"] == decided(first)["details"]
    assert scene["narration"] == CLIMBED["narration"]
    # The action was read once: nothing reads it again, or reads the one sent instead.
    assert len(model.backend.calls(Node.INTERPRET)) == 1
    assert played.completed["story"]["version"] == 3
    assert owed(story) is None
    assert shown(client, story)["unfinished_turn"] is None
    # K2: charged once, when it was saved.
    assert LedgerEntry.objects.filter(user_id=player.pk, kind="turn").count() == 2
    assert not CreditHold.objects.exists()


def test_a_resume_request_plays_out_the_turn_and_is_refused_when_none_is_owed(
    player, make_story, model
):
    story = opened(player, make_story, model)
    resume = {"kind": "resume", "expected_version": 2}

    nothing = play(player, story, resume)

    assert nothing.status == 400
    [problem] = nothing.body["error"]["details"]["fields"]
    assert (problem["field"], problem["type"]) == ("kind", "nothing_unfinished")
    assert not CreditHold.objects.exists()

    first = cast(player, story, model)
    model.backend.script(Node.NARRATOR, Reply(json=CLIMBED))
    played = play(player, story, resume)

    assert played.named("turn.started")[0]["resumed"] is True
    assert played.completed["scene"]["details"] == decided(first)["details"]
    assert played.completed["scene"]["kind"] == "action"


def test_a_resume_request_takes_no_action_of_its_own(player, make_story, model):
    story = opened(player, make_story, model)

    for extra in ({"action": "I go."}, {"choice_id": "c1"}, {"standing": "wait"}):
        played = play(player, story, {"kind": "resume", "expected_version": 2} | extra)
        assert (played.status, played.body["error"]["code"]) == (400, "validation_error"), extra


def test_a_player_who_leaves_once_the_dice_are_shown_still_owes_the_turn(player, make_story, model):
    story = opened(player, make_story, model)
    prepared = turns.prepare(story, TurnIn(**THE_CLIMB), player)
    model.backend.script(Node.INTERPRET, Reply(json=CLIMB))
    model.backend.script(Node.NARRATOR, Reply(json=CLIMBED))

    async def leave() -> None:
        ticket = await meter.astart(player, meter.TURN)
        chunks = turns.stream(prepared, ticket=ticket, byok=None)
        assert (await anext(chunks)).startswith(b"event: turn.started")
        assert (await anext(chunks)).startswith(b"event: steps.decided")
        await chunks.aclose()

    async_to_sync(leave)()

    assert Scene.objects.filter(story=story).count() == 1
    assert not CreditHold.objects.exists()
    assert owed(story)["action"] == "I climb the wall of the well"


def test_the_settings_a_throw_was_cast_under_hold_when_they_change(
    client, player, make_story, model
):
    """A5: switching to Story once a throw is shown doesn't lower the number it was thrown
    against."""
    story = opened(player, make_story, model)
    first = cast(player, story, model)
    changed = client.patch(
        f"/v1/stories/{story.pk}",
        {"settings": {"difficulty": "story", "event_frequency": "dramatic", "tone": "wry"}},
        content_type="application/json",
    )
    assert changed.status_code == 200, changed.json()
    story.refresh_from_db()

    prepared = turns.prepare(story, TurnIn(kind="resume", expected_version=2), player)

    settings = prepared.input.ctx.settings
    assert (settings.difficulty, settings.event_frequency) == (
        Difficulty.BALANCED,
        EventFrequency.NORMAL,
    )
    # What only shapes the telling is read fresh (S6).
    assert settings.tone == "wry"
    model.backend.script(Node.NARRATOR, Reply(json=CLIMBED))
    played = play(player, story, {"kind": "resume", "expected_version": 2})
    assert throw_of(played) == throw_of(first)

    # The same climb, cast on Story from the start, is thrown against a lower number.
    easy = opened(
        player, make_story, model, settings=StorySettings(difficulty="story").model_dump()
    )
    assert throw_of(cast(player, easy, model))["number"] < throw_of(first)["number"]


def test_a_standing_action_and_an_ending_note_are_kept_as_they_were_sent(player, make_story):
    """What is kept reads back as the turn that was sent, for each kind."""
    story = make_story(player)
    state = WorldState.model_validate(story.state)
    kept = {
        "turn": 1,
        "timeline_id": state.timeline_id,
        "difficulty": "brutal",
        "event_frequency": "calm",
        "intent": {"summary": "Lin waits."},
    }

    story.unfinished_turn = kept | {"kind": "standing", "standing": "wait", "input_mode": "choice"}
    waited = unfinished.of_story(story, state)
    assert (waited.kind, waited.standing, waited.player_action, waited.input_mode) == (
        TurnKind.STANDING,
        StandingAction.WAIT,
        "wait",
        "choice",
    )
    assert (waited.difficulty, waited.event_frequency) == (Difficulty.BRUTAL, EventFrequency.CALM)

    story.unfinished_turn = kept | {
        "kind": "end",
        "action": "He dies an old man.",
        "drop_refused": True,
        "overflow": ["and is mourned"],
    }
    ended = unfinished.of_story(story, state)
    assert (ended.kind, ended.player_action, ended.drop_refused) == (
        TurnKind.END,
        "He dies an old man.",
        True,
    )
    assert ended.reading.overflow == ("and is mourned",)
    assert ended.reading.intent.summary == "Lin waits."


# --- never two throws for one turn, never a story stuck (T10) ------------------------------------


@pytest.mark.parametrize(
    "sent_too",
    [SOMETHING_ELSE, {"kind": "standing", "standing": "wait", "expected_version": 2}],
    ids=["a throw", "no dice"],
)
def test_two_actions_sent_at_once_are_never_both_shown(sent_too, player, make_story, model):
    story = opened(player, make_story, model)
    other = turns.prepare(story, TurnIn(**sent_too), player)
    first = cast(player, story, model)

    model.backend.script(Node.INTERPRET, Reply(json=CLIMB))
    events = stream(player, other)

    # How the other action went is never shown: the story owes the first.
    assert [name for name, _ in events] == ["turn.started", "error"]
    assert events[-1][1]["code"] == "version_conflict"
    assert events[-1][1]["details"] == {"current_version": 2}
    assert owed(story)["action"] == "I climb the wall of the well"
    assert_nothing_saved(story, player)
    assert first.named("steps.decided")


def test_a_turn_with_no_steps_never_saves_over_the_turn_a_story_owes(player, make_story, model):
    """An ending with no note shows no steps and keeps nothing, so its save checks instead:
    sent together with a throw, it can't take the throw's place once the throw is seen."""
    story = opened(player, make_story, model)
    ending = turns.prepare(story, TurnIn(kind="end", expected_version=2), player)
    cast(player, story, model)

    model.backend.script(Node.NARRATOR, Reply(json=EPILOGUE))
    events = stream(player, ending)

    assert "steps.decided" not in [name for name, _ in events]
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "version_conflict"
    assert owed(story)["action"] == "I climb the wall of the well"
    assert_nothing_saved(story, player)


def test_a_turn_that_breaks_while_it_is_played_out_is_let_go(
    player, make_story, model, monkeypatch
):
    """A story is never stuck behind a turn that can't be finished: the first failure keeps it,
    and one more while it is played out lets it go."""
    story = opened(player, make_story, model)
    real_save = turns.asave

    def broken(*args, **kwargs):
        raise RuntimeError("the save broke")

    monkeypatch.setattr(turns, "asave", turns.sync_to_async(broken))
    model.backend.script(Node.INTERPRET, Reply(json=CLIMB))
    model.backend.script(Node.NARRATOR, Reply(json=CLIMBED))
    failed = play(player, story, THE_CLIMB)
    assert failed.named("error")[0]["code"] == "internal_error"
    assert owed(story) is not None

    model.backend.script(Node.NARRATOR, Reply(json=CLIMBED))
    again = play(player, story, SOMETHING_ELSE)
    assert again.named("turn.started")[0]["resumed"] is True
    assert again.named("error")[0]["code"] == "internal_error"
    assert owed(story) is None

    monkeypatch.setattr(turns, "asave", real_save)
    model.backend.script(Node.INTERPRET, Reply(json=STEP_AROUND))
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))
    played = play(player, story, SOMETHING_ELSE)
    assert played.named("turn.started") == [{"turn": 2}]
    assert played.completed["scene"]["player_action"] == "I step around Zhao"


@pytest.mark.parametrize(
    "kept",
    [
        {"nothing": "readable"},
        "not even an object",
        # Cast for a moment the story is no longer at.
        {
            "turn": 7,
            "timeline_id": "main",
            "kind": "action",
            "action": "I climb the wall of the well",
            "difficulty": "balanced",
            "event_frequency": "normal",
            "intent": CLIMB,
        },
        # Cast on a timeline the story left.
        {
            "turn": 2,
            "timeline_id": "another",
            "kind": "action",
            "action": "I climb the wall of the well",
            "difficulty": "balanced",
            "event_frequency": "normal",
            "intent": CLIMB,
        },
    ],
)
def test_a_kept_turn_that_is_stale_or_unreadable_never_holds_a_story_up(
    kept, client, player, make_story, model, log_lines
):
    story = opened(player, make_story, model)
    Story.objects.filter(pk=story.pk).update(unfinished_turn=kept)
    story.refresh_from_db()

    assert shown(client, story)["unfinished_turn"] is None
    model.backend.script(Node.INTERPRET, Reply(json=STEP_AROUND))
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))
    played = play(player, story, SOMETHING_ELSE)

    assert played.named("turn.started") == [{"turn": 2}]
    assert played.completed["scene"]["player_action"] == "I step around Zhao"
    assert owed(story) is None
    # T6: what was kept holds the player's words, so it is never logged.
    assert "climb the wall" not in str(log_lines())


def test_a_kept_turn_that_can_no_longer_be_played_is_let_go(player, make_story, model, log_lines):
    """It reads, but it isn't a turn the graph takes: a standing turn with no standing action."""
    story = opened(player, make_story, model)
    kept = {
        "turn": 2,
        "timeline_id": "main",
        "kind": "standing",
        "action": "I climb the wall of the well",
        "difficulty": "balanced",
        "event_frequency": "normal",
        "intent": {"summary": "Lin waits."},
    }
    Story.objects.filter(pk=story.pk).update(unfinished_turn=kept)
    story.refresh_from_db()
    model.backend.script(Node.INTERPRET, Reply(json=STEP_AROUND))
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))

    played = play(player, story, SOMETHING_ELSE)

    assert played.named("turn.started") == [{"turn": 2}]
    assert played.completed["scene"]["player_action"] == "I step around Zhao"
    assert owed(story) is None
    [line] = [line for line in log_lines() if "couldn't be played out" in line["message"]]
    assert line["unfinished_turn"] == {"story_turn": 1}
    assert "climb the wall" not in str(log_lines())


# --- what the player can take with them, and logs (T12, T5, T6) ----------------------------------


def test_the_exports_carry_what_was_sent_and_only_the_owners_how_it_was_read(
    player, make_story, model
):
    story = opened(player, make_story, model)
    assert export_stories(player.pk)[0]["unfinished_turn"] is None

    cast(player, story, model)

    # T12: the player's own words, never the reading, which is the engine's (C6).
    assert export_stories(player.pk)[0]["unfinished_turn"] == {
        "turn": 2,
        "kind": "action",
        "action": "I climb the wall of the well",
    }
    kept = owner_export._story(Story.objects.get(pk=story.pk))["unfinished_turn"]
    assert kept["intent"]["steps"][0]["text"] == "climb the wet wall of the well"
    assert (kept["difficulty"], kept["event_frequency"]) == ("balanced", "normal")

    story.unfinished_turn = {"kind": "standing", "standing": "observe", **_AT_TURN_2}
    assert unfinished.sent(story) == {"turn": 2, "kind": "standing", "action": "observe"}
    story.unfinished_turn = {"nothing": "readable"}
    assert unfinished.sent(story) is None


_AT_TURN_2 = {
    "turn": 2,
    "timeline_id": "main",
    "difficulty": "balanced",
    "event_frequency": "normal",
    "intent": {"summary": "Lin watches."},
}


def test_the_turn_line_counts_the_throws_and_never_tells_them(player, make_story, model, log_lines):
    story = opened(player, make_story, model)
    first = cast(player, story, model)
    model.backend.script(Node.NARRATOR, Reply(json=CLIMBED))
    play(player, story, {"kind": "resume", "expected_version": 2})

    lines = [line["turn"] for line in log_lines() if line["message"].startswith("Turn ")]
    failed, played = [line for line in lines if line["turn"] == 2]
    mark = throw_of(first)["mark"]
    assert (failed["outcome"], failed["resumed"]) == ("llm_unavailable", False)
    assert (played["outcome"], played["resumed"]) == ("ok", True)
    for line in (failed, played):
        assert (line["throws"], line["marks"], line["deadly"]) == (1, {mark: 1}, 0)
    opening_line = next(line for line in lines if line["turn"] == 1)
    assert (opening_line["throws"], opening_line["marks"]) == (0, {})
    logged = str([line for line in log_lines() if line["severity"] != "DEBUG"])
    assert "climb the wall" not in logged
    assert "wet wall" not in logged
