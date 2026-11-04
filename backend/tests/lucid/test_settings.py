import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

BACKEND = Path(__file__).resolve().parents[2]


def _python(code: str, **env: str) -> subprocess.CompletedProcess:
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "DEBUG"))}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=clean | env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_database_is_set_up_for_neons_pgbouncer():
    """B2: transaction pooling drops server-side cursors and persistent connections."""
    database = settings.DATABASES["default"]

    assert database["ENGINE"] == "django.db.backends.postgresql"
    assert database["CONN_MAX_AGE"] == 0
    assert database["DISABLE_SERVER_SIDE_CURSORS"] is True


def test_the_user_model_is_the_custom_one():
    assert settings.AUTH_USER_MODEL == "accounts.User"


def test_a_secret_key_is_required_outside_debug():
    result = _python("import lucid.settings", DJANGO_SECRET_KEY="", DEBUG="0")

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY is required" in result.stderr


def test_a_database_url_is_required_outside_debug():
    """/health never touches the database, so a missing URL must fail the start, not hide."""
    result = _python("import lucid.settings", DJANGO_SECRET_KEY="k", DATABASE_URL="", DEBUG="0")

    assert result.returncode != 0
    assert "DATABASE_URL is required" in result.stderr


@pytest.mark.parametrize("cloud_run", [{"K_SERVICE": "api"}, {"CLOUD_RUN_JOB": "migrate"}])
def test_the_published_app_runs_only_on_vertex_ai(cloud_run):
    """B6: on Cloud Run the offline model never answers a player. A deploy that lost
    LLM_PROVIDER fails to start, while the image itself still runs anywhere else (CI's smoke
    test runs it with the offline model)."""
    env = {"DJANGO_SECRET_KEY": "k", "DATABASE_URL": "postgresql://x/y", "DEBUG": "0"}

    offline = _python("import lucid.settings", LLM_PROVIDER="fake", **env, **cloud_run)
    assert offline.returncode != 0
    assert "LLM_PROVIDER must be vertex on Cloud Run" in offline.stderr

    vertex = _python(
        "import lucid.settings", LLM_PROVIDER="vertex", MEDIA_BUCKET="b", **env, **cloud_run
    )
    assert vertex.returncode == 0, vertex.stderr
    elsewhere = _python("import lucid.settings", LLM_PROVIDER="fake", **env)
    assert elsewhere.returncode == 0, elsewhere.stderr


def test_the_asgi_app_loads_without_the_model_sdk():
    """B10: heavy imports stay out of module load, so cold starts stay fast (T3). The URLconf
    is imported too, as the first request would, so every view module is checked."""
    result = _python(
        "import sys, lucid.asgi, lucid.urls; "
        "heavy = [m for m in ('google.genai', 'google.auth', 'langchain_core', 'langgraph') "
        "if m in sys.modules]; "
        "print(heavy); sys.exit(1 if heavy else 0)",
        DJANGO_SECRET_KEY="test",
        DATABASE_URL="postgresql://nowhere/none",
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.django_db
def test_the_models_and_migrations_agree():
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)


def test_the_system_checks_pass():
    call_command("check", fail_level="WARNING")
