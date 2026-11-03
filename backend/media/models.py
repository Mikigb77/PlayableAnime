"""The pictures of a story (M1 to M8).

An `Image` is one drawing of one subject: a character's portrait, a place, a scene or the
Library cover. It is drawn once and reused wherever its subject appears (M4): every scene that
shows the same character's portrait links to the same row. When a character changes for good,
the portrait is redrawn once as the next `version` of the same subject (M5).

A `ScenePicture` says which picture a scene shows, and whether code planned it (M1) or the player
asked for it with Illustrate (M2). The file itself lives in storage under `storage_key`.
"""

import uuid

from django.db import models

from stories.models import ImageKind, Scene, Story


class ImageStatus(models.TextChoices):
    # Code planned it, or the player asked for it, and nobody has started drawing it yet.
    PLANNED = "planned", "Planned"
    # A request is drawing it right now (see `Image.claim`).
    PENDING = "pending", "Drawing"
    READY = "ready", "Ready"
    # Never shown as an error: the scene is complete without it (M3).
    SKIPPED = "skipped", "Skipped"


class SkipReason(models.TextChoices):
    FAILED = "failed", "The model failed"
    BLOCKED = "blocked", "Blocked by a safety filter"
    NO_CREDITS = "no_credits", "Not enough credits"


class Payer(models.TextChoices):
    """Who paid for a picture (M7, K7)."""

    CREDITS = "credits", "The player's credits"
    OWNER = "owner", "The owner account, at no charge"
    BYOK = "byok", "The player's own API key"
    # No ledger to charge: a story from before sign-in, or before billing landed.
    FREE = "free", "Not charged"


class Image(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="images")
    kind = models.CharField(max_length=16, choices=ImageKind.choices)
    # What is drawn: a character id for a portrait, a place id for a place, `turn-12` for a
    # scene and `cover` for the cover. The same subject is drawn once and reused (M4).
    subject = models.CharField(max_length=128)
    # A portrait is redrawn once when its character changes for good (M5), as version 2, 3...
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=16, choices=ImageStatus.choices, default=ImageStatus.PLANNED
    )
    skip_reason = models.CharField(max_length=16, choices=SkipReason.choices, blank=True)
    # The M1 trigger that first planned it, such as `fight_start`, or `illustrate` (M2).
    trigger = models.CharField(max_length=32, blank=True)
    # What to draw (`media.prompts.Brief`): the description, the world's look and the people in
    # it with their appearance. Mild in every rating (M6); the prompt sent to the model is
    # built from it each time and never logged (T6).
    brief = models.JSONField(default=dict, blank=True)

    # Filled once it is drawn (M7, T5).
    model = models.CharField(max_length=80, blank=True)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    # Charged once, by the request that finished it, in the transaction that made it ready (M3).
    payer = models.CharField(max_length=16, choices=Payer.choices, blank=True)
    storage_key = models.CharField(max_length=512, blank=True)
    mime_type = models.CharField(max_length=40, blank=True)
    size_bytes = models.PositiveIntegerField(null=True, blank=True)

    # The request drawing it holds `claim` until it finishes. A claim older than the lease (a
    # request that died) can be taken over, at most `MAX_ATTEMPTS` times (`media.service`).
    attempts = models.PositiveSmallIntegerField(default=0)
    claim = models.UUIDField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["story", "kind", "subject", "version"], name="image_subject_version_unique"
            ),
        ]
        indexes = [
            # The latest version of a subject: a character's current portrait (M4, M5).
            models.Index(fields=["story", "kind", "subject", "-version"], name="image_latest_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.subject} v{self.version} ({self.status})"


class ScenePicture(models.Model):
    """The picture a scene shows. Many scenes can show one portrait or place (M4)."""

    scene = models.OneToOneField(Scene, on_delete=models.CASCADE, related_name="picture")
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name="scene_links")
    # True when code planned it (M1), false when the player asked for it with Illustrate (M2).
    planned = models.BooleanField(default=True)
    trigger = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.scene} shows {self.image}"
