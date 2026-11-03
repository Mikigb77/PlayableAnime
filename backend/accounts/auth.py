"""The Ninja auth that guards every endpoint except `/health` and `/v1/auth/*` (T8).

It reads `Authorization: Bearer <access_token>`, checks the signature and age without touching the
database, then loads the token's session with its user in one query, so a revoked session or a
disabled or deleted account is refused at once. `request.auth` and `request.user` become the
signed-in `accounts.User`, and the user id goes on every later log line (T4).
"""

from django.http import HttpRequest
from ninja.security import HttpBearer

from accounts import tokens
from accounts.models import AuthSession, User
from lucid import logs


class BearerAuth(HttpBearer):
    # Tells Ninja to await `__call__` instead of running it in a thread.
    is_async = True

    async def __call__(self, request: HttpRequest) -> User | None:  # type: ignore[override]
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None
        return await self.authenticate(request, token.strip())

    async def authenticate(self, request: HttpRequest, token: str) -> User | None:  # type: ignore[override]
        ids = tokens.read_access_token(token)
        if ids is None:
            return None
        user_id, session_id = ids
        session = (
            await AuthSession.objects.select_related("user")
            .filter(pk=session_id, user_id=user_id, revoked_at__isnull=True)
            .afirst()
        )
        if session is None or not session.user.is_active:
            return None
        user = session.user
        request.user = user
        logs.bind(user_id=str(user.pk))
        return user
