"""Lucid Saga's story engine: the rules that decide what happens, in plain Python.

Nothing in this package imports Django, Django Ninja, LangChain, LangGraph or a model SDK (B4), so
the rules can be tested on their own and moved between web frameworks unchanged. Model nodes
propose; the code here decides (CLAUDE.md rule 2).

Layout:

- `engine.state`: the world state (C2) and everything it holds, as Pydantic models that round-trip
  through JSON, because Django stores the state as JSONB.
- `engine.contracts`: what flows between the turn's steps (B5): `Intent` from the interpret step,
  `Resolution` from resolve, `DirectorPlan` from the director, and `StateDelta`, the changes a
  narrator or the engine proposes.
- `engine.context`: per-turn inputs that don't live in the world state (story settings, rating,
  content preferences).
- `engine.rng`: the seeded random numbers behind every roll (A3).
- `engine.pipeline`: the functions the turn graph calls. Other packages (`engine.resolve`,
  `engine.world`, `engine.director`) plug their logic in behind them.
- `engine.samples`: two example worlds, a grounded one and a cultivation one, for tests and
  development.
"""
