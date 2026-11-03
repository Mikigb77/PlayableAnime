"""Pictures leave with their story or account (T12, M4), and go along with the export.

Deleting a story or an account cascades to its `Image` rows, and each deleted row's file is
removed from storage once the transaction commits, so a delete that rolls back never loses a
picture. That covers `accounts.services.delete_account` too, which deletes the user inside a
transaction, so pictures need no `account_deleting` receiver.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete

from media.models import Image
from media.storage import get_storage

logger = logging.getLogger("media.pictures")


def delete_file(sender, instance: Image, **kwargs) -> None:
    key = instance.storage_key
    if not key:
        return

    def remove() -> None:
        try:
            get_storage().delete(key)
        except Exception:
            # Left behind, it is still private and unreachable without a signed URL.
            logger.warning(
                "A deleted picture's file couldn't be removed",
                exc_info=True,
                extra={"image_id": str(instance.pk)},
            )

    transaction.on_commit(remove)


def export_for(sender, user, **kwargs) -> dict:
    """`account_exporting`'s receiver: the user's pictures, with fresh signed URLs."""
    from media.lookups import export_pictures

    return {"images": export_pictures(user)}


def connect() -> None:
    from accounts.signals import account_exporting

    post_delete.connect(delete_file, sender=Image, dispatch_uid="media.delete_file")
    account_exporting.connect(export_for, dispatch_uid="media.export_for")
