"""Explicit caches for the start of a prompt that stays the same from turn to turn (T5, K2).

Gemini bills prompt tokens it reads from a cache at a tenth of the input price. Its implicit
caching never hit for us: `cached_tokens` was 0 on every call on 2026-11-04 and 05, although the
narrator's first 6K or so tokens (the system text, the style, the content rules and the world)
were the same on every turn of a story. So that start, `Prompt.stable_chars`, goes in an explicit
cache on Vertex AI:

- The first call with a new start is sent whole, and the cache is made in the background, so no
  player waits for it. The calls after it send only the rest, and name the cache.
- A use that finds less than `REFRESH_BELOW_S` left pushes the expiry back to `TTL_S`, in the
  background. A cache so lives about `TTL_S` past its story's last turn: storage costs $1 per
  million tokens an hour on Flash, a few hundredths of a cent a turn, against nearly a cent saved
  on each narrator call.
- A start Vertex AI finds too small to cache is remembered for its model, so no start that small
  is tried again, and any other failure waits `RETRY_AFTER_S` before the same start is tried
  again. Every call works without a cache; a cache only makes it cheaper.

Caches live in this process's memory. Another instance makes its own, which costs only storage.
This module imports nothing from Google: the backend hands it the calls that make and extend a
cache.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from graph.llm.types import ProviderError

logger = logging.getLogger("graph.llm")

TTL_S = 15 * 60
# A use with less than this left extends the cache, so it is extended at most every 5 minutes.
REFRESH_BELOW_S = 10 * 60
# A cache this close to expiring is no longer named: a call may take a minute.
USE_MARGIN_S = 90
RETRY_AFTER_S = 15 * 60
# How long a cache may take to make before it counts as failed (its task may have died with
# its event loop).
CREATE_TIMEOUT_S = 60
# A start under about 1,000 tokens is under every Gemini model's minimum, so it isn't tried.
MIN_CHARS = 4_000


@dataclass(frozen=True)
class Made:
    """A cache Vertex AI made: its name, the seconds it has left, and its size in tokens."""

    name: str
    ttl_s: float
    tokens: int = 0


# (model, system, stable start, ttl) -> the cache made.
CreateCache = Callable[[str, str, str, int], Awaitable[Made]]
# (model, cache name, ttl) -> the seconds it has left.
ExtendCache = Callable[[str, str, int], Awaitable[float]]


@dataclass
class _Entry:
    model: str
    name: str | None  # None while it is being made, or after it failed
    until: float  # when it expires, or when to try again
    refreshing: bool = False


class PromptCache:
    """The explicit caches this process made, by model, system text and stable start."""

    def __init__(
        self,
        create: CreateCache,
        extend: ExtendCache,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._create = create
        self._extend = extend
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        # The largest start, in characters, that Vertex AI found too small, per model.
        self._too_small: dict[str, int] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def use(self, model: str, system: str, stable: str) -> str | None:
        """The cache to name for this start, if one is ready. Otherwise starts making one in
        the background, unless one is being made or this start can't be cached."""
        size = len(system) + len(stable)
        if size < MIN_CHARS or size <= self._too_small.get(model, 0):
            return None
        now = self._clock()
        key = cache_key(model, system, stable)
        entry = self._entries.get(key)
        if entry is not None and entry.name is not None and entry.until - now > USE_MARGIN_S:
            if entry.until - now < REFRESH_BELOW_S and not entry.refreshing:
                entry.refreshing = True
                self._spawn(self._refresh(key, entry))
            return entry.name
        if entry is not None and entry.name is None and entry.until > now:
            return None  # being made, or failed a short while ago
        self._prune(now)
        self._entries[key] = _Entry(model, None, now + CREATE_TIMEOUT_S)
        self._spawn(self.make(model, system, stable))
        return None

    def forget(self, name: str) -> None:
        """Drops a cache Vertex AI no longer takes. The next call with its start makes another."""
        for key, entry in list(self._entries.items()):
            if entry.name == name:
                del self._entries[key]

    async def make(self, model: str, system: str, stable: str) -> Made | None:
        """Makes the cache for this start now, and remembers it; None if Vertex AI refused."""
        key = cache_key(model, system, stable)
        size = len(system) + len(stable)
        started = self._clock()
        self._entries[key] = _Entry(model, None, started + CREATE_TIMEOUT_S)
        try:
            made = await self._create(model, system, stable, TTL_S)
        except ProviderError as error:
            reason = "cache_too_small" if too_small(error) else "cache_failed"
            if reason == "cache_too_small":
                self._too_small[model] = max(self._too_small.get(model, 0), size)
            self._entries[key] = _Entry(model, None, self._clock() + RETRY_AFTER_S)
            logger.warning(
                "Couldn't cache a prompt's start",
                extra={
                    "llm": {
                        "model": model,
                        "reason": reason,
                        "chars": size,
                        "detail": error.detail[:300],
                    }
                },
            )
            return None
        self._entries[key] = _Entry(model, made.name, self._clock() + made.ttl_s)
        logger.info(
            "Cached a prompt's start",
            extra={
                "llm": {
                    "model": model,
                    "reason": "cache_made",
                    "chars": size,
                    "tokens": made.tokens,
                    "ttl_s": round(made.ttl_s),
                    "seconds": round(self._clock() - started, 2),
                }
            },
        )
        return made

    async def _refresh(self, key: str, entry: _Entry) -> None:
        name = entry.name
        try:
            ttl_s = await self._extend(entry.model, name or "", TTL_S)
        except ProviderError as error:
            # A passing failure leaves the cache to the next use, which tries again. Gone or
            # refused: the next call with this start makes a new one.
            if error.kind != "transient" and self._entries.get(key) is entry:
                del self._entries[key]
            logger.warning(
                "Couldn't extend a prompt cache",
                extra={
                    "llm": {"model": entry.model, "reason": "cache_failed", "detail": error.detail}
                },
            )
            return
        finally:
            entry.refreshing = False
        if self._entries.get(key) is entry:
            entry.until = self._clock() + ttl_s

    def _spawn(self, work: Awaitable[object]) -> None:
        async def run() -> None:
            try:
                await work
            except Exception:  # a cache is only ever a saving, never a reason to fail
                logger.exception("A prompt cache task failed")

        task = asyncio.get_running_loop().create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _prune(self, now: float) -> None:
        for key in [key for key, entry in self._entries.items() if entry.until <= now]:
            del self._entries[key]


def cache_key(model: str, system: str, stable: str) -> str:
    return hashlib.sha256(f"{model}\0{system}\0{stable}".encode()).hexdigest()


def too_small(error: ProviderError) -> bool:
    """Vertex AI's 400 for a cache under its model's minimum ("The minimum token count to start
    caching is 4096")."""
    detail = error.detail.lower()
    return error.status == 400 and "minimum" in detail and "token" in detail
