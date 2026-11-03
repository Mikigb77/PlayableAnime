"""`POST /v1/stories/{id}/turns` end to end on the scripted model (B5, B7, S3, T5, T7, T10, K2,
B12, F4, V7): the checks before the stream, the events, the one-transaction save, and what is
left when a turn fails."""

from asgiref.sync import async_to_sync
from django.db.models import F

from billing.models import CreditHold, LedgerEntry
from graph.llm import Block, Fail, Node, Reply
from media.models import Image, ScenePicture
from stories import pending, turns
from stories.models import PendingEvent, PendingEventStatus, Scene, Story
from stories.schemas import TurnIn
from tests.stories.conftest import opening, parse_events, play

OPENING = {
    "narration": "Cold water slops over your sandals as you lift the bucket from the well.",
    "suggestions": [
        {"label": "Step around Zhao", "kind": "thread"},
        {"label": "Wait", "kind": "side"},
        {"label": "Head to the herb garden", "kind": "side"},
    ],
    "image_prompt": "Lin Feng at the well at dawn, a full bucket in hand.",
    "update": {
        "scene_end": {
            "ended_on": "Zhao blocks the path, grinning.",
            "place_id": "well",
            "present_ids": ["lin", "zhao"],
        }
    },
}

STEP_AROUND = {
    "summary": "Lin steps around Zhao.",
    "steps": [
        {
            "text": "step around Zhao",
            "verb": "step around",
            "target_ids": ["zhao"],
            "kind": "move",
            "proposed_duration_s": 3,
        }
    ],
}

AFTER = {
    "narration": "You step wide. Zhao's foot finds only air.",
    "suggestions": [{"label": "Keep walking", "kind": "thread"}],
    "update": {"scene_end": {"ended_on": "Zhao scowls.", "present_ids": ["lin", "zhao"]}},
}


def opened(player, make_story, model, **fields) -> Story:
    story = make_story(player, **fields)
    model.backend.script(Node.NARRATOR, Reply(json=OPENING))
    played = play(player, story, opening(story))
    assert played.names[-1] == "scene.completed", played.events
    story.refresh_from_db()
    return story


def test_the_opening_streams_and_saves_the_scene_state_charge_and_picture(
    player, make_story, model
):
    story = make_story(player)
    model.backend.script(Node.NARRATOR, Reply(json=OPENING))

    played = play(player, story, opening(story))

    assert played.status == 200
    assert played.names[0] == "turn.started"
    assert played.named("turn.started") == [{"turn": 1}]
    assert played.names[-1] == "scene.completed"
    assert played.text == OPENING["narration"]
    assert len(played.named("narration.delta")) > 1
    scene = played.completed["scene"]
    assert scene["turn"] == 1
    assert scene["kind"] == "opening"
    assert scene["player_action"] is None
    assert scene["input_mode"] is None
    assert scene["narration"] == OPENING["narration"]
    # S2: wait is always offered, so it isn't a suggestion too.
    assert [(c["id"], c["label"]) for c in scene["choices"]] == [
        ("c1", "Step around Zhao"),
        ("c2", "Head to the herb garden"),
    ]
    assert scene["standing_actions"] == ["wait", "observe"]
    assert scene["time"]["label"]
    assert scene["time"]["duration_label"].startswith("+")
    # M1: the player character's portrait when the story starts, planned and drawn later (M3).
    assert scene["image"] == {
        "planned": True,
        "kind": "portrait",
        "status": "planned",
        "image_id": str(Image.objects.get().pk),
        "url": None,
        "expires_at": None,
    }
    assert scene["portraits"] == [{"character_id": "zhao", "name": "Zhao Kun", "url": None}]
    assert played.completed["story"]["version"] == 2
    assert set(played.completed["story"]["clock"]) == {"world_s", "label", "timeline_id"}

    story.refresh_from_db()
    assert (story.version, story.turn, story.state["turn"]) == (2, 1, 1)
    assert story.state["scene"]["ended_on"] == "Zhao blocks the path, grinning."
    row = Scene.objects.get(story=story)
    assert (row.turn, row.kind, row.input_mode) == (1, "opening", None)
    assert row.image_prompt == OPENING["image_prompt"]
    assert row.cast == [{"character_id": "zhao", "name": "Zhao Kun"}]
    image = ScenePicture.objects.get(scene=row).image
    assert (image.kind, image.subject, image.trigger) == ("portrait", "lin", "story_start")
    assert image.brief["subject_name"] == "Lin Feng"
    # K2: one ledger entry for the turn, and no hold left behind.
    entry = LedgerEntry.objects.get(user_id=player.pk, kind="turn")
    assert (str(entry.story_id), entry.turn) == (str(story.pk), 1)
    assert entry.amount_cents < 0
    assert not CreditHold.objects.exists()


