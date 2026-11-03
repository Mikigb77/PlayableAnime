from typing import Protocol

from app.domain import Story


class StoryRepository(Protocol):
    async def get(self, story_id: str) -> Story | None: ...

    async def list(self) -> list[Story]: ...

    async def save(self, story: Story) -> None: ...


class InMemoryStoryRepository:
    """Process-local storage. Stand-in until the Neon Postgres repository exists."""

    def __init__(self) -> None:
        self._stories: dict[str, Story] = {}

    async def get(self, story_id: str) -> Story | None:
        return self._stories.get(story_id)

    async def list(self) -> list[Story]:
        return list(self._stories.values())

    async def save(self, story: Story) -> None:
        self._stories[story.id] = story
