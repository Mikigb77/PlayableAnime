"""Typed settings from environment variables.

Precedence: environment variables, then `backend/.env`, then the repo-root `.env.local` that
`neon env pull` and `neon checkout` write. Django's `settings.py` reads this once at startup.
"""

from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
LOCAL_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/lucid"
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
    # The pooled Neon URL for the service; the direct one for `migrate` (B2). Required outside
    # DEBUG; with DEBUG on it defaults to the local Docker Postgres from the README.
    database_url: str = ""
    # Neon's direct (unpooled) URL. When set, `manage.py migrate --database direct` uses it.
    database_url_unpooled: str = ""
    # Comma-separated. Cloud Run only routes requests for the service's own hosts to it.
    allowed_hosts: str = "*"
    # Comma-separated origins for the Flutter web build, or "*".
    cors_origins: str = "*"
    csrf_trusted_origins: str = ""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Models (B6). "fake" is an offline model, so nothing needs cloud credentials. Vertex AI's
    # location and the per-node models are read by `graph.llm.config` from the same files.
    llm_provider: Literal["vertex", "fake"] = "fake"
    gcp_project: str = "playable-anime"

    # Sign-in (T8, K7, F8). Comma-separated OAuth client ids (web, Android, iOS) from the
    # `playable-anime` project: a Google ID token must name one of them as its audience. Empty
    # turns Google sign-in off. Client ids aren't secrets.
    google_oauth_client_ids: str = ""
    # Comma-separated. A verified Google sign-in with one of these emails gets the owner role.
    owner_emails: str = "mikigb77@gmail.com"
    # The youngest age that can sign up. Under 17 gets Teen only (F8).
    min_signup_age: int = 13
    # How many proxies append to X-Forwarded-For before the request reaches us: 1 on Cloud Run
    # (Google's front end). Raise it if a load balancer goes in front.
    trusted_proxy_hops: int = 1
    # Pictures (M4). With a bucket, files go to that private Cloud Storage bucket and the app gets
    # signed URLs; without one, to `picture_root` on local disk (development and tests).
    media_bucket: str = ""
    picture_root: str = ""
    # How long a picture's signed URL works. The app asks for a fresh one after that.
    picture_url_ttl_s: int = Field(default=3600, ge=60, le=7 * 24 * 3600)

    # Credits, quotas and rate limits (K1, K2, T9). The rest of the billing settings are in
    # settings.py's BILLING.
    # K1's starter credit, in cents ($0.50).
    starter_credit_cents: Decimal = Field(default=Decimal(50), ge=0)
    # "verified": only a verified account gets it (a Google account at once, an email account
    # when its address is verified), so throwaway emails can't farm it. "all": every account.
    starter_credit_policy: Literal["verified", "all"] = "verified"
    # The margin on our model cost (K2): 0.5 charges the cost plus half.
    billing_margin: Decimal = Field(default=Decimal("0.5"), ge=0)
    # T9: turns per user per minute, BYOK included (K6), and turns on our key per user per UTC
    # day. A quota of 0 stops every turn on our key.
    turn_rate_per_minute: int = Field(default=10, ge=1)
    daily_turn_quota: int = Field(default=300, ge=0)

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value
