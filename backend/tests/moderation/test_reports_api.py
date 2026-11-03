"""`POST /v1/stories/{id}/scenes/{turn}/report` (F6): report and block any scene."""

import json

import pytest
from asgiref.sync import async_to_sync
from django.test import Client

from moderation.models import Report, ReportStatus
from moderation.service import blocked_turns
from tests.conftest import auth_headers
from tests.moderation.conftest import TEEN_BIRTH_DATE

pytestmark = pytest.mark.django_db


def report(client: Client, story, turn=2, **body):
    body.setdefault("category", "sexual")
    return client.post(
        f"/v1/stories/{story.id}/scenes/{turn}/report",
        json.dumps(body),
        content_type="application/json",
    )


def test_a_report_reaches_the_queue(player_client, player, story):
    response = report(player_client, story, category="minor", note="  Too far.  ", block=True)

    assert response.status_code == 204
    saved = Report.objects.get()
    assert saved.story == story and saved.scene.turn == 2 and saved.reporter == player
    assert (saved.category, saved.note, saved.block) == ("minor", "Too far.", True)
    assert saved.status == ReportStatus.OPEN


def test_block_is_optional_and_off_by_default(player_client, story):
    assert report(player_client, story, category="other").status_code == 204
    assert Report.objects.get().block is False


def test_reporting_a_scene_again_updates_the_report(player_client, story):
    report(player_client, story, category="hate", note="First.", block=True)
    Report.objects.update(status=ReportStatus.DISMISSED)

    assert report(player_client, story, category="real_person").status_code == 204

    saved = Report.objects.get()
    assert saved.category == "real_person"
    assert saved.note == "First."  # no new note keeps the old one
    assert saved.block is True  # a block is never undone by a later report
    assert saved.status == ReportStatus.OPEN  # and a closed report opens again


def test_blocked_turns_are_the_ones_the_player_hid(player_client, story):
    report(player_client, story, turn=1, block=False)
    report(player_client, story, turn=2, block=True)

    assert async_to_sync(blocked_turns)(story) == {2}
    assert async_to_sync(blocked_turns)(str(story.id)) == {2}


def test_the_log_line_has_the_category_and_never_the_note(player_client, story, log_lines):
    report(player_client, story, category="self_harm", note="private words", block=True)

    [line] = [line for line in log_lines() if line.get("message") == "scene reported"]
    assert line["report"]["category"] == "self_harm"
    assert line["report"]["turn"] == 2 and line["report"]["block"] is True
    assert line["story_id"] == str(story.id)
    assert "private words" not in json.dumps(log_lines())


def test_an_unknown_scene_or_story_is_not_found(player_client, story):
    assert report(player_client, story, turn=9).json()["error"]["code"] == "not_found"
    story.id = "00000000-0000-0000-0000-000000000000"
    assert report(player_client, story).status_code == 404


def test_only_the_owner_can_report(make_user, story):
    stranger = Client(headers=auth_headers(make_user("stranger@example.com")))
    assert report(stranger, story).status_code == 403
    assert report(Client(), story).status_code == 401
    assert not Report.objects.exists()


def test_a_story_above_the_accounts_rating_is_forbidden(make_user, make_story):
    teen = make_user("teen@example.com", birth_date=TEEN_BIRTH_DATE)
    story = make_story(teen, rating="mature")

    response = report(Client(headers=auth_headers(teen)), story)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize(
    "body",
    [{"category": "spoilers"}, {"category": "other", "note": "x" * 1001}, {}],
)
def test_a_bad_report_is_a_validation_error(player_client, story, body):
    response = player_client.post(
        f"/v1/stories/{story.id}/scenes/2/report",
        json.dumps(body),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_reports_leave_with_the_story_and_the_account(player, player_client, story):
    report(player_client, story, block=True)
    story.delete()
    assert not Report.objects.exists()


def test_reports_are_in_the_export_and_deleted_with_the_account(player, player_client, story):
    report(player_client, story, category="hate", note="Mine.", block=True)

    exported = player_client.get("/v1/me/export").json()

    assert exported["reports"] == [
        {
            "story_id": str(story.id),
            "turn": 2,
            "category": "hate",
            "note": "Mine.",
            "block": True,
            "status": "open",
            "created_at": Report.objects.get().created_at.isoformat(),
        }
    ]
    assert player_client.delete("/v1/me").status_code == 204
    assert not Report.objects.exists()
