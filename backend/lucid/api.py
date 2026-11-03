"""The Ninja API root, mounted at /v1. Each app adds its router here (one line each)."""

from ninja import NinjaAPI

from lucid import errors
from stories.api import premises_router, stories_router

api = NinjaAPI(
    title="Lucid Saga API",
    version="1",
    description="The app to backend contract is docs/API.md.",
    docs_url="/docs",
    urls_namespace="v1",
)
errors.install(api)

api.add_router("/premises", premises_router)
api.add_router("/stories", stories_router)
