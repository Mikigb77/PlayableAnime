from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or backend/.env locally)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "fake" runs a canned offline narrator so the API works without any cloud credentials.
    llm_provider: Literal["vertex", "fake"] = "fake"
    gcp_project: str = "playable-anime"
    vertex_location: str = "global"
    narrator_model: str = "gemini-3.5-flash"
    # Neon Postgres connection string. Unused until the persistence layer lands.
    database_url: str | None = None
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
