import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Skip-Helper fuer native-Crash-Isolierung unter CPython 3.14 / linux-aarch64.
# _load_module("run_parallel_simulation") triggert denselben nicht-deterministischen
# Segfault-Pfad (oasis -> torch / camel.toolkits -> mcp -> pydantic-GC) wie der
# direkte Import in tests/scripts. Siehe HANDOVER-2026-07-25-crash-diag-followup.md.
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from _crash_skip import skipif_py314_aarch64  # noqa: E402


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


@skipif_py314_aarch64
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


@skipif_py314_aarch64
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


def _conflict_graph(module):
    """Minimaler AgentGraph mit den drei Feldern, an denen CAMEL haengt."""

    class DummyMessage:
        def __init__(self, content):
            self.content = content

    class DummyAgent:
        def __init__(self):
            self.system_message = DummyMessage("persona")
            self._original_system_message = DummyMessage("persona")
            self.init_messages_called = 0

        def init_messages(self):
            self.init_messages_called += 1

    class DummyGraph:
        def __init__(self):
            self.agents = [DummyAgent(), DummyAgent()]

        def get_agents(self):
            return list(enumerate(self.agents))

    return DummyGraph()


def test_conflict_instruction_reaches_every_agent_system_message():
    """#1215: die Regel muss ueber den realen Patch-Pfad ankommen.

    Bewusst gegen ``apply_conflict_instruction`` statt gegen die Konstante:
    ein Test, der nur ``CONFLICT_INSTRUCTION`` auf Stichworte prueft, waere
    genau der Fehler, den dieser Slice dokumentiert — die Vorgaenger-Tests aus
    #1220/#1223 waren gruen, waehrend die Regel keinen Agenten erreichte.

    ``_original_system_message`` ist kein Beiwerk: CAMEL serialisiert die
    System-Message beim Init in den Speicher, und ``ChatHistoryMemory`` haelt
    Dict-Snapshots. Ohne diesen zweiten Patch plus ``init_messages()`` sieht
    das Modell den alten Text.
    """
    module = _load_module("agent_tools_conflict_test", "backend/scripts/agent_tools.py")
    graph = _conflict_graph(module)

    patched = module.apply_conflict_instruction(graph)

    assert patched == 2
    for agent in graph.agents:
        assert "Interaction and Conflict" in agent.system_message.content
        assert "Interaction and Conflict" in agent._original_system_message.content
        assert "DISLIKE_POST" in agent.system_message.content
        assert agent.init_messages_called == 1


def test_conflict_instruction_is_idempotent():
    """Zweimal anwenden darf den Prompt nicht verdoppeln.

    Der Runner ruft die Funktion je Plattform einmal; ein zweiter Aufruf ist
    nach einem Retry oder einer Graph-Wiederverwendung trotzdem moeglich.
    """
    module = _load_module("agent_tools_conflict_idem_test", "backend/scripts/agent_tools.py")
    graph = _conflict_graph(module)

    assert module.apply_conflict_instruction(graph) == 2
    assert module.apply_conflict_instruction(graph) == 0
    for agent in graph.agents:
        assert agent.system_message.content.count("Interaction and Conflict") == 1
        assert agent.init_messages_called == 1


def test_conflict_instruction_survives_a_broken_agent():
    """Ein Agent ohne ``system_message`` darf die Graph-Vorbereitung nicht kippen."""
    module = _load_module("agent_tools_conflict_robust_test", "backend/scripts/agent_tools.py")
    graph = _conflict_graph(module)
    graph.agents.insert(0, object())

    assert module.apply_conflict_instruction(graph) == 2


def test_conflict_rule_is_wired_into_both_parallel_platform_paths():
    """Die Regel muss im Runner haengen, nicht nur importierbar sein.

    Sie wird bewusst ausserhalb des ``enable_agent_tools``-Zweigs aufgerufen:
    sie hat mit Werkzeugen nichts zu tun. Der Test bindet sich an die
    Aufrufstelle, weil genau deren Fehlen der Defekt war.
    """
    source = (REPO_ROOT / "backend/scripts/run_parallel_simulation.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    called_in = {
        fn.name
        for fn in ast.walk(tree)
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "apply_conflict_instruction"
            for node in ast.walk(fn)
        )
    }
    assert {"run_twitter_simulation", "run_reddit_simulation"} <= called_in, called_in


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


