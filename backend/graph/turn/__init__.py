"""The turn graph (B5): one player turn, from the words they typed or said to the saved scene.

    from graph.turn import PastScene, TurnInput, TurnKind, run_turn

    turn = TurnInput(state=state, ctx=ctx, kind=TurnKind.ACTION, action="I throw the stone")
    async with aclosing(run_turn(turn, llm)) as events:
        async for event in events:  # NarrationDelta, NarrationReset, then TurnCompleted
            ...

Importing this package doesn't load LangGraph; the first turn does (B10).
"""

from graph.turn.errors import UnreadableAction
from graph.turn.outputs import ChapterOutput, NarratorOutput, SuggestionOut
from graph.turn.runner import run_turn, turn_graph
from graph.turn.types import (
    CHAPTER_TURNS,
    Choice,
    Issue,
    NarrationDelta,
    NarrationMode,
    NarrationReset,
    PastScene,
    SceneDetails,
    SceneDraft,
    SceneEvent,
    ScenePicture,
    TurnCompleted,
    TurnDeps,
    TurnEvent,
    TurnInput,
    TurnKind,
    TurnResult,
)

__all__ = [
    "CHAPTER_TURNS",
    "ChapterOutput",
    "Choice",
    "Issue",
    "NarrationDelta",
    "NarrationMode",
    "NarrationReset",
    "NarratorOutput",
    "PastScene",
    "SceneDetails",
    "SceneDraft",
    "SceneEvent",
    "ScenePicture",
    "SuggestionOut",
    "TurnCompleted",
    "TurnDeps",
    "TurnEvent",
    "TurnInput",
    "TurnKind",
    "TurnResult",
    "UnreadableAction",
    "run_turn",
    "turn_graph",
]
