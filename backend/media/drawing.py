"""The picture model behind a small interface (M8), so tests use a fake and nothing else here
knows about Gemini.

`GraphPictureModel` draws through the model layer (`graph.llm`): the `picture` node's model from
config (`PICTURE_MODEL`, B6), Vertex AI with Application Default Credentials or the player's own
key (S9), the picture safety settings (M6, F5), one retry and the per-call telemetry (T5).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True, repr=False)
class Reference:
    """An image sent with the prompt, such as a known character's portrait (M5)."""

    name: str
    data: bytes
    mime_type: str = "image/png"

    def __repr__(self) -> str:
        return f"Reference(name={self.name!r}, bytes={len(self.data)})"


@dataclass(frozen=True, repr=False)
class DrawRequest:
    kind: str
    system: str
    prompt: str
    aspect_ratio: str
    references: tuple[Reference, ...] = ()

    def __repr__(self) -> str:
        chars = len(self.system) + len(self.prompt)
        return f"DrawRequest(kind={self.kind!r}, chars={chars}, references={len(self.references)})"


@dataclass(frozen=True, repr=False)
class Drawn:
    data: bytes
    mime_type: str
    model: str
    cost_usd: Decimal
    # The model layer's call records (`graph.llm.CallRecord`), which billing charges from (T5).
    calls: tuple[Any, ...] = ()

    def __repr__(self) -> str:
        return f"Drawn(model={self.model!r}, bytes={len(self.data)}, cost_usd={self.cost_usd})"


class DrawError(Exception):
    reason = "failed"


class DrawFailed(DrawError):
    """The model failed twice, timed out or answered without a picture."""


class DrawBlocked(DrawError):
    """A safety filter stopped the prompt or the picture (M6)."""

    reason = "blocked"

    def __init__(self, categories: tuple[str, ...] = ()) -> None:
        super().__init__("blocked")
        self.categories = categories


class KeyCannotDraw(DrawError):
    """The player's own key can't make pictures: rejected, or on the free tier, which has no
    image models (M7). The picture falls back to credits."""


class PictureModel(Protocol):
    model: str
    byok: bool

    async def draw(self, request: DrawRequest) -> Drawn: ...

    async def aclose(self) -> None: ...


class GraphPictureModel:
    """`client` is a `graph.llm.ModelClient` built with `telemetry` as its recorder."""

    def __init__(self, client, telemetry, model: str) -> None:
        self._client = client
        self.model = model
        self.byok = client.byok
        self.telemetry = telemetry

    async def draw(self, request: DrawRequest) -> Drawn:
        from graph.llm import ImagePart, ImageSpec, LLMBlocked, LLMError, Node, Prompt

        prompt = Prompt.build(
            request.system,
            request.prompt,
            images=[ImagePart(ref.data, ref.mime_type) for ref in request.references],
        )
        before = len(self.telemetry.calls)
        try:
            picture = await self._client.image(
                Node.PICTURE, prompt, spec=ImageSpec(aspect_ratio=request.aspect_ratio)
            )
        except LLMBlocked as exc:
            raise DrawBlocked(tuple(exc.categories)) from exc
        except LLMError as exc:
            if self.byok:
                raise KeyCannotDraw(exc.code) from exc
            raise DrawFailed(exc.code) from exc
        calls = self.telemetry.calls[before:]
        cost = sum((call.cost_usd for call in calls), Decimal(0))
        model = calls[-1].model if calls else self.model
        return Drawn(picture.data, picture.mime_type, model, cost, tuple(calls))

    async def aclose(self) -> None:
        await self._client.aclose()


def build_picture_model(*, rating: str, byok_provider: str | None, byok_key: str | None):
    """The picture model for one request: the player's own key when they sent one (S9), else
    our account. Raises `graph.llm.UnsupportedProvider` for an unknown BYOK provider."""
    from graph.llm import Node, TurnTelemetry, build_client, get_model_config, parse_byok

    config = get_model_config()
    byok = parse_byok(byok_provider, byok_key)
    telemetry = TurnTelemetry()
    client = build_client(rating=rating, byok=byok, config=config, recorder=telemetry)
    return GraphPictureModel(client, telemetry, config.node(Node.PICTURE).model)
