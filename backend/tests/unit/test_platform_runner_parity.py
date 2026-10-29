"""Unit-Tests für die Parität des SinglePlatformRunner (Befunde 6.1 und 6.2).

Verifiziert:
- Befund 6.1:
  - Modell-Präzedenz: config["llm_model"] > os.environ["LLM_MODEL_NAME"] > Default.
  - Ollama-URL-Normalisierung via resolve_camel_ollama_url.
  - Ollama :cloud ohne num_ctx, lokales Modell mit num_ctx.
  - Gemini Thought-Signature-Integration und GOOGLE/GEMINI_API_KEY-Setzung.
- Befund 6.2:
  - Stance-Augmentation in _get_profile_path via augment_profile_with_stance.
  - Native FunctionTools via attach_function_tools_to_agent_graph.
  - Runde 0: Trace-Reading aus DB mit post_id und _emit_post_created_to_redis.
  - Reguläre Runden: _emit_post_created_to_redis für relevante Aktionen.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from camel.types import ModelPlatformType

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import sim_runtime.platform_runner as pr_module  # noqa: E402
from sim_runtime.platform_runner import SinglePlatformRunner  # noqa: E402


def _create_runner_instance(config: dict[str, Any], tmp_path: Path, platform_slug: str = "twitter") -> SinglePlatformRunner:
    """Erzeugt eine Test-Instanz von SinglePlatformRunner ohne Datei-I/O in __init__."""
    runner = SinglePlatformRunner.__new__(SinglePlatformRunner)
    runner.config_path = str(tmp_path / "simulation_config.json")
    runner.config = config
    runner.simulation_dir = str(tmp_path)
    runner.random_seed = 42
    runner.wait_for_commands = False
    runner.PLATFORM_NAME = "Twitter" if platform_slug == "twitter" else "Reddit"
    runner.PLATFORM_SLUG = platform_slug
    runner.PROFILE_FILENAME = f"{platform_slug}_profiles.csv" if platform_slug == "twitter" else f"{platform_slug}_profiles.json"
    runner.DB_FILENAME = f"{platform_slug}_simulation.db"
    runner.env = None
    runner.agent_graph = None
    runner.ipc_handler = None
    runner.tool_loop = None
    runner.activation_limits = None
    runner.redis_bridge = None
    runner.action_logger = MagicMock()
    runner.keep_db = False
    profile_file = tmp_path / runner.PROFILE_FILENAME
    profile_file.write_text("id,name\n0,agent_0\n", encoding="utf-8")
    return runner


# ---------------------------------------------------------------------------
# Tests für Befund 6.1 (Modell-Erstellung und -Konfiguration)
# ---------------------------------------------------------------------------

def test_model_precedence_config_beats_env(monkeypatch, tmp_path):
    """config['llm_model'] hat Vorrang vor os.environ['LLM_MODEL_NAME']."""
    config = {"llm_model": "custom-model:latest"}
    monkeypatch.setenv("LLM_MODEL_NAME", "env-model:latest")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key")
    runner = _create_runner_instance(config, tmp_path)

    with patch("sim_runtime.platform_runner.ModelFactory.create") as mock_create:
        runner._create_model()
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["model_type"] == "custom-model:latest"


def test_model_precedence_env_fallback(monkeypatch, tmp_path):
    """os.environ['LLM_MODEL_NAME'] greift, wenn config['llm_model'] fehlt."""
    config = {}
    monkeypatch.setenv("LLM_MODEL_NAME", "env-model:latest")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key")
    runner = _create_runner_instance(config, tmp_path)

    with patch("sim_runtime.platform_runner.ModelFactory.create") as mock_create:
        runner._create_model()
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["model_type"] == "env-model:latest"


def test_model_precedence_default_fallback(monkeypatch, tmp_path):
    """Fallback ist qwen3-coder-next:cloud, wenn weder config noch env gesetzt ist."""
    config = {}
    monkeypatch.delenv("LLM_MODEL_NAME", raising=False)
    runner = _create_runner_instance(config, tmp_path)

    with patch("sim_runtime.platform_runner.ModelFactory.create") as mock_create:
        runner._create_model()
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["model_type"] == "qwen3-coder-next:cloud"


def test_ollama_url_normalization_and_cloud_no_num_ctx(monkeypatch, tmp_path):
    """Ollama-URL erhält /v1 und bei :cloud-Modellen wird kein num_ctx gesetzt."""
    config = {"llm_model": "qwen3-coder-next:cloud"}
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434")
    monkeypatch.delenv("LLM_MODEL_NAME", raising=False)
    runner = _create_runner_instance(config, tmp_path)

    with patch("sim_runtime.platform_runner.ModelFactory.create") as mock_create:
        runner._create_model()
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["model_platform"] == ModelPlatformType.OLLAMA
        assert kwargs["url"] == "http://localhost:11434/v1"
        extra_body = kwargs["model_config_dict"].get("extra_body", {})
        assert "options" not in extra_body


def test_ollama_local_sets_num_ctx(monkeypatch, tmp_path):
    """Lokales Ollama-Modell setzt num_ctx in extra_body.options."""
    config = {"llm_model": "llama3:latest"}
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434")
    monkeypatch.delenv("LLM_MODEL_NAME", raising=False)
    runner = _create_runner_instance(config, tmp_path)

    with patch("sim_runtime.platform_runner.ModelFactory.create") as mock_create:
        runner._create_model()
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["model_platform"] == ModelPlatformType.OLLAMA
        extra_body = kwargs["model_config_dict"].get("extra_body", {})
        assert "options" in extra_body
        assert "num_ctx" in extra_body["options"]


def test_gemini_thought_signature_and_keys(monkeypatch, tmp_path):
    """Gemini setzt GOOGLE_API_KEY und GEMINI_API_KEY und ruft _create_gemini_model auf."""
    config = {"llm_model": "gemini-2.5-pro"}
    monkeypatch.setenv("LLM_API_KEY", "test-gemini-key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    runner = _create_runner_instance(config, tmp_path)

    with patch("sim_runtime.platform_runner._create_gemini_model") as mock_gemini:
        mock_gemini.return_value = MagicMock()
        runner._create_model()
        mock_gemini.assert_called_once()
        _, kwargs = mock_gemini.call_args
        assert kwargs["model_type"] == "gemini-2.5-pro"
        assert kwargs["api_key"] == "test-gemini-key"
        assert os.environ.get("GOOGLE_API_KEY") == "test-gemini-key"
        assert os.environ.get("GEMINI_API_KEY") == "test-gemini-key"


# ---------------------------------------------------------------------------
# Tests für Befund 6.2 (SinglePlatformRunner Pipeline & Parität)
# ---------------------------------------------------------------------------

def test_get_profile_path_augments_with_stance(monkeypatch, tmp_path):
    """_get_profile_path ruft augment_profile_with_stance auf."""
    config = {
        "agent_configs": [{"agent_id": 1, "stance": "pro"}],
        "contested_question": {"statement": "Statement X"},
    }
    runner = _create_runner_instance(config, tmp_path, platform_slug="twitter")

    with patch.object(pr_module, "AGENT_TOOLS_AVAILABLE", True), \
         patch.object(pr_module, "augment_profile_with_stance") as mock_augment:
        mock_augment.return_value = "/path/to/augmented_profiles.csv"
        result_path = runner._get_profile_path()

        mock_augment.assert_called_once()
        _, kwargs = mock_augment.call_args
        assert kwargs["platform"] == "twitter"
        assert kwargs["contested_statement"] == "Statement X"
        assert result_path == "/path/to/augmented_profiles.csv"


def test_attach_function_tools_to_agent_graph(monkeypatch, tmp_path):
    """attach_function_tools_to_agent_graph bindet CAMEL-FunctionTools an Agenten."""
    config = {"enable_agent_tools": True}
    runner = _create_runner_instance(config, tmp_path)
    runner.agent_graph = MagicMock()

    with patch.object(pr_module, "AGENT_TOOLS_AVAILABLE", True), \
         patch.object(pr_module, "build_camel_function_tools") as mock_build, \
         patch.object(pr_module, "attach_tools_to_agents") as mock_attach:
        mock_build.return_value = [MagicMock()]
        mock_attach.return_value = 5

        attached = runner.attach_function_tools_to_agent_graph()
        assert attached == 5
        mock_build.assert_called_once_with(config)
        mock_attach.assert_called_once_with(runner.agent_graph, mock_build.return_value)


@pytest.mark.asyncio
async def test_round_zero_emits_to_redis_and_logs_with_real_post_id(tmp_path):
    """Runde 0 liest Aktionen via fetch_new_actions_from_db und emittiert PostCreatedEvent."""
    config = {
        "simulation_id": "test-sim-001",
        "event_config": {
            "initial_posts": [{"poster_agent_id": 0, "content": "Initial post content"}]
        },
        "time_config": {"total_simulation_hours": 1, "minutes_per_round": 30},
    }
    runner = _create_runner_instance(config, tmp_path, platform_slug="twitter")
    runner.env = MagicMock()
    runner.env.reset = AsyncMock()
    runner.env.step = AsyncMock()
    runner.env.close = AsyncMock()
    runner.env.agent_graph = MagicMock()
    runner.env.agent_graph.get_agent.return_value = MagicMock()

    db_actions = [{
        "agent_id": 0,
        "agent_name": "agent_0",
        "action_type": "CREATE_POST",
        "action_args": {"content": "Initial post content", "post_id": 42},
    }]

    with patch("sim_runtime.platform_runner.fetch_new_actions_from_db", return_value=(db_actions, 1)), \
         patch("sim_runtime.platform_runner._emit_post_created_to_redis", new_callable=AsyncMock) as mock_emit, \
         patch("sim_runtime.platform_runner.PlatformActionLogger") as mock_logger_cls:

        mock_action_logger = mock_logger_cls.return_value

        with patch.object(runner, "_create_model", return_value=MagicMock()), \
             patch("sim_runtime.platform_runner.preflight_model_probe"), \
             patch("sim_runtime.platform_runner.oasis.make", return_value=runner.env), \
             patch("os.remove"), \
             patch.object(runner, "GRAPH_GENERATOR", AsyncMock(return_value=runner.env.agent_graph)):

            runner.GRAPH_GENERATOR = AsyncMock(return_value=runner.env.agent_graph)
            # Führen max_rounds=0 aus, um nur Runde 0 zu durchlaufen
            await runner.run(max_rounds=0)

            # Prüfen, dass action_logger.log_action mit post_id 42 aufgerufen wurde
            mock_action_logger.log_action.assert_called_with(
                round_num=0,
                agent_id=0,
                agent_name="agent_0",
                action_type="CREATE_POST",
                action_args={"content": "Initial post content", "post_id": 42},
            )

            # Prüfen, dass _emit_post_created_to_redis aufgerufen wurde
            mock_emit.assert_called_once()
            _, kwargs = mock_emit.call_args
            assert kwargs["simulation_id"] == "test-sim-001"
            assert kwargs["platform"] == "twitter"
            assert kwargs["round_num"] == 0
            assert kwargs["action_data"]["action_args"]["post_id"] == 42


@pytest.mark.asyncio
async def test_regular_rounds_emit_to_redis(tmp_path):
    """Reguläre Runden emittieren CREATE_POST/REPOST/QUOTE_POST (Twitter) an Redis."""
    config = {
        "simulation_id": "test-sim-002",
        "time_config": {"total_simulation_hours": 1, "minutes_per_round": 30},
    }
    runner = _create_runner_instance(config, tmp_path, platform_slug="twitter")
    runner.env = MagicMock()
    runner.env.reset = AsyncMock()
    runner.env.step = AsyncMock()
    runner.env.close = AsyncMock()
    agent_mock = MagicMock()
    runner.env.agent_graph = MagicMock()
    runner.env.agent_graph.get_agent.return_value = agent_mock

    # Mock active agents in round 1
    runner._get_active_agents_for_round = MagicMock(return_value=[(0, agent_mock)])

    # Mock DB actions in round 1
    round_actions = [
        {"agent_id": 0, "agent_name": "agent_0", "action_type": "CREATE_POST", "action_args": {"content": "Post", "post_id": 101}},
        {"agent_id": 0, "agent_name": "agent_0", "action_type": "LIKE_POST", "action_args": {"post_id": 50}},
        {"agent_id": 0, "agent_name": "agent_0", "action_type": "REPOST", "action_args": {"post_id": 70, "new_post_id": 102}},
    ]

    with patch.object(runner, "_log_round_actions") as mock_log_round, \
         patch("sim_runtime.platform_runner._emit_post_created_to_redis", new_callable=AsyncMock) as mock_emit, \
         patch.object(runner, "_create_model", return_value=MagicMock()), \
         patch("sim_runtime.platform_runner.preflight_model_probe"), \
         patch("sim_runtime.platform_runner.oasis.make", return_value=runner.env), \
         patch("os.remove"), \
         patch.object(runner, "GRAPH_GENERATOR", AsyncMock(return_value=runner.env.agent_graph)):

        runner.GRAPH_GENERATOR = AsyncMock(return_value=runner.env.agent_graph)

        def side_effect_log(*args, **kwargs):
            runner._last_round_actions = round_actions
            return len(round_actions), 10

        mock_log_round.side_effect = side_effect_log

        await runner.run(max_rounds=1)

        # LIKE_POST darf nicht emittiert werden, CREATE_POST und REPOST aber schon (2 Aufrufe)
        assert mock_emit.call_count == 2
        emitted_types = [call.kwargs["action_data"]["action_type"] for call in mock_emit.call_args_list]
        assert emitted_types == ["CREATE_POST", "REPOST"]
