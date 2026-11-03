"""A drafted world and character, kept until the player starts the story (G1, G2).

A draft stores inputs, never the world state: the model's latest proposal (`graph.drafting.schema
.DraftProposal`) and what the player set up. The state is assembled from them in code whenever it
is needed (`graph.drafting.chain.Draft.state`), and copied into the story when it starts. The
proposal holds hidden truth (mystery answers, secrets, agendas), so it never leaves the server.
"""

import uuid
from enum import StrEnum

from django.conf import settings as django_settings
from django.db import models

from engine.context import Difficulty, EventFrequency
from engine.state import GiftStrength, PhysicsMode
from stories.models import Rating, Story


def _choices(values: type[StrEnum]) -> list[tuple[str, str]]:
    """Column choices from the engine's own enums, so the two can't drift apart."""
    return [(v.value, v.value.replace("_", " ").capitalize()) for v in values]


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
    # A9: fun first by default, or strict for players who want things rougher.
    physics = models.CharField(
        max_length=16, choices=_choices(PhysicsMode), default=PhysicsMode.FUN_FIRST.value
    )
    # The gift strength the player picked (G22); null keeps the premise's own.
    gift_strength = models.CharField(
        max_length=16, choices=_choices(GiftStrength), null=True, blank=True
    )
    # The starter template's rules the player let go of while setting up the story (G7).
    released_rules = models.JSONField(default=list, blank=True)
    # Story settings chosen while drafting, copied into the story on start (S6).
    difficulty = models.CharField(
        max_length=16, choices=_choices(Difficulty), default=Difficulty.BALANCED.value
    )
    event_frequency = models.CharField(
        max_length=16, choices=_choices(EventFrequency), default=EventFrequency.NORMAL.value
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
