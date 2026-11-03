"""Running one turn: the LangGraph graph of B5, streamed (B7).

    async with aclosing(run_turn(turn, llm)) as events:
        async for event in events:  # NarrationDelta, NarrationReset, then TurnCompleted
            ...

The graph has no checkpointer: story state lives in our own tables (B9), so a turn that fails
partway is simply run again. Everything finishes before `TurnCompleted`, so nothing relies on
running after the response ends (B8). LangGraph loads on the first turn, not at startup (B10).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from graph.turn.types import (
    NarrationDelta,
    NarrationReset,
    TurnCompleted,
    TurnDeps,
    TurnEvent,
    TurnInput,
    TurnResult,
    TurnState,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from graph.llm import ModelClient

logger = logging.getLogger("graph.turn")


@lru_cache(maxsize=1)
def turn_graph() -> CompiledStateGraph:
    """The compiled graph: the seven nodes in B5's order, one after the other."""
    from langgraph.graph import END, START, StateGraph

    from graph.turn.nodes import NODES

    builder = StateGraph(TurnState, context_schema=TurnDeps)
    previous = START
    for name, node in NODES:
        builder.add_node(name, node)
        builder.add_edge(previous, name)
        previous = name
    builder.add_edge(previous, END)
    return builder.compile(name="turn")


async def run_turn(turn: TurnInput, llm: ModelClient) -> AsyncIterator[TurnEvent]:
    """Plays one turn, yielding the narration as it is written and then the finished turn.

    Raises `UnreadableAction` when the action can't be read (F4), and the model layer's
    `LLMUnavailable` or `BadKey` when the narration can't be written (T7). Nothing is saved here:
    the caller saves `TurnCompleted.result` in one transaction.
    """
    final: dict[str, Any] = {}
    initial: TurnState = {"input": turn, "issues": [], "timings_ms": {}}
    stream = turn_graph().astream(
        initial, context=TurnDeps(llm=llm), stream_mode=["custom", "values"]
    )
    async with aclosing(stream) as chunks:
        async for mode, chunk in chunks:
            if mode == "custom":
                if isinstance(chunk, NarrationDelta | NarrationReset):
                    yield chunk
            elif mode == "values":
                final = chunk
    result: TurnResult | None = final.get("result")
    if result is None:
        raise RuntimeError("the turn graph ended without a result")
    result = dataclasses.replace(result, timings_ms=dict(final.get("timings_ms") or {}))
    logger.info(
        "turn played",
        extra={
            "turn_graph": {
                "turn": turn.ctx.turn,
                "kind": turn.kind.value,
                "narration_mode": result.narration_mode,
                "issues": [issue.code for issue in result.issues],
                "timings_ms": result.timings_ms,
            }
        },
    )
    yield TurnCompleted(result)
