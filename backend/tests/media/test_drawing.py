"""The picture model on the model layer: the `picture` node, reference images, the picture
safety settings, typed failures and the call records billing charges from (M5, M6, M8, T5)."""

import asyncio
from decimal import Decimal

import pytest

from graph.llm import Block, Fail, FakeBackend, ModelClient, ModelConfig, Node, Reply, TurnTelemetry
from media.drawing import (
    DrawBlocked,
    DrawFailed,
    DrawRateLimited,
    DrawRequest,
    GraphPictureModel,
    KeyCannotDraw,
    Reference,
    build_picture_model,
)
from tests.media.conftest import PNG

REQUEST = DrawRequest(
    kind="scene",
    system="house style",
    prompt="the duel",
    aspect_ratio="16:9",
    references=(Reference("Rosa", b"rosa-portrait"), Reference("Tonio", b"tonio-portrait")),
)


def _model(fake: FakeBackend, *, rating="mature", byok=False) -> GraphPictureModel:
    telemetry = TurnTelemetry()
    client = ModelClient(
        fake, ModelConfig(), rating=rating, recorder=telemetry, byok=byok, retry_delay_s=0
    )
    return GraphPictureModel(client, telemetry, "gemini-3.1-flash-lite-image")


def test_a_picture_is_drawn_by_the_picture_node_with_its_references():
    fake = FakeBackend().script(Node.PICTURE, Reply(images=(PNG,)))

    drawn = asyncio.run(_model(fake).draw(REQUEST))

    assert drawn.data == PNG
    assert drawn.mime_type == "image/png"
    assert drawn.model == "gemini-3.1-flash-lite-image"
    assert len(drawn.calls) == 1 and drawn.calls[0].images == 1
    # What billing charges from: the call's own estimate, a 1K picture plus the reference tokens.
    assert drawn.cost_usd == drawn.calls[0].cost_usd > Decimal("0.03")
    request = fake.calls(Node.PICTURE)[0]
    assert [image.data for image in request.prompt.images] == [b"rosa-portrait", b"tonio-portrait"]
    assert request.image.aspect_ratio == "16:9"
    assert request.prompt.system == "house style"


@pytest.mark.parametrize("rating", ["teen", "mature"])
def test_pictures_use_the_strict_picture_filters_in_every_rating(rating):
    """M6: a Mature story's pictures are filtered as tightly as a Teen's."""
    fake = FakeBackend().script(Node.PICTURE, Reply(images=(PNG,)))

    asyncio.run(_model(fake, rating=rating).draw(REQUEST))

    safety = fake.calls(Node.PICTURE)[0].safety
    assert safety["sexually_explicit"] == "block_low_and_above"
    assert safety["dangerous_content"] == "block_medium_and_above"


def test_a_blocked_picture_says_what_blocked_it():
    fake = FakeBackend().script(Node.PICTURE, Block(categories=("sexually_explicit",)))

    with pytest.raises(DrawBlocked) as blocked:
        asyncio.run(_model(fake).draw(REQUEST))

    assert blocked.value.categories == ("sexually_explicit",)


def test_a_picture_that_fails_twice_fails():
    fake = FakeBackend().script(Node.PICTURE, Fail(), Fail())

    with pytest.raises(DrawFailed):
        asyncio.run(_model(fake).draw(REQUEST))


def test_our_picture_quota_running_out_says_so():
    """A 429 on our account may pass with a wait, which the starter covers take."""
    fake = FakeBackend().script(Node.PICTURE, *(Fail(status=429) for _ in range(3)))

    with pytest.raises(DrawRateLimited):
        asyncio.run(_model(fake).draw(REQUEST))


@pytest.mark.parametrize(
    "steps", [(Fail(status=503), Fail(status=503)), (Fail(status=429), Fail(status=500))]
)
def test_other_failures_are_not_a_quota_that_ran_out(steps):
    fake = FakeBackend().script(Node.PICTURE, *steps)

    with pytest.raises(DrawFailed) as failed:
        asyncio.run(_model(fake).draw(REQUEST))

    assert not isinstance(failed.value, DrawRateLimited)


@pytest.mark.parametrize(
    "step", [Fail(kind="auth", status=403), Fail(status=429), Fail(kind="invalid", status=404)]
)
def test_a_players_key_that_cant_draw_falls_back(step):
    """M7: a rejected key, a free-tier key with no picture quota, or a model the key can't use
    falls back to credits."""
    fake = FakeBackend().script(Node.PICTURE, step, step)

    with pytest.raises(KeyCannotDraw):
        asyncio.run(_model(fake, byok=True).draw(REQUEST))


@pytest.mark.parametrize("step", [Fail(status=503), Fail(status=500)])
def test_a_players_key_that_hits_an_outage_doesnt_spend_their_credits(step):
    """A server error isn't the key's fault: the picture is skipped, not charged to credits."""
    fake = FakeBackend().script(Node.PICTURE, step, step)

    with pytest.raises(DrawFailed):
        asyncio.run(_model(fake, byok=True).draw(REQUEST))


def test_the_offline_model_draws_a_placeholder(settings):
    """`LLM_PROVIDER=fake` (the default) draws without any cloud access."""
    model = build_picture_model(rating="teen", byok_provider=None, byok_key=None)

    drawn = asyncio.run(model.draw(REQUEST))

    assert drawn.data.startswith(b"\x89PNG")
    assert model.byok is False
    assert model.model == ModelConfig().node(Node.PICTURE).model


def test_requests_never_print_their_prompt():
    assert "the duel" not in repr(REQUEST)
    assert "rosa-portrait" not in repr(REQUEST.references[0])
