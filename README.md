# PlayableAnime

> Working name **Lucid Saga**. Requirements for all work: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

An AI interactive-story app (working title): pick or write a premise, play through choices or
free-text actions, and an LLM keeps the story going forever while a memory engine keeps it
consistent. If a character dies, they stay dead.

| Folder | Stack |
| --- | --- |
| [`app/`](app/) | Flutter mobile app (iOS and Android, plus web for quick testing) |
| [`backend/`](backend/) | Python Django and Django Ninja story engine for Cloud Run, with Gemini on Vertex AI |
| [`docs/`](docs/) | [Requirements](docs/REQUIREMENTS.md) · [Plan](docs/PLAN.md) · [API](docs/API.md) · [Feature list](docs/FEATURES.md) · [Architecture](docs/ARCHITECTURE.md) · [Deploy](docs/DEPLOY.md) |

## Quick start

Backend. It uses an offline fake narrator unless configured otherwise, and stores stories in a
local Postgres (or a Neon branch, see [backend/README.md](backend/README.md#database-neon-postgres)):

```bash
docker run -d --name lucid-pg -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:18
docker exec lucid-pg createdb -U postgres lucid
cd backend
uv sync
uv run python manage.py migrate
DEBUG=1 uv run uvicorn lucid.asgi:application --reload --port 8080
```

App, in a second terminal:

```bash
cd app
flutter run
```

On an Android emulator, add `--dart-define=API_BASE_URL=http://10.0.2.2:8080`.

To get real stories, set `LLM_PROVIDER=vertex` in `backend/.env` (see
[backend/README.md](backend/README.md)), or paste your own Gemini API key under **Settings** in the
app.
