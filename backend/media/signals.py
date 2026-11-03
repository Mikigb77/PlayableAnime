"""Pictures leave with their story or account (T12, M4), and go along with the export.

Deleting a story or an account cascades to its `Image` rows, and each deleted row's file is
removed from storage once the transaction commits, so a delete that rolls back never loses a
picture. This covers WS6's account deletion with no receiver of its own.
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
    """WS6's account export: the user's pictures, with fresh signed URLs."""
    from media.lookups import export_pictures

    return {"images": export_pictures(user)}


def connect() -> None:
    post_delete.connect(delete_file, sender=Image, dispatch_uid="media.delete_file")
    try:
        from accounts import signals as account_signals
    except ImportError:  # WS6's signals haven't landed yet
        return
    exporting = getattr(account_signals, "account_exporting", None)
    if exporting is not None:
        exporting.connect(export_for, dispatch_uid="media.export_for")
