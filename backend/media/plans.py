"""Planning a scene's picture: which subject it shows, reusing a picture that already exists.

Code decides when a scene gets a picture (M1, the director's `PictureDecision`), never the
narrator. The turn calls `plan_picture()` in the transaction that saves the scene, with what to
draw. Nothing is drawn yet: the app asks for the picture in its own request once the narration
is shown (M3, B8).
"""

from __future__ import annotations

from django.db import IntegrityError, transaction

from engine.contracts import FIRST_PICTURES
from engine.looks import place_version
from engine.state.world import WorldState
from lucid.errors import ApiError, ErrorCode
from media.briefs import player_at, scene_figures, time_of_day
from media.models import Image, ImageStatus, ScenePicture, SkipReason
from media.prompts import Brief, WorldLook
from stories.models import ImageKind, Scene, Story

ILLUSTRATE = "illustrate"
# A portrait or place skipped for these reasons is tried again when code next plans it. A blocked
# one would most likely be blocked again, so only Illustrate tries it again (M3).
RETRIED_WHEN_PLANNED = (SkipReason.FAILED, SkipReason.NO_CREDITS)
# A scene marked planned without a plan (`Scene.image_planned`), such as by hand in a test.
SCENE_FLAG = "scene_flag"
# C8: what marks the subject of a picture a rewind took out of the story, so nothing reuses it.
RETIRED = "~"


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
        locked = Scene.objects.select_for_update().filter(pk=scene.pk).only("rewound_at").first()
        if locked is not None and locked.rewound_at is not None:
            # A rewind took the scene back while this waited (C8): the story no longer has it.
            raise ApiError(ErrorCode.NOT_FOUND, "Scene not found.")
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


def retire_rewound(story_id, state: WorldState, scene_ids) -> int:
    """C8: takes the pictures a rewind took out of the story out of reuse, in the rewind's
    transaction: the pictures of the rewound scenes `scene_ids`, so a scene played anew in their
    turn gets its own, and each portrait or place drawn for a look the world as it is now
    (`state`) never had, so a face or place that changes again is drawn again (M1, M4, M5).
    Their rows stay, renamed, with what they cost. Returns how many it took out."""
    retired = list(
        Image.objects.filter(
            story_id=story_id, kind=ImageKind.SCENE, scene_links__scene_id__in=list(scene_ids)
        ).exclude(subject__contains=RETIRED)
    )
    looks = Image.objects.filter(
        story_id=story_id, kind__in=(ImageKind.PORTRAIT, ImageKind.PLACE)
    ).exclude(subject__contains=RETIRED)
    for image in looks.only("id", "kind", "subject", "version"):
        if image.version > _look_now(state, image.kind, image.subject):
            retired.append(image)
    for image in retired:
        # Unique per picture, and within the column's length.
        room = Image._meta.get_field("subject").max_length - len(RETIRED) - 32
        image.subject = f"{image.subject[:room]}{RETIRED}{image.pk.hex}"
    Image.objects.bulk_update(retired, ["subject"])
    return len(retired)


def _look_now(state: WorldState, kind: str, subject: str) -> int:
    """The look version a portrait's character or a place has in `state`, or 0 if it has none."""
    if kind == ImageKind.PORTRAIT:
        character = state.characters.get(subject)
        return character.look_version if character is not None else 0
    place = state.places.get(subject)
    return place_version(place) if place is not None else 0


def look_for_story(story: Story) -> WorldLook:
    """The world's look from the story itself: the bible's genre, era and tone when the story
    has one. Never its premise, which tells how the story began, not the scene a picture shows,
    and would bring its places and things into a picture that has none of them (M5)."""
    state = story.state if isinstance(story.state, dict) else {}
    bible = state.get("bible") if isinstance(state.get("bible"), dict) else {}
    return WorldLook(
        genre=str(bible.get("genre") or story.genre or ""),
        era=str(bible.get("era") or ""),
        tone=str(bible.get("tone") or ""),
    )


def brief_for_scene(story: Story, scene: Scene) -> Brief:
    """What to draw for a scene nobody planned a picture for, such as Illustrate on any scene: the
    scene's own text, which the picture rules keep mild (M6), with the people it names as they
    look and their reference portraits (M5), who "you" is, and the time of day, as a planned
    scene picture has them. The people are the scene's player character and the cast saved with
    the scene, drawn with the look they have now. What the player character has on them goes
    along only for the story's latest scene, since the record holds what they have now, not what
    they had then (C10)."""
    description = scene.image_prompt or _ending(scene.narration)
    look = look_for_story(story)
    try:
        state = WorldState.model_validate(story.state)
    except ValueError:
        return Brief(description=description, look=look)
    player = player_at(state, scene.turn)
    present = [
        str(entry.get("character_id") or "")
        for entry in scene.cast or ()
        if isinstance(entry, dict)
    ]
    return Brief(
        description=description,
        look=look,
        figures=scene_figures(
            state,
            description,
            player_id=player,
            present=present,
            # What the record holds now is what the latest scene ended with, unless its player
            # character fell in it and someone else carries the story on (N6).
            carried=scene.turn >= state.turn and player == state.player_id,
        ),
        you=state.characters[player].name,
        time=time_of_day(state.bible.calendar, scene.world_end_s),
    )


def _ending(text: str, limit: int = 1000) -> str:
    """The end of a long narration, where the scene's moment is, from a sentence start."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    tail = text[-limit:]
    ends = [i for i in (tail.find(". "), tail.find("! "), tail.find("? ")) if i >= 0]
    cut = min(ends, default=-1)
    return tail[cut + 2 :] if 0 <= cut < limit // 2 else tail
