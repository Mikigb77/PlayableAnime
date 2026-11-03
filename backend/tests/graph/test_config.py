import pytest

from graph.llm import DEFAULT_NODES, CallOptions, ModelConfig, Node
from graph.llm.config import read_env
from graph.llm.pricing import price_for


def test_every_node_has_a_model_and_a_deadline():
    config = ModelConfig()

    assert set(config.nodes) == set(Node)
    for node in Node:
        assert config.node(node).model
        assert config.node(node).options.timeout_s


def test_defaults_are_offline_on_the_global_endpoint():
    config = ModelConfig.from_env({})

    assert config.provider == "fake"
    assert config.project == "playable-anime"
    assert config.location == "global"
    assert config.nodes == DEFAULT_NODES


def test_every_default_model_has_a_price():
    for settings in DEFAULT_NODES.values():
        assert price_for(settings.model)[1], settings.model


def test_env_sets_the_provider_and_each_node():
    config = ModelConfig.from_env(
        {
            "LLM_PROVIDER": "Vertex",
            "GCP_PROJECT": "other-project",
            "VERTEX_LOCATION": "europe-west3",
            "NARRATOR_MODEL": "gemini-3.6-flash",
            "INTERPRET_THINKING": "HIGH",
        }
    )

    assert config.provider == "vertex"
    assert config.project == "other-project"
    assert config.location == "europe-west3"
    assert config.node(Node.NARRATOR).model == "gemini-3.6-flash"
    assert config.node(Node.NARRATOR).options == DEFAULT_NODES[Node.NARRATOR].options
    assert config.node(Node.INTERPRET).options.thinking == "high"
    assert config.node(Node.CHECKER) == DEFAULT_NODES[Node.CHECKER]


def test_nodes_left_out_keep_their_defaults():
    narrator = DEFAULT_NODES[Node.NARRATOR]
    config = ModelConfig(nodes={Node.NARRATOR: narrator})

    assert config.node(Node.PICTURE) == DEFAULT_NODES[Node.PICTURE]


@pytest.mark.parametrize("env", [{"LLM_PROVIDER": "openai"}, {"NARRATOR_THINKING": "a lot"}])
def test_bad_settings_fail_at_startup(env):
    with pytest.raises(ValueError):
        ModelConfig.from_env(env)


def test_call_options_override_only_what_they_set():
    base = CallOptions(thinking="low", max_output_tokens=100, timeout_s=30)

    merged = base.merged(CallOptions(thinking="high", seed=7))

    assert merged == CallOptions(thinking="high", max_output_tokens=100, seed=7, timeout_s=30)
    assert base.merged(None) is base


def test_env_files_are_read_like_django_settings_with_the_environment_on_top(tmp_path):
    neon = tmp_path / ".env.local"
    neon.write_text("LLM_PROVIDER=fake\nGCP_PROJECT=from-neon\nDATABASE_URL=postgres://x\n")
    local = tmp_path / ".env"
    local.write_text("LLM_PROVIDER=vertex\nINTERPRET_THINKING=medium\nNARRATOR_MODEL=from-file\n")

    env = read_env([neon, local, tmp_path / "missing"], environ={"NARRATOR_MODEL": "from-env"})
    config = ModelConfig.from_env(env)

    assert config.provider == "vertex"
    assert config.project == "from-neon"
    assert config.node(Node.INTERPRET).options.thinking == "medium"
    assert config.node(Node.NARRATOR).model == "from-env"
