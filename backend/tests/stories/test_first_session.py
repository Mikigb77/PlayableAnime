"""K1 with a new player's first pictures on the house (M7): a new verified account's first story
on the $0.50 starter credit, played as the app plays it. Each turn goes through the turn
endpoint, and each scene's planned picture is asked for in its own request afterwards (M3).

The model is scripted with the evals' answer sizes (`evals.scripted`: about 2,700 tokens in and
900 out for the narrator, priced as Gemini 3.5 Flash), so a turn costs about what a real one
would, about 2.1 cents with the margin. Pictures are drawn by the offline model at the picture
model's price, about 5 cents each. T5's first live numbers will move both."""

import uuid
from decimal import Decimal

import pytest
from django.test import Client

from accounts.models import User
from billing.models import CreditAccount, EntryKind, LedgerEntry
from engine.base import HOUR
from engine.contracts import FIRST_PICTURES, ActionKind
from evals.scenarios.common import act
from evals.scripted import Line, ScriptedModel
from media.models import Image, ImageStatus, Payer
from tests.conftest import ADULT_BIRTH_DATE, auth_headers
from tests.stories.conftest import opening, play

pytestmark = pytest.mark.django_db

ACTION = "I practise my sword forms by the well"
INTENT = act("practise sword forms", "practise", ActionKind.TASK, HOUR)
# Rolls are seeded by the story's id (A3), and which scenes get a key-scene picture follows the
# rolls, so a fixed id makes every run play the same story and spend the same.
STORY_ID = uuid.UUID("00000000-0000-4000-8000-00000000f157")


def first_session(make_story, model) -> tuple[int, User]:
    """Plays a new Google account's first story until the starter credit runs out. Returns how
    many turns it played and the player."""
    player = User.objects.create_user(
        "new.player@example.com",
        google_sub="google-new-player",
        email_verified=True,
        birth_date=ADULT_BIRTH_DATE,
        display_name="New Player",
    )
    story = make_story(player, id=STORY_ID)
    scripted = ScriptedModel()
    model.backend = scripted.backend
    pictures = Client(headers=auth_headers(player))
    played = play(player, story, opening(story))
    turns = 0
    while played.status == 200 and turns < 80:
        assert played.names[-1] == "scene.completed", played.events
        turns += 1
        scene = played.completed["scene"]
        if scene["image"] is not None:
            asked = pictures.post(f"/v1/stories/{story.id}/scenes/{scene['turn']}/image")
            assert asked.status_code == 200, asked.content
        story.refresh_from_db()
        scripted.line = Line.of(story.turn + 1, ACTION, INTENT, None)
        played = play(
            player, story, {"kind": "action", "action": ACTION, "expected_version": story.version}
        )
    assert played.status == 402, played.body
    assert played.body["error"]["code"] == "out_of_credits"
    return turns, player


@pytest.fixture
def verified_only(settings):
    """K1's default: only a verified account gets the starter credit and the first pictures.
    The per-minute limit (T9) is lifted, since the test plays faster than anyone types."""
    settings.BILLING = {
        **settings.BILLING,
        "STARTER_POLICY": "verified",
        "PER_MINUTE": {"turn": 1000, "draft": 1000, "image": 1000},
    }


def test_a_new_players_first_story_draws_its_first_pictures_on_the_house(
    verified_only, make_story, model
):
    turns, player = first_session(make_story, model)

    images = Image.objects.filter(story__owner=player)
    first = images.filter(trigger__in=FIRST_PICTURES)
    # The player's portrait, the cover, the first key NPC met and the first place visited.
    assert set(first.values_list("trigger", flat=True)) == set(FIRST_PICTURES)
    assert {(i.status, i.payer) for i in first} == {(ImageStatus.READY, Payer.HOUSE)}
    # Key scenes are the player's, while the credit lasts.
    key_scenes = images.exclude(trigger__in=FIRST_PICTURES).filter(status=ImageStatus.READY)
    assert key_scenes.exists()
    assert {i.payer for i in key_scenes} == {Payer.CREDITS}

    account = CreditAccount.objects.get(user=player)
    entries = LedgerEntry.objects.filter(user=player)
    house = entries.filter(house=True)
    assert house.count() == first.count()
    assert all(e.amount_cents == 0 for e in house)
    assert account.house_pictures_cents == sum(
        (Decimal(e.detail["list_cents"]) for e in house), Decimal(0)
    )
    assert account.house_pictures_cents <= 30 + 6  # at most one picture past the allowance
    # Everything the player paid for came out of the $0.50.
    spent = -sum((e.amount_cents for e in entries.exclude(kind=EntryKind.STARTER)), Decimal(0))
    assert spent + account.balance_cents == 50
    assert account.balance_cents < 5  # less than a turn's hold is left
    # About 4.1 cents a turn and a key scene: the $0.50 lasts about 10 turns. Both models'
    # system text, with the narrator's guide to the brief (T5) and every rule the two read by
    # (the last ones W2's crowd, V3's unnamed "him" and W17's romance), bills in full here: the
    # scripted model has no prompt cache, and this small world's start is under Vertex AI's
    # minimum for one anyway. A drafted world's start passes it, and from its second turn the
    # system text bills at a tenth.
    assert 10 <= turns <= 22, turns


def test_without_the_house_the_first_pictures_eat_the_starter_credit(
    verified_only, make_story, model, settings
):
    """What the house allowance buys: the same first story with the allowance off loses about
    as many turns as the first pictures cost."""
    settings.BILLING = {**settings.BILLING, "HOUSE_PICTURES_CENTS": Decimal(0)}

    turns, player = first_session(make_story, model)

    assert not LedgerEntry.objects.filter(user=player, house=True).exists()
    assert turns <= 11, turns