def test_an_action_plays_with_its_input_mode_and_shows_why(player, make_story, model):
    story = opened(player, make_story, model)
    model.backend.script(Node.INTERPRET, Reply(json=STEP_AROUND))
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))

    played = play(
        player,
        story,
        {
            "kind": "action",
            "action": "  I step around Zhao.  ",
            "input_mode": "voice",
            "expected_version": 2,
        },
    )

    scene = played.completed["scene"]
    assert (scene["turn"], scene["kind"]) == (2, "action")
    assert scene["player_action"] == "I step around Zhao."
    assert scene["input_mode"] == "voice"
    # A8: the step, its class and the reason in the world's words.
    [step] = scene["details"]["steps"]
    assert step["text"] == "step around Zhao"
    assert step["class"] in {"certain", "contested", "long_shot", "ruled_out"}
    assert step["reason"]
    assert scene["image"] is None
    assert played.completed["story"]["version"] == 3
    assert Scene.objects.get(story=story, turn=2).input_mode == "voice"
    assert LedgerEntry.objects.filter(user_id=player.pk, kind="turn").count() == 2


def test_a_choice_plays_the_label_of_the_last_scene_suggestion(player, make_story, model):
    story = opened(player, make_story, model)
    model.backend.script(Node.INTERPRET, Reply(json=STEP_AROUND))
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))

    played = play(player, story, {"kind": "choice", "choice_id": "c1", "expected_version": 2})

    scene = played.completed["scene"]
    assert (scene["kind"], scene["player_action"], scene["input_mode"]) == (
        "choice",
        "Step around Zhao",
        "choice",
    )
    [interpret] = model.backend.calls(Node.INTERPRET)
    assert "Step around Zhao" in interpret.prompt.messages[-1].text


def test_a_standing_action_needs_no_interpret_call(player, make_story, model):
    story = opened(player, make_story, model)
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))

    played = play(player, story, {"kind": "standing", "standing": "wait", "expected_version": 2})

    scene = played.completed["scene"]
    assert (scene["kind"], scene["player_action"], scene["input_mode"]) == (
        "standing",
        "wait",
        "choice",
    )
    assert model.backend.calls(Node.INTERPRET) == []


def test_the_checks_before_the_stream_are_json_errors_that_count_nothing(player, make_story, model):
    story = opened(player, make_story, model)
    cases = [
        ({"kind": "action", "action": "I wait.", "expected_version": 1}, 409, "version_conflict"),
        ({"kind": "opening", "expected_version": 2}, 400, "validation_error"),
        ({"kind": "choice", "choice_id": "c9", "expected_version": 2}, 400, "validation_error"),
        ({"kind": "action", "expected_version": 2}, 400, "validation_error"),
        ({"kind": "action", "action": " ", "expected_version": 2}, 400, "validation_error"),
        (
            {"kind": "action", "action": "I go.", "choice_id": "c1", "expected_version": 2},
            400,
            "validation_error",
        ),
        (
            {"kind": "action", "action": "I go.", "input_mode": "choice", "expected_version": 2},
            400,
            "validation_error",
        ),
        ({"kind": "standing", "standing": "sleep", "expected_version": 2}, 400, "validation_error"),
        ({"kind": "action", "action": "I go."}, 400, "validation_error"),
    ]
    for body, status, code in cases:
        played = play(player, story, body)
        assert (played.status, played.body["error"]["code"]) == (status, code), body
    stale = play(player, story, {"kind": "action", "action": "I go.", "expected_version": 1})
    assert stale.body["error"]["details"] == {"current_version": 2}
    unknown = play(player, story, {"kind": "choice", "choice_id": "c9", "expected_version": 2})
    assert unknown.body["error"]["details"]["fields"][0]["field"] == "choice_id"
    # Nothing ran, so nothing was counted against the rate limit or held (T9).
    assert model.backend.calls(Node.INTERPRET) == []
    assert len(model.builds) == 1
    assert not CreditHold.objects.exists()
    story.refresh_from_db()
    assert story.version == 2


