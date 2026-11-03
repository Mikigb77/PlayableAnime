"""The picture endpoints: drawn and charged at most once, `pending` while drawing, `skipped`
quietly on a failure, a block or no credits (M2, M3, M7)."""

from datetime import date, timedelta

import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import Role, User
from lucid.errors import ApiError, ErrorCode
from media import billing
from media.drawing import DrawBlocked, DrawFailed, KeyCannotDraw
from media.models import Image, ImageStatus, Payer, SkipReason
from media.plans import plan_picture
from media.prompts import Brief, Figure
from media.service import LEASE, MAX_ATTEMPTS
from media.storage import get_storage
from tests.conftest import auth_headers
from tests.media.conftest import PNG, make_scene, make_story, story_owner

pytestmark = pytest.mark.django_db


@pytest.fixture
def client() -> Client:
    """Signed in as the player who owns the test stories."""
    return Client(headers=auth_headers(story_owner()))


def _image(client: Client, story, turn: int, **headers):
    return client.post(f"/v1/stories/{story.id}/scenes/{turn}/image", headers=headers)


def _illustrate(client: Client, story, turn: int, **headers):
    return client.post(f"/v1/stories/{story.id}/scenes/{turn}/illustrate", headers=headers)


def _planned_scene(story, turn: int = 2, **brief):
    scene = make_scene(story, turn)
    plan_picture(scene, kind="scene", trigger="fight_start", brief=Brief(**brief))
    return scene


def test_a_planned_picture_is_drawn_stored_and_served(client, painters, meter, log_lines):
    story = make_story()
    _planned_scene(story, description="Two swordsmen clash on a bridge.")

    response = _image(client, story, 2)

    assert response.status_code == 200, response.content
    body = response.json()
    image = Image.objects.get(story=story)
    assert body["status"] == "ready"
    assert body["image_id"] == str(image.id)
    assert body["kind"] == "scene"
    assert body["url"].startswith("http://testserver/media/stories/")
    assert body["expires_at"]
    assert image.status == ImageStatus.READY
    assert (image.model, image.payer, image.attempts) == ("fake-image", Payer.CREDITS, 1)
    assert image.storage_key == f"stories/{story.id}/{image.id}.png"
    assert get_storage().load(image.storage_key) == PNG
    served = client.get(body["url"])
    assert served.status_code == 200
    assert b"".join(served.streaming_content) == PNG
    # Drawn on our account, mature story, with the story's look and the planned description.
    assert painters.builds == [("ours", "mature")]
    request = painters.ours.requests[0]
    assert "Two swordsmen clash on a bridge." in request.prompt
    assert "an ancient empire of sects" not in request.prompt  # the plan's brief, not the story's
    assert request.aspect_ratio == "16:9"
    assert len(meter.started) == 1
    assert meter.charged == [
        {
            "hold": 1,
            "calls": (painters.ours.call,),
            "cost": image.cost_usd,
            "turn": 2,
            "image": image.id,
        }
    ]
    picture_lines = [line for line in log_lines() if line.get("picture")]
    assert len(picture_lines) == 1
    line = picture_lines[0]
    assert line["story_id"] == str(story.id)
    assert line["picture"] | {"latency_ms": 0} == line["picture"] | {
        "image_id": str(image.id),
        "status": "ready",
        "model": "fake-image",
        "cost_usd": 0.034,
        "payer": "credits",
        "trigger": "fight_start",
        "latency_ms": 0,
    }
    assert "swordsmen" not in str(line)  # never the prompt (T6)


def test_the_scenes_showing_a_picture_follow_its_state(client, painters, meter):
    story = make_story()
    _planned_scene(story, 2)
    _planned_scene(story, 3)
    painters.ours.script(PNG, DrawFailed("x"))

    _image(client, story, 2)
    _image(client, story, 3)

    from stories.models import Scene

    statuses = dict(Scene.objects.filter(story=story).values_list("turn", "image_status"))
    assert statuses == {2: "ready", 3: "skipped"}
    assert not Scene.objects.filter(story=story).exclude(image_url=None).exists()


def test_asking_again_never_draws_or_charges_twice(client, painters, meter):
    story = make_story()
    _planned_scene(story)

    first = _image(client, story, 2).json()
    again = _image(client, story, 2).json()
    illustrated = _illustrate(client, story, 2).json()

    assert first["status"] == again["status"] == illustrated["status"] == "ready"
    assert first["image_id"] == again["image_id"] == illustrated["image_id"]
    assert painters.drawings == 1
    assert (len(meter.started), len(meter.charged)) == (1, 1)


