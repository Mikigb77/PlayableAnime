"""A drafted world and character, kept until the player starts the story (G1, G2).

A draft stores inputs, never the world state: the model's latest proposal (`graph.drafting.schema
.DraftProposal`) and what the player set up. The state is assembled from them in code whenever it
is needed (`graph.drafting.chain.Draft.state`), and copied into the story when it starts. The
proposal holds hidden truth (mystery answers, secrets, agendas), so it never leaves the server.
"""

import uuid

from django.conf import settings as django_settings
from django.db import models

from stories.models import Rating, Story


class Physics(models.TextChoices):
    """A9: fun first by default, or strict for players who want things rougher."""

    FUN_FIRST = "fun_first", "Fun first"
    STRICT = "strict", "Strict"


class GiftStrength(models.TextChoices):
    """G22."""

    NONE = "none", "None"
    SMALL = "small", "Small"
    RARE = "rare", "Rare"
    OVERPOWERED = "overpowered", "Overpowered"


class Difficulty(models.TextChoices):
    """A5."""

    STORY = "story", "Story"
    BALANCED = "balanced", "Balanced"
    BRUTAL = "brutal", "Brutal"


class EventFrequency(models.TextChoices):
    """W16."""

    CALM = "calm", "Calm"
    NORMAL = "normal", "Normal"
    DRAMATIC = "dramatic", "Dramatic"


class Draft(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Drafts belong to a player and are deleted with the account (S8, T12).
    owner = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="drafts"
    )
    premise = models.TextField()
    # The starter premise it came from (S1), whose genre's fixed rules the draft keeps (G7).
    premise_id = models.CharField(max_length=64, blank=True)
    rating = models.CharField(max_length=16, choices=Rating.choices)
    # The model's latest proposal: graph.drafting.schema.DraftProposal as JSON.
    proposal = models.JSONField()
    physics = models.CharField(max_length=16, choices=Physics.choices, default=Physics.FUN_FIRST)
    # The gift strength the player picked (G22); null keeps the premise's own.
    gift_strength = models.CharField(
        max_length=16, choices=GiftStrength.choices, null=True, blank=True
    )
    # The starter template's rules the player let go of while setting up the story (G7).
    released_rules = models.JSONField(default=list, blank=True)
    # Story settings chosen while drafting, copied into the story on start (S6).
    difficulty = models.CharField(
        max_length=16, choices=Difficulty.choices, default=Difficulty.BALANCED
    )
    event_frequency = models.CharField(
        max_length=16, choices=EventFrequency.choices, default=EventFrequency.NORMAL
    )
    # Set when the player starts the story; a started draft can't change. Deleting the story
    # deletes its draft, which holds the story's hidden truth.
    story = models.OneToOneField(
        Story, on_delete=models.CASCADE, null=True, blank=True, related_name="draft"
    )
    # Bumped by every saved change, so two edits at once can't overwrite each other (T10).
    version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "-updated_at"], name="draft_owner_updated_idx")]

    def __str__(self) -> str:
        return f"Draft {self.id}"