def test_a_story_must_open_before_anything_else_is_played(player, make_story, model):
    story = make_story(player)

    played = play(player, story, {"kind": "action", "action": "I go.", "expected_version": 1})

    assert played.status == 400
    assert played.body["error"]["details"]["fields"][0]["type"] == "not_opened"


def test_out_of_credits_is_refused_before_the_stream(player, make_story, model, settings):
    from billing.credits import locked_account

    story = make_story(player)
    account = locked_account(player.pk, user=player)
    LedgerEntry.objects.filter(user_id=player.pk).delete()
    account.balance_cents = 0
    account.save()

    played = play(player, story, opening(story))

    assert (played.status, played.body["error"]["code"]) == (402, "out_of_credits")
    assert model.builds == []


def test_an_unsupported_key_provider_is_a_header_error(player, make_story, model):
    story = make_story(player)

    played = play(player, story, opening(story), **{"X-LLM-Provider": "nope", "X-LLM-Api-Key": "k"})

    assert played.status == 400
    [problem] = played.body["error"]["details"]["fields"]
    assert (problem["field"], problem["source"]) == ("X-LLM-Provider", "header")


def test_someone_elses_story_and_a_rating_above_the_account_are_refused(
    player, make_user, make_story, model
):
    from datetime import date

    other = make_story(make_user("other@example.com"))
    teen = make_user(
        "teen@example.com", birth_date=date.today().replace(year=date.today().year - 15)
    )
    mature = make_story(teen, rating="mature")

    assert play(player, other, opening(other)).status == 403
    assert play(teen, mature, opening(mature)).status == 403
    assert play(player, "not-a-story", {"kind": "opening", "expected_version": 1}).status == 404


def assert_nothing_saved(story: Story, player) -> None:
    fresh = Story.objects.get(pk=story.pk)
    assert (fresh.version, fresh.turn) == (story.version, story.turn)
    assert fresh.state == story.state
    assert Scene.objects.filter(story=story).count() == story.turn
    assert LedgerEntry.objects.filter(user_id=player.pk, kind="turn").count() == story.turn
    assert not CreditHold.objects.exists()


def test_an_unreadable_action_is_an_error_event_and_saves_nothing(player, make_story, model):
    story = opened(player, make_story, model)
    model.backend.script(Node.INTERPRET, Block(stage="prompt"))

    played = play(player, story, {"kind": "action", "action": "I do it.", "expected_version": 2})

    assert played.status == 200
    assert played.names == ["turn.started", "error"]
    [error] = played.named("error")
    assert error["code"] == "unreadable_action"
    assert error["message"]
    assert_nothing_saved(story, player)


def test_a_model_that_fails_twice_is_llm_unavailable_and_saves_nothing(player, make_story, model):
    story = opened(player, make_story, model)
    model.backend.script(Node.NARRATOR, Fail(), Fail())

    played = play(player, story, {"kind": "standing", "standing": "wait", "expected_version": 2})

    assert played.names == ["turn.started", "error"]
    assert played.named("error")[0]["code"] == "llm_unavailable"
    assert_nothing_saved(story, player)


def test_a_failure_mid_stream_resets_the_text_and_retries(player, make_story, model):
    story = opened(player, make_story, model)
    model.backend.script(Node.NARRATOR, Fail(after_text='{"narration": "You st'), Reply(json=AFTER))

    played = play(player, story, {"kind": "standing", "standing": "wait", "expected_version": 2})

    assert played.named("narration.reset") == [{"reason": "retry"}]
    assert played.names[-1] == "scene.completed"
    reset = played.names.index("narration.reset")
    after_reset = "".join(d["text"] for e, d in played.events[reset:] if e == "narration.delta")
    assert after_reset == AFTER["narration"]


def test_a_blocked_narration_is_retold_and_the_turn_saves(player, make_story, model):
    story = opened(player, make_story, model)
    retold = AFTER | {"narration": "The moment passes; Zhao is left behind."}
    model.backend.script(Node.NARRATOR, Block(after_text='{"narration": "You'), Reply(json=retold))

    played = play(player, story, {"kind": "standing", "standing": "wait", "expected_version": 2})

    assert played.named("narration.reset") == [{"reason": "cutaway"}]
    assert played.completed["scene"]["narration"] == retold["narration"]


