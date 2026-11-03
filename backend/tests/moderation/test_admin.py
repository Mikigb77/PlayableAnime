"""The review queue and who reads story text in the admin (F6, T16)."""

import pytest
from django.contrib.auth.models import Group, Permission
from django.test import Client
from django.urls import reverse

from accounts.models import User
from drafts.models import Draft
from media.models import Image
from moderation.models import REPORT_HANDLERS_GROUP, Report, ReportStatus
from moderation.service import report_scene
from moderation.signals import GROUP_PERMISSIONS

pytestmark = pytest.mark.django_db

SECRET = "Secret narration of turn 2."


def staff(email: str, *, handler: bool = False, superuser: bool = False) -> Client:
    if superuser:
        user = User.objects.create_superuser(email, "pw")
    else:
        user = User.objects.create_user(email, "pw", is_staff=True)
        if handler:
            user.groups.add(Group.objects.get(name=REPORT_HANDLERS_GROUP))
        else:
            # Staff who help with accounts and stories, but not with reports.
            user.user_permissions.add(
                *Permission.objects.filter(
                    content_type__app_label__in=["stories", "media", "drafts"],
                    codename__startswith="view_",
                )
            )
    client = Client()
    client.force_login(user)
    return client


def file_report(story, **fields) -> Report:
    scene = story.scenes.get(turn=2)
    fields.setdefault("category", "sexual")
    fields.setdefault("note", "Please look.")
    fields.setdefault("block", True)
    return report_scene(story, scene, story.owner, **fields)


def test_migrate_creates_the_report_handlers_group():
    group = Group.objects.get(name=REPORT_HANDLERS_GROUP)
    granted = {(p.content_type.app_label, p.codename) for p in group.permissions.all()}
    assert granted == set(GROUP_PERMISSIONS)


def test_a_report_handler_reads_the_report_and_its_scene(story):
    report = file_report(story)
    client = staff("mod@example.com", handler=True)

    queue = client.get(reverse("admin:moderation_report_changelist"))
    page = client.get(reverse("admin:moderation_report_change", args=[report.pk]))

    assert queue.status_code == 200 and page.status_code == 200
    body = page.content.decode()
    assert SECRET in body
    assert "Secret narration of turn 1." in body  # the scene before, for context
    assert "secret action 2" in body and "Please look." in body


def test_other_staff_never_see_the_queue_or_story_text(story):
    report = file_report(story)
    client = staff("help@example.com")

    assert client.get(reverse("admin:moderation_report_changelist")).status_code == 403
    assert (
        client.get(reverse("admin:moderation_report_change", args=[report.pk])).status_code == 403
    )
    for name, obj in [("stories_scene", story.scenes.get(turn=2)), ("stories_story", story)]:
        page = client.get(reverse(f"admin:{name}_change", args=[obj.pk]))
        assert page.status_code == 200
        assert "Secret narration" not in page.content.decode()
        assert "secret action" not in page.content.decode()
        assert "outer-court well" not in page.content.decode()  # the premise
    index = client.get(reverse("admin:index")).content.decode()
    assert "Reports" not in index


def test_a_superuser_reads_everything(story):
    file_report(story)
    client = staff("owner@example.com", superuser=True)
    page = client.get(reverse("admin:stories_scene_change", args=[story.scenes.get(turn=2).pk]))
    assert SECRET in page.content.decode()
    assert client.get(reverse("admin:moderation_report_changelist")).status_code == 200


def test_a_pictures_brief_is_story_text(story):
    image = Image.objects.create(
        story=story, kind="scene", subject="turn-2", brief={"description": "A secret moment."}
    )
    url = reverse("admin:media_image_change", args=[image.pk])

    other = staff("help@example.com").get(url)
    handler = staff("mod@example.com", handler=True).get(url)

    assert other.status_code == 200 and "A secret moment." not in other.content.decode()
    assert handler.status_code == 200 and "A secret moment." in handler.content.decode()


def test_a_drafts_premise_and_proposal_are_story_text(player):
    draft = Draft.objects.create(
        owner=player,
        premise="A secret premise about a lighthouse.",
        rating="teen",
        proposal={"title": "A secret proposal."},
    )
    url = reverse("admin:drafts_draft_change", args=[draft.pk])

    other = staff("help@example.com").get(url)
    handler = staff("owner@example.com", superuser=True).get(url)

    assert other.status_code == 200
    assert "A secret premise" not in other.content.decode()
    assert "A secret proposal." not in other.content.decode()
    assert "A secret premise" in handler.content.decode()


def test_the_queue_puts_open_reports_first_oldest_first(player, make_story):
    first, second, third = (make_story(player, title=f"S{i}") for i in range(3))
    closed = file_report(first)
    older = file_report(second)
    newer = file_report(third)
    Report.objects.filter(pk=closed.pk).update(status=ReportStatus.DISMISSED)
    client = staff("mod@example.com", handler=True)

    response = client.get(reverse("admin:moderation_report_changelist"))

    ids = [r.pk for r in response.context["cl"].result_list]
    assert ids == [older.pk, newer.pk, closed.pk]


def test_closing_a_report_records_who_and_when(story):
    report = file_report(story)
    client = staff("mod@example.com", handler=True)

    response = client.post(
        reverse("admin:moderation_report_changelist"),
        {"action": "mark_dismissed", "_selected_action": [str(report.pk)]},
    )

    assert response.status_code == 302
    report.refresh_from_db()
    assert report.status == ReportStatus.DISMISSED
    assert report.reviewer.email == "mod@example.com" and report.reviewed_at is not None


def test_a_decision_in_the_form_records_the_reviewer(story):
    report = file_report(story)
    client = staff("mod@example.com", handler=True)

    response = client.post(
        reverse("admin:moderation_report_change", args=[report.pk]),
        {"status": "actioned", "resolution": "Narrator prompt tightened."},
    )

    assert response.status_code == 302, response.content
    report.refresh_from_db()
    assert report.status == ReportStatus.ACTIONED
    assert report.resolution == "Narrator prompt tightened."
    assert report.reviewer.email == "mod@example.com"
    # What the player sent never changes in the admin.
    assert (report.category, report.note, report.block) == ("sexual", "Please look.", True)


def test_staff_never_file_or_delete_reports_unless_superuser(story):
    report = file_report(story)
    client = staff("mod@example.com", handler=True)
    assert client.get(reverse("admin:moderation_report_add")).status_code == 403
    assert (
        client.get(reverse("admin:moderation_report_delete", args=[report.pk])).status_code == 403
    )
