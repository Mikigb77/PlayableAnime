"""The report handlers group, and reports in the account export (T12, T16).

The group is kept in step after every `migrate`, so a fresh database has it and a new
permission joins it, with no data migration to keep up to date. Staff join it in the admin.
Reports leave with their story or account through their foreign keys.
"""

from django.db.models.signals import post_migrate

from moderation.models import REPORT_HANDLERS_GROUP

# What the group may do: read the queue and record decisions (and, through `handle_reports`,
# read the story text reports are about). Deleting a report stays with superusers.
GROUP_PERMISSIONS = (
    ("moderation", "view_report"),
    ("moderation", "change_report"),
    ("moderation", "handle_reports"),
    ("stories", "view_story"),
    ("stories", "view_scene"),
    ("media", "view_image"),
)


def ensure_report_handlers(sender, using="default", apps=None, **kwargs) -> None:
    from django.contrib.auth.models import Group, Permission

    group, _ = Group.objects.using(using).get_or_create(name=REPORT_HANDLERS_GROUP)
    for app_label, codename in GROUP_PERMISSIONS:
        permission = (
            Permission.objects.using(using)
            .filter(content_type__app_label=app_label, codename=codename)
            .first()
        )
        if permission is not None:
            group.permissions.add(permission)


def export_for(sender, user, **kwargs) -> dict:
    """`account_exporting`'s receiver: the player's own reports."""
    from moderation.service import export_reports

    return {"reports": export_reports(user)}


def connect(app_config) -> None:
    from accounts.signals import account_exporting

    post_migrate.connect(
        ensure_report_handlers, sender=app_config, dispatch_uid="moderation.report_handlers"
    )
    account_exporting.connect(export_for, dispatch_uid="moderation.export_for")