def test_a_rejected_own_key_is_bad_key_and_the_key_is_never_logged(
    player, make_story, model, log_lines
):
    story = make_story(player)
    model.backend.script(Node.NARRATOR, Fail(kind="auth", status=400))
    key = "AIza-very-secret-key"

    played = play(
        player, story, opening(story), **{"X-LLM-Provider": "gemini", "X-LLM-Api-Key": key}
    )

    assert played.named("error")[0]["code"] == "bad_key"
    assert model.builds[0]["byok"] is not None
    assert key not in str(log_lines())
    assert key not in str(played.events)
    assert not Scene.objects.exists()


def test_a_turn_on_the_players_own_key_is_not_charged(player, make_story, model):
    story = make_story(player)
    model.backend.script(Node.NARRATOR, Reply(json=OPENING))

    played = play(
        player, story, opening(story), **{"X-LLM-Provider": "gemini", "X-LLM-Api-Key": "key"}
    )

    assert played.names[-1] == "scene.completed"
    assert not LedgerEntry.objects.filter(user_id=player.pk, kind="turn").exists()


def test_the_loser_of_two_concurrent_turns_saves_nothing(player, make_story, model):
    """T10: both turns read version 2. The other saves first, so this one ends with
    version_conflict and nothing of it is saved."""
    from billing import meter

    story = opened(player, make_story, model)
    prepared = turns.prepare(
        story, TurnIn(kind="standing", standing="wait", expected_version=2), player
    )
    Story.objects.filter(pk=story.pk).update(version=F("version") + 1)
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))

    async def run() -> bytes:
        ticket = await meter.astart(player, meter.TURN)
        chunks = turns.stream(prepared, ticket=ticket, byok=None)
        return b"".join([chunk async for chunk in chunks])

    events = parse_events(async_to_sync(run)())

    names = [name for name, _ in events]
    assert (names[0], set(names[1:-1]), names[-1]) == ("turn.started", {"narration.delta"}, "error")
    assert events[-1][1]["code"] == "version_conflict"
    assert events[-1][1]["details"] == {"current_version": 3}
    assert Scene.objects.filter(story=story).count() == 1
    assert LedgerEntry.objects.filter(user_id=player.pk, kind="turn").count() == 1
    assert not CreditHold.objects.exists()


def test_a_player_who_leaves_mid_turn_gets_the_hold_back_and_nothing_is_saved(
    player, make_story, model, log_lines
):
    from billing import meter

    story = opened(player, make_story, model)
    prepared = turns.prepare(
        story, TurnIn(kind="standing", standing="wait", expected_version=2), player
    )
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))

    async def leave() -> None:
        ticket = await meter.astart(player, meter.TURN)
        chunks = turns.stream(prepared, ticket=ticket, byok=None)
        assert (await anext(chunks)).startswith(b"event: turn.started")
        await anext(chunks)
        await chunks.aclose()

    async_to_sync(leave)()

    assert Scene.objects.filter(story=story).count() == 1
    assert not CreditHold.objects.exists()
    [line] = [line for line in log_lines() if line["message"] == "Turn abandoned"]
    assert line["turn"]["outcome"] == "abandoned"


def test_pending_events_are_written_back_and_rows_from_outside_a_turn_fire(
    player, make_story, model
):
    """B12: the state's events become rows, and a row scheduled without a turn is read into the
    world state and applied when it falls due."""
    story = make_story(player, world="grounded")
    outside = PendingEvent.objects.create(
        story=story, due_world_s=0, kind="rumor", payload={"title": "Word spreads"}
    )
    model.backend.script(
        Node.NARRATOR,
        Reply(json=OPENING | {"update": {"scene_end": {"ended_on": "Carmine waits."}}}),
    )

    played = play(player, story, opening(story))

    assert played.names[-1] == "scene.completed"
    council = PendingEvent.objects.get(pk=pending.row_id(story.pk, "council-meets"))
    assert (council.kind, council.status, council.due_world_s) == ("clock_end", "pending", 864000)
    assert council.payload["title"] == "The council names the next boss"
    outside.refresh_from_db()
    assert outside.status == PendingEventStatus.APPLIED
    assert outside.applied_turn == 1
    story.refresh_from_db()
    assert story.state["pending_events"][str(outside.pk)]["status"] == "applied"


