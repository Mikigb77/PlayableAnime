"""Powers in play (WS9b): time stop and its hit modes (W10a), the player's theories about their
own powers (A9), growth and new ways to use a power (A4), breakthroughs (G19), sensing and hiding
strength (G20) and backstory claims (N4).

Pure Python under `engine.resolve`, which calls into it while it settles a plan. Code follows
each rule here as logic; the model only proposes (B4, A2).
"""

from engine.resolve.powers.time_stop import might_with_powers

__all__ = ["might_with_powers"]
