"""Builds the model client for one request: our Vertex AI account, a player's key, or the fake.

The player's key arrives in the `X-LLM-Provider` and `X-LLM-Api-Key` headers (S9). It is used
for that request only: wrapped so it never prints, never cached, never stored or logged (T6).
"""

from __future__ import annotations

from functools import lru_cache

from graph.llm.client import ModelClient
from graph.llm.config import ModelConfig, get_model_config
from graph.llm.errors import UnsupportedProvider
from graph.llm.fake import FakeBackend, offline_reply
from graph.llm.telemetry import CallRecorder
from graph.llm.types import Backend, Rating

BYOK_PROVIDERS = frozenset({"gemini"})


class ByokKey:
    """A player's own API key. Its repr is masked, and it refuses to be pickled or cached."""

    __slots__ = ("_secret", "provider")

    def __init__(self, provider: str, secret: str):
        self.provider = provider
        self._secret = secret

    def reveal(self) -> str:
        return self._secret

    def __repr__(self) -> str:
        return f"ByokKey(provider={self.provider!r}, key='***')"

    __str__ = __repr__

    def __reduce__(self) -> object:
        raise TypeError("A player's API key must not be pickled or stored")


def parse_byok(provider: str | None, key: str | None) -> ByokKey | None:
    """Reads the BYOK headers. No key means our own account; an unknown provider is an error."""
    key = (key or "").strip()
    if not key:
        return None
    name = (provider or "gemini").strip().lower()
    if name not in BYOK_PROVIDERS:
        raise UnsupportedProvider(f"Bring your own key isn't supported for {name!r} yet")
    return ByokKey(name, key)


def build_client(
    *,
    rating: Rating,
    byok: ByokKey | None = None,
    recorder: CallRecorder | None = None,
    config: ModelConfig | None = None,
    backend: Backend | None = None,
) -> ModelClient:
    """The client for one request. Pass `backend` to use a scripted fake in tests."""
    config = config or get_model_config()
    owns_backend = False
    if backend is None and byok is not None:
        from graph.llm.gemini import GeminiBackend  # heavy imports load on first use (B10)

        backend = GeminiBackend.with_api_key(byok.reveal())
        owns_backend = True
    elif backend is None and config.provider == "vertex":
        from graph.llm.gemini import vertex_backend

        backend = vertex_backend(config.project, config.location)
    elif backend is None:
        backend = _offline_backend()
    return ModelClient(
        backend,
        config,
        rating=rating,
        recorder=recorder,
        byok=byok is not None,
        owns_backend=owns_backend,
    )


@lru_cache
def _offline_backend() -> FakeBackend:
    return FakeBackend(default=offline_reply, keep_requests=False)
