from functools import lru_cache
from typing import TYPE_CHECKING

from legacy.config import Settings
from legacy.llm.base import LLMProvider
from legacy.llm.fake import FakeNarratorProvider

if TYPE_CHECKING:
    from legacy.llm.gemini import GeminiProvider

# Providers users can bring their own key for. Others (OpenAI, Anthropic, ...) come later.
BYOK_PROVIDERS = {"gemini"}


class UnsupportedProviderError(ValueError):
    pass


def build_provider(
    settings: Settings, *, byok_provider: str | None = None, byok_key: str | None = None
) -> LLMProvider:
    """Picks the model backend for one request.

    A user-supplied key wins over the server default. The key is used for this request only and
    must never be stored or logged.
    """
    if byok_key:
        provider = (byok_provider or "gemini").lower()
        if provider not in BYOK_PROVIDERS:
            raise UnsupportedProviderError(f"Bring-your-own-key is not supported for '{provider}'")
        # Imported only when needed: the SDK is slow to import (B10).
        from legacy.llm.gemini import GeminiProvider

        return GeminiProvider.with_api_key(byok_key, settings.narrator_model)
    if settings.llm_provider == "vertex":
        return _vertex_provider(
            settings.gcp_project, settings.vertex_location, settings.narrator_model
        )
    return FakeNarratorProvider()


@lru_cache
def _vertex_provider(project: str, location: str, model: str) -> "GeminiProvider":
    from legacy.llm.gemini import GeminiProvider

    return GeminiProvider.vertex(project=project, location=location, model=model)
