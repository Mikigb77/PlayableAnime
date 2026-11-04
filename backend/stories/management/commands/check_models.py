"""Calls each model the app uses once, with a tiny prompt, and says which ones answer (B6, T13).

Each deploy runs it as the migration job, on the service's settings and account, once the service
is live (docs/DEPLOY.md). A model that Vertex AI refuses, such as a retired name, a missing
permission or no quota, then fails the deploy run with Vertex AI's own reason, instead of a player
finding out from "The storyteller is unavailable".

    uv run python manage.py check_models               # each model in use, pictures included
    uv run python manage.py check_models --no-picture  # every model but the picture model

Only the models the app uses are called, each once, whichever nodes share it: today three text
models, the picture model and the speech model, for about 4 cents in all, most of it the picture.
The speech model is sent a second of silence with the settings dictation uses (V6), so a name or
setting Vertex AI refuses shows here. The evals' judge is left out, since it never serves a
player. With the offline model (`LLM_PROVIDER=fake`) it checks nothing and says so.

Then each response format a node asks for (its JSON schema) is sent once as that node sends it,
with room for only a few words: Gemini refuses a schema outside what it takes with a bare 400
before writing anything, which is how every draft failed on 2026-11-04 while plain calls worked.
A refused schema goes in the prompt instead (`graph.llm.gemini`), so the line says so and the
check still passes; only a format that fails both ways fails it.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from contextlib import aclosing
from dataclasses import dataclass, replace
from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError
from pydantic import BaseModel

from graph.llm import (
    AudioPart,
    CallOptions,
    ImageSpec,
    LLMError,
    ModelClient,
    ModelConfig,
    Node,
    Prompt,
    Transcription,
    TurnTelemetry,
    build_client,
    get_model_config,
    safety_settings,
)
from graph.llm.types import ProviderError, Request

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
# Dictation's settings (V6): the story's language, a name to listen for, and smart mode.
SPEECH_SPEC = Transcription(language_codes=("en-US",), vocabulary=("Lucid Saga",))
# Room for the thinking a node keeps on, so a one-word answer is never cut off.
TEXT_OPTIONS = CallOptions(max_output_tokens=1024)
# Vertex AI's reasons can be long; the start says what went wrong.
DETAIL_CHARS = 600
SCHEMA_SYSTEM = "You answer a health check."
SCHEMA_PROMPT = "Start an answer in the required format. It may stop after a few words."
# Gemini checks a schema before it writes, so a few words show it took it, at almost no cost.
# Thinking stays low: the drafter's own thinking spent up to a minute on these few words on
# 2026-11-04, once past the probe's deadline, and how hard a model thinks never changes whether
# Gemini takes a schema.
SCHEMA_OPTIONS = CallOptions(max_output_tokens=64, thinking="low")
# A format is sent straight to the backend, past the client's retries, so it gets its own, like
# a 429 in the client: a passing 429 or 503 is no reason to fail a deploy (on 2026-11-04 the
# narrator's format met two 429s 7 s apart, and the next call a few seconds later went through).
SCHEMA_RETRY_DELAYS_S = (2.0, 6.0)


def response_formats() -> tuple[tuple[Node, type[BaseModel]], ...]:
    """Each node's structured output, as it asks for it. The judge's is left out with it."""
    from graph.drafting.chain import CharacterProposal, DraftProposal, WorldProposal
    from graph.turn.nodes import ChapterOutput, Intent, NarratorOutput

    return (
        (Node.INTERPRET, Intent),
        (Node.NARRATOR, NarratorOutput),
        (Node.SUMMARIZER, ChapterOutput),
        (Node.DRAFTER, DraftProposal),
        (Node.DRAFTER, WorldProposal),
        (Node.DRAFTER, CharacterProposal),
    )


@dataclass(frozen=True)
class Check:
    """One model's answer. `nodes` are the nodes that use it."""

    model: str
    nodes: tuple[str, ...]
    ok: bool
    seconds: float
    reason: str = ""
    detail: str = ""
    # For a response format: the schema's name, and whether Gemini took it as a schema.
    schema: str = ""
    in_prompt: bool = False


