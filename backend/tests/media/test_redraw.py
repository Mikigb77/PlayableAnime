"""Story pictures drawn again in the current house style (S7, M4, M5): every ready picture from an
older style, once, by the house, with the portraits drawn first so the scenes use the new ones,
and the old drawing kept until the new one is stored."""

import io
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync
from django.core.management import CommandError, call_command
from django.test import Client
from django.utils import timezone

from billing.models import LedgerEntry
from media import premise_covers, redraw
from media.drawing import DrawBlocked, DrawFailed, DrawRateLimited
from media.models import Image, ImageStatus, Payer
from media.notes import PictureNote
from media.plans import RETIRED, plan_picture
from media.prompts import HOUSE_STYLE, HOUSE_STYLE_VERSION, Brief, Figure
from media.storage import get_storage, storage_key
from stories.models import Engine, ImageKind
from tests.conftest import auth_headers
from tests.media.conftest import PNG, make_scene, make_story, story_owner

pytestmark = pytest.mark.django_db

OLD = b"old drawing"
NEW_FACE = b"new portrait"
LIN = Figure("lin", "Lin Feng", "a lean youth in grey", age=16)
LEAP = "You grip the bark and swing up, branch to branch through the old pines, at dusk."
NOTE = PictureNote(description="Lin Feng leaps between high pine branches.", people=["Lin Feng"])


@pytest.fixture(autouse=True)
def real_model(monkeypatch):
    """The configured model is a real one unless a test says otherwise; `painters` stands in."""
    monkeypatch.setattr(premise_covers, "offline_model", lambda: False)


