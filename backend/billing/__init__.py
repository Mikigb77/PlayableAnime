"""Credits, quotas and rate limits (K1, K2, K6, K7, K8, M7, T9).

- `billing.meter`: the guard and the charge around every model call (`start`, `charge`,
  `charge_image`, `release`, and their async twins).
- `billing.credits`: accounts, the starter credit and the append-only ledger; `summary(user)`
  is the `credits` part of the User in docs/API.md.
- `billing.limits`: per-user fixed-window counters in Postgres.
- `billing.pricing`: plain-Python cost and charge arithmetic, and K8's cost spread.
"""
