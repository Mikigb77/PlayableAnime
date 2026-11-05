"""C8 over HTTP: a death by others or by the world can be rewound a few scenes, by the difficulty
it was played on (N6): up to 5 scenes on Story, 1 on Balanced and none on Brutal. A death the
player chose is always real. A rewind puts the world back exactly as it was, takes the later scenes
out of the story, and the version moves on."""

import pytest
from django.test import Client
from django.utils import timezone

from drafts import service
from engine.context import StorySettings
from engine.state.records import EventStatus
from engine.state.records import PendingEvent as Event
from engine.state.world import WorldState
from graph.drafting.samples import SUCCESSOR
from graph.llm import FakeBackend, Node, Reply
from lucid.errors import ApiError, ErrorCode
from media.models import Image, ImageStatus, ScenePicture
from media.plans import plan_picture, retire_rewound
from media.prompts import Brief
from moderation.models import Report
from stories import pending, rewind
from stories.export import export_stories
from stories.models import PendingEvent, PendingEventStatus, Scene, Story, TurnSnapshot
from tests.conftest import auth_headers
from tests.stories.conftest import play
from tests.stories.test_endings import dead
from tests.stories.test_succession import carry_on, draw
from tests.stories.test_turns import opened

pytestmark = pytest.mark.django_db

LOOK = {
    "summary": "Lin looks around.",
    "steps": [
        {
            "text": "look around the courtyard",
            "verb": "look",
            "kind": "observe",
            "proposed_duration_s": 60,
            "facts": {"means": "clearly_enough"},
        }
    ],
}
SEEN = {
    "narration": "The courtyard is quiet. Wind combs the pines.",
    "suggestions": [{"label": "Cross the bridge", "kind": "thread"}],
}
# A death no one chose: the bridge gives way under the player character (N6).
CROSS = {
    "summary": "Lin crosses the rotten bridge.",
    "steps": [
        {
            "text": "cross the rope bridge over the gorge",
            "verb": "cross",
            "kind": "move",
            "proposed_duration_s": 60,
            "facts": {
                "means": "clearly_enough",
                "danger": "the rotten planks give way over the gorge",
                "danger_class": "certain",
                "danger_harm": "kill",
            },
        }
    ],
}
FELL = {"narration": "The planks crack, and the gorge takes you.", "suggestions": []}
# A step the dice settle (A2).
LEAP_THE_STREAM = {
    "summary": "Lin leaps the stream.",
    "steps": [
        {
            "text": "leap across the stream",
            "verb": "leap",
            "kind": "move",
            "proposed_duration_s": 5,
            "facts": {
                "means": "clearly_enough",
                "danger": "the slick rocks of the stream",
                "danger_class": "contested",
                "danger_harm": "wound",
            },
        }
    ],
}
LEAPT = {
    "narration": "You land on the far bank, or near enough.",
    "suggestions": [{"label": "Walk on", "kind": "thread"}],
}


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


def act(player, story: Story, model, intent=LOOK, told=SEEN) -> dict:
    model.backend.script(Node.INTERPRET, Reply(json=intent))
    model.backend.script(Node.NARRATOR, Reply(json=told))
    played = play(
        player, story, {"kind": "action", "action": "I go on", "expected_version": story.version}
    )
    assert played.names[-1] == "scene.completed", played.events
    story.refresh_from_db()
    return played.completed


def fallen(player, make_story, model, *, looks: int = 2, difficulty: str = "story") -> Story:
    """A story whose player character looked around `looks` times after the opening, then fell
    to their death crossing a bridge."""
    story = opened(player, make_story, model, settings=_settings(difficulty))
    for _ in range(looks):
        act(player, story, model)
    completed = act(player, story, model, CROSS, FELL)
    assert completed["story"]["ending"]["kind"] == "death"
    assert completed["story"]["ending"]["self_inflicted"] is False
    return story


def _settings(difficulty: str) -> dict:
    return StorySettings(difficulty=difficulty).model_dump(mode="json")


def rewind_by(client, story: Story, scenes: int, version: int | None = None):
    return client.post(
        f"/v1/stories/{story.pk}/rewind",
        {"expected_version": story.version if version is None else version, "scenes": scenes},
        content_type="application/json",
    )


def error_type(response) -> str:
    return response.json()["error"]["details"]["fields"][0]["type"]


# --- what a turn keeps ---------------------------------------------------------------------------


def test_each_turn_keeps_the_world_it_left_and_only_as_many_as_a_rewind_reaches(
    player, make_story, model
):
    story = opened(player, make_story, model)
    assert TurnSnapshot.objects.get(story=story, turn=1).state == story.state

    for _ in range(rewind.KEPT + 2):
        act(player, story, model)

    kept = list(TurnSnapshot.objects.filter(story=story).values_list("turn", flat=True))
    assert kept == list(range(story.turn - rewind.KEPT, story.turn + 1))
    assert TurnSnapshot.objects.get(story=story, turn=story.turn).state == story.state


