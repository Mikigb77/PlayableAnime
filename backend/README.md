# Story API

FastAPI service that runs the story engine. Python 3.13, managed with [uv](https://docs.astral.sh/uv/).

## Run locally

```bash
uv sync
cp .env.example .env    # optional
uv run uvicorn app.main:app --reload --port 8080
```

Open http://localhost:8080/docs for the interactive API.

By default `LLM_PROVIDER=fake` returns a canned scene, so everything works offline. For real
stories, either:

- send your own Gemini key in the `X-LLM-Api-Key` header (the app's Settings screen does this), or
- set `LLM_PROVIDER=vertex` and give Application Default Credentials access to the
  `playable-anime` project: `gcloud auth application-default login`, signing in as
  tech.garbar@gmail.com. Note that ADC is machine-wide, so this replaces whatever ADC you use for
  other projects.

## Test and lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

## API

| Method | Path | |
| --- | --- | --- |
| GET | `/health` | Liveness |
| GET | `/v1/premises` | Starter premises |
| POST | `/v1/stories` | `{premise, title?}` → story with its opening scene |
| GET | `/v1/stories` | Story summaries |
| GET | `/v1/stories/{id}` | Full story |
| POST | `/v1/stories/{id}/turns` | `{choice_id}` or `{action}` → next scene and state |
| GET | `/v1/stories/{id}/memory` | World state |

Optional headers: `X-LLM-Provider: gemini` and `X-LLM-Api-Key: <key>` (bring your own key).

## Layout

```
app/
  main.py            FastAPI app and routers
  config.py          Settings from env / .env
  domain.py          Story, Scene, WorldState, Character, Faction, Fact
  premises.py        Starter premises
  storage.py         StoryRepository protocol + in-memory implementation
  api/               HTTP routes and dependencies
  engine/
    narrator.py      Prompt building and one story turn
    memory.py        Applies model-proposed state changes and enforces continuity
    schemas.py       Structured output the model must return
  llm/
    base.py          LLMProvider protocol
    gemini.py        Gemini via Vertex AI or an API key
    fake.py          Offline narrator for dev and tests
    factory.py       Picks a provider per request (BYOK first)
```

## Deploy to Cloud Run

Not deployed yet. Add auth first: an open endpoint lets anyone spend the Vertex budget. When ready:

```bash
gcloud run deploy playable-anime-api --source . --configuration=playable-anime --region=europe-southwest1 --service-account=playable-anime-api@playable-anime.iam.gserviceaccount.com --set-env-vars=LLM_PROVIDER=vertex
```