def silence(seconds: float = 1.0, rate: int = 16_000) -> bytes:
    """A WAV of silence, as the app records it: 16 kHz, 16-bit, mono."""
    out = io.BytesIO()
    with wave.open(out, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(rate)
        clip.writeframes(b"\x00\x00" * round(seconds * rate))
    return out.getvalue()


def models_in_use(config: ModelConfig, *, picture: bool) -> list[tuple[str, tuple[Node, ...]]]:
    """Each model the app uses, once, with the nodes that use it, in the nodes' order."""
    nodes = [*TEXT_NODES, Node.SPEECH]
    if picture:
        nodes.append(Node.PICTURE)
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
    """Calls each model in use once. A picture model is asked for a picture, the speech model to
    write down a recording, the others for a word, through the first node that uses it, with that
    node's settings. Then sends each
    response format once, as its node does."""
    client = build_client(rating="teen", recorder=TurnTelemetry(), config=config)
    failures = _LastFailure()
    llm_logger = logging.getLogger("graph.llm")
    llm_logger.addHandler(failures)
    checks: list[Check] = []
    try:
        for model, nodes in models_in_use(config, picture=picture):
            checks.append(await _check(client, failures, model, nodes))
        for node, schema in response_formats():
            checks.append(await _check_format(client, failures, config, node, schema))
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
        if nodes[0] is Node.SPEECH:
            await client.transcribe(Node.SPEECH, AudioPart(silence(), "audio/wav"), SPEECH_SPEC)
        elif nodes[0] is Node.PICTURE:
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


async def _check_format(
    client: ModelClient,
    failures: _LastFailure,
    config: ModelConfig,
    node: Node,
    schema: type[BaseModel],
) -> Check:
    """Sends `schema` as `node` asks for it, straight to the backend: the answer is cut off on
    purpose, so only whether Gemini takes the request counts, not the JSON."""
    settings = config.node(node)
    request = Request(
        node=node,
        model=settings.model,
        prompt=Prompt.build(SCHEMA_SYSTEM, SCHEMA_PROMPT),
        options=replace(settings.options.merged(SCHEMA_OPTIONS), timeout_s=60),
        safety=safety_settings("teen", node=node),
        json_schema=schema.model_json_schema(),
    )
    failures.fields = {}
    started = time.monotonic()
    for delay in (*SCHEMA_RETRY_DELAYS_S, None):
        try:
            async with aclosing(client.backend.stream(request)) as chunks:
                async for _chunk in chunks:
                    pass
            break
        except ProviderError as error:
            if error.kind == "transient" and delay is not None:
                await asyncio.sleep(delay)
                continue
            return Check(
                settings.model,
                (node.value,),
                ok=False,
                seconds=time.monotonic() - started,
                reason=f"{error.kind}_{error.status}" if error.status else error.kind,
                detail=error.detail[:DETAIL_CHARS],
                schema=schema.__name__,
            )
    return Check(
        settings.model,
        (node.value,),
        ok=True,
        seconds=time.monotonic() - started,
        schema=schema.__name__,
        in_prompt=failures.fields.get("reason") == "schema_refused",
    )


def describe(check: Check) -> str:
    line = f"{check.model} ({', '.join(check.nodes)})"
    line = f"{line} {check.schema} format: " if check.schema else f"{line}: "
    if check.ok:
        line = f"{line}ok in {check.seconds:.1f} s"
        if check.in_prompt:
            line = f"{line}, though Gemini refused it as a schema, so it goes in the prompt"
        return line
    line = f"{line}FAILED ({check.reason})"
    return f"{line}: {check.detail}" if check.detail else line


class Command(BaseCommand):
    help = "Calls each model the app uses once, and says which ones answer."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--no-picture", action="store_true", help="Leave out the picture model."
        )

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
        models = [check for check in checks if not check.schema]
        formats = [check for check in checks if check.schema]
        problems = []
        if failed := [check for check in models if not check.ok]:
            names = ", ".join(check.model for check in failed)
            problems.append(f"{len(failed)} of {len(models)} models didn't answer ({names})")
        if failed := [check for check in formats if not check.ok]:
            names = ", ".join(f"{check.nodes[0]} {check.schema}" for check in failed)
            problems.append(
                f"{len(failed)} of {len(formats)} response formats were refused ({names})"
            )
        if problems:
            raise CommandError(
                f"{'; '.join(problems)}. Players can't use what they serve until this is fixed."
            )
        self.stdout.write(
            f"All {len(models)} models answered, and Gemini took all {len(formats)} response "
            "formats."
        )
