"""Fakes for the picture tests: a scripted picture model, a recording credit meter, and a story
with scenes, owned by `story_owner()` unless a test says otherwise. Files go to a fresh folder per
test."""

import asyncio
import threading
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from billing.pricing import ModelCall
from media import billing, drawing, storage
from media.drawing import Drawn
from media.models import Payer
from stories.models import Engine, Scene, SceneKind, Story
from tests.conftest import ADULT_BIRTH_DATE

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


class FakePictureModel:
    """Draws each scripted outcome in turn: picture bytes, or an exception to raise. With no
    script left it draws `PNG`. A `gate` holds every drawing until it is set."""

    def __init__(self, *outcomes, byok: bool = False, model: str = "fake-image") -> None:
        self.outcomes = deque(outcomes)
        self.byok = byok
        self.model = model
        self.requests: list[drawing.DrawRequest] = []
        # The note step (`media.notes`): each scripted note or exception in turn, then none.
        self.notes: deque = deque()
        self.note_prompts: list = []
        self.closed = 0
        self.gate: threading.Event | None = None
        self.started = threading.Event()

    def script(self, *outcomes) -> "FakePictureModel":
        self.outcomes.extend(outcomes)
        return self

    def script_notes(self, *notes) -> "FakePictureModel":
        self.notes.extend(notes)
        return self

    async def note(self, prompt):
        self.note_prompts.append(prompt)
        outcome = self.notes.popleft() if self.notes else None
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def draw(self, request: drawing.DrawRequest) -> Drawn:
        self.requests.append(request)
        self.started.set()
        if self.gate is not None:
            await asyncio.to_thread(self.gate.wait, 10)
        outcome = self.outcomes.popleft() if self.outcomes else PNG
        if isinstance(outcome, BaseException):
            raise outcome
        return Drawn(outcome, "image/png", self.model, Decimal("0.034"), calls=(self.call,))

    @property
    def call(self) -> ModelCall:
        """The call record billing charges from, as the model layer would write it (T5)."""
        return ModelCall(model=self.model, images=1, cost_usd=Decimal("0.034"), byok=self.byok)

    async def aclose(self) -> None:
        self.closed += 1


@dataclass
class Painters:
    ours: FakePictureModel
    byok: FakePictureModel
    builds: list[tuple[str, str]] = field(default_factory=list)

    @property
    def drawings(self) -> int:
        return len(self.ours.requests) + len(self.byok.requests)


@pytest.fixture
def painters(monkeypatch) -> Painters:
    """Replaces the picture model: `ours` on our account, `byok` on the player's key."""
    painters = Painters(FakePictureModel(), FakePictureModel(byok=True, model="byok-image"))

    def build(*, rating, byok_provider, byok_key):
        if byok_key:
            painters.builds.append(("byok", rating))
            return painters.byok
        painters.builds.append(("ours", rating))
        return painters.ours

    monkeypatch.setattr(drawing, "build_picture_model", build)
    return painters


@dataclass
class Meter:
    """Records the credit meter's calls. Set `refuse` to an exception for `start` to raise."""

    started: list = field(default_factory=list)
    charged: list = field(default_factory=list)
    released: list = field(default_factory=list)
    refuse: BaseException | None = None
    payer: Payer = Payer.CREDITS


@pytest.fixture
def meter(monkeypatch) -> Meter:
    meter = Meter()

    async def start(user, *, story_id, image_id, first_picture=False):
        meter.started.append(image_id)
        if meter.refuse is not None:
            raise meter.refuse
        return billing.Ticket(meter.payer, hold=len(meter.started))

    def charge(ticket, *, calls, cost_usd, story_id, turn, image_id):
        meter.charged.append(
            {"hold": ticket.hold, "calls": calls, "cost": cost_usd, "turn": turn, "image": image_id}
        )
        return ticket.payer

    async def release(ticket):
        meter.released.append(ticket.hold)

    monkeypatch.setattr(billing, "start", start)
    monkeypatch.setattr(billing, "charge", charge)
    monkeypatch.setattr(billing, "release", release)
    return meter


@pytest.fixture(autouse=True)
def starter_credit_for_everyone(settings):
    """Tests that don't fake the meter draw on real credits, and the shared `make_user` makes
    unverified email accounts, which get no starter credit under the default policy (K1)."""
    settings.BILLING = {**settings.BILLING, "STARTER_POLICY": "all"}


@pytest.fixture(autouse=True)
def picture_files(settings, tmp_path):
    """A fresh local picture folder per test, and no URL carried over from another test."""
    settings.MEDIA_BUCKET = ""
    settings.PICTURE_ROOT = str(tmp_path / "pictures")
    storage._url_cache.clear()
    yield tmp_path / "pictures"
    storage._url_cache.clear()


def story_owner():
    """The adult player who owns a test story unless the test names another owner."""
    from accounts.models import User

    user, _ = User.objects.get_or_create(
        email="painter@example.com",
        defaults={"birth_date": ADULT_BIRTH_DATE, "display_name": "painter"},
    )
    return user


def make_story(**fields) -> Story:
    if "owner" not in fields:
        fields["owner"] = story_owner()
    defaults = {
        "title": "The Jade Sect",
        "premise": "A sect disciple with a forbidden technique.",
        "genre": "cultivation",
        "rating": "mature",
        "engine": Engine.GRAPH,
        "state": {"bible": {"era": "an ancient empire of sects", "tone": "grim and grand"}},
    }
    return Story.objects.create(**(defaults | fields))


def make_scene(story: Story, turn: int, **fields) -> Scene:
    defaults = {
        "kind": SceneKind.OPENING if turn == 1 else SceneKind.ACTION,
        "narration": f"Scene {turn}. The elder raises his sword.",
    }
    return Scene.objects.create(story=story, turn=turn, **(defaults | fields))
