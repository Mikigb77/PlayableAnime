import pytest
from django.db import IntegrityError

from accounts.models import User
from stories.models import Engine, PendingEvent, PendingEventStatus, Rating, Scene, Story

pytestmark = pytest.mark.django_db


def _story(**fields) -> Story:
    return Story.objects.create(title="The Drowned Capital", premise="A ronin wakes.", **fields)


def test_a_new_story_starts_empty_at_version_zero():
    story = _story()

    assert (story.version, story.turn, story.state, story.settings) == (0, 0, {}, {})
    assert story.rating == Rating.TEEN
    assert story.engine == Engine.GRAPH
    assert story.owner is None


def test_the_world_state_round_trips_as_jsonb():
    state = {"clock": {"world_s": 3600, "timeline_id": "main"}, "characters": [{"id": "ren"}]}
    story = _story(state=state)

    assert Story.objects.get(pk=story.pk).state == state
    assert Story.objects.filter(state__clock__world_s=3600).exists()


def test_one_scene_per_turn():
    story = _story()
    Scene.objects.create(story=story, turn=1, kind="opening", narration="It begins.")

    with pytest.raises(IntegrityError):
        Scene.objects.create(story=story, turn=1, kind="action", narration="Again.")


def test_scenes_and_pending_events_go_with_their_story_and_stories_with_their_owner():
    owner = User.objects.create_user("p@example.com")
    story = _story(owner=owner)
    Scene.objects.create(story=story, turn=1, kind="opening", narration="It begins.")
    PendingEvent.objects.create(story=story, due_world_s=60, kind="arrival")

    owner.delete()

    assert not Story.objects.exists()
    assert not Scene.objects.exists()
    assert not PendingEvent.objects.exists()


def test_pending_events_come_due_in_in_world_time_order():
    story = _story()
    for due, kind in [(500, "late"), (100, "early"), (300, "middle")]:
        PendingEvent.objects.create(story=story, due_world_s=due, kind=kind)
    PendingEvent.objects.create(
        story=story, due_world_s=50, kind="done", status=PendingEventStatus.APPLIED
    )
    PendingEvent.objects.create(story=story, due_world_s=10, kind="other", timeline_id="stopped")

    due = PendingEvent.objects.filter(
        story=story, timeline_id="main", status=PendingEventStatus.PENDING, due_world_s__lte=400
    )

    assert [e.kind for e in due] == ["early", "middle"]
