"""A new player's first pictures are on the house (K1, M7), through the picture endpoints and the
real credit meter: in an account's first story, the player character's portrait, the cover, a
key NPC's first-meeting portrait and a place's first visit draw at no charge until the house
allowance is spent. Key scenes, fights, redraws (M5) and Illustrate stay the player's."""

from decimal import Decimal

import pytest
from django.test import Client

from accounts.models import Role
from billing import credits
from billing.models import CreditAccount, EntryKind, LedgerEntry
from media.drawing import KeyCannotDraw
from media.models import Image, ImageStatus, Payer, SkipReason
from media.plans import plan_picture
from media.prompts import Brief
from tests.conftest import auth_headers
from tests.media.conftest import make_scene, make_story, story_owner

pytestmark = pytest.mark.django_db

FIRST = [
    (1, "portrait", "story_start", "lin"),
    (2, "cover", "cover", None),
    (3, "portrait", "first_meeting", "zhao"),
    (4, "place", "first_visit", "well"),
]


@pytest.fixture
def client() -> Client:
    return Client(headers=auth_headers(story_owner()))


def _plan(story, turn: int, kind: str, trigger: str, subject: str | None = None, **fields):
    scene = make_scene(story, turn)
    plan_picture(
        scene, kind=kind, trigger=trigger, subject_id=subject, brief=Brief("A picture."), **fields
    )
    return scene


def _image(client: Client, story, turn: int, **headers) -> dict:
    response = client.post(f"/v1/stories/{story.id}/scenes/{turn}/image", headers=headers)
    assert response.status_code == 200, response.content
    return response.json()


def _illustrate(client: Client, story, turn: int):
    return client.post(f"/v1/stories/{story.id}/scenes/{turn}/illustrate")


def _account(user=None) -> CreditAccount:
    return CreditAccount.objects.get(user=user or story_owner())


def _payers(story) -> dict[str, str]:
    return dict(Image.objects.filter(story=story).values_list("trigger", "payer"))


def test_the_first_storys_first_pictures_are_on_the_house(client, painters, log_lines):
    story = make_story()
    for turn, kind, trigger, subject in FIRST:
        _plan(story, turn, kind, trigger, subject)

    assert [_image(client, story, turn)["status"] for turn, *_ in FIRST] == ["ready"] * 4

    assert set(_payers(story).values()) == {Payer.HOUSE}
    account = _account()
    assert (account.balance_cents, account.house_pictures_cents) == (50, Decimal("20.4"))
    entries = LedgerEntry.objects.filter(kind=EntryKind.IMAGE)
    assert [(e.amount_cents, e.house, e.detail["list_cents"]) for e in entries] == [
        (0, True, "5.1000")
    ] * 4
    # T5: each picture's line names the house and keeps its cost.
    lines = [line["picture"] for line in log_lines() if line.get("picture")]
    assert [(line["payer"], line["cost_usd"]) for line in lines] == [("house", 0.034)] * 4


def test_key_scenes_fights_redraws_and_illustrate_stay_the_players(client, painters):
    story = make_story()
    _plan(story, 2, "scene", "event")
    _plan(story, 3, "scene", "fight_start")
    Image.objects.create(
        story=story, kind="portrait", subject="zhao", version=1, status=ImageStatus.READY
    )
    _plan(story, 4, "portrait", "look_changed", "zhao", version=2)
    make_scene(story, 5, narration="The rain stops.")

    for turn in (2, 3, 4):
        assert _image(client, story, turn)["status"] == "ready"
    assert _illustrate(client, story, 5).json()["status"] == "ready"

    assert _payers(story) == {
        "event": Payer.CREDITS,
        "fight_start": Payer.CREDITS,
        "look_changed": Payer.CREDITS,
        "illustrate": Payer.CREDITS,
        "": "",  # the portrait drawn before, untouched
    }
    account = _account()
    assert (account.balance_cents, account.house_pictures_cents) == (Decimal("29.6"), 0)


def test_illustrate_on_a_first_picture_not_drawn_yet_draws_it_on_the_house(client, painters):
    """Illustrate on a scene whose first picture is still planned adds nothing: it draws the
    picture the house was going to draw anyway."""
    story = make_story()
    _plan(story, 3, "portrait", "first_meeting", "zhao")

    assert _illustrate(client, story, 3).json()["status"] == "ready"

    assert Image.objects.get(story=story).payer == Payer.HOUSE


def test_illustrate_on_a_skipped_first_picture_is_the_players(client, painters):
    """The player asked to try it again, so it is theirs, even a portrait the house would have
    drawn (M2, M3)."""
    story = make_story()
    _plan(story, 3, "portrait", "first_meeting", "zhao")
    Image.objects.filter(story=story).update(
        status=ImageStatus.SKIPPED, skip_reason=SkipReason.BLOCKED
    )

    assert _illustrate(client, story, 3).json()["status"] == "ready"

    assert Image.objects.get(story=story).payer == Payer.CREDITS
    assert _account().house_pictures_cents == 0


