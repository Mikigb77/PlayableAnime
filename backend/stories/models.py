"""Stories, their scenes, and off-screen events waiting on in-world time.

Only a turn writes a story row (B12): it saves the new world state, the scene and any pending
events in one transaction, and bumps `version` so a concurrent turn can't overwrite it (T10).
The one thing a turn writes before that is itself, before its decided steps are shown
(`unfinished_turn`, A3).
"""

import uuid

from django.conf import settings as django_settings
from django.db import models


class Rating(models.TextChoices):
    """The content rating chosen at creation (F2, F8)."""

    TEEN = "teen", "Teen"
    MATURE = "mature", "Mature 17+"


class Engine(models.TextChoices):
    """Which engine wrote `Story.state`, so a newer engine never misreads an older story."""

    # Stories from before the turn graph. The one-call narrator that wrote them is gone, so no
    # endpoint serves them; they stay in the database until their owner's account is deleted.
    LEGACY = "legacy", "Legacy one-call narrator"
    GRAPH = "graph", "Turn graph"


class Story(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Stories belong to a user and the Library shows only your own (S8). Deleting the account
    # deletes its stories (T12).
    owner = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stories"
    )
    title = models.CharField(max_length=200)
    premise = models.TextField()
    genre = models.CharField(max_length=80, blank=True)
    rating = models.CharField(max_length=16, choices=Rating.choices, default=Rating.TEEN)
    # StorySettings from docs/API.md: narration length, tone, difficulty, event frequency,
    # pictures and suggestions (S6), and the color the player chose (S13).
    settings = models.JSONField(default=dict, blank=True)
    engine = models.CharField(max_length=16, choices=Engine.choices, default=Engine.GRAPH)
    # The whole world state as one document (C2), written only by a turn (B12).
    state = models.JSONField(default=dict, blank=True)
    # Turns saved so far: the number of the latest scene.
    turn = models.PositiveIntegerField(default=0)
    # Bumped by every saved turn. A turn saves only if the version it read is still current,
    # so of two concurrent turns the loser gets a 409 (T10).
    version = models.PositiveIntegerField(default=0)
    # N6: how the player character's story ended, once it has, as API.md's `Ending`. Null while
    # it plays on. A story at an ending takes no more turns.
    ending = models.JSONField(null=True, blank=True)
    # N6: the person drawn to carry the story on after its ending, until the player starts as
    # them or draws someone else: `stories.succession.Drawn`.
    successor = models.JSONField(null=True, blank=True)
    # A3: a turn whose steps were decided and shown but whose scene isn't saved yet. Whatever
    # turn is sent next plays this one out, so a throw can't be looked at and then taken back
    # (`stories.unfinished`). Null once the scene is saved, which is nearly always.
    unfinished_turn = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "stories"
        indexes = [
            # The Library lists your most recently played stories first.
            models.Index(fields=["owner", "-updated_at"], name="story_owner_updated_idx"),
        ]

    def __str__(self) -> str:
        return self.title


class SceneKind(models.TextChoices):
    OPENING = "opening", "Opening"
    ACTION = "action", "Action"
    CHOICE = "choice", "Choice"
    STANDING = "standing", "Standing action"
    END = "end", "Ending"


class InputMode(models.TextChoices):
    """How the player entered the action (V7)."""

    TYPED = "typed", "Typed"
    VOICE = "voice", "Voice"
    VOICE_EDITED = "voice_edited", "Voice, then edited"
    CHOICE = "choice", "Choice"


class ImageStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    READY = "ready", "Ready"
    SKIPPED = "skipped", "Skipped"


class ImageKind(models.TextChoices):
    PORTRAIT = "portrait", "Portrait"
    PLACE = "place", "Place"
    SCENE = "scene", "Scene"
    COVER = "cover", "Cover"


class SceneQuerySet(models.QuerySet):
    def live(self) -> "SceneQuerySet":
        """The scenes of the story as it stands, without those a rewind took back (C8)."""
        return self.filter(rewound_at__isnull=True)


