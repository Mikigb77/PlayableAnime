import pickle
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from graph.llm import (
    ByokKey,
    FakeBackend,
    ModelConfig,
    Node,
    Prompt,
    Reply,
    UnsupportedProvider,
    build_client,
    fill_schema,
    parse_byok,
)
from graph.llm.fake import OFFLINE_TEXT, TINY_PNG
from tests.graph.conftest import Narration, run

PROMPT = Prompt.build("system", "user")


class Step(BaseModel):
    text: str = Field(min_length=3)
    kind: Literal["certain", "contested", "long_shot", "ruled_out"]
    odds: float = Field(ge=0, le=1)


class Intent(BaseModel):
    verb: str
    target: str | None
    steps: list[Step] = Field(min_length=1)
    beats: list[str]
    duration_s: int = Field(gt=0)
    chained: bool
    tags: dict[str, str] = {}
    mode: Literal["typed", "voice"] = "typed"


def test_fill_schema_satisfies_nested_constrained_schemas():
    value = fill_schema(Intent.model_json_schema())

    intent = Intent.model_validate(value)
    assert intent.steps and intent.steps[0].kind == "certain"
    assert intent.duration_s > 0


def test_the_offline_model_answers_any_schema_text_and_pictures():
    client = build_client(rating="teen", config=ModelConfig(provider="fake"))

    async def calls():
        scene = await client.structured(Node.NARRATOR, PROMPT, Narration)
        text = await client.text(Node.SUMMARIZER, PROMPT)
        image = await client.image(Node.PICTURE, PROMPT)
        return scene, text, image

    scene, text, image = run(calls())
    assert scene.narration == OFFLINE_TEXT
    assert text == OFFLINE_TEXT
    assert image.data == TINY_PNG


def test_scripts_replay_in_order_per_node_and_run_out_loudly():
    fake = FakeBackend()
    fake.script(Node.NARRATOR, Reply(text="one"), Reply(text="two"))
    fake.script(Node.INTERPRET, Reply(text="i"))
    client = build_client(rating="mature", backend=fake)

    async def calls():
        return [
            await client.text(Node.NARRATOR, PROMPT),
            await client.text(Node.INTERPRET, PROMPT),
            await client.text(Node.NARRATOR, PROMPT),
        ]

    assert run(calls()) == ["one", "i", "two"]
    assert [r.node for r in fake.calls(Node.NARRATOR)] == [Node.NARRATOR, Node.NARRATOR]
    with pytest.raises(AssertionError, match="no scripted reply"):
        run(client.text(Node.NARRATOR, PROMPT))


def test_no_key_means_our_own_account():
    assert parse_byok(None, None) is None
    assert parse_byok("gemini", "   ") is None


def test_a_gemini_key_is_read_and_masked():
    key = parse_byok(" Gemini ", " AIzaSecret ")

    assert key is not None
    assert key.provider == "gemini"
    assert key.reveal() == "AIzaSecret"
    assert "AIzaSecret" not in repr(key) and "AIzaSecret" not in str(key)
    with pytest.raises(TypeError):
        pickle.dumps(key)


def test_a_key_without_a_provider_is_gemini_and_other_providers_are_refused():
    assert parse_byok(None, "k").provider == "gemini"  # type: ignore[union-attr]
    with pytest.raises(UnsupportedProvider):
        parse_byok("openai", "sk-123")


def test_a_player_key_builds_its_own_gemini_client():
    client = build_client(rating="mature", byok=ByokKey("gemini", "AIzaFAKE"))

    assert client.byok
    assert client._backend.provider == "gemini_api"
    assert client._owns_backend
    run(client.aclose())


def test_our_own_account_shares_one_vertex_backend():
    config = ModelConfig(provider="vertex", project="p", location="global")

    first = build_client(rating="teen", config=config)
    second = build_client(rating="mature", config=config)

    assert first._backend is second._backend
    assert first._backend.provider == "vertex"
    assert not first.byok and not first._owns_backend
