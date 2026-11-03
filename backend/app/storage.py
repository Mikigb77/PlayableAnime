from typing import Protocol

import asyncpg
from pydantic import TypeAdapter

from app.domain import Scene, Story, StorySummary, WorldState

_scenes = TypeAdapter(list[Scene])


class StoryRepository(Protocol):
    async def get(self, story_id: str) -> Story | None: ...

    async def list_summaries(self, limit: int = 50) -> list[StorySummary]:
        """Most recently played first."""
        ...

    async def save(self, story: Story) -> None: ...


class InMemoryStoryRepository:
    """Process-local storage, used by tests and when no DATABASE_URL is configured."""

    def __init__(self) -> None:
        self._stories: dict[str, Story] = {}

    async def get(self, story_id: str) -> Story | None:
        return self._stories.get(story_id)

    async def list_summaries(self, limit: int = 50) -> list[StorySummary]:
        return [_summary(s) for s in reversed(self._stories.values())][:limit]

    async def save(self, story: Story) -> None:
        # Re-insert so iteration order tracks the last update, like updated_at in Postgres.
        self._stories.pop(story.id, None)
        self._stories[story.id] = story


class PostgresStoryRepository:
    """Stories in Neon Postgres: one row per story, scenes and world state as JSONB."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, story_id: str) -> Story | None:
        row = await self._pool.fetchrow(
            "SELECT id, title, premise, scenes, state FROM stories WHERE id = $1", story_id
        )
        if row is None:
            return None
        return Story(
            id=row["id"],
            title=row["title"],
            premise=row["premise"],
            scenes=_scenes.validate_json(row["scenes"]),
            state=WorldState.model_validate_json(row["state"]),
        )

    async def list_summaries(self, limit: int = 50) -> list[StorySummary]:
        rows = await self._pool.fetch(
            "SELECT id, title, premise, turn FROM stories ORDER BY updated_at DESC LIMIT $1",
            limit,
        )
        return [StorySummary(**dict(row)) for row in rows]

    async def save(self, story: Story) -> None:
        await self._pool.execute(
            """
            INSERT INTO stories (id, title, premise, turn, scenes, state)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                premise = EXCLUDED.premise,
                turn = EXCLUDED.turn,
                scenes = EXCLUDED.scenes,
                state = EXCLUDED.state,
                updated_at = now()
            """,
            story.id,
            story.title,
            story.premise,
            story.state.turn,
            _scenes.dump_json(story.scenes).decode(),
            story.state.model_dump_json(),
        )


def _summary(story: Story) -> StorySummary:
    return StorySummary(
        id=story.id, title=story.title, premise=story.premise, turn=story.state.turn
    )