def test_only_the_accounts_first_story_has_its_first_pictures_on_the_house(client, painters):
    first = make_story()
    second = make_story(title="The Second Sect")
    _plan(second, 1, "portrait", "story_start", "lin")
    _plan(first, 1, "portrait", "story_start", "lin")

    _image(client, second, 1)
    _image(client, first, 1)

    assert Image.objects.get(story=second).payer == Payer.CREDITS
    assert Image.objects.get(story=first).payer == Payer.HOUSE


def test_deleting_the_first_story_never_starts_the_allowance_again(client, painters, settings):
    settings.BILLING = {**settings.BILLING, "HOUSE_PICTURES_CENTS": Decimal(10)}
    first = make_story()
    second = make_story(title="The Second Sect")
    for turn, kind, trigger, subject in FIRST[:2]:
        _plan(first, turn, kind, trigger, subject)
        _image(client, first, turn)
    first.delete()

    _plan(second, 1, "portrait", "story_start", "lin")
    _image(client, second, 1)

    # The second story is the oldest now, but the allowance was spent on the first.
    assert Image.objects.get(story=second).payer == Payer.CREDITS
    assert _account().house_pictures_cents == Decimal("10.2")


def test_the_house_stops_paying_once_its_allowance_is_spent(client, painters, settings):
    """The picture that crosses the allowance is still free; the next is the player's."""
    settings.BILLING = {**settings.BILLING, "HOUSE_PICTURES_CENTS": Decimal(10)}
    story = make_story()
    for turn, kind, trigger, subject in FIRST[:3]:
        _plan(story, turn, kind, trigger, subject)
        _image(client, story, turn)

    assert _payers(story) == {
        "story_start": Payer.HOUSE,
        "cover": Payer.HOUSE,
        "first_meeting": Payer.CREDITS,
    }
    account = _account()
    assert (account.house_pictures_cents, account.balance_cents) == (
        Decimal("10.2"),
        Decimal("44.9"),
    )


def test_first_pictures_draw_when_the_credits_are_gone(client, painters):
    story = make_story()
    _plan(story, 1, "portrait", "story_start", "lin")
    _plan(story, 2, "scene", "event")
    credits.credit(story_owner(), Decimal(-50))

    assert _image(client, story, 1)["status"] == "ready"
    assert _image(client, story, 2)["status"] == "skipped"

    assert Image.objects.get(trigger="story_start").payer == Payer.HOUSE
    assert Image.objects.get(trigger="event").skip_reason == SkipReason.NO_CREDITS


def test_an_unverified_account_pays_for_its_first_pictures(painters, settings):
    """The same accounts as the starter credit (K1): an unverified email account gets neither,
    so without credits its first picture is skipped like any other (M7)."""
    settings.BILLING = {**settings.BILLING, "STARTER_POLICY": "verified"}
    story = make_story()  # its owner signs up now, with an email address nobody verified
    _plan(story, 1, "portrait", "story_start", "lin")
    client = Client(headers=auth_headers(story_owner()))

    assert _image(client, story, 1)["status"] == "skipped"
    assert Image.objects.get(story=story).skip_reason == SkipReason.NO_CREDITS
    assert not LedgerEntry.objects.filter(house=True).exists()


def test_asking_again_charges_the_house_once(client, painters):
    story = make_story()
    _plan(story, 1, "portrait", "story_start", "lin")

    _image(client, story, 1)
    _image(client, story, 1)
    _illustrate(client, story, 1)

    assert painters.drawings == 1
    assert LedgerEntry.objects.filter(kind=EntryKind.IMAGE).count() == 1
    assert _account().house_pictures_cents == Decimal("5.1")


def test_the_owners_first_pictures_are_the_owners(painters):
    """K7: unchanged. The owner pays nothing anyway, and spends none of the house allowance."""
    owner = story_owner()
    owner.role = Role.OWNER
    owner.save(update_fields=["role"])
    story = make_story()
    _plan(story, 1, "portrait", "story_start", "lin")

    _image(Client(headers=auth_headers(owner)), story, 1)

    assert Image.objects.get(story=story).payer == Payer.OWNER
    assert LedgerEntry.objects.get(kind=EntryKind.IMAGE).unlimited
    assert _account(owner).house_pictures_cents == 0


def test_the_players_own_key_draws_first_and_the_house_covers_its_fallback(client, painters):
    """K6, M7: unchanged for a key that draws. A key that can't falls back to our account, where
    a first picture is the house's rather than the player's credits."""
    story = make_story()
    _plan(story, 1, "portrait", "story_start", "lin")
    _plan(story, 3, "portrait", "first_meeting", "zhao")
    painters.byok.script(b"\x89PNG own key", KeyCannotDraw("free tier"))

    _image(client, story, 1, **{"X-LLM-Api-Key": "paid-tier"})
    _image(client, story, 3, **{"X-LLM-Api-Key": "free-tier"})

    assert _payers(story) == {"story_start": Payer.BYOK, "first_meeting": Payer.HOUSE}
    assert _account().balance_cents == 50
