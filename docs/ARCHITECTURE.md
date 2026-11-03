# Architecture

```
┌──────────────┐  HTTPS/JSON   ┌───────────────────────────┐   ┌──────────────────────────┐
│ Flutter app  │ ────────────▶ │ Story API (FastAPI)       │──▶│ Vertex AI: Gemini        │
│ app/         │  X-LLM-* hdrs │ Cloud Run, backend/       │   │ (or the user's own key)  │
│ iOS, Android │ ◀──────────── │ engine: narrator + memory │   └──────────────────────────┘
└──────────────┘               │                           │   ┌──────────────────────────┐
                               │                           │──▶│ Neon Postgres (pending)  │
                               │                           │   └──────────────────────────┘
                               │                           │   ┌──────────────────────────┐
                               │                           │──▶│ Cloud Storage: images    │
                               └───────────────────────────┘   │ (later)                  │
                                                               └──────────────────────────┘
```

## Repo layout

| Path | What |
| --- | --- |
| `app/` | Flutter client: Riverpod, go_router, http, flutter_secure_storage |
| `backend/` | Python 3.13 + FastAPI, managed with uv, deployed to Cloud Run |
| `docs/` | Product and architecture notes |
| `.github/workflows/ci.yml` | Lint and test for both halves on every PR |

## Story engine

One turn (`backend/app/engine/narrator.py`):

1. **Build the prompt** from the premise, rolling summary, continuity rules, goals, known characters
   and factions, the last 3 scenes and the player's action.
2. **Call Gemini** with a JSON response schema (`NarratorOutput`): narration, 3 choices, an image
   prompt and a `state_update` describing what changed.
3. **Apply the update** (`backend/app/engine/memory.py`). The engine owns the invariants: a dead
   character can't come back, a destroyed faction can't be restored, affinity is clamped to ±100,
   and nameless "new" characters are ignored.
4. **Save** the story and return the new scene and state.

How the reference app's memory layers map onto ours:

| Layer | Here |
| --- | --- |
| Long-term memory | `facts` (importance 1–5) + `summary` |
| Short-term memory | the last `RECENT_SCENES` scenes in the prompt |
| Relationships | `Character.affinity`, `Faction.stance` |
| Current goals | `goals` |

Facts with importance ≥ 4 and all deaths and destructions are restated as **continuity rules** on
every turn.

**Still to build for endless stories:** chapter summaries every N turns, and retrieval of relevant
facts and scenes with pgvector on Neon, so the prompt stays small however long the story runs.

## Bring your own key

- The app keeps the key in `flutter_secure_storage` and sends it per request as `X-LLM-Provider` and
  `X-LLM-Api-Key`.
- The backend uses the key for that request only. It must never be persisted or logged.
- Only `gemini` is supported for now (same SDK, `genai.Client(api_key=...)`).

## Images

Nothing is generated yet; `Scene.image_prompt` is already produced every turn. Options:

| Option | Cost | Notes |
| --- | --- | --- |
| Vertex AI Gemini image models (`gemini-3.1-flash-image`, `gemini-3-pro-image`) | Paid per image | Already enabled in our project. Best prompt-following and image editing, which helps keep characters consistent. |
| Gemini API free tier, using the player's own key | Free, small daily quota | Reportedly tightened in Dec 2025. Fits BYOK naturally. |
| Cloudflare Workers AI (FLUX.1 schnell) | 10k free "neurons"/day, roughly 20–50 images | Needs a separate Cloudflare account. |
| Pollinations.ai | Free, no key, rate-limited | Prototyping only. Check the terms for commercial use. |
| Self-hosted FLUX.1-schnell or SDXL on a Cloud Run GPU | Pay per second, scales to zero | Most control; cold starts. |

Suggested plan: start with the Vertex Gemini image model. Generate **one portrait per character**
and only the occasional key scene, store them in Cloud Storage and reuse them. Players who bring
their own key can use their own free quota.

## Google Cloud

| Item | Value |
| --- | --- |
| Project | `playable-anime` (number 528988811295), owned by tech.garbar@gmail.com, billing on |
| gcloud configuration | `playable-anime` (not the active one; use `--configuration=playable-anime`) |
| Region | `europe-southwest1` (Madrid) for Cloud Run; Vertex AI on the `global` endpoint |
| APIs enabled | Cloud Run, Artifact Registry, Cloud Build, Secret Manager, Vertex AI, IAM |
| Runtime service account | `playable-anime-api@playable-anime.iam.gserviceaccount.com` with `aiplatform.user`, `secretmanager.secretAccessor`, `logging.logWriter` |
| Default narrator model | `gemini-3.5-flash` (checked working on 2026-11-03) |

Deploying is described in [backend/README.md](../backend/README.md#deploy-to-cloud-run).
**Don't deploy publicly before auth exists:** an open endpoint lets anyone spend our Vertex budget.

## Neon Postgres (pending)

- Store the pooled connection string in Secret Manager as `database-url` and mount it as
  `DATABASE_URL` on Cloud Run.
- Swap `InMemoryStoryRepository` (`backend/app/storage.py`) for a Postgres repository behind the
  same `StoryRepository` protocol.
- Enable `pgvector` for memory retrieval.
- The schema will be designed in a follow-up.
