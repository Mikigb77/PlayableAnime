import pytest
from django.test import Client
from django.urls import reverse

from accounts import tokens
from accounts.models import AuthSession, RefreshToken, SignInMethod

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client(make_user) -> Client:
    client = Client()
    client.force_login(make_user("staff@example.com", is_staff=True, is_superuser=True))
    return client


def test_staff_see_a_players_devices_and_can_sign_them_out(staff_client, player):
    session = tokens.issue(player, SignInMethod.GOOGLE).session
    headers = {"Authorization": f"Bearer {tokens.make_access_token(player.pk, session.pk)}"}
    assert Client().get("/v1/me", headers=headers).status_code == 200

    assert (
        staff_client.get(reverse("admin:accounts_user_change", args=[player.pk])).status_code == 200
    )
    assert staff_client.get(reverse("admin:accounts_authsession_changelist")).status_code == 200
    response = staff_client.post(
        reverse("admin:accounts_authsession_changelist"),
        {"action": "revoke", "_selected_action": [str(session.pk)]},
    )

    assert response.status_code == 302
    assert AuthSession.objects.get().revoked_reason == "admin"
    assert not RefreshToken.objects.exists()
    assert Client().get("/v1/me", headers=headers).status_code == 401


def test_the_role_is_read_only_in_the_admin(staff_client, player):
    """K7: only a verified Google sign-in for an OWNER_EMAILS address makes an owner."""
    page = staff_client.get(reverse("admin:accounts_user_change", args=[player.pk]))

    assert b'name="role"' not in page.content
