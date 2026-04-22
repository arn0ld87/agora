import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module(module_name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_model_runtime_settings_cloud(monkeypatch):
    module = _load_module("run_parallel_simulation_test", "backend/scripts/run_parallel_simulation.py")

    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "4096")
    monkeypatch.setenv("LLM_CONTEXT_LIMIT", "262144")
    monkeypatch.setenv(
        "LLM_MODEL_CONTEXT_LIMITS_JSON",
        '{"qwen3-coder-next:cloud": 131072, "qwen2.5:32b": 32768}',
    )

    settings = module.resolve_model_runtime_settings("qwen3-coder-next:cloud")

    assert settings["completion_max_tokens"] == 4096
    assert settings["memory_token_limit"] == 131072
    assert settings["ollama_num_ctx"] is None
    assert settings["is_cloud_model"] is True


def test_resolve_model_runtime_settings_local(monkeypatch):
    module = _load_module("run_parallel_simulation_test_local", "backend/scripts/run_parallel_simulation.py")

    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "12288")
    monkeypatch.setenv("LLM_CONTEXT_LIMIT", "65536")
    monkeypatch.setenv("LLM_MODEL_CONTEXT_LIMITS_JSON", '{"qwen2.5:32b": 32768}')

    settings = module.resolve_model_runtime_settings("qwen2.5:32b")

    assert settings["completion_max_tokens"] == 12288
    assert settings["memory_token_limit"] == 32768
    assert settings["ollama_num_ctx"] == 32768
    assert settings["is_cloud_model"] is False


def test_attach_tools_to_agents_patches_context_and_sanity(monkeypatch):
    module = _load_module("agent_tools_test", "backend/scripts/agent_tools.py")

    monkeypatch.setenv("LLM_CONTEXT_LIMIT", "262144")
    monkeypatch.setenv("LLM_MODEL_CONTEXT_LIMITS_JSON", '{"qwen3-coder-next:cloud": 131072}')

    class DummyTool:
        def __init__(self, name):
            self.name = name

    class DummyMessage:
        def __init__(self, content):
            self.content = content

    class DummyCreator:
        def __init__(self):
            self._token_limit = 8192

        @property
        def token_limit(self):
            return self._token_limit

    class DummyMemory:
        def __init__(self):
            self.creator = DummyCreator()

        def get_context_creator(self):
            return self.creator

    class DummyModelBackend:
        def __init__(self):
            self.model_type = "qwen3-coder-next:cloud"
            self.model_config_dict = {"max_tokens": 4096}

    class DummyAgent:
        def __init__(self):
            self._internal_tools = {}
            self.system_message = DummyMessage("persona")
            self._original_system_message = DummyMessage("persona")
            self.memory = DummyMemory()
            self.model_backend = DummyModelBackend()
            self.max_iteration = 1
            self.init_messages_called = 0

        @property
        def tool_dict(self):
            return self._internal_tools

        def add_tool(self, tool):
            self._internal_tools[tool.name] = tool

        def init_messages(self):
            self.init_messages_called += 1

    class DummyGraph:
        def __init__(self):
            self.agent = DummyAgent()

        def get_agents(self):
            return [(0, self.agent)]

    graph = DummyGraph()
    attached = module.attach_tools_to_agents(graph, [DummyTool("web_search"), DummyTool("web_fetch")])

    assert attached == 2
    assert set(graph.agent.tool_dict.keys()) == {"web_search", "web_fetch"}
    assert graph.agent.max_iteration == 4
    assert graph.agent.memory.get_context_creator().token_limit == 131072
    assert graph.agent.init_messages_called == 1
    assert "Research Tools" in graph.agent.system_message.content
    assert "Research Tools" in graph.agent._original_system_message.content