def test_staff_changes_to_a_pending_row_win_over_the_state(player, make_story, model):
    story = make_story(player, world="grounded")
    state = pending.load(story, _state(story))
    row_id = pending.row_id(story.pk, "council-meets")
    PendingEvent.objects.create(
        id=row_id,
        story=story,
        due_world_s=10,
        kind="clock_end",
        status=PendingEventStatus.CANCELLED,
        payload=state.pending_events["council-meets"].model_dump(mode="json"),
    )

    loaded = pending.load(story, _state(story))

    assert loaded.pending_events["council-meets"].status == "cancelled"
    assert loaded.pending_events["council-meets"].due_s == 10


def _state(story: Story):
    from engine.state.world import WorldState

    return WorldState.model_validate(story.state)


def test_one_t5_line_per_turn_with_numbers_and_never_the_story(
    player, make_story, model, log_lines
):
    story = opened(player, make_story, model)
    model.backend.script(Node.INTERPRET, Reply(json=STEP_AROUND))
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))

    play(
        player,
        story,
        {
            "kind": "action",
            "action": "I step around Zhao.",
            "input_mode": "voice_edited",
            "expected_version": 2,
        },
    )

    lines = [line for line in log_lines() if line["message"].startswith("Turn ")]
    [line] = [line for line in lines if line["turn"]["turn"] == 2]
    fields = line["turn"]
    assert fields["outcome"] == "ok"
    assert fields["input_mode"] == "voice_edited"
    assert fields["kind"] == "action"
    assert fields["calls"] == 2
    assert fields["models"]
    assert fields["input_tokens"] > 0
    assert fields["cost_usd"] > 0
    assert fields["first_text_ms"] is not None
    assert set(fields["node_ms"]) >= {"interpret", "narrate"}
    assert line["story_id"] == str(story.pk)
    logged = str(log_lines())
    assert "I step around Zhao." not in logged
    assert AFTER["narration"] not in logged


def test_a_turn_saved_after_its_player_left_is_logged_as_saved(
    player, make_story, model, log_lines, monkeypatch
):
    """The player leaves while the turn is being saved. The save still commits in its thread, so
    T5 says `ok` and unsent, never `abandoned`."""
    import asyncio
    import threading

    from billing import meter

    story = opened(player, make_story, model)
    prepared = turns.prepare(
        story, TurnIn(kind="standing", standing="wait", expected_version=2), player
    )
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))
    saving, release = threading.Event(), threading.Event()
    real_save = turns.save

    def slow_save(*args, **kwargs):
        saving.set()
        release.wait(10)
        return real_save(*args, **kwargs)

    monkeypatch.setattr(turns, "asave", turns.sync_to_async(slow_save))

    async def leave_during_save() -> None:
        ticket = await meter.astart(player, meter.TURN)
        chunks = turns.stream(prepared, ticket=ticket, byok=None)

        async def read_all():
            async for _ in chunks:
                pass

        reader = asyncio.ensure_future(read_all())
        await asyncio.to_thread(saving.wait, 10)
        reader.cancel()
        release.set()
        try:
            await reader
        except asyncio.CancelledError:
            pass

    async_to_sync(leave_during_save)()

    assert Scene.objects.filter(story=story).count() == 2
    [line] = [line for line in log_lines() if line["message"] == "Turn ok"][-1:]
    assert (line["turn"]["turn"], line["turn"]["sent"]) == (2, False)
    assert not CreditHold.objects.exists()


def test_closing_a_stream_that_never_started_gives_the_hold_back(player, make_story, model):
    from django.core import signals
    from django.db import close_old_connections

    from billing import meter

    story = make_story(player)
    prepared = turns.prepare(story, TurnIn(kind="opening", expected_version=1), player)
    ticket = async_to_sync(meter.astart)(player, meter.TURN)
    assert CreditHold.objects.filter(pk=ticket.id).exists()

    response = turns.TurnStream(turns.stream(prepared, ticket=ticket, byok=None), ticket)
    # Closing a response ends the request, which would close the test's database connection.
    signals.request_finished.disconnect(close_old_connections)
    try:
        response.close()
    finally:
        signals.request_finished.connect(close_old_connections)

    assert not CreditHold.objects.exists()


