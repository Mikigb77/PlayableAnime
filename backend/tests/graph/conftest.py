import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import aclosing
from typing import Any

import pytest
from pydantic import BaseModel

from graph.llm import FakeBackend, ModelClient, ModelConfig, TurnTelemetry


class Narration(BaseModel):
    title: str = ""
    narration: str
    choices: list[str] = []


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def collect(events: AsyncIterator[Any]) -> list[Any]:
    async with aclosing(events) as stream:
        return [event async for event in stream]


@pytest.fixture
def fake() -> FakeBackend:
    return FakeBackend(chunk_size=7)


@pytest.fixture
def telemetry() -> TurnTelemetry:
    return TurnTelemetry()


@pytest.fixture
def make_client(fake, telemetry):
    def make(*, rating="mature", byok=False, backend=None) -> ModelClient:
        return ModelClient(
            backend or fake,
            ModelConfig(),
            rating=rating,
            recorder=telemetry,
            byok=byok,
            retry_delay_s=0,
        )

    return make
