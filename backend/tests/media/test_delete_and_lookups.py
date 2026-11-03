"""Pictures leave with their story and account (T12, M4), and the lookups other endpoints use
to show them: scene pictures, portraits, covers and the export."""

import sys
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.db import transaction

from accounts.models import User
from accounts.services import delete_account, export_account
from media import signals
from media.lookups import (
    cover_urls,
    export_pictures,
    place_url,
    place_urls,
    portrait_urls,
    scene_images,
)
from media.models import Image, ImageStatus, SkipReason
from media.plans import plan_picture
from media.prompts import Brief
from media.service import scene_picture
from media.storage import get_storage
from tests.media.conftest import make_scene, make_story

pytestmark = pytest.mark.django_db


def _draw(story, turn: int) -> Image:
    from stories.models import Scene

    scene = Scene.objects.get(story=story, turn=turn)
    result = async_to_sync(scene_picture)(story, scene, user=story.owner)
    return Image.objects.get(pk=result.image.pk)


def _plan(story, turn: int, kind: str = "scene", subject_id: str | None = None) -> Image:
    scene = make_scene(story, turn)
    return plan_picture(
        scene, kind=kind, subject_id=subject_id, trigger="t", brief=Brief(subject_name="X")
    ).image


def test_deleting_a_story_deletes_its_picture_files_once_committed(
    painters, django_capture_on_commit_callbacks
):
    story = make_story()
    _plan(story, 2)
    key = _draw(story, 2).storage_key
    assert get_storage().exists(key)

    with django_capture_on_commit_callbacks(execute=True):
        story.delete()

    assert not get_storage().exists(key)


def test_a_delete_that_rolls_back_keeps_the_files(painters, django_capture_on_commit_callbacks):
    story = make_story()
    _plan(story, 2)
    key = _draw(story, 2).storage_key

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(RuntimeError), transaction.atomic():
            story.delete()
            raise RuntimeError("rolled back")

    assert callbacks == []
    assert get_storage().exists(key)
    assert Image.objects.filter(storage_key=key).exists()


def test_deleting_an_account_deletes_every_picture_of_its_stories(
    painters, django_capture_on_commit_callbacks
):
    rosa = User.objects.create_user("rosa@example.com")
    keep = make_story()
    _plan(keep, 2)
    kept = _draw(keep, 2).storage_key
    keys = []
    for _ in range(2):
        story = make_story(owner=rosa)
        _plan(story, 2)
        keys.append(_draw(story, 2).storage_key)

    with django_capture_on_commit_callbacks(execute=True):
        delete_account(rosa)

    assert not any(get_storage().exists(key) for key in keys)
    assert get_storage().exists(kept)
    assert Image.objects.count() == 1


def test_scenes_show_their_picture_state(painters):
    story = make_story()
    ready = _plan(story, 2)
    _draw(story, 2)
    planned = _plan(story, 3)
    skipped = _plan(story, 4)
    Image.objects.filter(pk=skipped.pk).update(
        status=ImageStatus.SKIPPED, skip_reason=SkipReason.BLOCKED
    )
    Image.objects.filter(pk=planned.pk).update(status=ImageStatus.PENDING)
    flagged = make_scene(story, 5, image_planned=True, image_kind="place")
    plain = make_scene(story, 6)
    from stories.models import Scene

    images = scene_images(Scene.objects.filter(story=story).order_by("turn"))

    assert set(images) == {2, 3, 4, 5}
    assert images[2]["status"] == "ready"
    assert images[2]["image_id"] == str(ready.id)
    assert images[2]["url"].startswith("/media/stories/")
    assert images[2]["expires_at"]
    assert images[3] == {
        "planned": True,
        "kind": "scene",
        "status": "planned",  # still being drawn: the app asks for it (M3)
        "image_id": str(planned.id),
    }
    assert images[4]["status"] == "skipped"
    assert images[5] == {"planned": True, "kind": "place", "status": "planned"}
    assert plain.turn not in images and flagged.turn in images


def test_lookups_make_local_urls_absolute_with_the_request(painters):
    story = make_story()
    _plan(story, 2)
    _draw(story, 2)
    request = SimpleNamespace(build_absolute_uri=lambda url: f"https://api.example{url}")
    from stories.models import Scene

    images = scene_images(Scene.objects.filter(story=story), request=request)

    assert images[2]["url"].startswith("https://api.example/media/")


def test_a_characters_current_portrait_is_its_latest_ready_one(painters):
    story = make_story()
    _plan(story, 1, "portrait", "rosa")
    first = _draw(story, 1)
    scene = make_scene(story, 9)
    plan_picture(
        scene, kind="portrait", subject_id="rosa", trigger="changed", redraw=True,
        brief=Brief(subject_name="Rosa", subject_appearance="grey hair now"),
    )  # fmt: skip

    before = portrait_urls(story, ["rosa", "nobody"])
    second = _draw(story, 9)
    after = portrait_urls(story, ["rosa"])

    assert set(before) == {"rosa"}
    assert first.storage_key in before["rosa"].url
    assert second.version == 2
    assert second.storage_key in after["rosa"].url


def test_a_places_current_picture_is_its_latest_ready_one(painters):
    story = make_story()
    _plan(story, 1, "place", "harbor")
    harbor = _draw(story, 1)
    _plan(story, 2, "portrait", "harbor")  # a character who shares the id is not the place
    _draw(story, 2)
    _plan(story, 3, "place", "tower")  # planned, never drawn

    urls = place_urls(story, ["harbor", "tower", "nowhere"])

    assert list(urls) == ["harbor"]
    assert harbor.storage_key in urls["harbor"].url
    assert place_url(story, "harbor") == urls["harbor"]
    assert place_url(story, "tower") is None
    assert place_url(make_story(), "harbor") is None


def test_covers_are_listed_per_story(painters):
    with_cover = make_story()
    without = make_story()
    _plan(with_cover, 3, "cover")
    _draw(with_cover, 3)
    _plan(without, 3, "cover")

    covers = cover_urls([with_cover.id, without.id])

    assert list(covers) == [str(with_cover.id)]


def test_the_export_holds_every_ready_picture_of_the_users_stories(painters):
    rosa = User.objects.create_user("rosa@example.com")
    story = make_story(owner=rosa)
    _plan(story, 1, "portrait", "rosa")
    portrait = _draw(story, 1)
    plan_picture(
        make_scene(story, 4), kind="portrait", subject_id="rosa", trigger="t", brief=Brief()
    )
    _plan(story, 5)  # planned, never drawn: not exported
    _plan(make_story(), 2)
    _draw(Image.objects.exclude(story=story).get().story, 2)

    exported = export_account(rosa, {})["images"]

    assert [(p["id"], p["kind"], p["turns"]) for p in exported] == [
        (str(portrait.id), "portrait", [1, 4])
    ]
    assert exported[0]["url"].startswith("/media/")
    assert exported == export_pictures(rosa) == signals.export_for(None, user=rosa)["images"]


def test_loading_the_app_doesnt_load_the_cloud_storage_client():
    """B10: the storage client loads on the first upload, not at startup (T3)."""
    import subprocess

    code = (
        "import sys, django, os; os.environ['DJANGO_SETTINGS_MODULE']='lucid.test_settings'; "
        "django.setup(); import lucid.asgi, lucid.urls; "
        "sys.exit(1 if 'google.cloud.storage' in sys.modules else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
