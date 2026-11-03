"""Stories made the way starting a draft makes them, a scripted model under the real client, and
a helper that plays a turn over ASGI and reads its server-sent events."""

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from asgiref.sync import async_to_sync
from django.test import AsyncClient

from engine.context import StorySettings
from engine.samples import cultivation_world, grounded_world
from graph.llm import FakeBackend, ModelClient, ModelConfig
from stories import turns
from stories.models import Engine, Story
from tests.conftest import auth_headers

WORLDS = {"cultivation": cultivation_world, "grounded": grounded_world}


@pytest.fixture(autouse=True)
def starter_credit_for_everyone(settings):
    """Turns draw on real credits, and `make_user` makes unverified email accounts, which get no
    starter credit under the default policy (K1)."""
    settings.BILLING = {**settings.BILLING, "STARTER_POLICY": "all"}


@pytest.fixture(autouse=True)
def picture_files(settings, tmp_path):
    settings.MEDIA_BUCKET = ""
    settings.PICTURE_ROOT = str(tmp_path / "pictures")


@dataclass
class Model:
    """The scripted model every turn in the test uses, and the clients built on it."""

    backend: FakeBackend
    builds: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def model(monkeypatch) -> Model:
    model = Model(FakeBackend(chunk_size=9))

    def build(*, rating, byok=None, recorder=None):
        model.builds.append({"rating": rating, "byok": byok})
        return ModelClient(
            model.backend,
            ModelConfig(),
            rating=rating,
            recorder=recorder,
            byok=byok is not None,
            retry_delay_s=0,
        )

    monkeypatch.setattr(turns, "build_client", build)
    return model


@pytest.fixture
def make_story(db):
    """A story as `POST /v1/drafts/{id}/start` saves it: the world at turn 0, no scenes."""

    def make(owner, world: str = "cultivation", **fields) -> Story:
        state = WORLDS[world]()
        fields.setdefault("settings", StorySettings().model_dump(mode="json"))
        return Story.objects.create(
            owner=owner,
            title=fields.pop("title", state.bible.title),
            premise=fields.pop("premise", "A premise."),
            genre=fields.pop("genre", state.bible.genre),
            rating=fields.pop("rating", "mature"),
            engine=Engine.GRAPH,
            state=fields.pop("state", state.model_dump(mode="json")),
            turn=0,
            version=1,
            **fields,
        )

    return make


@dataclass
class Played:
    status: int
    events: list[tuple[str, dict[str, Any]]]
    body: dict[str, Any] | None = None

    def named(self, name: str) -> list[dict[str, Any]]:
        return [data for event, data in self.events if event == name]

    @property
    def names(self) -> list[str]:
        return [event for event, _ in self.events]

    @property
    def text(self) -> str:
        return "".join(data["text"] for data in self.named("narration.delta"))

    @property
    def completed(self) -> dict[str, Any]:
        [data] = self.named("scene.completed")
        return data


def parse_events(raw: bytes) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in raw.decode().split("\n\n"):
        if not block.strip():
            continue
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def play(user, story: Story | str, body: dict[str, Any], **headers) -> Played:
    """Plays one turn over ASGI and reads the whole stream."""
    story_id = story if isinstance(story, str) else str(story.pk)
    headers = auth_headers(user) | headers

    async def run() -> Played:
        # Headers go on each request: AsyncClient(headers=...) sends them under WSGI names.
        response = await AsyncClient().post(
            f"/v1/stories/{story_id}/turns",
            body,
            content_type="application/json",
            headers=headers,
        )
        if not response.streaming:
            return Played(response.status_code, [], response.json())
        assert response["Content-Type"].startswith("text/event-stream")
        raw = b"".join([chunk async for chunk in response.streaming_content])
        return Played(response.status_code, parse_events(raw))

    return async_to_sync(run)()


def opening(story: Story) -> dict[str, Any]:
    return {"kind": "opening", "expected_version": story.version}
