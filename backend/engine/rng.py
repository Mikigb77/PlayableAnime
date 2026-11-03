"""Seeded random numbers for every roll (A3).

Every draw comes from SHA-256 over a seed string and a counter, so a seed gives the same numbers on
any machine and any Python version, and a seed recorded on a scene replays its roll exactly. Seeds
are readable paths such as `story=s1/timeline=main/turn=12/resolve/step=0`.

The turn graph makes one `SeededRng.for_turn(...)` per turn and passes it to every pipeline seam.
Each seam derives its own child streams with stable labels (`rng.child("resolve", "step", 0)`), so
adding a roll in one place never shifts the numbers anywhere else. Retrying a failed turn uses the
same turn number and so the same seeds: a retry never rerolls.
"""

import hashlib
import math
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")

_U64 = 2**64
_FLOAT_BITS = 53


def _escape(label: object) -> str:
    return str(label).replace("%", "%25").replace("/", "%2F")


class SeededRng:
    """A deterministic random stream for one seed."""

    __slots__ = ("_counter", "seed")

    def __init__(self, seed: str) -> None:
        if not seed:
            raise ValueError("a seed must not be empty")
        self.seed = seed
        self._counter = 0

    @classmethod
    def for_turn(cls, story_id: str, timeline_id: str, turn: int) -> "SeededRng":
        """The root stream for one turn of one story on one timeline (A3)."""
        return cls(f"story={_escape(story_id)}/timeline={_escape(timeline_id)}/turn={int(turn)}")

    def child(self, *labels: object) -> "SeededRng":
        """An independent stream derived from this seed and the labels, never from its state."""
        if not labels:
            raise ValueError("a child stream needs at least one label")
        return SeededRng("/".join([self.seed, *(_escape(label) for label in labels)]))

    def _next_u64(self) -> int:
        digest = hashlib.sha256(f"{self.seed}#{self._counter}".encode()).digest()
        self._counter += 1
        return int.from_bytes(digest[:8], "big")

    def random(self) -> float:
        """A float in [0, 1)."""
        return (self._next_u64() >> (64 - _FLOAT_BITS)) / (1 << _FLOAT_BITS)

    def below(self, n: int) -> int:
        """An integer in [0, n), without modulo bias."""
        if n <= 0:
            raise ValueError("n must be positive")
        limit = _U64 - (_U64 % n)
        while True:
            value = self._next_u64()
            if value < limit:
                return value % n

    def randint(self, low: int, high: int) -> int:
        """An integer in [low, high], both ends included."""
        if high < low:
            raise ValueError("high must not be below low")
        return low + self.below(high - low + 1)

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self.random()

    def log_uniform(self, low: float, high: float) -> float:
        """Spread evenly across orders of magnitude, for durations that can run from minutes to
        days (W10: a trap can hold someone five minutes or a week)."""
        if low <= 0 or high < low:
            raise ValueError("log_uniform needs 0 < low <= high")
        return math.exp(self.uniform(math.log(low), math.log(high)))

    def chance(self, probability: float) -> bool:
        """True with the given probability."""
        return self.random() < probability

    def choice(self, items: Sequence[T]) -> T:
        if not items:
            raise ValueError("cannot choose from an empty sequence")
        return items[self.below(len(items))]

    def weighted(self, items: Sequence[T], weights: Sequence[float]) -> T:
        """One item, with chances in proportion to the weights. Zero weights are never picked."""
        if len(items) != len(weights) or not items:
            raise ValueError("items and weights must be non-empty and the same length")
        if any(w < 0 for w in weights):
            raise ValueError("weights must not be negative")
        total = sum(weights)
        if total <= 0:
            raise ValueError("at least one weight must be positive")
        point = self.random() * total
        running = 0.0
        for item, weight in zip(items, weights, strict=True):
            running += weight
            if weight > 0 and point < running:
                return item
        return next(i for i, w in zip(reversed(items), reversed(weights), strict=True) if w > 0)

    def shuffled(self, items: Sequence[T]) -> list[T]:
        """A shuffled copy (Fisher-Yates)."""
        result = list(items)
        for i in range(len(result) - 1, 0, -1):
            j = self.below(i + 1)
            result[i], result[j] = result[j], result[i]
        return result

    def __repr__(self) -> str:
        return f"SeededRng({self.seed!r})"
