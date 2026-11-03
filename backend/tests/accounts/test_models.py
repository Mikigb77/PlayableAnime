import pytest
from django.db import IntegrityError

from accounts.models import Role, User

pytestmark = pytest.mark.django_db


def test_the_email_is_the_login_and_is_stored_lowercased():
    user = User.objects.create_user("Kaede@Example.COM", "a long password")

    assert user.email == "kaede@example.com"
    assert user.check_password("a long password")
    assert user.role == Role.PLAYER
    assert not user.is_owner
    assert not user.is_staff
    assert User.objects.get_by_natural_key("KAEDE@example.com") == user


def test_emails_are_unique_regardless_of_case():
    User.objects.create_user("ren@example.com")

    with pytest.raises(IntegrityError):
        User.objects.create_user("REN@example.com")


def test_a_google_only_account_has_no_usable_password():
    user = User.objects.create_user("g@example.com", google_sub="1234567890")

    assert not user.has_usable_password()
    assert user.birth_date is None


def test_google_subject_ids_are_unique():
    User.objects.create_user("a@example.com", google_sub="sub-1")

    with pytest.raises(IntegrityError):
        User.objects.create_user("b@example.com", google_sub="sub-1")


def test_a_superuser_is_staff():
    user = User.objects.create_superuser("admin@example.com", "pw")

    assert user.is_staff and user.is_superuser


def test_an_email_is_required():
    with pytest.raises(ValueError):
        User.objects.create_user("")


def test_the_owner_role():
    assert User(email="o@example.com", role=Role.OWNER).is_owner
