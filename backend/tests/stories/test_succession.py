"""N6 over HTTP: after its ending, a story carries on as a random person of its world. Drawing them
is one drafting call, charged like a draft; carrying on as them lifts the ending, and the story's
next turn is their opening."""

import pytest
from django.db.models import F
from django.test import Client

from billing.models import CreditHold, LedgerEntry
from drafts import service
from engine import heirs
from engine.base import DAY, YEAR
from engine.samples import cultivation_world
from engine.state import (
    Character,
    CharacterStatus,
    DeathCertainty,
    OriginKind,
    Pregnancy,
    WorldState,
)
from graph.drafting.samples import SUCCESSOR
from graph.llm import FakeBackend, Node, Reply
from lucid.errors import ApiError, ErrorCode
from stories import succession
from stories.models import Story
from tests.conftest import auth_headers
from tests.stories.conftest import opening, play
from tests.stories.test_endings import dead

pytestmark = pytest.mark.django_db

OPENING = {
    "narration": "Before dawn, Mara heaves the first crate as the axle groans.",
    "suggestions": [{"label": "Brace the axle", "kind": "personal"}],
}


@pytest.fixture
def client(player) -> Client:
    return Client(headers=auth_headers(player))


@pytest.fixture
def drafter(monkeypatch) -> FakeBackend:
    fake = FakeBackend(default=lambda request: Reply(json=SUCCESSOR))
    monkeypatch.setattr(service, "model_backend", lambda *, grounded, byok: fake)
    return fake


def draw(client, story) -> dict:
    response = client.post(f"/v1/stories/{story.pk}/successor")
    assert response.status_code == 200, response.json()
    return response.json()


def carry_on(client, story, version=None):
    return client.post(
        f"/v1/stories/{story.pk}/carry-on",
        {"expected_version": story.version if version is None else version},
        content_type="application/json",
    )


def test_drawing_someone_to_carry_the_story_on(client, player, make_story, model, drafter):
    story = dead(player, make_story, model)

    drawn = draw(client, story)

    assert drawn["name"] == "Mara Venn"
    assert drawn["station"] in {"common", "skilled", "notable", "noble", "royal"}
    assert drawn["one_in"] >= 1 and drawn["draws"] == 1
    assert drawn["lines"][0].startswith("Mara Venn,")
    assert drawn["situation"].startswith("Before dawn")
    [call] = drafter.calls(Node.DRAFTER)
    assert "THE DRAW" in call.prompt.messages[-1].text
    # Charged like a draft (K2), with nothing held back.
    assert LedgerEntry.objects.filter(user_id=player.pk, kind="draft").count() == 1
    assert not CreditHold.objects.exists()
    # The story shows who was drawn until the player starts as them or draws again.
    assert client.get(f"/v1/stories/{story.pk}").json()["successor"]["name"] == "Mara Venn"


def test_drawing_again_draws_someone_else(client, player, make_story, model, drafter):
    story = dead(player, make_story, model)
    draw(client, story)

    again = draw(client, story)

    assert again["draws"] == 2
    assert Story.objects.get(pk=story.pk).successor["draws"] == 2


def test_carrying_on_lifts_the_ending_and_opens_on_the_newcomer(
    client, player, make_story, model, drafter
):
    story = dead(player, make_story, model)
    draw(client, story)

    response = carry_on(client, story)

    assert response.status_code == 200, response.json()
    shown = response.json()
    assert shown["ending"] is None and shown["successor"] is None
    assert shown["opening_due"] is True
    assert shown["version"] == story.version + 1
    story.refresh_from_db()
    assert story.state["player_id"] != "lin"
    assert story.state["fallen"][0]["character_id"] == "lin"
    [summary] = client.get("/v1/stories").json()
    assert summary["ending"] is None

    # Only the newcomer's opening can come next.
    action = {"kind": "action", "action": "I look", "expected_version": story.version}
    acted = play(player, story, action)
    assert acted.status == 400
    assert acted.body["error"]["details"]["fields"][0]["type"] == "not_opened"
    model.backend.script(Node.NARRATOR, Reply(json=OPENING))
    opened = play(player, story, opening(story))
    assert opened.names[-1] == "scene.completed", opened.events
    assert opened.completed["scene"]["kind"] == "opening"
    story.refresh_from_db()
    assert story.state["opening_due"] is False and story.turn == 3
    assert story.state["player_id"] == "pc-2"
    assert client.get(f"/v1/stories/{story.pk}").json()["opening_due"] is False


