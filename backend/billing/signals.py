"""Opens a credit account with every new user, and grants K1's starter credit when it is due."""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from billing import credits
from billing.models import CreditAccount

# Saves that can make an account qualify for the starter credit (`credits.qualifies_for_starter`).
_QUALIFYING_FIELDS = frozenset({"email_verified", "google_sub"})


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="billing_open_account")
def open_credit_account(sender, instance, created, raw=False, update_fields=None, **kwargs):
    """New accounts are created inside a transaction (WS6), so the credit account and its
    starter entry commit with the user or not at all. A later save that verifies the account,
    such as setting `email_verified`, grants the starter credit then, once."""
    if raw:
        return  # loaddata: fixtures carry their own rows.
    if not created:
        if update_fields is not None and not _QUALIFYING_FIELDS & set(update_fields):
            return
        if not credits.qualifies_for_starter(instance):
            return
        if CreditAccount.objects.filter(user_id=instance.pk, starter_granted=True).exists():
            return
    credits.open_account(instance)
