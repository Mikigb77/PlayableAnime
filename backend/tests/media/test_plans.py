"""Planning a scene's picture: made once and reused (M4), redrawn once when a character changes
for good (M5)."""

import pytest

from media.models import Image, ImageStatus, ScenePicture, SkipReason
from media.plans import brief_for_scene, look_for_story, plan_picture
from media.prompts import Brief, Figure, WorldLook
from tests.media.conftest import make_scene, make_story

pytestmark = pytest.mark.django_db

ELDER = Brief(subject_name="Elder Mo", subject_appearance="white beard, jade hairpin")


def test_a_key_npc_is_drawn_once_and_reused_in_later_scenes():
    story = make_story()
    first_meeting = plan_picture(
        make_scene(story, 2),
        kind="portrait",
        subject_id="elder-mo",
        trigger="first_meeting",
        brief=ELDER,
    )
    fight = plan_picture(
        make_scene(story, 5),
        kind="portrait",
        subject_id="elder-mo",
        trigger="fight_start",
        brief=ELDER,
    )
    other = plan_picture(
        make_scene(story, 6), kind="portrait", subject_id="disciple-li", trigger="x", brief=ELDER
    )

    assert first_meeting.image == fight.image
    assert other.image != first_meeting.image
    assert Image.objects.filter(story=story).count() == 2
    assert (fight.planned, fight.trigger, fight.image.trigger) == (
        True,
        "fight_start",
        "first_meeting",
    )


def test_scenes_have_their_own_picture_and_a_story_one_cover():
    story = make_story()

    scene = plan_picture(make_scene(story, 3), kind="scene", trigger="decisive_blow", brief=Brief())
    cover = plan_picture(make_scene(story, 4), kind="cover", trigger="cover", brief=Brief())

    assert (scene.image.subject, cover.image.subject) == ("turn-3", "cover")


def test_portraits_and_places_need_their_subject():
    story = make_story()

    with pytest.raises(ValueError):
        plan_picture(make_scene(story, 1), kind="place", trigger="first_visit", brief=Brief())
    with pytest.raises(ValueError):
        plan_picture(make_scene(story, 2), kind="mural", trigger="x", brief=Brief())


def test_planning_a_scene_twice_keeps_the_first_plan():
    story = make_story()
    scene = make_scene(story, 2)

    first = plan_picture(scene, kind="scene", trigger="big_deed", brief=Brief(description="a"))
    again = plan_picture(scene, kind="portrait", subject_id="x", trigger="y", brief=Brief())

    assert again == first
    assert ScenePicture.objects.count() == 1


def test_a_changed_character_is_redrawn_once():
    story = make_story()
    v1 = plan_picture(
        make_scene(story, 2), kind="portrait", subject_id="mo", trigger="first_meeting", brief=ELDER
    ).image
    Image.objects.filter(pk=v1.pk).update(status=ImageStatus.READY)
    scarred = Brief(subject_name="Elder Mo", subject_appearance="white beard, one eye lost")

    redrawn = plan_picture(
        make_scene(story, 9),
        kind="portrait",
        subject_id="mo",
        trigger="changed",
        brief=scarred,
        redraw=True,
    ).image
    again = plan_picture(
        make_scene(story, 12),
        kind="portrait",
        subject_id="mo",
        trigger="changed",
        brief=scarred,
        redraw=True,
    ).image

    assert redrawn.version == 2
    assert redrawn.status == ImageStatus.PLANNED
    assert again == redrawn  # the same change doesn't redraw it again
    assert Image.objects.filter(subject="mo").count() == 2


def test_a_redraw_before_the_first_portrait_is_drawn_just_draws_the_new_look():
    story = make_story()
    plan_picture(
        make_scene(story, 2), kind="portrait", subject_id="mo", trigger="first_meeting", brief=ELDER
    )
    scarred = Brief(subject_name="Elder Mo", subject_appearance="one eye lost")

    image = plan_picture(
        make_scene(story, 3),
        kind="portrait",
        subject_id="mo",
        trigger="changed",
        brief=scarred,
        redraw=True,
    ).image

    assert image.version == 1
    assert Brief.from_json(image.brief).subject_appearance == "one eye lost"


def test_a_skipped_portrait_is_planned_again_when_it_comes_up_again():
    story = make_story()
    skipped = plan_picture(
        make_scene(story, 2), kind="portrait", subject_id="mo", trigger="first_meeting", brief=ELDER
    ).image
    Image.objects.filter(pk=skipped.pk).update(
        status=ImageStatus.SKIPPED, skip_reason=SkipReason.NO_CREDITS, attempts=1
    )

    again = plan_picture(
        make_scene(story, 7), kind="portrait", subject_id="mo", trigger="fight_start", brief=ELDER
    ).image

    assert again.pk == skipped.pk
    assert (again.status, again.skip_reason, again.attempts) == (ImageStatus.PLANNED, "", 0)


def test_a_blocked_portrait_is_not_tried_again_by_a_later_plan():
    """M3: a block would most likely happen again, so only Illustrate retries it."""
    story = make_story()
    blocked = plan_picture(
        make_scene(story, 2), kind="portrait", subject_id="mo", trigger="first_meeting", brief=ELDER
    ).image
    Image.objects.filter(pk=blocked.pk).update(
        status=ImageStatus.SKIPPED, skip_reason=SkipReason.BLOCKED
    )

    again = plan_picture(
        make_scene(story, 7), kind="portrait", subject_id="mo", trigger="fight_start", brief=ELDER
    ).image

    assert (again.pk, again.status) == (blocked.pk, ImageStatus.SKIPPED)


def test_planning_marks_the_scene_row():
    story = make_story()
    scene = make_scene(story, 2)

    plan_picture(scene, kind="portrait", subject_id="mo", trigger="first_meeting", brief=ELDER)

    scene.refresh_from_db()
    assert (scene.image_planned, scene.image_kind, scene.image_status) == (
        True,
        "portrait",
        "planned",
    )


def test_a_storys_own_look_comes_from_its_bible():
    story = make_story(genre="cultivation")

    assert look_for_story(story) == WorldLook(
        genre="cultivation",
        era="an ancient empire of sects",
        tone="grim and grand",
        setting="A sect disciple with a forbidden technique.",
    )
    story.state = ["not", "a", "dict"]
    assert look_for_story(story).era == ""


def test_an_unplanned_scene_is_described_by_the_end_of_its_narration():
    story = make_story()
    prompt = make_scene(story, 2, image_prompt="Two swordsmen on a bridge in the rain.")
    long = make_scene(story, 3, narration="It began quietly. " * 80 + "The blade fell. He won.")

    assert brief_for_scene(story, prompt).description == "Two swordsmen on a bridge in the rain."
    described = brief_for_scene(story, long).description
    assert described.endswith("The blade fell. He won.")
    assert described.startswith("It began quietly.")
    assert len(described) <= 1000


def test_figures_survive_the_plan():
    story = make_story()
    brief = Brief(description="duel", figures=(Figure("mo", "Elder Mo", "beard"),))

    image = plan_picture(make_scene(story, 2), kind="scene", trigger="fight_start", brief=brief)

    assert Brief.from_json(Image.objects.get(pk=image.image.pk).brief) == brief
