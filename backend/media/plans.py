"""Planning a scene's picture: which subject it shows, reusing a picture that already exists.

Code decides when a scene gets a picture (M1, the director's `PictureDecision`), never the
narrator. The turn calls `plan_picture()` in the transaction that saves the scene, with what to
draw. Nothing is drawn yet: the app asks for the picture in its own request once the narration
is shown (M3, B8).
"""

from __future__ import annotations

from django.db import IntegrityError, transaction

from engine.contracts import FIRST_PICTURES
from media.models import Image, ImageStatus, ScenePicture, SkipReason
from media.prompts import Brief, WorldLook
from stories.models import ImageKind, Scene, Story

ILLUSTRATE = "illustrate"
# A portrait or place skipped for these reasons is tried again when code next plans it. A blocked
# one would most likely be blocked again, so only Illustrate tries it again (M3).
RETRIED_WHEN_PLANNED = (SkipReason.FAILED, SkipReason.NO_CREDITS)
# A scene marked planned without a plan (`Scene.image_planned`), such as by hand in a test.
SCENE_FLAG = "scene_flag"


def subject_for(kind: str, scene: Scene, subject_id: str | None) -> str:
    """Portraits and places are keyed by the character or place, so they are reused (M4). A
    scene picture belongs to its turn, and a story has one cover."""
    if kind == ImageKind.SCENE:
        return f"turn-{scene.turn}"
    if kind == ImageKind.COVER:
        return "cover"
    if kind not in (ImageKind.PORTRAIT, ImageKind.PLACE):
        raise ValueError(f"Unknown picture kind {kind!r}")
    if not subject_id:
        raise ValueError(f"A {kind} picture needs the id of its character or place")
    return subject_id


def plan_picture(
    scene: Scene,
    *,
    kind: str,
    trigger: str,
    brief: Brief,
    subject_id: str | None = None,
    version: int | None = None,
    planned: bool = True,
) -> ScenePicture:
    """Plans the picture `scene` shows: a portrait, a place, the scene itself or the cover.

    Call it after the scene is saved, inside the turn's transaction. A portrait or place that
    already has a picture is reused instead of drawn again (M4), and one that failed or wasn't
    affordable is planned again; a blocked one is tried again only through Illustrate (M3).
    `version` is the look version of a portrait or place (`engine.looks`): each version is drawn
    once, so a place or face that changed for good is drawn once more and that picture is reused
    from then on (M1, M5). Without one, the latest version is reused. `planned` is false for a
    picture the player asked for with Illustrate (M2). Planning a scene that already has a
    picture returns its existing plan.
    """
    subject = subject_for(kind, scene, subject_id)
    if kind not in (ImageKind.PORTRAIT, ImageKind.PLACE):
        version = None
    with transaction.atomic():
        # Serialises planning per scene, so two requests can't both plan it.
        Scene.objects.select_for_update().filter(pk=scene.pk).first()
        existing = ScenePicture.objects.select_related("image").filter(scene=scene).first()
        if existing is not None:
            return existing
        image = _image_for(scene.story_id, kind, subject, trigger, brief, version=version)
        link = ScenePicture.objects.create(
            scene=scene, image=image, planned=planned, trigger=trigger
        )
        fields = {"image_kind": kind} | ({"image_planned": True} if planned else {})
        Scene.objects.filter(pk=scene.pk).update(**fields)
        image.sync_scenes()
        return link


def plan_again(image: Image, *, trigger: str) -> None:
    """Plans a skipped picture again, as when the player asks for it with Illustrate (M2). The
    caller holds the picture's row lock and saves it."""
    if image.status == ImageStatus.SKIPPED:
        _reset(image, trigger)


def _image_for(
    story_id, kind: str, subject: str, trigger: str, brief: Brief, *, version: int | None
) -> Image:
    pictures = Image.objects.select_for_update().filter(
        story_id=story_id, kind=kind, subject=subject
    )
    if version is not None:
        pictures = pictures.filter(version=version)
    image = pictures.order_by("-version").first()
    if image is None:
        return _create(story_id, kind, subject, version or 1, trigger, brief)
    if image.status == ImageStatus.SKIPPED and image.skip_reason in RETRIED_WHEN_PLANNED:
        _reset(image, trigger)
        image.brief = brief.to_json()
        image.save()
    return image


def _create(story_id, kind: str, subject: str, version: int, trigger: str, brief: Brief) -> Image:
    try:
        with transaction.atomic():
            return Image.objects.create(
                story_id=story_id,
                kind=kind,
                subject=subject,
                version=version,
                trigger=trigger,
                first_picture=trigger in FIRST_PICTURES,
                brief=brief.to_json(),
            )
    except IntegrityError:
        # Another turn or request planned the same subject at the same moment: share it.
        return Image.objects.get(story_id=story_id, kind=kind, subject=subject, version=version)


def _reset(image: Image, trigger: str) -> None:
    image.status = ImageStatus.PLANNED
    image.skip_reason = ""
    image.trigger = trigger
    image.attempts = 0
    image.claim = None
    image.claimed_at = None


def look_for_story(story: Story) -> WorldLook:
    """The world's look from the story itself, for a picture nobody planned with a brief, such
    as Illustrate on any scene. Reads the bible's genre, era and tone when the story has one."""
    state = story.state if isinstance(story.state, dict) else {}
    bible = state.get("bible") if isinstance(state.get("bible"), dict) else {}
    return WorldLook(
        genre=str(bible.get("genre") or story.genre or ""),
        era=str(bible.get("era") or ""),
        tone=str(bible.get("tone") or ""),
        setting=story.premise,
    )


def brief_for_scene(story: Story, scene: Scene) -> Brief:
    """What to draw for a scene nobody wrote an image prompt for: the scene's own text, which the
    picture rules keep mild (M6)."""
    description = scene.image_prompt or _ending(scene.narration)
    return Brief(description=description, look=look_for_story(story))


def _ending(text: str, limit: int = 1000) -> str:
    """The end of a long narration, where the scene's moment is, from a sentence start."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    tail = text[-limit:]
    ends = [i for i in (tail.find(". "), tail.find("! "), tail.find("? ")) if i >= 0]
    cut = min(ends, default=-1)
    return tail[cut + 2 :] if 0 <= cut < limit // 2 else tail
