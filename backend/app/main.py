from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import premises, stories
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PlayableAnime API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(premises.router)
    app.include_router(stories.router)

    # Not /healthz: Cloud Run reserves some paths ending in "z".
    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
