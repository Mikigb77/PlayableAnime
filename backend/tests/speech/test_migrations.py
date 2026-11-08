"""The speech app's data migrations (V9, V10).

Each test builds rows with the models as they were before its migration, since the current ones
may have fields the database doesn't have yet."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from engine.context import StorySettings
from media.storage import get_storage
from speech.models import AudioStatus, SceneAudio
from stories.models import Scene, SceneKind, Story


def migrate_to(target):
    """Migrates the speech app to `target`, and gives the models as they are there."""
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor.loader.project_state(target).apps


def migrate_to_latest() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


def kept_file(story, name: str, files) -> str:
    key = f"stories/{story.id}/voice/{name}.mp3"
    get_storage().save(key, b"ID3", "audio/mpeg")
    assert (files / key).exists()
    return key


@pytest.mark.django_db(transaction=True)
def test_parts_read_with_directions_are_forgotten_with_their_files(player, settings, tmp_path):
    """Parts read before 2026-11-07 may have the directions spoken in them: they go, files and
    all, so the next listen reads them again with the scene's words alone."""
    settings.PICTURE_ROOT = tmp_path / "files"
    apps = migrate_to([("speech", "0001_initial")])
    OldAudio = apps.get_model("speech", "SceneAudio")
    story = Story.objects.create(owner=player, title="T", premise="P")
    scene = Scene.objects.create(story=story, turn=1, kind=SceneKind.OPENING, narration="N")
    key = kept_file(story, "old", tmp_path / "files")
    OldAudio.objects.create(
        scene_id=scene.pk, voice="Sulafat", part=0, status=AudioStatus.READY, storage_key=key
    )
    OldAudio.objects.create(scene_id=scene.pk, voice="Sulafat", part=1, status=AudioStatus.BLOCKED)
    try:
        migrate_to_latest()

        assert not SceneAudio.objects.exists()
        assert not (tmp_path / "files" / key).exists()
        assert Scene.objects.filter(pk=scene.pk).exists()
    finally:
        story.delete()


@pytest.mark.django_db(transaction=True)
def test_spanish_and_catalan_parts_are_read_again_in_their_own_accent(player, settings, tmp_path):
    """Parts kept before 2026-11-08 were read in whatever language and accent the voice model
    guessed: Spanish and Catalan stories' parts go, files and all, so the next listen reads them
    in Spain's Spanish or in Catalan. English stories' parts were read in English, and stay."""
    files = tmp_path / "files"
    settings.PICTURE_ROOT = files
    apps = migrate_to([("speech", "0002_forget_parts_read_with_directions")])
    OldAudio = apps.get_model("speech", "SceneAudio")
    stories = {
        language: Story.objects.create(
            owner=player,
            title=language or "older",
            premise="P",
            settings=StorySettings(language=language).model_dump(mode="json") if language else {},
        )
        for language in ("en", "es", "ca", "")
    }
    keys = {}
    for language, story in stories.items():
        scene = Scene.objects.create(story=story, turn=1, kind=SceneKind.OPENING, narration="N")
        keys[language] = kept_file(story, "old", files)
        OldAudio.objects.create(
            scene_id=scene.pk,
            voice="Sulafat",
            part=0,
            status=AudioStatus.READY,
            storage_key=keys[language],
        )
        OldAudio.objects.create(
            scene_id=scene.pk, voice="Sulafat", part=1, status=AudioStatus.BLOCKED
        )
    try:
        migrate_to_latest()

        kept = SceneAudio.objects.order_by("scene__story__title", "part")
        assert [(a.scene.story.title, a.part, a.language) for a in kept] == [
            ("en", 0, "en-US"),
            ("en", 1, "en-US"),
            ("older", 0, "en-US"),  # a story from before languages is English (S10)
            ("older", 1, "en-US"),
        ]
        for language in ("en", ""):
            assert (files / keys[language]).exists()
        for language in ("es", "ca"):
            assert not (files / keys[language]).exists()
        assert Scene.objects.filter(story__in=stories.values()).count() == 4
    finally:
        for story in stories.values():
            story.delete()
