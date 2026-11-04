"""Calls each model the app uses once, with a tiny prompt, and says which ones answer (B6, T13).

Each deploy runs it as the migration job, on the service's settings and account, once the service
is live (docs/DEPLOY.md). A model that Vertex AI refuses, such as a retired name, a missing
permission or no quota, then fails the deploy run with Vertex AI's own reason, instead of a player
finding out from "The storyteller is unavailable".

    uv run python manage.py check_models               # each model in use, pictures included
    uv run python manage.py check_models --no-picture  # the text models only

Only the models the app uses are called, each once, whichever nodes share it: today three text
models and the picture model, for about 4 cents in all, most of it the picture. The evals' judge
is left out, since it never serves a player. With the offline model (`LLM_PROVIDER=fake`) it
checks nothing and says so.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError

from graph.llm import (
    CallOptions,
    ImageSpec,
    LLMError,
    ModelClient,
    ModelConfig,
    Node,
    Prompt,
    TurnTelemetry,
    build_client,
    get_model_config,
)

# The nodes a player's turn, draft or picture calls, in the order they are checked.
TEXT_NODES = (
    Node.INTERPRET,
    Node.NARRATOR,
    Node.CHECKER,
    Node.TICK,
    Node.SUMMARIZER,
    Node.DRAFTER,
)
SYSTEM = "You answer a health check. Reply with exactly one word."
PROMPT = "Reply with the word ok."
PICTURE_SYSTEM = "You draw one simple picture."
PICTURE_PROMPT = "A single red apple on a plain wooden table, in soft daylight."
# Room for the thinking a node keeps on, so a one-word answer is never cut off.
TEXT_OPTIONS = CallOptions(max_output_tokens=1024)
# Vertex AI's reasons can be long; the start says what went wrong.
DETAIL_CHARS = 600


@dataclass(frozen=True)
class Check:
    """One model's answer. `nodes` are the nodes that use it."""

    model: str
    nodes: tuple[str, ...]
    ok: bool
    seconds: float
    reason: str = ""
    detail: str = ""


def models_in_use(config: ModelConfig, *, picture: bool) -> list[tuple[str, tuple[Node, ...]]]:
    """Each model the app uses, once, with the nodes that use it, in the nodes' order."""
    nodes = [*TEXT_NODES, Node.PICTURE] if picture else list(TEXT_NODES)
    models: dict[str, list[Node]] = {}
    for node in nodes:
        models.setdefault(config.node(node).model, []).append(node)
    return [(model, tuple(users)) for model, users in models.items()]


class _LastFailure(logging.Handler):
    """Keeps the reason and detail the model client logs for the call that just failed."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.fields: dict[str, Any] = {}

    def emit(self, record: logging.LogRecord) -> None:
        fields = getattr(record, "llm", None)
        if isinstance(fields, dict):
            self.fields = fields


async def run_checks(config: ModelConfig, *, picture: bool) -> list[Check]:
    """Calls each model in use once. A picture model is asked for a picture, the others for a
    word, through the first node that uses it, with that node's settings."""
    client = build_client(rating="teen", recorder=TurnTelemetry(), config=config)
    failures = _LastFailure()
    llm_logger = logging.getLogger("graph.llm")
    llm_logger.addHandler(failures)
    checks: list[Check] = []
    try:
        for model, nodes in models_in_use(config, picture=picture):
            checks.append(await _check(client, failures, model, nodes))
    finally:
        llm_logger.removeHandler(failures)
        await client.aclose()
    return checks


async def _check(
    client: ModelClient, failures: _LastFailure, model: str, nodes: tuple[Node, ...]
) -> Check:
    names = tuple(node.value for node in nodes)
    failures.fields = {}
    started = time.monotonic()
    try:
        if nodes[0] is Node.PICTURE:
            await client.image(
                Node.PICTURE,
                Prompt.build(PICTURE_SYSTEM, PICTURE_PROMPT),
                spec=ImageSpec(aspect_ratio="1:1"),
            )
        else:
            await client.text(nodes[0], Prompt.build(SYSTEM, PROMPT), options=TEXT_OPTIONS)
    except LLMError as error:
        fields = failures.fields
        return Check(
            model,
            names,
            ok=False,
            seconds=time.monotonic() - started,
            reason=str(fields.get("reason") or error.code),
            detail=str(fields.get("detail") or "")[:DETAIL_CHARS],
        )
    return Check(model, names, ok=True, seconds=time.monotonic() - started)


def describe(check: Check) -> str:
    line = f"{check.model} ({', '.join(check.nodes)}): "
    if check.ok:
        return f"{line}ok in {check.seconds:.1f} s"
    line = f"{line}FAILED ({check.reason})"
    return f"{line}: {check.detail}" if check.detail else line


class Command(BaseCommand):
    help = "Calls each model the app uses once, and says which ones answer."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--no-picture", action="store_true", help="Check the text models only.")

    def handle(self, *args, no_picture: bool, **options) -> None:
        config = get_model_config()
        if config.provider != "vertex":
            self.stdout.write(
                "The offline model is configured (LLM_PROVIDER=fake), so there is nothing to check."
            )
            return
        self.stdout.write(
            f"Calling each model in use once, on Vertex AI in {config.project} ({config.location})."
        )
        checks = async_to_sync(run_checks)(config, picture=not no_picture)
        for check in checks:
            self.stdout.write(describe(check))
        failed = [check for check in checks if not check.ok]
        if failed:
            models = ", ".join(check.model for check in failed)
            raise CommandError(
                f"{len(failed)} of {len(checks)} models didn't answer ({models}). Players can't "
                "use what they serve until this is fixed."
            )
        self.stdout.write(f"All {len(checks)} models answered.")
