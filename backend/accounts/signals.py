"""Hooks other apps use to take part in deleting and exporting an account (T12, M4).

- `account_deleting(sender=User, user=...)` is sent inside the delete transaction, just before the
  user row goes. Rows with a foreign key to the user or their stories cascade on their own, so a
  receiver only handles what lives outside Postgres, such as pictures in Cloud Storage, and should
  do that with `transaction.on_commit(...)` so a rolled-back delete loses nothing.
- `account_exporting(sender=User, user=...)` is sent while `GET /v1/me/export` builds the export.
  Each receiver returns a dict whose keys are added to the export's top level, such as
  `{"images": [...]}`. It can't replace `user` or `stories`.

Both are sent from sync code off the event loop, so receivers may use the ORM directly.
"""

from django.dispatch import Signal

account_deleting = Signal()
account_exporting = Signal()
