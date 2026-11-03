"""What the story endpoints answer, built from the rows, the world state and the pictures.

These read the database and sign picture URLs (`media.lookups`), so call them off the event loop
(`sync_to_async`). Pass the request so local development's picture URLs come back absolute.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from django.db.models.fields.json import KeyTransform
from django.http import HttpRequest

from engine.labels import clock_label
from engine.state.bible import Calendar
from engine.state.world import WorldState
from engine.visibility import MemoryView, StatusView, clock_view, memory_view, status_view
from media.lookups import cover_urls, place_urls, portrait_urls, scene_images
from stories.models import Scene, Story
from stories.schemas import (
    ChoiceOut,
    PortraitOut,
    SceneImageOut,
    SceneOut,
    SceneTimeOut,
    StoryOut,
    StorySettings,
    StorySummaryOut,
)

LIBRARY_SIZE = 50


def scenes_out(
    story: Story, scenes: Sequence[Scene], *, request: HttpRequest | None = None
) -> list[SceneOut]:
    """API.md's `Scene` for each of `scenes`, with its picture and the portraits of the known
    characters in it (M3, M4, M5)."""
    if not scenes:
        return []
    images = scene_images(scenes, request=request)
    ids = {entry.get("character_id") for scene in scenes for entry in _cast(scene)}
    portraits = portrait_urls(story, sorted(filter(None, ids)), request=request) if ids else {}
    return [_scene_out(scene, images.get(scene.turn), portraits) for scene in scenes]


def _scene_out(scene: Scene, image: dict | None, portraits: dict) -> SceneOut:
    return SceneOut(
        turn=scene.turn,
        kind=scene.kind,
        player_action=scene.player_action,
        input_mode=scene.input_mode,
        narration=scene.narration,
        choices=[ChoiceOut.model_validate(choice) for choice in scene.choices or []],
        time=SceneTimeOut(
            world_start_s=scene.world_start_s,
            world_end_s=scene.world_end_s,
            label=scene.time_label,
            duration_label=scene.duration_label,
            personal_label=scene.personal_label or None,
        ),
        details=scene.details or {},
        event=scene.event,
        image=SceneImageOut.model_validate(image) if image else None,
        portraits=[
            PortraitOut(
                character_id=entry["character_id"],
                name=entry.get("name") or entry["character_id"],
                url=portraits[entry["character_id"]].url
                if entry["character_id"] in portraits
                else None,
            )
            for entry in _cast(scene)
            if entry.get("character_id")
        ],
        created_at=scene.created_at,
    )


def _cast(scene: Scene) -> list[dict]:
    return [entry for entry in scene.cast or [] if isinstance(entry, dict)]


def story_out(
    story: Story, state: WorldState, scenes: Sequence[Scene], *, request: HttpRequest | None
) -> StoryOut:
    cover = cover_urls([story.pk], request=request).get(str(story.pk))
    return StoryOut(
        id=str(story.pk),
        title=story.title,
        genre=story.genre,
        rating=story.rating,
        version=story.version,
        turn=story.turn,
        settings=settings_of(story),
        clock=clock_view(state),
        scenes=scenes_out(story, scenes, request=request),
        cover_url=cover.url if cover else None,
    )


def settings_of(story: Story) -> StorySettings:
    """The story's settings with every field filled (S6)."""
    return StorySettings.model_validate(story.settings if isinstance(story.settings, dict) else {})


def library(stories: Iterable[Story], *, request: HttpRequest | None) -> list[StorySummaryOut]:
    """The Library, from stories annotated by `with_clock` (no world state loaded)."""
    stories = list(stories)
    covers = cover_urls([story.pk for story in stories], request=request)
    summaries = []
    for story in stories:
        calendar = Calendar.model_validate(story.calendar or {})
        cover = covers.get(str(story.pk))
        summaries.append(
            StorySummaryOut(
                id=str(story.pk),
                title=story.title,
                genre=story.genre,
                rating=story.rating,
                turn=story.turn,
                world_time_label=clock_label(calendar, int(story.world_s or 0)),
                cover_url=cover.url if cover else None,
                updated_at=story.updated_at,
            )
        )
    return summaries


def with_clock(stories):
    """Stories with their calendar and world clock read from the state in the database, so the
    Library doesn't load whole world states."""
    return stories.defer("state").annotate(
        calendar=KeyTransform("calendar", KeyTransform("bible", "state")),
        world_s=KeyTransform("world_s", "state"),
    )


def memory_out(story: Story, state: WorldState, *, request: HttpRequest | None) -> MemoryView:
    """The Memory screen (C6) with the pictures the player has seen (M4)."""
    view = memory_view(state)
    portraits = portrait_urls(
        story, [state.player_id, *(person.id for person in view.people)], request=request
    )
    places = place_urls(story, [place.id for place in view.places], request=request)
    if state.player_id in portraits:
        view.character.portrait_url = portraits[state.player_id].url
    for person in view.people:
        if person.id in portraits:
            person.portrait_url = portraits[person.id].url
    for place in view.places:
        if place.id in places:
            place.image_url = places[place.id].url
    return view


def status_out(state: WorldState) -> StatusView:
    return status_view(state)
