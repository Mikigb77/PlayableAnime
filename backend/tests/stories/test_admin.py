import pytest
from asgiref.sync import async_to_sync
from django.test import Client
from django.urls import reverse

from accounts.models import User
from stories.models import PendingEvent, Scene, Story

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client() -> Client:
    client = Client()
    client.force_login(User.objects.create_superuser("staff@example.com", "pw"))
    return client


def test_staff_can_browse_users_stories_scenes_and_pending_events(staff_client):
    story = Story.objects.create(title="T", premise="P")
    scene = Scene.objects.create(story=story, turn=1, kind="opening", narration="N")
    event = PendingEvent.objects.create(story=story, due_world_s=1, kind="k")
    user = User.objects.get()

    for name, obj in [
        ("accounts_user", user),
        ("stories_story", story),
        ("stories_scene", scene),
        ("stories_pendingevent", event),
    ]:
        assert staff_client.get(reverse(f"admin:{name}_changelist")).status_code == 200
        assert staff_client.get(reverse(f"admin:{name}_change", args=[obj.pk])).status_code == 200
    assert staff_client.get(reverse("admin:accounts_user_add")).status_code == 200


def test_the_admin_needs_staff():
    client = Client()
    client.force_login(User.objects.create_user("player@example.com", "pw"))

    response = client.get(reverse("admin:stories_story_changelist"))

    assert response.status_code == 302


def test_the_admins_static_files_are_served():
    response = Client().get("/static/admin/css/base.css")

    assert response.status_code == 200

    async def read() -> bytes:
        return b"".join([chunk async for chunk in response.streaming_content])

    assert b"body" in async_to_sync(read)()
