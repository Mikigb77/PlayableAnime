FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /bin/

WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/srv/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
# Precompile our own code too, and collect the admin's CSS and JS for ServeStatic. The key only
# satisfies the settings check at build time; the real one comes from Secret Manager (T11).
RUN python -m compileall -q . -x '/\.venv/' \
    && DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput -v 0 \
    && useradd --system --uid 10001 --no-create-home lucid
USER lucid

# Cloud Run injects PORT; 8080 is the local default. Logs are JSON from Django's LOGGING, and the
# request line comes from our middleware, so uvicorn's own access log is off. Django has no
# lifespan handler. Migrations run separately before a deploy: `python manage.py migrate` with
# DATABASE_URL set to Neon's direct URL (B2).
CMD ["sh", "-c", "exec uvicorn lucid.asgi:application --host 0.0.0.0 --port ${PORT:-8080} --no-access-log --lifespan off"]
