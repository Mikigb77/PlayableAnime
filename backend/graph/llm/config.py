"""Which model each node uses, and its defaults (B6).

Read from environment variables so that Django settings, scripts and tests share one source:

- `LLM_PROVIDER`: `vertex` (Gemini on Vertex AI through Application Default Credentials, B11) or
  `fake` (the offline model, the default, so nothing calls a model by accident).
- `GCP_PROJECT`, `VERTEX_LOCATION`: where Vertex AI runs. `global` is the cheapest endpoint.
- `<NODE>_MODEL` and `<NODE>_THINKING` for each node, such as `NARRATOR_MODEL=gemini-3.5-flash`
  and `INTERPRET_THINKING=medium`.

Like Django's settings (`lucid.env`), `get_model_config()` also reads `backend/.env` and the
repo-root `.env.local`, with real environment variables winning over both.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast, get_args

from graph.llm.types import CallOptions, Node, Thinking


@dataclass(frozen=True)
class NodeSettings:
    model: str
    options: CallOptions


# Defaults, chosen on 2026-11-03 from the Vertex AI price list (see `graph.llm.pricing`).
# The narrator is the one large call on the critical path (B8), so it thinks at `low` to keep the
# first words under 2 s (S3). The interpret step is cheap but reasons about cause and effect
# (A9); the graph can raise its thinking for a turn that rests on a chain. Checker, tick and
# summaries use the cheapest model (B8). Drafting is off the turn path, so it keeps the model's
# own thinking default for quality. Image models take no thinking setting. A deadline counts
# only time spent waiting on the model, and a retry gets a fresh one, so the slowest turn
# (interpret, then narrate, each timing out twice) still ends well inside Cloud Run's 300 s.
DEFAULT_NODES: Mapping[Node, NodeSettings] = {
    Node.INTERPRET: NodeSettings(
        "gemini-3.5-flash-lite", CallOptions(thinking="low", max_output_tokens=4096, timeout_s=20)
    ),
    Node.NARRATOR: NodeSettings(
        "gemini-3.5-flash", CallOptions(thinking="low", max_output_tokens=8192, timeout_s=60)
    ),
    Node.CHECKER: NodeSettings(
        "gemini-3.1-flash-lite", CallOptions(thinking="low", max_output_tokens=2048, timeout_s=30)
    ),
    Node.TICK: NodeSettings(
        "gemini-3.1-flash-lite", CallOptions(thinking="low", max_output_tokens=2048, timeout_s=30)
    ),
    Node.SUMMARIZER: NodeSettings(
        "gemini-3.1-flash-lite", CallOptions(thinking="low", max_output_tokens=2048, timeout_s=60)
    ),
    Node.DRAFTER: NodeSettings(
        "gemini-3.5-flash", CallOptions(max_output_tokens=16384, timeout_s=120)
    ),
    Node.PICTURE: NodeSettings("gemini-3.1-flash-lite-image", CallOptions(timeout_s=60)),
    # The evals' judge (WS17) runs nightly, never for a player, so it uses the strongest model we
    # price and thinks hard: a judge that misreads a scene makes the numbers worthless.
    Node.JUDGE: NodeSettings(
        "gemini-3.1-pro-preview",
        CallOptions(thinking="high", max_output_tokens=8192, timeout_s=120),
    ),
}

ProviderSetting = Literal["vertex", "fake"]


@dataclass(frozen=True)
class ModelConfig:
    provider: ProviderSetting = "fake"
    project: str = "playable-anime"
    location: str = "global"
    nodes: Mapping[Node, NodeSettings] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Nodes left out keep their defaults.
        object.__setattr__(self, "nodes", {**DEFAULT_NODES, **self.nodes})

    def node(self, node: Node) -> NodeSettings:
        return self.nodes[node]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ModelConfig:
        env = os.environ if env is None else env
        provider = env.get("LLM_PROVIDER", "fake").strip().lower()
        if provider not in get_args(ProviderSetting):
            raise ValueError(f"LLM_PROVIDER must be 'vertex' or 'fake', not {provider!r}")
        nodes: dict[Node, NodeSettings] = {}
        for node, default in DEFAULT_NODES.items():
            prefix = node.value.upper()
            model = env.get(f"{prefix}_MODEL", "").strip() or default.model
            thinking = env.get(f"{prefix}_THINKING", "").strip().lower()
            options = default.options
            if thinking:
                if thinking not in get_args(Thinking):
                    raise ValueError(f"{prefix}_THINKING must be one of {get_args(Thinking)}")
                options = replace(options, thinking=cast(Thinking, thinking))
            nodes[node] = NodeSettings(model, options)
        return cls(
            provider=cast(ProviderSetting, provider),
            project=env.get("GCP_PROJECT", "").strip() or "playable-anime",
            location=env.get("VERTEX_LOCATION", "").strip() or "global",
            nodes=nodes,
        )


_BACKEND_DIR = Path(__file__).resolve().parents[2]
# In rising precedence, as in `lucid.env`: `neon env pull` writes the first, developers the second.
ENV_FILES = (_BACKEND_DIR.parent / ".env.local", _BACKEND_DIR / ".env")


def read_env(
    files: Sequence[Path] = ENV_FILES, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The env files' values, then the real environment on top."""
    from dotenv import dotenv_values

    merged: dict[str, str] = {}
    for path in files:
        if path.is_file():
            merged.update({k: v for k, v in dotenv_values(path).items() if v is not None})
    merged.update(os.environ if environ is None else environ)
    return merged


@lru_cache
def get_model_config() -> ModelConfig:
    """The process-wide config, read once at first use."""
    return ModelConfig.from_env(read_env())