class Scene(models.Model):
    """One turn of a story, as the player reads it (the Scene in docs/API.md).

    A rewind (C8) takes the scenes after the moment it goes back to out of the story, but keeps
    their rows, marked `rewound_at`, so a report on one still reaches staff (F6, T16). The story's
    own scenes are `Scene.objects.live()`: one per turn.
    """

    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="scenes")
    turn = models.PositiveIntegerField()
    kind = models.CharField(max_length=16, choices=SceneKind.choices)
    player_action = models.TextField(null=True, blank=True)
    input_mode = models.CharField(max_length=16, choices=InputMode.choices, null=True, blank=True)
    narration = models.TextField()
    # [{id, label, kind}], 0 to 4 suggestions (S2).
    choices = models.JSONField(default=list, blank=True)
    # SceneDetails: the steps with their class, reason and roll, a cause-and-effect chain, and
    # where a chained plan stopped (A2, A8, A9, R6).
    details = models.JSONField(default=dict, blank=True)
    # A W16 event that arrived in this scene: {size, title}.
    event = models.JSONField(null=True, blank=True)
    # In-world time in seconds since the story's epoch (W10), and the player character's own
    # elapsed time where it differs, such as during a time stop (W10a).
    world_start_s = models.BigIntegerField(default=0)
    world_end_s = models.BigIntegerField(default=0)
    personal_elapsed_s = models.BigIntegerField(null=True, blank=True)
    # Labels in the world's own calendar, written when the scene is saved, so the app never
    # formats in-world dates itself.
    time_label = models.CharField(max_length=120, blank=True)
    duration_label = models.CharField(max_length=60, blank=True)
    personal_label = models.CharField(max_length=120, blank=True)
    # W10: the heading over a scene that hours or days passed in, such as "Three days later".
    # Empty for a short scene, and for scenes saved before the story marked the passing of time.
    passage_label = models.CharField(max_length=60, blank=True, default="", db_default="")
    timeline_id = models.CharField(max_length=64, default="main")
    # The other characters the player knew who were there when the scene ended, as
    # [{character_id, name}], for the scene's portraits (M4, M5).
    cast = models.JSONField(default=list, blank=True)
    # The picture for this scene (M1 to M3): whether code planned one, and what became of it.
    image_planned = models.BooleanField(default=False)
    image_kind = models.CharField(max_length=16, choices=ImageKind.choices, null=True, blank=True)
    image_status = models.CharField(
        max_length=16, choices=ImageStatus.choices, null=True, blank=True
    )
    image_prompt = models.TextField(null=True, blank=True)
    image_url = models.URLField(max_length=2048, null=True, blank=True)
    # C8: when a rewind took this scene back. The story no longer has it, and a scene played
    # anew takes its turn.
    rewound_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SceneQuerySet.as_manager()

    class Meta:
        ordering = ["story", "turn"]
        constraints = [
            models.UniqueConstraint(
                fields=["story", "turn"],
                condition=models.Q(rewound_at__isnull=True),
                name="scene_story_turn_live_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.story_id} turn {self.turn}"


class TurnSnapshot(models.Model):
    """C8: the world state a saved turn left, so a rewind can put the story back to it.

    Saved with the turn, in its transaction, as the same document as `Story.state`. A story keeps
    only the few a rewind can reach (`stories.rewind`), and none from before someone new carried
    it on (N6).
    """

    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="snapshots")
    turn = models.PositiveIntegerField()
    state = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["story", "turn"]
        constraints = [
            models.UniqueConstraint(fields=["story", "turn"], name="snapshot_story_turn_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.story_id} after turn {self.turn}"


class PendingEventStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPLIED = "applied", "Applied"
    CANCELLED = "cancelled", "Cancelled"


class PendingEvent(models.Model):
    """Something off-screen that falls due at an in-world time (B12, W10).

    Off-screen results land here instead of on the story row, and the next turn applies the ones
    that have fallen due, in time order, so nothing races a turn's version check.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="pending_events")
    timeline_id = models.CharField(max_length=64, default="main")
    # In-world seconds since the story's epoch.
    due_world_s = models.BigIntegerField()
    kind = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=PendingEventStatus.choices, default=PendingEventStatus.PENDING
    )
    # The turn that scheduled it, and the turn that applied it.
    created_turn = models.PositiveIntegerField(default=0)
    applied_turn = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["story", "due_world_s", "created_at"]
        indexes = [
            # Step 1 of a turn: this story's pending events on this timeline, due by now.
            models.Index(
                fields=["story", "timeline_id", "due_world_s"],
                condition=models.Q(status="pending"),
                name="pending_event_due_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} at {self.due_world_s}s ({self.status})"
