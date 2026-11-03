from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings
from app.engine.narrator import Narrator
from app.llm.factory import UnsupportedProviderError, build_provider
from app.storage import InMemoryStoryRepository, StoryRepository

_repository = InMemoryStoryRepository()


def get_repository() -> StoryRepository:
    return _repository


def get_narrator(
    settings: Annotated[Settings, Depends(get_settings)],
    x_llm_provider: Annotated[str | None, Header()] = None,
    x_llm_api_key: Annotated[str | None, Header()] = None,
) -> Narrator:
    try:
        llm = build_provider(settings, byok_provider=x_llm_provider, byok_key=x_llm_api_key)
    except UnsupportedProviderError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return Narrator(llm)