# --- how far an ending reaches -------------------------------------------------------------------


def test_a_death_on_story_can_be_rewound_as_far_back_as_the_story_kept(
    client, player, make_story, model
):
    story = fallen(player, make_story, model, looks=2)

    # Opening, two looks and the fall: three scenes to go back over, short of Story's five.
    assert story.turn == 4
    assert story.ending["rewind"] == 3
    assert client.get(f"/v1/stories/{story.pk}").json()["ending"]["rewind"] == 3
    [summary] = client.get("/v1/stories").json()
    assert summary["ending"]["rewind"] == 3


def test_story_reaches_five_scenes_at_most(player, make_story, model):
    story = fallen(player, make_story, model, looks=6)

    assert story.ending["rewind"] == 5


def test_balanced_reaches_one_scene_and_brutal_none(client, player, make_story, model):
    balanced = fallen(player, make_story, model, difficulty="balanced")
    assert balanced.ending["rewind"] == 1
    response = rewind_by(client, balanced, 2)
    assert response.status_code == 400
    assert error_type(response) == "too_far"

    brutal = fallen(player, make_story, model, difficulty="brutal")
    assert brutal.ending["rewind"] == 0
    response = rewind_by(client, brutal, 1)
    assert response.status_code == 400
    assert error_type(response) == "too_far"
    assert response.json()["error"]["message"] == "This ending can't be rewound."


def test_a_death_the_player_chose_is_always_real(client, player, make_story, model):
    story = dead(player, make_story, model)

    assert story.ending["self_inflicted"] is True
    assert story.ending["rewind"] == 0
    assert error_type(rewind_by(client, story, 1)) == "too_far"


def test_changing_the_difficulty_after_a_death_changes_nothing(client, player, make_story, model):
    story = fallen(player, make_story, model, difficulty="brutal")

    client.patch(
        f"/v1/stories/{story.pk}",
        {"settings": {"difficulty": "story"}},
        content_type="application/json",
    )

    assert client.get(f"/v1/stories/{story.pk}").json()["ending"]["rewind"] == 0
    assert error_type(rewind_by(client, story, 1)) == "too_far"


def test_a_closed_story_cant_be_rewound(client, player, make_story, model):
    story = fallen(player, make_story, model)

    closed = client.post(f"/v1/stories/{story.pk}/close").json()

    assert closed["ending"]["closed"] is True and closed["ending"]["rewind"] == 0
    response = rewind_by(client, story, 1)
    assert response.status_code == 400
    assert error_type(response) == "closed"


def test_a_story_playing_on_has_nothing_to_rewind(client, player, make_story, model):
    story = opened(player, make_story, model)
    act(player, story, model)

    response = rewind_by(client, story, 1)

    assert response.status_code == 400
    assert error_type(response) == "not_ended"


def test_a_rewind_on_a_story_that_moved_on_is_a_version_conflict(client, player, make_story, model):
    story = fallen(player, make_story, model)

    response = rewind_by(client, story, 1, version=story.version - 1)

    assert response.status_code == 409
    assert response.json()["error"]["details"]["current_version"] == story.version


def test_more_scenes_than_any_difficulty_reaches_is_refused(client, player, make_story, model):
    story = fallen(player, make_story, model)

    response = rewind_by(client, story, rewind.FARTHEST + 1)

    assert response.status_code == 400
    [error] = response.json()["error"]["details"]["fields"]
    assert (error["field"], error["type"]) == ("scenes", "too_far")


# --- the rewind ----------------------------------------------------------------------------------


def test_rewinding_puts_the_world_back_and_takes_the_later_scenes_out(
    client, player, make_story, model
):
    story = fallen(player, make_story, model, looks=2)
    then = TurnSnapshot.objects.get(story=story, turn=2).state

    response = rewind_by(client, story, 2)

    assert response.status_code == 200, response.json()
    shown = response.json()
    assert shown["ending"] is None and shown["successor"] is None
    assert shown["turn"] == 2 and shown["version"] == story.version + 1
    assert [scene["turn"] for scene in shown["scenes"]] == [1, 2]
    fresh = Story.objects.get(pk=story.pk)
    assert fresh.state == then and fresh.turn == 2 and fresh.ending is None
    # The scenes taken back stay, marked, and the story no longer has them.
    assert list(
        Scene.objects.filter(story=story, rewound_at__isnull=False).values_list("turn", flat=True)
    ) == [3, 4]
    older = client.get(f"/v1/stories/{story.pk}/scenes?before=5").json()
    assert [scene["turn"] for scene in older] == [1, 2]
    # Only the states a later rewind could still reach are kept.
    assert list(TurnSnapshot.objects.filter(story=story).values_list("turn", flat=True)) == [1, 2]