def test_a_scene_whose_pictures_cant_be_read_is_still_sent(player, make_story, model, monkeypatch):
    """The turn is saved and charged before the scene's picture URLs are read, so failing to
    read them sends the scene without them instead of an error."""
    from stories import responses

    def broken(*args, **kwargs):
        raise RuntimeError("IAM is down")

    monkeypatch.setattr(responses, "scenes_out", broken)
    story = make_story(player)
    model.backend.script(Node.NARRATOR, Reply(json=OPENING))

    played = play(player, story, opening(story))

    scene = played.completed["scene"]
    assert scene["narration"] == OPENING["narration"]
    assert scene["portraits"] == [{"character_id": "zhao", "name": "Zhao Kun", "url": None}]
    assert played.completed["story"]["version"] == 2


def test_an_unexpected_validation_error_is_logged_without_story_text(
    player, make_story, model, monkeypatch, log_lines
):
    """T6: a Pydantic error quotes what it rejected. The ERROR line keeps the traceback and the
    field names, never the values."""
    from pydantic import BaseModel

    class Strict(BaseModel):
        count: int

    secret = "Lin's hidden scar"

    def broken(*args, **kwargs):
        Strict.model_validate({"count": secret})

    monkeypatch.setattr(turns, "asave", turns.sync_to_async(broken))
    story = make_story(player)
    model.backend.script(Node.NARRATOR, Reply(json=OPENING))

    played = play(player, story, opening(story))

    assert played.named("error")[0]["code"] == "internal_error"
    [line] = [line for line in log_lines() if line["message"].startswith("A turn failed")]
    assert line["severity"] == "ERROR"
    assert "count: int_parsing" in line["stack_trace"]
    errors = [line for line in log_lines() if line["severity"] != "DEBUG"]
    assert secret not in str(errors)


def test_a_row_of_another_story_is_never_touched(player, make_story, model):
    """B12: an event whose id is another story's row id gets this story's own row."""
    elsewhere = make_story(player, world="grounded")
    theirs = PendingEvent.objects.create(story=elsewhere, due_world_s=99, kind="rumor")
    story = make_story(player)
    state = story.state
    state["pending_events"][str(theirs.pk)] = {
        "id": str(theirs.pk),
        "kind": "rumor",
        "due_s": 0,
    }
    Story.objects.filter(pk=story.pk).update(state=state)
    story.refresh_from_db()
    model.backend.script(Node.NARRATOR, Reply(json=OPENING))

    assert play(player, story, opening(story)).names[-1] == "scene.completed"

    theirs.refresh_from_db()
    assert (theirs.story_id, theirs.status, theirs.due_world_s) == (elsewhere.pk, "pending", 99)
    mine = PendingEvent.objects.get(pk=pending.row_id(story.pk, str(theirs.pk)))
    assert mine.story_id == story.pk


def test_a_story_started_from_a_draft_opens_on_the_drafts_moment(player, model, monkeypatch):
    """WS12's start saves the story at turn 0; the opening turn plays from the moment the draft
    ended on (R3)."""
    from django.test import Client

    from drafts import service
    from graph.llm import FakeBackend
    from tests.conftest import auth_headers
    from tests.drafts.conftest import _sample_reply

    drafting = FakeBackend(default=_sample_reply)
    monkeypatch.setattr(service, "model_backend", lambda *, grounded, byok: drafting)
    client = Client(headers=auth_headers(player))
    draft = client.post(
        "/v1/drafts",
        {"premise_id": "naples-vendetta", "rating": "mature"},
        content_type="application/json",
    ).json()
    started = client.post(
        f"/v1/drafts/{draft['id']}/start", {}, content_type="application/json"
    ).json()
    story = Story.objects.get(pk=started["story_id"])
    moment = story.state["scene"]["ended_on"]
    model.backend.script(
        Node.NARRATOR,
        Reply(json=OPENING | {"update": {"scene_end": {"ended_on": "The cards stay face down."}}}),
    )

    played = play(player, story, {"kind": "opening", "expected_version": started["version"]})

    assert played.names[-1] == "scene.completed"
    assert moment
    [narrator] = model.backend.calls(Node.NARRATOR)
    assert moment in narrator.prompt.messages[-1].text
