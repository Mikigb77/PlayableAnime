"""Per-user rate limits and daily quotas in Postgres (T9), so they hold across Cloud Run instances.

Each limit is a fixed window counted in one row per user and bucket. `hit()` adds one in a single
upsert, which locks the row, so concurrent requests on any instance are counted exactly. Call it
inside a transaction: when the request is refused, by this limit or a later check, rolling back
leaves the count as it was, so only requests that went ahead are counted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.db import connection

from billing.models import UsageCounter

MINUTE = 60
DAY = 86_400

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Hit:
    allowed: bool
    count: int
    limit: int
    window_start: datetime
    window_end: datetime

    def retry_after_s(self, now: datetime) -> int:
        """Whole seconds until the window rolls over, at least 1."""
        return max(1, math.ceil((self.window_end - now).total_seconds()))


def window_start(now: datetime, window_s: int) -> datetime:
    """The start of the fixed window that holds `now`. A day window starts at midnight UTC."""
    elapsed = (now - _EPOCH).total_seconds()
    return _EPOCH + timedelta(seconds=(elapsed // window_s) * window_s)


def hit(user_id, bucket: str, *, limit: int, window_s: int, now: datetime) -> Hit:
    """Counts one use of `bucket` for this user and says whether it is within `limit`.

    A refused hit is still counted until the caller's transaction rolls back, so call this
    inside one and raise when it isn't allowed.
    """
    start = window_start(now, window_s)
    table = connection.ops.quote_name(UsageCounter._meta.db_table)
    # A window that rolled over starts again at one. A row already in a later window, written by
    # an instance whose clock runs ahead, keeps its window and counts on.
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {table} AS c (user_id, bucket, window_start, count)
            VALUES (%s, %s, %s, 1)
            ON CONFLICT (user_id, bucket) DO UPDATE SET
                count = CASE WHEN c.window_start >= EXCLUDED.window_start
                             THEN c.count + 1 ELSE 1 END,
                window_start = GREATEST(c.window_start, EXCLUDED.window_start)
            RETURNING count, window_start
            """,
            [user_id, bucket, start],
        )
        count, current_start = cursor.fetchone()
    return Hit(
        allowed=count <= limit,
        count=count,
        limit=limit,
        window_start=current_start,
        window_end=current_start + timedelta(seconds=window_s),
    )
