"""A scene read aloud in the studio voice (V9, V10).

The app reads a scene in parts (`speech.reading`). Each part is read once per voice, in the story's
language and accent, and kept as a `SceneAudio`, so hearing a scene again costs nothing. The file
lives in the same private bucket as pictures, under the story, and leaves with the scene's story
or account (T12): deleting a row deletes its file once the transaction commits
(`speech.signals`).
"""

import uuid

from django.db import models

from stories.models import Scene


class AudioStatus(models.TextChoices):
    # A request is reading it right now. One that died leaves it here: after `STALE_AFTER_S` the
    # next request reads it again.
    PENDING = "pending", "Reading"
    READY = "ready", "Ready"
    # The voice model refused the text. Never tried again, never charged: the app reads the part
    # in the phone's own voice instead (V10).
    BLOCKED = "blocked", "Blocked by the voice model"


class SceneAudio(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scene = models.ForeignKey(Scene, on_delete=models.CASCADE, related_name="audio")
    # One of `speech.voices.VOICES`, such as `Sulafat`.
    voice = models.CharField(max_length=32)
    # The language and accent it was read in, such as `es-ES` (`speech.voices.READING_LOCALES`).
    # A story keeps its language (S10), so this changes only when the accent a language is read
    # in does, and then each part is read again in the new one. Empty in a row an older server
    # wrote while a deploy that added the field was rolling out: never served again.
    language = models.CharField(max_length=16, default="", db_default="")
    # Which part of the scene's spoken text, from 0 (`speech.reading.reading_parts`).
    part = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=AudioStatus.choices)
    storage_key = models.CharField(max_length=512, blank=True)
    mime_type = models.CharField(max_length=64, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    # How long the part's text was, to tell a narration that changed (it never does today).
    chars = models.PositiveIntegerField(default=0)
    # The request reading it while `pending`: a request that lost its claim to a later one
    # (`STALE_AFTER_S`) never deletes that one's row.
    claim = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scene", "voice", "language", "part"],
                name="scene_audio_voice_language_part_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.scene_id} {self.voice} {self.language} part {self.part}: {self.status}"
