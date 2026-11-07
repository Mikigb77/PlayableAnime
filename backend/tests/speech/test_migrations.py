"""The speech app's data migrations (V9, V10)."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from media.storage import get_storage
from speech.models import AudioStatus, SceneAudio
from stories.models import Scene, SceneKind, Story

BEFORE = [("speech", "0001_initial")]


@pytest.mark.django_db(transaction=True)
def test_parts_read_with_directions_are_forgotten_with_their_files(player, settings, tmp_path):
    """Parts read before 2026-11-07 may have the directions spoken in them: they go, files and
    all, so the next listen reads them again with the scene's words alone."""
    settings.PICTURE_ROOT = tmp_path / "files"
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    story = Story.objects.create(owner=player, title="T", premise="P")
    scene = Scene.objects.create(story=story, turn=1, kind=SceneKind.OPENING, narration="N")
    key = f"stories/{story.id}/voice/old.mp3"
    get_storage().save(key, b"ID3", "audio/mpeg")
    assert (tmp_path / "files" / key).exists()
    SceneAudio.objects.create(
        scene=scene, voice="Sulafat", part=0, status=AudioStatus.READY, storage_key=key
    )
    SceneAudio.objects.create(scene=scene, voice="Sulafat", part=1, status=AudioStatus.BLOCKED)
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

        assert not SceneAudio.objects.exists()
        assert not (tmp_path / "files" / key).exists()
        assert Scene.objects.filter(pk=scene.pk).exists()
    finally:
        story.delete()
