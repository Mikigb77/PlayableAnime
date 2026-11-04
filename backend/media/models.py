"""The pictures of a story (M1 to M8).

An `Image` is one drawing of one subject: a character's portrait, a place, a scene or the
Library cover. It is drawn once and reused wherever its subject appears (M4): every scene that
shows the same character's portrait links to the same row. A portrait or place is keyed by its
look version too (`engine.looks`): when a character or a place changes for good, it is drawn once
more as that `version` of the same subject, and the latest one ready is shown from then on (M1,
M5). Earlier versions stay, for the scenes that showed them and the export (T12).

A `ScenePicture` says which picture a scene shows, and whether code planned it (M1) or the player
asked for it with Illustrate (M2). The file itself lives in storage under `storage_key`.

A `PremiseCover` is a starter premise's cover on Discover (S1): drawn once by the house with
`manage.py draw_premise_covers` and shown to every player, so it belongs to no story.
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
    # A portrait or place's look version (`engine.looks`): drawn once more when its character or
    # place changes for good (M1, M5). Always 1 for a scene or the cover.
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

    @property
    def scene_status(self) -> str:
        """The state a scene shows (`SceneImage.status` in docs/API.md): planned until drawn."""
        if self.status in (ImageStatus.READY, ImageStatus.SKIPPED):
            return self.status
        return ImageStatus.PLANNED

    def sync_scenes(self) -> None:
        """Keeps `Scene.image_status` of every scene showing this picture in step with it, for
        the stories admin and anything reading the scene row. Signed URLs are never stored."""
        Scene.objects.filter(picture__image=self).update(image_status=self.scene_status)


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


class PremiseCover(models.Model):
    """A starter premise's cover (S1, M4), keyed by the premise's id in `graph.drafting.catalog`.

    The house draws it once (`media.premise_covers`) and pays for it: its cost is logged (T5),
    and no player's ledger is charged. Drawn again only when asked (`--force`), or when the one
    kept is the offline model's placeholder and a real model is configured.
    """

    premise_id = models.CharField(max_length=64, primary_key=True)
    storage_key = models.CharField(max_length=512)
    mime_type = models.CharField(max_length=40)
    size_bytes = models.PositiveIntegerField()
    model = models.CharField(max_length=80, blank=True)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    # Drawn by the offline model (`LLM_PROVIDER=fake`): a placeholder for development.
    offline = models.BooleanField(default=False)
    # What was drawn (`media.prompts.Brief`), from the premise's public text. A premise whose text
    # has changed since is reported by the command, and redrawn with `--force`.
    brief = models.JSONField(default=dict, blank=True)
    drawn_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"cover of {self.premise_id}"
