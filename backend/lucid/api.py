"""The Ninja API root, mounted at /v1. Each app adds its router here (one line each).

Every endpoint needs a signed-in user (`Authorization: Bearer <access_token>`, T8): the auth is set
once here, so a new router is guarded with no code of its own, and in a view `request.auth` is the
`accounts.User`. Only the sign-in endpoints under `/v1/auth/` opt out. `/health` is outside Ninja.
"""

from ninja import NinjaAPI

from accounts.api import auth_router, me_router
from accounts.auth import BearerAuth
from lucid import errors
from stories.api import premises_router, stories_router

api = NinjaAPI(
    title="Lucid Saga API",
    version="1",
    description="The app to backend contract is docs/API.md.",
    docs_url="/docs",
    urls_namespace="v1",
    auth=BearerAuth(),
)
errors.install(api)

api.add_router("/auth", auth_router)
api.add_router("/me", me_router)
api.add_router("/premises", premises_router)
api.add_router("/stories", stories_router)
