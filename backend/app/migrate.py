"""Applies pending database migrations: `uv run python -m app.migrate`."""

import asyncio
import sys

from app.config import get_settings
from app.db import migrate


def main() -> None:
    url = get_settings().database_url_unpooled
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED is not set. Run `neon env pull` in the repo root.")
    applied = asyncio.run(migrate(url))
    print(f"Applied: {', '.join(applied)}" if applied else "Database is up to date.")


if __name__ == "__main__":
    main()
