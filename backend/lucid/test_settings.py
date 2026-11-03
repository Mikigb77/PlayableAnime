"""Settings for pytest. Tests never use DATABASE_URL, which may point at a Neon branch through
.env.local: they use TEST_DATABASE_URL, by default the local Docker Postgres from the README.
pytest-django creates and drops its own `test_*` database there."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")

from lucid.settings import *  # noqa: E402, F403
from lucid.settings import _database  # noqa: E402

DATABASES = {
    "default": _database(
        os.environ.get(
            "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
        )
    )
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
LLM_PROVIDER = "fake"
# The admin's assets straight from the apps, so tests don't need `collectstatic`.
SERVESTATIC_USE_FINDERS = True
