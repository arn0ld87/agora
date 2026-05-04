import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


RUNNER_SCRIPTS = (
    "backend/scripts/run_parallel_simulation.py",
    "backend/scripts/run_twitter_simulation.py",
    "backend/scripts/run_reddit_simulation.py",
)


def _load_module(module_name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    parent_dir = str(module_path.parent.resolve())
    sys_path_added = False
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
        sys_path_added = True
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        if sys_path_added and parent_dir in sys.path:
            sys.path.remove(parent_dir)


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


def test_sanitize_memory_records_drops_empty_assistant_without_tool_calls():
    module = _load_module("agent_tools_sanitize_test", "backend/scripts/agent_tools.py")

    class DummyMessage:
        def __init__(self, content, meta_dict=None):
            self.content = content
            self.meta_dict = meta_dict

    class DummyRecord:
        def __init__(self, role_at_backend, content, meta_dict=None):
            self.role_at_backend = role_at_backend
            self.message = DummyMessage(content, meta_dict)

    empty_assistant = DummyRecord("assistant", None)
    assistant_with_tool_calls = DummyRecord(
        "assistant",
        None,
        {"tool_calls": [{"id": "call_1", "type": "function"}]},
    )
    assistant_with_content = DummyRecord("assistant", "")
    user_record = DummyRecord("user", None)

    sanitized = module._sanitize_memory_records([
        empty_assistant,
        assistant_with_tool_calls,
        assistant_with_content,
        user_record,
    ])

    assert sanitized == [
        assistant_with_tool_calls,
        assistant_with_content,
        user_record,
    ]


def test_attach_tools_to_agents_wraps_memory_write_records(monkeypatch):
    module = _load_module("agent_tools_memory_wrap_test", "backend/scripts/agent_tools.py")

    class DummyTool:
        name = "web_search"

    class DummyMessage:
        def __init__(self, content, meta_dict=None):
            self.content = content
            self.meta_dict = meta_dict

    class DummyCreator:
        _token_limit = 8192

        @property
        def token_limit(self):
            return self._token_limit

    class DummyMemory:
        def __init__(self):
            self.creator = DummyCreator()
            self.records = []

        def get_context_creator(self):
            return self.creator

        def write_records(self, records):
            self.records.extend(records)

    class DummyRecord:
        role_at_backend = "assistant"
        message = DummyMessage(None)

    class DummyAgent:
        def __init__(self):
            self._internal_tools = {}
            self.system_message = DummyMessage("persona")
            self._original_system_message = DummyMessage("persona")
            self.memory = DummyMemory()
            self.model_backend = type(
                "ModelBackend",
                (),
                {"model_type": "other-model", "model_config_dict": {}},
            )()
            self.max_iteration = 1

        @property
        def tool_dict(self):
            return self._internal_tools

        def add_tool(self, tool):
            self._internal_tools[tool.name] = tool

        def init_messages(self):
            return None

    class DummyGraph:
        def __init__(self):
            self.agent = DummyAgent()

        def get_agents(self):
            return [(0, self.agent)]

    graph = DummyGraph()
    module.attach_tools_to_agents(graph, [DummyTool()])
    graph.agent.memory.write_records([DummyRecord()])

    assert graph.agent.memory.records == []


def test_enforce_memory_token_limit_without_tools(monkeypatch):
    """enforce_memory_token_limit muss creator._token_limit auch dann
    anheben, wenn KEIN attach_tools-Pfad benutzt wird. Ohne diese Garantie
    bleibt CAMELs ScoreBasedContextCreator-Default 8192 stehen, sobald
    Persona-Workflows ohne Tool-Registry laufen."""
    module = _load_module("agent_tools_enforce_test", "backend/scripts/agent_tools.py")

    monkeypatch.setenv("LLM_CONTEXT_LIMIT", "262144")
    monkeypatch.setenv(
        "LLM_MODEL_CONTEXT_LIMITS_JSON",
        '{"qwen3-coder-next:cloud": 262144}',
    )

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

    class DummyAgent:
        def __init__(self):
            self.memory = DummyMemory()
            self.model_backend = DummyModelBackend()

    class DummyGraph:
        def __init__(self):
            self.agent = DummyAgent()

        def get_agents(self):
            return [(0, self.agent)]

    graph = DummyGraph()
    patched = module.enforce_memory_token_limit(graph)
    assert patched == 1
    assert graph.agent.memory.get_context_creator().token_limit == 262144


def test_all_runners_apply_camel_context_floor():
    """Alle drei OASIS-Runner-Scripts (twitter/reddit/parallel) muessen
    CAMELs ScoreBasedContextCreator-Default-Floor (8192) auf
    LLM_CONTEXT_LIMIT hochziehen. Regression-Schutz dafuer, dass der
    Patch nicht erneut nur in einem Subset der Runner laeuft."""
    for relative_path in RUNNER_SCRIPTS:
        text = (REPO_ROOT / relative_path).read_text()
        assert (
            "apply_camel_context_floor" in text
        ), f"{relative_path}: apply_camel_context_floor() not invoked"


def test_resolve_memory_token_limit_uses_substring_heuristic_for_unknown_models(monkeypatch):
    """Bei Frontend-gewaehlten Modell-Strings, die nicht in
    LLM_MODEL_CONTEXT_LIMITS stehen, soll _resolve_memory_token_limit
    eine konservative Substring-Heuristik nutzen statt blind auf 262144
    zu fallen. Gemini-3-Familien koennen 1M Tokens, gpt-oss/llama nur 128k."""
    module = _load_module("agent_tools_heuristic_test", "backend/scripts/agent_tools.py")
    monkeypatch.setenv("LLM_CONTEXT_LIMIT", "262144")
    monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)

    assert module._resolve_memory_token_limit("gemini-3-pro:cloud") >= 1_000_000
    assert module._resolve_memory_token_limit("gemini-3-flash:cloud") >= 1_000_000
    assert module._resolve_memory_token_limit("deepseek-v3.1:cloud") >= 131_072
    assert module._resolve_memory_token_limit("qwen3-coder-next:cloud") >= 262_144
    assert module._resolve_memory_token_limit("gpt-oss:120b-cloud") >= 131_072
    assert module._resolve_memory_token_limit("some-unknown-model") == 262_144