def test_the_story_plays_on_from_the_moment_it_went_back_to(client, player, make_story, model):
    story = fallen(player, make_story, model, looks=1)
    rewind_by(client, story, 1)
    story.refresh_from_db()

    completed = act(player, story, model)

    assert completed["scene"]["turn"] == 3
    assert completed["story"].get("ending") is None
    live = Scene.objects.live().filter(story=story).order_by("turn")
    assert [(scene.turn, scene.narration) for scene in live][-1] == (3, SEEN["narration"])
    assert Scene.objects.filter(story=story, turn=3).count() == 2


def test_dying_again_after_a_rewind_can_be_rewound_again(client, player, make_story, model):
    story = fallen(player, make_story, model, looks=3, difficulty="balanced")
    rewind_by(client, story, 1)
    story.refresh_from_db()

    act(player, story, model, CROSS, FELL)

    assert story.ending["rewind"] == 1
    assert rewind_by(client, story, 1).status_code == 200


def test_the_same_moment_plays_the_same_way_again(client, player, make_story, model):
    """A3: a rewind isn't a reroll. A step's roll is seeded by the story, timeline and turn, so
    doing exactly the same again rolls the same."""
    story = opened(player, make_story, model, settings=_settings("story"))
    act(player, story, model)
    act(player, story, model, LEAP_THE_STREAM, LEAPT)
    first = Scene.objects.live().get(story=story, turn=3).details["steps"]
    assert first[0]["struck"][0]["roll"] is not None
    # However the leap went, say the player character died in it.
    Story.objects.filter(pk=story.pk).update(
        ending={"kind": "death", "character_id": "lin", "character": "Lin Feng", "rewind": 1}
    )
    rewind_by(client, story, 1)
    story.refresh_from_db()

    act(player, story, model, LEAP_THE_STREAM, LEAPT)

    assert Scene.objects.live().get(story=story, turn=3).details["steps"] == first


def test_after_a_rewind_as_far_as_it_goes_the_next_death_reaches_as_far_again(
    client, player, make_story, model
):
    story = fallen(player, make_story, model, looks=8)
    assert (story.turn, story.ending["rewind"]) == (10, 5)
    assert rewind_by(client, story, 5).status_code == 200
    story.refresh_from_db()
    act(player, story, model)

    act(player, story, model, CROSS, FELL)

    assert (story.turn, story.ending["rewind"]) == (7, 5)
    assert rewind_by(client, story, 5).status_code == 200
    assert Story.objects.get(pk=story.pk).turn == 2


def test_carrying_on_as_someone_new_forgets_the_kept_worlds(
    client, player, make_story, model, monkeypatch
):
    fake = FakeBackend(default=lambda request: Reply(json=SUCCESSOR))
    monkeypatch.setattr(service, "model_backend", lambda *, grounded, byok: fake)
    story = fallen(player, make_story, model)
    draw(client, story)

    assert carry_on(client, story).status_code == 200

    assert not TurnSnapshot.objects.filter(story=story).exists()


# --- what else goes back -------------------------------------------------------------------------


def _event(event_id: str, status=EventStatus.PENDING, created_turn=1, **fields) -> Event:
    return Event(
        id=event_id,
        kind="arrival",
        due_s=10_000,
        status=status,
        created_turn=created_turn,
        **fields,
    )


def test_events_the_rewound_scenes_applied_wait_again_and_the_ones_they_set_never_come(
    player, make_story
):
    world = WorldState.model_validate(make_story(player).state)
    then = world.model_copy(update={"turn": 1, "pending_events": {"rider": _event("rider")}})
    now = world.model_copy(
        update={
            "turn": 2,
            "pending_events": {
                "rider": _event("rider", EventStatus.APPLIED, applied_turn=2),
                "rumor": _event("rumor", created_turn=2),
                "omen": _event("omen", EventStatus.APPLIED, created_turn=2, applied_turn=2),
            },
        }
    )
    story = _at_death(player, make_story, then, now)

    rewind.rewind(story, story.version, 1)

    rows = {row.payload["id"]: row for row in PendingEvent.objects.filter(story=story)}
    assert rows["rider"].status == PendingEventStatus.PENDING
    assert rows["rider"].applied_turn is None
    assert rows["rumor"].status == PendingEventStatus.CANCELLED
    # Set and fired in a scene taken back: the world it went back to never had it.
    assert rows["omen"].status == PendingEventStatus.CANCELLED