# ── _create_manual_action: OASIS-Vertrag (#1215 / CodeRabbit Finding A) ──
#
# Der Prompt-Builder verlangt Ziel-IDs als post_id/comment_id/agent_id und
# Content als "content". OASIS' Plattform-Funktionen erwarten aber teils andere
# kwarg-Namen (followee_id, mutee_id, quote_content). _create_manual_action
# muss mappen; zuvor wurden Dislike/Comment/Mute gar nicht gemappt und
# Ziel-IDs verworfen — jede paarerweise Aktion schlug bei env.step fehl und
# hinterließ nur CREATE_POST (B1) bzw. keinen Dislike (B2).

_ALL_ACTIONS = [
    "CREATE_POST", "LIKE_POST", "DISLIKE_POST", "REPOST", "QUOTE_POST",
    "FOLLOW", "MUTE", "CREATE_COMMENT", "LIKE_COMMENT", "DISLIKE_COMMENT",
    "DO_NOTHING",
]


def _action_loop():
    module = _load_module(
        "agent_tools_action_map_test", "backend/scripts/agent_tools.py"
    )
    return module.ToolAwareActionLoop(model=None, tools=None), module


def test_create_manual_action_maps_all_pairwise_actions_with_oasis_kwargs():
    from oasis import ActionType

    loop, _ = _action_loop()

    cases = [
        ({"action": "CREATE_POST", "content": "hi"}, ActionType.CREATE_POST, {"content": "hi"}),
        ({"action": "LIKE_POST", "post_id": 7}, ActionType.LIKE_POST, {"post_id": 7}),
        ({"action": "DISLIKE_POST", "post_id": 7}, ActionType.DISLIKE_POST, {"post_id": 7}),
        ({"action": "REPOST", "post_id": 9}, ActionType.REPOST, {"post_id": 9}),
        ({"action": "QUOTE_POST", "post_id": 3, "content": "q"},
         ActionType.QUOTE_POST, {"post_id": 3, "quote_content": "q"}),
        ({"action": "FOLLOW", "agent_id": 42}, ActionType.FOLLOW, {"followee_id": 42}),
        ({"action": "MUTE", "agent_id": 42}, ActionType.MUTE, {"mutee_id": 42}),
        ({"action": "CREATE_COMMENT", "post_id": 5, "content": "c"},
         ActionType.CREATE_COMMENT, {"post_id": 5, "content": "c"}),
        ({"action": "LIKE_COMMENT", "comment_id": 11},
         ActionType.LIKE_COMMENT, {"comment_id": 11}),
        ({"action": "DISLIKE_COMMENT", "comment_id": 11},
         ActionType.DISLIKE_COMMENT, {"comment_id": 11}),
        ({"action": "DO_NOTHING"}, ActionType.DO_NOTHING, {}),
    ]

    for action_data, exp_type, exp_args in cases:
        action = loop._create_manual_action(action_data, _ALL_ACTIONS)
        assert action.action_type == exp_type, (
            f"{action_data}: action_type {action.action_type} != {exp_type}"
        )
        assert action.action_args == exp_args, (
            f"{action_data}: action_args {action.action_args} != {exp_args}"
        )


def test_create_manual_action_falls_back_to_do_nothing_on_missing_required_payload():
    from oasis import ActionType

    loop, _ = _action_loop()

    missing_cases = [
        {"action": "CREATE_POST"},                       # kein content
        {"action": "LIKE_POST"},                        # kein post_id
        {"action": "DISLIKE_POST"},                     # kein post_id
        {"action": "REPOST"},                           # kein post_id
        {"action": "QUOTE_POST", "content": "q"},        # kein post_id
        {"action": "FOLLOW"},                           # kein agent_id
        {"action": "MUTE"},                             # kein agent_id
        {"action": "CREATE_COMMENT", "post_id": 5},      # kein content
        {"action": "CREATE_COMMENT", "content": "c"},    # kein post_id
        {"action": "LIKE_COMMENT"},                     # kein comment_id
        {"action": "DISLIKE_COMMENT"},                  # kein comment_id
    ]

    for action_data in missing_cases:
        action = loop._create_manual_action(action_data, _ALL_ACTIONS)
        assert action.action_type == ActionType.DO_NOTHING, (
            f"{action_data}: sollte auf DO_NOTHING fallen, got {action.action_type}"
        )
        assert action.action_args == {}