def test_a_scene_without_a_planned_picture_is_skipped(client, painters, meter):
    story = make_story()
    make_scene(story, 2)

    body = _image(client, story, 2).json()

    assert body == {
        "status": "skipped",
        "image_id": None,
        "kind": None,
        "url": None,
        "expires_at": None,
    }
    assert painters.drawings == 0
    assert not Image.objects.exists()


def test_a_scene_marked_planned_by_hand_gets_its_own_picture(client, painters, meter):
    story = make_story()
    make_scene(story, 3, image_planned=True, image_kind="portrait", image_prompt="A duel at dawn.")

    body = _image(client, story, 3).json()

    image = Image.objects.get(pk=body["image_id"])
    assert (body["status"], image.kind, image.subject) == ("ready", "scene", "turn-3")
    assert "A duel at dawn." in painters.ours.requests[0].prompt
    assert "an ancient empire of sects" in painters.ours.requests[0].prompt  # the story's look


def test_pictures_turned_off_are_skipped_but_illustrate_still_draws(client, painters, meter):
    story = make_story(settings={"images": "off"})
    _planned_scene(story)

    assert _image(client, story, 2).json()["status"] == "skipped"
    assert painters.drawings == 0
    assert _illustrate(client, story, 2).json()["status"] == "ready"
    assert painters.drawings == 1


@pytest.mark.parametrize(
    ("failure", "reason"),
    [(DrawFailed("llm_unavailable"), SkipReason.FAILED), (DrawBlocked(("sexual",)), "blocked")],
)
def test_a_failed_or_blocked_picture_is_skipped_quietly_and_not_charged(
    client, painters, meter, log_lines, failure, reason
):
    story = make_story()
    _planned_scene(story)
    painters.ours.script(failure)

    first = _image(client, story, 2)
    again = _image(client, story, 2).json()

    assert first.status_code == 200
    assert first.json()["status"] == again["status"] == "skipped"
    image = Image.objects.get(story=story)
    assert (image.status, image.skip_reason) == (ImageStatus.SKIPPED, reason)
    assert painters.drawings == 1  # never retried by a repeat (M3)
    assert (meter.charged, meter.released) == ([], [1])
    line = next(line for line in log_lines() if line.get("picture"))
    assert line["picture"]["skip_reason"] == reason
    if reason == "blocked":
        assert line["picture"]["block_categories"] == ["sexual"]


def test_without_credits_the_picture_is_skipped_and_never_drawn(client, painters, meter):
    story = make_story()
    _planned_scene(story)
    meter.refuse = billing.NoCredits()

    body = _image(client, story, 2).json()

    assert body["status"] == "skipped"
    assert Image.objects.get(story=story).skip_reason == SkipReason.NO_CREDITS
    assert painters.drawings == 0
    assert meter.charged == []


def test_a_rate_limit_is_passed_on_and_the_picture_stays_planned(client, painters, meter):
    story = make_story()
    _planned_scene(story)
    meter.refuse = ApiError(ErrorCode.RATE_LIMITED, details={"retry_after_s": 5})

    limited = _image(client, story, 2)

    assert limited.status_code == 429
    assert limited.json()["error"]["details"] == {"retry_after_s": 5}
    image = Image.objects.get(story=story)
    assert (image.status, image.attempts, image.claim) == (ImageStatus.PLANNED, 0, None)
    meter.refuse = None
    assert _image(client, story, 2).json()["status"] == "ready"


def test_a_picture_being_drawn_answers_pending(client, painters, meter):
    story = make_story()
    _planned_scene(story)
    Image.objects.update(status=ImageStatus.PENDING, claimed_at=timezone.now(), attempts=1)

    body = _image(client, story, 2).json()

    assert body["status"] == "pending"
    assert body["image_id"] == str(Image.objects.get().id)
    assert painters.drawings == 0


def test_a_claim_left_by_a_request_that_died_is_taken_over(client, painters, meter):
    story = make_story()
    _planned_scene(story)
    stale = timezone.now() - LEASE - timedelta(seconds=1)
    Image.objects.update(status=ImageStatus.PENDING, claimed_at=stale, attempts=1)

    assert _image(client, story, 2).json()["status"] == "ready"
    assert Image.objects.get().attempts == 2


def test_a_picture_that_keeps_dying_is_given_up(client, painters, meter):
    story = make_story()
    _planned_scene(story)
    stale = timezone.now() - LEASE - timedelta(seconds=1)
    Image.objects.update(status=ImageStatus.PENDING, claimed_at=stale, attempts=MAX_ATTEMPTS)

    assert _image(client, story, 2).json()["status"] == "skipped"
    assert Image.objects.get().skip_reason == SkipReason.FAILED
    assert painters.drawings == 0


