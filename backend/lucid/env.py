"""Typed settings from environment variables.

Precedence: environment variables, then `backend/.env`, then the repo-root `.env.local` that
`neon env pull` and `neon checkout` write. Django's `settings.py` reads this once at startup.
"""

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
_NEON_ENV_FILE = BACKEND_DIR.parent / ".env.local"


def split_csv(value: str) -> list[str]:
    """Splits a comma-separated env value, dropping blanks."""
    return [item.strip() for item in value.split(",") if item.strip()]


class Env(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_NEON_ENV_FILE, BACKEND_DIR / ".env"), extra="ignore"
    )

    debug: bool = False
    # Required outside DEBUG. Comes from Secret Manager on Cloud Run (T11).
    django_secret_key: str = ""
    # The pooled Neon URL for the service; the direct one for `migrate` (B2). Without it, the
    # local Docker Postgres from the README is used.
    database_url: str = "postgresql://postgres:postgres@localhost:5432/lucid"
    # Neon's direct (unpooled) URL. When set, `manage.py migrate --database direct` uses it.
    database_url_unpooled: str = ""
    # Comma-separated. Cloud Run only routes requests for the service's own hosts to it.
    allowed_hosts: str = "*"
    # Comma-separated origins for the Flutter web build, or "*".
    cors_origins: str = "*"
    csrf_trusted_origins: str = ""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Models (B6). "fake" runs a canned offline narrator, so nothing needs cloud credentials.
    llm_provider: Literal["vertex", "fake"] = "fake"
    gcp_project: str = "playable-anime"
    vertex_location: str = "global"
    narrator_model: str = "gemini-3.5-flash"

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value