def test_create_manual_action_rejects_actions_not_in_available_actions():
    from oasis import ActionType

    loop, _ = _action_loop()
    # Twitter-Action-Space: weder DISLIKE_* noch CREATE_COMMENT verfügbar.
    twitter_actions = [
        "CREATE_POST", "LIKE_POST", "REPOST", "FOLLOW", "DO_NOTHING", "QUOTE_POST",
    ]

    assert loop._create_manual_action(
        {"action": "DISLIKE_POST", "post_id": 1}, twitter_actions
    ).action_type == ActionType.DO_NOTHING
    assert loop._create_manual_action(
        {"action": "CREATE_COMMENT", "post_id": 1, "content": "x"}, twitter_actions
    ).action_type == ActionType.DO_NOTHING
    # Erlaubte Aktion wird ausgeführt.
    assert loop._create_manual_action(
        {"action": "LIKE_POST", "post_id": 1}, twitter_actions
    ).action_type == ActionType.LIKE_POST
    # Leere available_actions = kein Filter (Fallback-Pfad).
    assert loop._create_manual_action(
        {"action": "DISLIKE_POST", "post_id": 1}, []
    ).action_type == ActionType.DISLIKE_POST


def test_build_agent_prompt_with_tools_binds_conflict_rule_to_available_actions():
    """ACHTUNG (#1215): prueft den Prompt-Text eines toten Pfads.

    ``build_agent_prompt_with_tools`` wird im Lauf ueber
    ``ToolAwareActionLoop.decide_action`` erreicht, und der Loop ist im
    Parallel-Runner seit der Umstellung auf natives CAMEL-Function-Calling
    abgeschaltet (``tool_loop = None``). Dieser Test ist gruen und sagt nichts
    darueber aus, ob ein Agent die Konfliktregel zu sehen bekommt — das tut
    ``test_conflict_instruction_reaches_every_agent_system_message`` gegen
    ``apply_conflict_instruction``. Er bleibt stehen, weil
    ``SinglePlatformRunner`` den ReACT-Pfad weiterhin nutzt.
    """
    module = _load_module(
        "agent_tools_prompt_conflict_test", "backend/scripts/agent_tools.py"
    )

    class DummyTools:
        def tools_description_text(self):
            return ""

    prompt = module.build_agent_prompt_with_tools(
        agent_name="A", agent_role="r", agent_bio="b",
        observation="o", available_actions=["CREATE_POST", "LIKE_POST"],
        tools=DummyTools(), language="de",
    )
    # Die Konflikt-Regel muss die Modell-Auswahl an "Available Actions" binden,
    # damit auf Plattformen ohne DISLIKE_*/CREATE_COMMENT keine nicht verfügbaren
    # Aktionen emittiert werden (#1215 / CodeRabbit Finding B).
    assert "Available Actions" in prompt
    assert "not available" in prompt.lower()


def test_build_agent_prompt_with_tools_skips_tools_for_dislike_actions():
    """CodeRabbit Finding 1316 (#1215): Die Tool-Usage-Rule darf keinen
    Tool-Aufruf fuer DISLIKE_* erzwingen. Vorher erlaubte die Klausel den
    Tool-Skip nur fuer LIKE_POST/DO_NOTHING — bei Tool-Limit oder Tool-Fehler
    fiel DISLIKE_* auf DO_NOTHING zurueck, was B2 (Reddit nie Dislike)
    mit-erklaert. Die Skip-Klausel muss DISLIKE_POST/DISLIKE_COMMENT explizit
    nennen, damit das Modell sie direkt ausgeben kann, wenn die Observation
    das Ziel schon zeigt."""
    module = _load_module(
        "agent_tools_prompt_toolskip_test", "backend/scripts/agent_tools.py"
    )

    class DummyTools:
        def tools_description_text(self):
            return ""

    prompt = module.build_agent_prompt_with_tools(
        agent_name="A", agent_role="r", agent_bio="b",
        observation="o",
        available_actions=["CREATE_POST", "LIKE_POST", "DISLIKE_POST",
                           "DISLIKE_COMMENT", "DO_NOTHING"],
        tools=DummyTools(), language="de",
    )
    assert "trivial reactions" in prompt.lower()
    skip_window = prompt.lower().split("trivial reactions", 1)[1][:300]
    assert "dislike_post" in skip_window
    assert "dislike_comment" in skip_window