def test_illustrate_draws_any_scene_and_retries_a_skipped_one(client, painters, meter):
    story = make_story()
    make_scene(story, 4, narration="The rain stops. Lin draws her blade.")
    _planned_scene(story, 5)
    painters.ours.script(DrawFailed("x"))
    assert _image(client, story, 5).json()["status"] == "skipped"

    unplanned = _illustrate(client, story, 4).json()
    retried = _illustrate(client, story, 5).json()

    assert unplanned["status"] == retried["status"] == "ready"
    assert "Lin draws her blade." in painters.ours.requests[1].prompt
    images = {i.subject: i for i in Image.objects.all()}
    assert images["turn-4"].trigger == "illustrate"
    assert images["turn-5"].status == ImageStatus.READY
    assert painters.drawings == 3


def test_a_players_own_key_draws_for_free(client, painters, meter):
    story = make_story()
    _planned_scene(story)

    body = _image(client, story, 2, **{"X-LLM-Provider": "gemini", "X-LLM-Api-Key": "k"}).json()

    assert body["status"] == "ready"
    assert painters.builds == [("byok", "mature")]
    assert meter.started == []
    image = Image.objects.get()
    assert (image.payer, image.model) == (Payer.BYOK, "byok-image")


def test_a_key_that_cant_draw_falls_back_to_credits(client, painters, meter, log_lines):
    story = make_story()
    _planned_scene(story)
    painters.byok.script(KeyCannotDraw("bad_key"))

    body = _image(client, story, 2, **{"X-LLM-Api-Key": "free-tier"}).json()

    assert body["status"] == "ready"
    assert [kind for kind, _ in painters.builds] == ["byok", "ours"]
    assert (len(meter.started), len(meter.charged)) == (1, 1)
    assert Image.objects.get().payer == Payer.CREDITS
    line = next(line for line in log_lines() if line.get("picture"))
    assert (line["picture"]["byok"], line["picture"]["byok_fell_back"]) == (True, True)
    assert "free-tier" not in str(log_lines())  # never the key (T6)


def test_an_unknown_key_provider_is_refused_before_anything_is_drawn(client, painters, meter):
    story = make_story()
    _planned_scene(story)

    response = _image(client, story, 2, **{"X-LLM-Provider": "openai", "X-LLM-Api-Key": "k"})

    assert response.status_code == 400
    assert response.json()["error"]["details"]["fields"][0]["field"] == "X-LLM-Provider"
    assert Image.objects.get().status == ImageStatus.PLANNED


def test_known_characters_portraits_go_along_as_references(client, painters, meter):
    story = make_story()
    rosa = plan_picture(
        make_scene(story, 1), kind="portrait", subject_id="rosa", trigger="story_start",
        brief=Brief(subject_name="Rosa", subject_appearance="dark curls"),
    )  # fmt: skip
    assert _image(client, story, 1).json()["status"] == "ready"
    _planned_scene(
        story, 2, description="Rosa duels a stranger.",
        figures=(Figure("stranger", "Stranger", "hooded"), Figure("rosa", "Rosa", "dark curls")),
    )  # fmt: skip

    assert _image(client, story, 2).json()["status"] == "ready"

    scene_request = painters.ours.requests[1]
    assert [(ref.name, ref.data) for ref in scene_request.references] == [("Rosa", PNG)]
    assert "reference portraits of Rosa" in scene_request.prompt
    assert rosa.image.kind == "portrait"


def test_a_redrawn_portrait_is_drawn_from_the_earlier_one(client, painters, meter):
    story = make_story()
    plan_picture(
        make_scene(story, 1), kind="portrait", subject_id="mo", trigger="first_meeting",
        brief=Brief(subject_name="Mo", subject_appearance="two eyes"),
    )  # fmt: skip
    _image(client, story, 1)
    plan_picture(
        make_scene(story, 8), kind="portrait", subject_id="mo", trigger="changed", redraw=True,
        brief=Brief(subject_name="Mo", subject_appearance="one eye lost"),
    )  # fmt: skip

    body = _image(client, story, 8).json()

    assert body["status"] == "ready"
    redraw = painters.ours.requests[1]
    assert [ref.name for ref in redraw.references] == ["Mo"]
    assert "earlier portrait" in redraw.prompt
    assert redraw.aspect_ratio == "3:4"
    assert Image.objects.get(pk=body["image_id"]).version == 2


