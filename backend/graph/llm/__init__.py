"""The model layer: one client for every model call the graph makes (B6, T5, T7).

    from graph.llm import Node, Prompt, TurnTelemetry, build_client

    telemetry = TurnTelemetry()
    llm = build_client(rating="mature", byok=parse_byok(provider, key), recorder=telemetry)
    intent = await llm.structured(Node.INTERPRET, Prompt.build(system, action), Intent)

Importing this package loads no model SDK; the Gemini backend loads on the first real call.
"""

from graph.llm.client import (
    Completed,
    GeneratedImage,
    ModelClient,
    StreamEvent,
    StreamRestart,
    TextDelta,
)
from graph.llm.config import DEFAULT_NODES, ModelConfig, NodeSettings, get_model_config
from graph.llm.errors import BadKey, LLMBlocked, LLMError, LLMUnavailable, UnsupportedProvider
from graph.llm.factory import BYOK_PROVIDERS, ByokKey, build_client, parse_byok
from graph.llm.fake import Block, Fail, FakeBackend, Hang, Reply, fill_schema, offline_reply
from graph.llm.pricing import estimate_cost
from graph.llm.safety import safety_settings
from graph.llm.telemetry import CallRecord, CallRecorder, TurnTelemetry
from graph.llm.types import (
    CallOptions,
    ImagePart,
    ImageSpec,
    Message,
    Node,
    Prompt,
    Rating,
    Thinking,
)

__all__ = [
    "BYOK_PROVIDERS",
    "DEFAULT_NODES",
    "BadKey",
    "Block",
    "ByokKey",
    "CallOptions",
    "CallRecord",
    "CallRecorder",
    "Completed",
    "Fail",
    "FakeBackend",
    "GeneratedImage",
    "Hang",
    "ImagePart",
    "ImageSpec",
    "LLMBlocked",
    "LLMError",
    "LLMUnavailable",
    "Message",
    "ModelClient",
    "ModelConfig",
    "Node",
    "NodeSettings",
    "Prompt",
    "Rating",
    "Reply",
    "StreamEvent",
    "StreamRestart",
    "TextDelta",
    "Thinking",
    "TurnTelemetry",
    "UnsupportedProvider",
    "build_client",
    "estimate_cost",
    "fill_schema",
    "get_model_config",
    "offline_reply",
    "parse_byok",
    "safety_settings",
]
