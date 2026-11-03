"""Neon Postgres access: the connection pool and SQL migrations."""

from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Arbitrary key for the advisory lock that serialises concurrent migration runs.
_MIGRATION_LOCK = 7_241_001


async def create_pool(database_url: str) -> asyncpg.Pool:
    """Small pool over Neon's pooled (PgBouncer) URL.

    Idle connections are dropped after a minute so the compute can still scale to zero.
    """
    return await asyncpg.create_pool(
        database_url, min_size=0, max_size=5, max_inactive_connection_lifetime=60
    )


async def migrate(database_url: str) -> list[str]:
    """Applies pending `migrations/*.sql` files in name order and returns the ones applied.

    Pass the direct (unpooled) URL: PgBouncer's transaction mode drops the session state that
    the advisory lock and DDL rely on.
    """
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", _MIGRATION_LOCK)
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
        done: list[str] = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.stem in applied:
                continue
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
                await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", path.stem)
            done.append(path.stem)
        return done
    finally:
        await conn.close()