def test_carrying_on_needs_someone_drawn(client, player, make_story, model):
    story = dead(player, make_story, model)

    response = carry_on(client, story)

    assert response.status_code == 400
    assert response.json()["error"]["details"]["fields"][0]["type"] == "no_successor"


def test_carrying_on_from_a_stale_version_is_refused(client, player, make_story, model, drafter):
    story = dead(player, make_story, model)
    draw(client, story)

    response = carry_on(client, story, version=story.version - 1)

    assert response.status_code == 409
    assert Story.objects.get(pk=story.pk).ending is not None


@pytest.mark.parametrize("closed", [False, True])
def test_only_a_story_at_an_open_ending_carries_on(
    client, player, make_story, model, drafter, closed
):
    if closed:
        story = dead(player, make_story, model)
        client.post(f"/v1/stories/{story.pk}/close")
        expected = "closed"
    else:
        story = make_story(player)
        expected = "not_ended"

    response = client.post(f"/v1/stories/{story.pk}/successor")

    assert response.status_code == 400
    assert response.json()["error"]["details"]["fields"][0]["type"] == expected
    assert drafter.calls(Node.DRAFTER) == []
    assert not LedgerEntry.objects.filter(user_id=player.pk, kind="draft").exists()


def test_only_your_own_story_carries_on(make_user, player, make_story, model, drafter):
    story = dead(player, make_story, model)
    other = Client(headers=auth_headers(make_user("other@example.com")))

    assert other.post(f"/v1/stories/{story.pk}/successor").status_code == 403
    assert carry_on(other, story).status_code == 403


def test_closing_the_story_puts_away_whoever_was_drawn(client, player, make_story, model, drafter):
    story = dead(player, make_story, model)
    draw(client, story)

    client.post(f"/v1/stories/{story.pk}/close")

    assert client.get(f"/v1/stories/{story.pk}").json()["successor"] is None
    assert carry_on(client, story).json()["error"]["details"]["fields"][0]["type"] == "closed"


def test_drawing_again_counts_after_a_draw_that_landed_meanwhile(
    client, player, make_story, model, drafter
):
    story = dead(player, make_story, model)
    draw(client, story)
    stale = Story.objects.get(pk=story.pk)
    drawn = succession.Drawn.model_validate(stale.successor)
    draw(client, story)

    kept = succession._keep(stale, drawn, _Call())

    assert kept.draws == 3
    assert Story.objects.get(pk=story.pk).successor["draws"] == 3


def test_someone_drawn_from_a_world_that_moved_on_is_not_kept(
    client, player, make_story, model, drafter
):
    story = dead(player, make_story, model)
    draw(client, story)
    stale = Story.objects.get(pk=story.pk)
    drawn = succession.Drawn.model_validate(stale.successor)
    Story.objects.filter(pk=story.pk).update(version=F("version") + 1, successor=None)
    call = _Call()

    with pytest.raises(ApiError) as refused:
        succession._keep(stale, drawn, call)

    assert refused.value.code is ErrorCode.VERSION_CONFLICT
    assert not call.charged and Story.objects.get(pk=story.pk).successor is None


def test_an_opening_moment_that_names_a_stranger_to_them_is_not_shown(
    client, player, make_story, model, drafter
):
    story = dead(player, make_story, model)
    drafter.default = lambda request: Reply(
        json=SUCCESSOR | {"situation": "Mara watches Elder Mo cross the courtyard."}
    )

    drawn = draw(client, story)

    assert "Elder Mo" not in drawn["situation"]
    assert drawn["situation"].startswith("An ordinary day for Mara Venn")


class _Call:
    charged = False

    def charge(self) -> None:
        self.charged = True


# --- Heirs (N6) -------------------------------------------------------------------------------