def _at_death(player, make_story, then: WorldState, now: WorldState) -> Story:
    """A story that died in turn 2, with turn 1's world kept and the events of turn 2 saved."""
    story = make_story(player, state=now.model_dump(mode="json"))
    Story.objects.filter(pk=story.pk).update(
        turn=2,
        ending={
            "kind": "death",
            "character_id": now.player_id,
            "character": now.player.name,
            "turn": 2,
            "rewind": 1,
        },
    )
    story.refresh_from_db()
    pending.write_back(story, then.model_copy(update={"pending_events": {}}), then)
    pending.write_back(story, then, now)
    TurnSnapshot.objects.create(story=story, turn=1, state=then.model_dump(mode="json"))
    for turn in (1, 2):
        Scene.objects.create(story=story, turn=turn, kind="action", narration=f"Scene {turn}.")
    return story


def test_a_rewound_scenes_picture_isnt_reused_by_the_scene_played_anew(player, make_story):
    story = make_story(player)
    world = WorldState.model_validate(story.state)
    scene = Scene.objects.create(story=story, turn=2, kind="action", narration="The fall.")
    picture = Image.objects.create(story=story, kind="scene", subject="turn-2")
    ScenePicture.objects.create(scene=scene, image=picture)
    kept = Image.objects.create(story=story, kind="scene", subject="turn-1")

    assert retire_rewound(story.pk, world, [scene.pk]) == 1

    picture.refresh_from_db()
    kept.refresh_from_db()
    assert picture.subject == f"turn-2~{picture.pk.hex}"
    assert kept.subject == "turn-1"


def test_a_picture_asked_for_a_scene_a_rewind_took_back_meanwhile_isnt_planned(player, make_story):
    story = make_story(player)
    scene = Scene.objects.create(story=story, turn=2, kind="action", narration="The fall.")
    Scene.objects.filter(pk=scene.pk).update(rewound_at=timezone.now())

    with pytest.raises(ApiError) as refused:
        plan_picture(scene, kind="scene", trigger="illustrate", brief=Brief(description="A fall."))

    assert refused.value.code == ErrorCode.NOT_FOUND
    assert not Image.objects.filter(story=story).exists()


def test_a_face_or_place_drawn_for_a_look_the_world_went_back_from_is_drawn_again(
    player, make_story
):
    story = make_story(player)
    world = WorldState.model_validate(story.state)
    pid = world.player_id
    place_id = next(iter(world.places))
    as_now = Image.objects.create(story=story, kind="portrait", subject=pid, version=1)
    scarred = Image.objects.create(
        story=story, kind="portrait", subject=pid, version=2, status=ImageStatus.READY
    )
    stranger = Image.objects.create(story=story, kind="portrait", subject="met-later")
    place = Image.objects.create(story=story, kind="place", subject=place_id)
    ruined = Image.objects.create(story=story, kind="place", subject=place_id, version=2)

    assert retire_rewound(story.pk, world, []) == 3

    subjects = {image.pk: image.subject for image in Image.objects.filter(story=story)}
    assert subjects[as_now.pk] == pid and subjects[place.pk] == place_id
    assert subjects[scarred.pk].startswith(f"{pid}~")
    assert subjects[stranger.pk].startswith("met-later~")
    assert subjects[ruined.pk].startswith(f"{place_id}~")
    # Taken out once: a second rewind leaves them be.
    assert retire_rewound(story.pk, world, []) == 0


def test_a_block_on_a_rewound_scene_doesnt_hide_the_one_played_anew(
    client, player, make_story, model
):
    story = fallen(player, make_story, model, looks=1)
    fall = Scene.objects.live().get(story=story, turn=3)
    Report.objects.create(story=story, scene=fall, reporter=player, category="other", block=True)
    rewind_by(client, story, 1)
    story.refresh_from_db()

    act(player, story, model)

    scenes = client.get(f"/v1/stories/{story.pk}").json()["scenes"]
    assert scenes[-1]["turn"] == 3 and scenes[-1]["blocked"] is False
    # A report on turn 3 now reaches the scene played anew.
    response = client.post(
        f"/v1/stories/{story.pk}/scenes/3/report",
        {"category": "other"},
        content_type="application/json",
    )
    assert response.status_code == 204
    reported = Report.objects.exclude(scene=fall).get(story=story)
    assert reported.scene.rewound_at is None


def test_the_account_export_keeps_rewound_scenes_marked(client, player, make_story, model):
    story = fallen(player, make_story, model, looks=1)
    rewind_by(client, story, 1)

    [exported] = export_stories(player.pk)

    assert [(scene["turn"], scene["rewound"]) for scene in exported["scenes"]] == [
        (1, False),
        (2, False),
        (3, True),
    ]


def test_scenes_rewound_at_the_same_turn_can_pile_up(player, make_story):
    story = make_story(player)
    for _ in range(3):
        Scene.objects.create(
            story=story, turn=1, kind="action", narration="Again.", rewound_at=timezone.now()
        )
    Scene.objects.create(story=story, turn=1, kind="action", narration="Now.")

    assert Scene.objects.live().get(story=story, turn=1).narration == "Now."