@pytest.fixture(autouse=True)
def waits(monkeypatch) -> list[float]:
    """The pauses the drawing takes, in seconds, recorded instead of slept."""
    waited: list[float] = []

    async def wait(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(redraw, "_wait", wait)
    return waited


def run(*args) -> str:
    out = io.StringIO()
    call_command("redraw_pictures", *args, stdout=out)
    return out.getvalue()


def ready(story, kind, *, turn, subject=None, version=None, brief=None, style=1) -> Image:
    """A ready picture drawn in house style `style`, shown in scene `turn`, paid for by credits."""
    scene = make_scene(story, turn, narration=LEAP, player_action="I leap up the old pines")
    brief = brief or Brief(description="Lin Feng on a rooftop.", figures=(LIN,), turn=turn)
    link = plan_picture(
        scene, kind=kind, trigger="first_meeting", brief=brief, subject_id=subject, version=version
    )
    image = link.image
    key = storage_key(story.id, image.id, "image/png")
    get_storage().save(key, OLD, "image/png")
    Image.objects.filter(pk=image.pk).update(
        status=ImageStatus.READY,
        storage_key=key,
        mime_type="image/png",
        size_bytes=len(OLD),
        model="old-image",
        cost_usd=Decimal("0.030"),
        payer=Payer.CREDITS,
        style=style,
        ready_at=timezone.now(),
    )
    image.refresh_from_db()
    return image


def portrait(story, turn=1, version=None, **fields) -> Image:
    brief = Brief(subject_name="Lin Feng", subject_appearance="a lean youth", subject_age=16)
    return ready(
        story, ImageKind.PORTRAIT, turn=turn, subject="lin", version=version, brief=brief, **fields
    )


def drawing_of(image: Image) -> bytes:
    image.refresh_from_db()
    return get_storage().load(image.storage_key)


# Drawing again.


def test_every_older_picture_is_drawn_again_once_by_the_house(
    painters, meter, log_lines, django_capture_on_commit_callbacks
):
    story = make_story(rating="teen")
    pictures = [
        portrait(story),
        ready(story, ImageKind.PLACE, turn=2, subject="gate"),
        ready(story, ImageKind.SCENE, turn=3),
        ready(story, ImageKind.COVER, turn=4),
    ]
    old_keys = [image.storage_key for image in pictures]
    entries = LedgerEntry.objects.count()  # the owner's starter credit

    with django_capture_on_commit_callbacks(execute=True):
        out = run()

    assert "Drawing 4 pictures again (1 cover, 1 place, 1 portrait, 1 scene)" in out
    assert "Drew 4 pictures again with" in out and "paid by the house" in out
    for image, old_key in zip(pictures, old_keys, strict=True):
        assert drawing_of(image) == PNG
        assert image.style == HOUSE_STYLE_VERSION
        assert image.model == "fake-image"
        # A file of its own, and the old one gone, so no URL shows a mix of the two.
        assert image.storage_key != old_key
        assert image.storage_key.startswith(f"stories/{story.id}/{image.id}-")
        assert not get_storage().exists(old_key)
        # What the player paid for the first drawing stays on record; this one is the house's.
        assert image.payer == Payer.CREDITS and image.cost_usd == Decimal("0.030")
        assert image.status == ImageStatus.READY
    assert painters.builds == [("ours", "teen")] * 4
    assert all(HOUSE_STYLE in request.system for request in painters.ours.requests)
    assert meter.started == [] and LedgerEntry.objects.count() == entries
    lines = [line["picture"] for line in log_lines() if line["message"] == "Redrawn picture ready"]
    assert len(lines) == 4
    assert {line["payer"] for line in lines} == {"house"}
    assert {line["trigger"] for line in lines} == {"redraw_pictures"}
    assert {line["story_id"] for line in lines} == {str(story.id)}
    assert "rooftop" not in str(log_lines())  # never the prompt (T6)

    again = run()

    assert len(painters.ours.requests) == 4
    assert "Every story picture is in the current house style" in again


def test_portraits_go_first_so_scenes_and_newer_looks_use_the_new_ones(painters, meter):
    story = make_story()
    scene = ready(story, ImageKind.SCENE, turn=3)
    changed = portrait(story, turn=2, version=2)
    first = portrait(story, turn=1, version=1)
    painters.ours.script(NEW_FACE)

    run()

    requests = painters.ours.requests
    assert [r.kind for r in requests] == ["portrait", "portrait", "scene"]
    # The changed look is drawn from the new first portrait, and the scene with the new face.
    assert requests[1].references[0].data == NEW_FACE
    assert drawing_of(first) == NEW_FACE
    assert [ref.data for ref in requests[2].references] == [drawing_of(changed)]
    assert scene.pk and drawing_of(scene) == PNG


def test_a_scene_picture_is_drawn_from_a_note_on_its_scene(painters, meter, log_lines):
    story = make_story()
    ready(story, ImageKind.SCENE, turn=3)
    painters.ours.script_notes(NOTE)

    run()

    [note] = painters.ours.note_prompts
    assert note.user.endswith(f"SCENE:\n{LEAP}")
    [request] = painters.ours.requests
    assert "What it shows: Lin Feng leaps between high pine branches." in request.prompt
    [line] = [line["picture"] for line in log_lines() if line["message"] == "Redrawn picture ready"]
    assert line["noted"] is True


def test_only_ready_pictures_from_an_older_style_that_a_player_can_see(painters, meter):
    story = make_story()
    current = portrait(story, style=HOUSE_STYLE_VERSION)
    rewound = ready(story, ImageKind.SCENE, turn=2)
    Image.objects.filter(pk=rewound.pk).update(subject=f"turn-2{RETIRED}{rewound.pk.hex}")
    skipped = ready(story, ImageKind.SCENE, turn=3)
    Image.objects.filter(pk=skipped.pk).update(status=ImageStatus.SKIPPED, storage_key="")
    legacy = ready(make_story(engine=Engine.LEGACY), ImageKind.COVER, turn=1)
    wanted = ready(story, ImageKind.COVER, turn=4)

    assert redraw.to_redraw() == [wanted]
    run()

    assert drawing_of(current) == OLD
    assert drawing_of(rewound) == OLD
    assert drawing_of(legacy) == OLD
    assert drawing_of(wanted) == PNG


def test_only_the_stories_named(painters, meter):
    one, other = make_story(), make_story()
    mine = ready(one, ImageKind.COVER, turn=1)
    theirs = ready(other, ImageKind.COVER, turn=1)

    run(str(one.id))

    assert drawing_of(mine) == PNG and drawing_of(theirs) == OLD
    with pytest.raises(CommandError, match="not a story id"):
        run("nope")


def test_new_pictures_are_drawn_in_the_current_style(painters, meter):
    story = make_story()
    scene = make_scene(story, 2)
    plan_picture(scene, kind=ImageKind.SCENE, trigger="fight_start", brief=Brief(description="x"))

    client = Client(headers=auth_headers(story_owner()))
    assert client.post(f"/v1/stories/{story.id}/scenes/2/image").json()["status"] == "ready"

    assert Image.objects.get(story=story).style == HOUSE_STYLE_VERSION
    assert redraw.to_redraw() == []


# When it doesn't go as planned.


@pytest.mark.parametrize(
    "error, status, reason",
    [(DrawFailed("boom"), "failed", "failed"), (DrawBlocked(("violence",)), "blocked", "blocked")],
)
def test_a_failed_or_blocked_picture_keeps_its_old_drawing_until_the_next_run(
    painters, meter, log_lines, error, status, reason
):
    story = make_story()
    image = ready(story, ImageKind.COVER, turn=1)
    other = ready(story, ImageKind.SCENE, turn=2)
    painters.ours.script(error)

    with pytest.raises(CommandError, match="1 picture wasn't drawn again"):
        run()

    assert drawing_of(image) == OLD and image.style == 1
    assert drawing_of(other) == PNG
    [line] = [
        line["picture"] for line in log_lines() if line["message"] == "Redrawn picture skipped"
    ]
    assert line["skip_reason"] == reason
    assert [o.kind for o in redraw.to_redraw()] == ["cover"]

    run()

    assert drawing_of(image) == PNG


def test_a_picture_out_of_quota_is_drawn_again_after_a_wait(painters, meter, waits):
    story = make_story()
    image = ready(story, ImageKind.COVER, turn=1)
    painters.ours.script(DrawRateLimited("transient_429"))

    run()

    assert waits == [redraw.RATE_LIMIT_WAIT_S]
    assert drawing_of(image) == PNG


def test_pictures_are_drawn_apart(painters, meter, waits):
    story = make_story()
    for turn in (1, 2, 3):
        ready(story, ImageKind.SCENE, turn=turn)

    run()

    assert waits == [redraw.PAUSE_S] * 2


def test_a_picture_that_changed_meanwhile_keeps_what_it_has(
    painters, meter, django_capture_on_commit_callbacks
):
    story = make_story()
    image = ready(story, ImageKind.COVER, turn=1)
    gone = ready(story, ImageKind.SCENE, turn=2)
    before = {image.storage_key, gone.storage_key}
    newer_key = storage_key(story.id, image.id, "image/png", fresh=True)
    get_storage().save(newer_key, b"drawn meanwhile", "image/png")
    stale = redraw.to_redraw()
    Image.objects.filter(pk=image.pk).update(storage_key=newer_key)
    Image.objects.filter(pk=gone.pk).delete()

    with django_capture_on_commit_callbacks(execute=True):
        outcomes = async_to_sync(redraw.redraw_all)(stale, offline=False).outcomes

    assert [o.status for o in outcomes] == ["kept", "kept"]
    assert len(painters.ours.requests) == 2
    assert drawing_of(image) == b"drawn meanwhile"
    # Both new drawings went; nothing else was touched.
    folder = get_storage().root / "stories" / str(story.id)
    assert {f"stories/{story.id}/{f.name}" for f in folder.iterdir()} == before | {newer_key}


def test_a_run_stops_at_its_budget_and_leaves_the_rest_to_the_next(painters, meter):
    story = make_story()
    for turn in (1, 2, 3):
        ready(story, ImageKind.SCENE, turn=turn)

    out = run("--max-usd", "0.05")

    assert len(painters.ours.requests) == 2  # $0.034 each: the second goes past $0.05
    assert "Stopped at the $0.05 budget with 1 picture left" in out
    assert len(redraw.to_redraw()) == 1


def test_a_run_stops_starting_drawings_at_its_time_limit(painters, meter, monkeypatch):
    story = make_story()
    for turn in (1, 2):
        ready(story, ImageKind.SCENE, turn=turn)
    # The run starts at 0 s, and the first drawing takes two minutes.
    clock = iter([0.0, 0.0])
    monkeypatch.setattr(redraw, "_clock", lambda: next(clock, 120.0))

    found = redraw.to_redraw()
    result = async_to_sync(redraw.redraw_all)(found, offline=False, minutes=1)

    assert len(result.outcomes) == 1
    assert result.left == 1 and result.stopped_by == "time"


# The command.


def test_a_dry_run_counts_and_estimates_without_drawing(painters, meter):
    story = make_story()
    portrait(story)
    ready(story, ImageKind.SCENE, turn=2)

    out = run("--dry-run")

    assert "Would draw 2 pictures again (1 portrait, 1 scene) in 1 story" in out
    assert "about $" in out
    assert painters.ours.requests == []


@pytest.mark.parametrize("args", [("--max-usd", "0"), ("--max-usd", "NaN"), ("--minutes", "0")])
def test_a_run_needs_a_budget_and_time(args):
    with pytest.raises(CommandError, match="more than 0"):
        run(*args)


def test_the_offline_model_never_draws_into_the_bucket(settings, monkeypatch):
    monkeypatch.setattr(premise_covers, "offline_model", lambda: True)
    settings.MEDIA_BUCKET = "lucid-pictures"

    with pytest.raises(CommandError, match="offline model"):
        run()


def test_a_fresh_storage_key_is_new_each_time():
    first = storage_key("s1", "i1", "image/png", fresh=True)

    assert first.startswith("stories/s1/i1-") and first.endswith(".png")
    assert first != storage_key("s1", "i1", "image/png", fresh=True)
