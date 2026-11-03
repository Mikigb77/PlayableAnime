from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import premises, stories
from app.config import Settings, get_settings
from app.db import create_pool
from app.storage import InMemoryStoryRepository, PostgresStoryRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        if not settings.database_url:
            app.state.repository = InMemoryStoryRepository()
            yield
            return
        pool = await create_pool(settings.database_url)
        app.state.repository = PostgresStoryRepository(pool)
        try:
            yield
        finally:
            await pool.close()

    app = FastAPI(title="PlayableAnime API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(premises.router)
    app.include_router(stories.router)

    # Not /healthz: Cloud Run reserves some paths ending in "z". Deliberately does not query
    # the database, so probes don't keep the Neon compute awake.
    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "storage": "postgres" if settings.database_url else "memory"}

    return app


app = create_app()