def with_family(story: Story) -> Story:
    """Lin, dead at his ending, with a son of 3 and a child on the way with Mei."""
    state = WorldState.model_validate(story.state)
    state.characters["bao"] = Character(
        id="bao", name="Lin Bao", age=3, location_id="well", parent_ids=["lin"]
    )
    state.characters["mei"] = Character(
        id="mei",
        name="Mei",
        age=22,
        location_id="well",
        expecting=Pregnancy(other_parent_id="lin", conceived_s=0, due_s=state.world_s + 30 * DAY),
    )
    story.state = state.model_dump(mode="json")
    story.save(update_fields=["state"])
    return story


def test_the_ending_offers_the_player_characters_heirs(client, player, make_story, model):
    story = with_family(dead(player, make_story, model))

    shown = client.get(f"/v1/stories/{story.pk}").json()

    assert shown["heirs"] == [
        {
            "id": "bao",
            "name": "Lin Bao",
            "relation": "child",
            "age": 3,
            "unborn": False,
            "years": 13,
        },
        {
            "id": "unborn:mei",
            "name": "Mei's child, not yet born",
            "relation": "child",
            "age": None,
            "unborn": True,
            "years": 17,
        },
    ]
    client.post(f"/v1/stories/{story.pk}/close")
    assert client.get(f"/v1/stories/{story.pk}").json()["heirs"] == []


def test_carrying_on_as_an_heir_after_the_years_they_need_to_grow_up(
    client, player, make_story, model, drafter
):
    story = with_family(dead(player, make_story, model))
    ended_s = story.state["world_s"]

    response = client.post(f"/v1/stories/{story.pk}/successor?heir_id=bao")

    assert response.status_code == 200, response.json()
    drawn = response.json()
    assert drawn["name"] == "Lin Bao" and drawn["age"] == 16  # the name the story gave him
    assert drawn["heir"] == {
        "id": "bao",
        "name": "Lin Bao",
        "relation": "child",
        "age": 3,
        "unborn": False,
        "years": 13,
    }
    [call] = drafter.calls(Node.DRAFTER)
    assert "THE HEIR" in call.prompt.messages[-1].text
    assert LedgerEntry.objects.filter(user_id=player.pk, kind="draft").count() == 1
    story.refresh_from_db()
    assert story.state["world_s"] == ended_s  # the world runs on only when they start

    carried = carry_on(client, story)

    assert carried.status_code == 200, carried.json()
    story.refresh_from_db()
    state = WorldState.model_validate(story.state)
    assert state.player_id == "bao" and state.player.age == 16
    assert state.world_s == ended_s + 13 * YEAR
    assert state.fallen[0].world_s == ended_s
    assert state.opening_due and carried.json()["heirs"] == []


def test_carrying_on_as_a_child_not_yet_born(client, player, make_story, model, drafter):
    story = with_family(dead(player, make_story, model))

    drawn = client.post(f"/v1/stories/{story.pk}/successor?heir_id=unborn:mei").json()

    assert drawn["name"] == "Mara Venn" and drawn["age"] == 16  # named by the drafter
    assert drawn["heir"]["unborn"] is True and drawn["heir"]["years"] == 17
    assert carry_on(client, story).status_code == 200
    story.refresh_from_db()
    state = WorldState.model_validate(story.state)
    you = state.player
    assert you.name == "Mara Venn" and you.parent_ids == ["mei", "lin"] and you.age == 16
    assert you.origin.kind is OriginKind.BIRTH
    assert state.characters["mei"].expecting is None


def test_an_heir_must_be_one_the_story_offers(client, player, make_story, model, drafter):
    story = with_family(dead(player, make_story, model))

    response = client.post(f"/v1/stories/{story.pk}/successor?heir_id=elder-mo")

    assert response.status_code == 400
    assert response.json()["error"]["details"]["fields"][0]["type"] == "unknown_heir"
    assert drafter.calls(Node.DRAFTER) == []


def test_an_heir_who_didnt_live_to_act_cant_carry_the_story_on():
    state = WorldState.model_validate(cultivation_world().model_dump())
    bao = Character(id="bao", name="Lin Bao", age=3, parent_ids=["lin"])
    bao.status, bao.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED
    state.characters["bao"] = bao
    heir = heirs.Heir(id="bao", name="Lin Bao", generation=1, age=3, jump_s=13 * YEAR)

    with pytest.raises(ApiError) as refused:
        succession._heir_now(state, heir)

    assert refused.value.details["fields"][0]["type"] == "heir_lost"
