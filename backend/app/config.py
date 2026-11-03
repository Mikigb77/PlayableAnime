from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# `neon deploy`, `neon checkout` and `neon env pull` write the linked branch's variables here.
_NEON_ENV_FILE = Path(__file__).resolve().parents[2] / ".env.local"


class Settings(BaseSettings):
    """Runtime configuration.

    Precedence: environment variables, then backend/.env, then the repo-root .env.local.
    """

    model_config = SettingsConfigDict(env_file=(_NEON_ENV_FILE, ".env"), extra="ignore")

    # "fake" runs a canned offline narrator so the API works without any cloud credentials.
    llm_provider: Literal["vertex", "fake"] = "fake"
    gcp_project: str = "playable-anime"
    vertex_location: str = "global"
    narrator_model: str = "gemini-3.5-flash"
    # Neon Postgres: the pooled URL serves the app, the direct one runs migrations.
    # Without DATABASE_URL, stories are kept in memory.
    database_url: str | None = None
    database_url_unpooled: str | None = None
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
