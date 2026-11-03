"""Who in the Django admin may read story text (T16).

Story text can reveal a player's sexual preferences, which GDPR treats as special-category data,
so only staff handling reports read it: superusers (the owner, K7) and staff in the report
handlers group, which holds `moderation.handle_reports`. Other staff still see a story's title,
rating, turns and numbers, so they can help with accounts and credits without reading anyone's
story.
"""

from django.http import HttpRequest

from moderation.models import HANDLE_REPORTS


def can_read_story_text(user) -> bool:
    return bool(
        user is not None and user.is_active and user.is_staff and user.has_perm(HANDLE_REPORTS)
    )


class StoryTextAdmin:
    """For a `ModelAdmin` or an inline: hides the fields in `story_text_fields` from staff who
    don't handle reports, in forms, read-only fields and lists alike."""

    story_text_fields: tuple[str, ...] = ()

    def _hidden(self, request: HttpRequest) -> set[str]:
        return set() if can_read_story_text(request.user) else set(self.story_text_fields)

    def get_fields(self, request, obj=None):
        hidden = self._hidden(request)
        return [f for f in super().get_fields(request, obj) if f not in hidden]

    def get_readonly_fields(self, request, obj=None):
        hidden = self._hidden(request)
        return [f for f in super().get_readonly_fields(request, obj) if f not in hidden]

    def get_exclude(self, request, obj=None):
        return [*(super().get_exclude(request, obj) or ()), *self._hidden(request)] or None

    def get_list_display(self, request):
        hidden = self._hidden(request)
        return [f for f in super().get_list_display(request) if f not in hidden]

    def get_search_fields(self, request):
        # Searching by a hidden field would let staff probe its text.
        hidden = self._hidden(request)
        return [f for f in super().get_search_fields(request) if f.split("__")[0] not in hidden]
