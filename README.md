# PlayableAnime

An AI interactive-story app (working title): pick or write a premise, play through choices or
free-text actions, and an LLM keeps the story going forever while a memory engine keeps it
consistent. If a character dies, they stay dead.

| Folder | Stack |
| --- | --- |
| [`app/`](app/) | Flutter mobile app (iOS and Android, plus web for quick testing) |
| [`backend/`](backend/) | Python FastAPI story engine for Cloud Run, with Gemini on Vertex AI |
| [`docs/`](docs/) | [Feature list](docs/FEATURES.md) · [Architecture](docs/ARCHITECTURE.md) |

## Quick start

Backend (it uses an offline fake narrator unless configured otherwise):

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8080
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