def _dead_guarded_branches(source: str) -> list[str]:
    """Findet ``if <name> and ...``-Zweige, deren Name nur ``None`` sein kann.

    Bewusst konservativ: gemeldet wird nur, wenn *jede* Zuweisung an den Namen
    innerhalb derselben Funktion die Konstante ``None`` ist. Eine zweite
    Zuweisung — auch in einem anderen Zweig — macht den Guard erreichbar und
    den Fund hinfaellig. Tupel-Ziele und ``AugAssign`` werden nicht erfasst;
    das kostet hoechstens einen uebersehenen Fund, nie einen falschen.
    """
    none_dump = ast.dump(ast.Constant(value=None))
    findings: list[str] = []
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        assigned: dict[str, set[str]] = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned.setdefault(target.id, set()).add(ast.dump(node.value))
        constant_none = {name for name, vals in assigned.items() if vals == {none_dump}}
        if not constant_none:
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            used = {
                sub.id for sub in ast.walk(node.test)
                if isinstance(sub, ast.Name) and sub.id in constant_none
            }
            for name in sorted(used):
                findings.append(f"{fn.name}():{node.lineno} — Guard auf '{name}', das nur None ist")
    return findings


def test_single_platform_runner_keeps_the_tool_loop_reachable():
    """Der Einzelplattform-Pfad baut den Prompt tatsaechlich.

    ``SinglePlatformRunner`` (``sim_runtime/platform_runner.py``) weist
    ``self.tool_loop`` per ``create_tool_aware_loop`` zu. Diese Seite ist der
    Gegenbeweis dazu, dass der Defekt in #1215 eine generelle Eigenschaft des
    Systems waere — er betrifft ausschliesslich den Parallel-Runner.
    """
    source = (REPO_ROOT / "backend/scripts/sim_runtime/platform_runner.py").read_text(
        encoding="utf-8"
    )
    assert "create_tool_aware_loop(" in source
    assert not _dead_guarded_branches(source)


@pytest.mark.xfail(
    reason=(
        "#1215: run_parallel_simulation setzt tool_loop in beiden Plattform-Pfaden "
        "hart auf None ('Native CAMEL function-calling replaces the old ReACT-style "
        "tool_loop'), womit ToolAwareActionLoop.decide_action unerreichbar ist. "
        "Die Konfliktregel haengt seit apply_conflict_instruction nicht mehr daran; "
        "offen bleibt nur das Aufraeumen des toten Pfads samt "
        "build_agent_prompt_with_tools und seinen Tests. Der Guard bleibt bis dahin "
        "stehen, damit die naechste Prompt-Regel nicht wieder dort landet."
    ),
    strict=True,
)
def test_parallel_runner_prompt_builder_is_reachable():
    """Eine Prompt-Regel muss von einem erreichbaren Produktivpfad gebaut werden.

    Guard gegen die Fehlerklasse, die #1230 fuer Befund 5c benannt hat und die
    sich bei #1215 wiederholt hat: ein Fix ist nominell vorhanden, feuert aber
    nie, und der zugehoerige Test prueft die Annahme statt der Realitaet. Ein
    toter ``if <flag> and ...``-Zweig ist die billigste maschinell pruefbare
    Signatur dafuer.
    """
    script = "backend/scripts/run_parallel_simulation.py"
    findings = _dead_guarded_branches((REPO_ROOT / script).read_text(encoding="utf-8"))
    assert not findings, f"{script}: unerreichbare Zweige — " + "; ".join(findings)