def test_the_owner_pays_nothing(client, painters):
    owner = User.objects.create_user("owner@example.com", role=Role.OWNER)
    story = make_story(owner=owner)
    _planned_scene(story)
    image = Image.objects.get()

    async def run():
        from media.service import scene_picture
        from stories.models import Scene

        scene = await Scene.objects.aget(story=story, turn=2)
        return await scene_picture(story, scene, user=owner)

    from asgiref.sync import async_to_sync

    result = async_to_sync(run)()

    assert result.status == "ready"
    image.refresh_from_db()
    assert image.payer == Payer.OWNER


def test_a_storage_failure_skips_the_picture_and_releases_its_hold(
    client, painters, meter, monkeypatch
):
    story = make_story()
    _planned_scene(story)
    local = get_storage()

    def broken(key, data, mime_type):
        raise OSError("disk full")

    monkeypatch.setattr(local, "save", broken)

    assert _image(client, story, 2).json()["status"] == "skipped"
    assert meter.released == [1]
    assert meter.charged == []


def test_a_player_who_leaves_mid_drawing_leaves_the_picture_for_the_next_request(painters, meter):
    """Django cancels the view when the client disconnects. Nothing runs on (B8): the hold is
    released and the picture is planned again, not stuck as pending."""
    import asyncio
    import threading

    from asgiref.sync import async_to_sync

    from media.service import scene_picture
    from stories.models import Scene

    story = make_story()
    _planned_scene(story)
    scene = Scene.objects.get(story=story, turn=2)
    painters.ours.gate = threading.Event()

    async def leave_mid_drawing():
        task = asyncio.create_task(scene_picture(story, scene, user=None))
        await asyncio.to_thread(painters.ours.started.wait, 10)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return "cancelled"
        finally:
            painters.ours.gate.set()

    assert async_to_sync(leave_mid_drawing)() == "cancelled"

    image = Image.objects.get()
    assert (image.status, image.claim, image.attempts) == (ImageStatus.PLANNED, None, 0)
    assert meter.released == [1]
    assert meter.charged == []
    assert not any(get_storage().root.rglob("*.png"))


def test_a_picture_is_fetched_again_with_a_fresh_url(client, painters, meter):
    story = make_story()
    _planned_scene(story)
    image_id = _image(client, story, 2).json()["image_id"]

    body = client.get(f"/v1/stories/{story.id}/images/{image_id}").json()

    assert body["status"] == "ready"
    assert body["url"].startswith("http://testserver/media/")
    assert painters.drawings == 1


def test_a_planned_picture_reads_as_pending_until_it_is_asked_for(client):
    story = make_story()
    image = plan_picture(make_scene(story, 2), kind="scene", trigger="t", brief=Brief()).image

    body = client.get(f"/v1/stories/{story.id}/images/{image.id}").json()

    assert (body["status"], body["url"]) == ("pending", None)


@pytest.mark.parametrize(
    "path",
    [
        "/v1/stories/{story}/scenes/9/image",
        "/v1/stories/not-a-uuid/scenes/2/image",
        "/v1/stories/00000000-0000-0000-0000-000000000000/scenes/2/image",
        "/v1/stories/{story}/images/{other_image}",
        "/v1/stories/{story}/images/nope",
    ],
)
def test_unknown_stories_scenes_and_pictures_are_not_found(client, path):
    story = make_story()
    other = make_story()
    other_image = plan_picture(make_scene(other, 2), kind="scene", trigger="t", brief=Brief())
    url = path.format(story=story.id, other_image=other_image.image.id)

    response = client.get(url) if "/images/" in url else client.post(url)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_someone_elses_story_is_forbidden(client):
    owner = User.objects.create_user("rosa@example.com")
    story = make_story(owner=owner)
    _planned_scene(story)

    response = _image(client, story, 2)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert Image.objects.get().status == ImageStatus.PLANNED


def test_a_story_above_the_accounts_rating_limit_is_forbidden(painters, meter):
    fifteen = date.today() - timedelta(days=15 * 366)
    teen = User.objects.create_user("kai@example.com", birth_date=fifteen)
    story = make_story(owner=teen, rating="mature")
    _planned_scene(story)

    response = _image(Client(headers=auth_headers(teen)), story, 2)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert painters.drawings == 0


@pytest.mark.parametrize(
    "method, path",
    [("post", "scenes/2/image"), ("post", "scenes/2/illustrate"), ("get", "images/{image}")],
)
def test_pictures_need_a_signed_in_player(painters, meter, method, path):
    story = make_story()
    image = _planned_scene(story).picture.image

    response = getattr(Client(), method)(f"/v1/stories/{story.id}/" + path.format(image=image.id))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert painters.drawings == 0
