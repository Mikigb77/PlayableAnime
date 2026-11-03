"""Concurrent requests for one picture, on separate database connections as on Cloud Run: one
drawing, one charge (M3, M7)."""

import threading
import time

import pytest
from django.db import connection
from django.test import Client

from media.models import Image, ImageStatus, Payer
from media.plans import plan_picture
from media.prompts import Brief
from media.storage import get_storage
from tests.media.conftest import make_scene, make_story

pytestmark = pytest.mark.django_db(transaction=True)


def _in_thread(target):
    results: list = []

    def run() -> None:
        try:
            results.append(target())
        finally:
            connection.close()

    thread = threading.Thread(target=run)
    thread.start()
    return thread, results


def test_requests_that_arrive_while_a_picture_is_drawn_get_pending(painters, meter):
    story = make_story()
    plan_picture(make_scene(story, 2), kind="scene", trigger="fight_start", brief=Brief())
    url = f"/v1/stories/{story.id}/scenes/2/image"
    painters.ours.gate = threading.Event()

    drawer, drawn = _in_thread(lambda: Client().post(url).json())
    assert painters.ours.started.wait(10)
    waiting = [Client().post(url).json() for _ in range(3)]
    painters.ours.gate.set()
    drawer.join(10)
    after = Client().post(url).json()

    assert [body["status"] for body in waiting] == ["pending"] * 3
    assert drawn[0]["status"] == after["status"] == "ready"
    assert painters.drawings == 1
    assert (len(meter.started), len(meter.charged), meter.released) == (1, 1, [])


def test_two_requests_at_the_same_instant_draw_once(painters, meter):
    story = make_story()
    plan_picture(make_scene(story, 2), kind="scene", trigger="fight_start", brief=Brief())
    url = f"/v1/stories/{story.id}/scenes/2/image"
    painters.ours.gate = threading.Event()
    start = threading.Barrier(2)

    def ask():
        start.wait(10)
        return Client().post(url).json()["status"]

    threads = [_in_thread(ask) for _ in range(2)]
    assert painters.ours.started.wait(10)
    # The request that lost the claim answers while the winner is still drawing.
    deadline = time.monotonic() + 10
    while not any(result for _, result in threads) and time.monotonic() < deadline:
        time.sleep(0.01)
    painters.ours.gate.set()
    for thread, _ in threads:
        thread.join(10)

    assert sorted(result[0] for _, result in threads) == ["pending", "ready"]
    assert painters.drawings == 1
    assert len(meter.charged) == 1


def test_a_slow_request_that_lost_its_claim_keeps_the_winners_picture(painters, meter):
    """A request whose claim ran out finishes after another request made the picture: it
    charges nothing, releases its hold and deletes its own file."""
    story = make_story()
    image = plan_picture(make_scene(story, 2), kind="scene", trigger="t", brief=Brief()).image
    url = f"/v1/stories/{story.id}/scenes/2/image"
    painters.ours.gate = threading.Event()

    slow, result = _in_thread(lambda: Client().post(url).json())
    assert painters.ours.started.wait(10)
    get_storage().save("stories/winner.png", b"winner", "image/png")
    Image.objects.filter(pk=image.pk).update(
        status=ImageStatus.READY, storage_key="stories/winner.png", payer=Payer.CREDITS
    )
    painters.ours.gate.set()
    slow.join(10)

    assert result[0]["status"] == "ready"
    assert "stories/winner.png" in result[0]["url"]
    assert (meter.charged, meter.released) == ([], [1])
    assert not get_storage().exists(f"stories/{story.id}/{image.id}.png")


def test_a_slow_drawing_still_counts_when_the_picture_was_put_back_meanwhile(painters, meter):
    """A request whose claim ran out finishes while nobody else is drawing (another request took
    over and was rate limited, which puts the picture back): the finished drawing is kept."""
    story = make_story()
    image = plan_picture(make_scene(story, 2), kind="scene", trigger="t", brief=Brief()).image
    url = f"/v1/stories/{story.id}/scenes/2/image"
    painters.ours.gate = threading.Event()

    slow, result = _in_thread(lambda: Client().post(url).json())
    assert painters.ours.started.wait(10)
    Image.objects.filter(pk=image.pk).update(status=ImageStatus.PLANNED, claim=None)
    painters.ours.gate.set()
    slow.join(10)

    assert result[0]["status"] == "ready"
    assert Image.objects.get(pk=image.pk).status == ImageStatus.READY
    assert (len(meter.charged), meter.released) == (1, [])


def test_a_story_deleted_while_its_picture_is_drawn_leaves_no_file(painters, meter):
    story = make_story()
    image = plan_picture(make_scene(story, 2), kind="scene", trigger="t", brief=Brief()).image
    url = f"/v1/stories/{story.id}/scenes/2/image"
    painters.ours.gate = threading.Event()

    slow, result = _in_thread(lambda: Client().post(url).json())
    assert painters.ours.started.wait(10)
    story.delete()
    painters.ours.gate.set()
    slow.join(10)

    assert result[0]["status"] == "skipped"
    assert meter.released == [1]
    assert not get_storage().exists(f"stories/{story.id}/{image.id}.png")
