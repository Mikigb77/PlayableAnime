"""A scene's audio leaves with its story or account (T12), like its pictures (`media.signals`).

Deleting a story or an account cascades to its scenes and their `SceneAudio` rows, and each
deleted row's file is removed from storage once the transaction commits, so a delete that rolls
back never loses a file. That covers `accounts.services.delete_account`, which deletes the user
inside a transaction. The export (T12) leaves audio out: it is the scenes' own text, read aloud.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete

from media.storage import get_storage
from speech.models import SceneAudio

logger = logging.getLogger("speech")


def delete_file(sender, instance: SceneAudio, **kwargs) -> None:
    key = instance.storage_key
    if not key:
        return

    def remove() -> None:
        try:
            get_storage().delete(key)
        except Exception:
            # Left behind, it is still private and unreachable without a signed URL.
            logger.warning(
                "A deleted scene audio's file couldn't be removed",
                exc_info=True,
                extra={"audio_id": str(instance.pk)},
            )

    transaction.on_commit(remove)


def connect() -> None:
    post_delete.connect(delete_file, sender=SceneAudio, dispatch_uid="speech.delete_file")
