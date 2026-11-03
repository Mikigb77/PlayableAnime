"""Integration tests against a real Postgres, e.g. a Neon dev branch.

Skipped unless TEST_DATABASE_URL is set. TEST_DATABASE_URL_UNPOOLED (for migrations) defaults
to the same URL. Never point these at production: they write and delete rows.
"""

import asyncio
import os

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import migrate
from app.main import create_app

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
DATABASE_URL_UNPOOLED = os.environ.get("TEST_DATABASE_URL_UNPOOLED", DATABASE_URL)

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")


@pytest.fixture(scope="module")
def created_ids():
    asyncio.run(migrate(DATABASE_URL_UNPOOLED))
    ids: list[str] = []
    yield ids
    asyncio.run(_delete(ids))


def _client() -> TestClient:
    """A fresh app instance, as after a server restart."""
    return TestClient(create_app(Settings(llm_provider="fake", database_url=DATABASE_URL)))


def test_migrations_are_idempotent(created_ids):
    assert asyncio.run(migrate(DATABASE_URL_UNPOOLED)) == []


def test_stories_survive_a_restart(created_ids):
    with _client() as client:
        assert client.get("/health").json()["storage"] == "postgres"
        story = client.post("/v1/stories", json={"premise": "A courier finds a package."}).json()
        created_ids.append(story["id"])
        client.post(f"/v1/stories/{story['id']}/turns", json={"choice_id": "c2"})

    with _client() as client:
        loaded = client.get(f"/v1/stories/{story['id']}").json()
        memory = client.get(f"/v1/stories/{story['id']}/memory").json()
        summaries = client.get("/v1/stories").json()

    assert [s["player_action"] for s in loaded["scenes"]] == [None, "Search for allies"]
    assert memory["turn"] == 2
    assert [c["name"] for c in memory["characters"]] == ["Ren"]
    assert summaries[0] == {
        "id": story["id"],
        "title": story["title"],
        "premise": story["premise"],
        "turn": 2,
    }


async def _delete(ids: list[str]) -> None:
    conn = await asyncpg.connect(DATABASE_URL_UNPOOLED)
    try:
        await conn.execute("DELETE FROM stories WHERE id = ANY($1::text[])", ids)
    finally:
        await conn.close()
