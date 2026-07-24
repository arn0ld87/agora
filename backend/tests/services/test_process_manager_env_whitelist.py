"""Tests für die SAFE_ENV_KEYS-Whitelist im Subprozess-Env (PR 4 Hardening §1.6)."""
from __future__ import annotations

from unittest.mock import MagicMock


from app.services.sim import process_manager
from app.services.sim.process_manager import SAFE_ENV_KEYS


def _run_start_simulation(tmp_path, monkeypatch, runtime_env=None):
    """Hilfsfunktion: startet eine Simulation und gibt das captured env zurück."""
    script_path = tmp_path / "run_parallel_simulation.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    sim_dir = tmp_path / "sim_whitelist"
    sim_dir.mkdir()
    (sim_dir / "simulation_config.json").write_text("{}", encoding="utf-8")

    captured_env: dict = {}

    class FakeProcess:
        pid = 99999

    def fake_popen(*args, **kwargs):
        captured_env.update(kwargs["env"])
        return FakeProcess()

    monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

    process_manager.start_simulation(
        "sim_whitelist",
        "parallel",
        run_state_dir=str(tmp_path),
        scripts_dir=str(tmp_path),
        processes={},
        action_queues={},
        monitor_threads={},
        stdout_files={},
        stderr_files={},
        graph_memory_enabled={},
        get_run_state=lambda _: None,
        save_state=MagicMock(),
        on_monitor_start=MagicMock(),
        write_control_state=MagicMock(),
        get_config=lambda _: {
            "time_config": {
                "total_simulation_hours": 1,
                "minutes_per_round": 60,
            }
        },
        config_exists=lambda _: True,
        setup_graph_memory=MagicMock(),
        runtime_env=runtime_env or {},
    )
    return captured_env


class TestSubprocessEnvExcludesSecrets:
    def test_subprocess_env_excludes_secrets(self, tmp_path, monkeypatch):
        """SECRET_KEY, AGORA_AUTH_TOKEN, NEO4J_PASSWORD, LLM_API_KEY werden NICHT vererbt."""
        monkeypatch.setenv("SECRET_KEY", "super-secret-flask-key")
        monkeypatch.setenv("AGORA_AUTH_TOKEN", "agora-master-token")
        monkeypatch.setenv("NEO4J_PASSWORD", "neo4j-database-password")
        monkeypatch.setenv("LLM_API_KEY", "sk-envleak-secret")

        captured = _run_start_simulation(tmp_path, monkeypatch)

        assert "SECRET_KEY" not in captured
        assert "AGORA_AUTH_TOKEN" not in captured
        assert "NEO4J_PASSWORD" not in captured
        # LLM_API_KEY ohne runtime_env darf nicht im Env landen
        assert "LLM_API_KEY" not in captured

    def test_subprocess_env_includes_whitelisted_runtime_keys(self, tmp_path, monkeypatch):
        """Whitelisted Keys (LLM_BASE_URL, OLLAMA_THINKING, TZ) werden korrekt übernommen."""
        monkeypatch.setenv("LLM_BASE_URL", "https://ollama.local/v1")
        monkeypatch.setenv("OLLAMA_THINKING", "false")
        monkeypatch.setenv("TZ", "Europe/Berlin")

        captured = _run_start_simulation(tmp_path, monkeypatch)

        assert captured.get("LLM_BASE_URL") == "https://ollama.local/v1"
        assert captured.get("OLLAMA_THINKING") == "false"
        assert captured.get("TZ") == "Europe/Berlin"

    def test_runtime_env_overrides_whitelist(self, tmp_path, monkeypatch):
        """runtime_env-Werte überschreiben os.environ für gleiche Keys."""
        monkeypatch.setenv("LLM_BASE_URL", "https://env-value.local/v1")

        captured = _run_start_simulation(
            tmp_path,
            monkeypatch,
            runtime_env={"LLM_BASE_URL": "https://override.local/v1"},
        )

        assert captured.get("LLM_BASE_URL") == "https://override.local/v1"

    def test_runtime_env_can_pass_api_key(self, tmp_path, monkeypatch):
        """LLM_API_KEY via runtime_env landet im Subprozess (explizite Übergabe erlaubt)."""
        captured = _run_start_simulation(
            tmp_path,
            monkeypatch,
            runtime_env={"LLM_API_KEY": "runtime-api-key"},
        )

        assert captured.get("LLM_API_KEY") == "runtime-api-key"

    def test_safe_env_keys_constant_excludes_secrets(self):
        """SAFE_ENV_KEYS enthält keine bekannten Secret-Keys."""
        forbidden = {"SECRET_KEY", "AGORA_AUTH_TOKEN", "NEO4J_PASSWORD", "AGORA_FERNET_KEY"}
        overlap = SAFE_ENV_KEYS & forbidden
        assert not overlap, f"SAFE_ENV_KEYS enthält verbotene Keys: {overlap}"


class TestSubprocessEnvIncludesOptionalConnectionKeys:
    """RED-Tests: Optionale Connection-Keys (REDIS_URL, HF_TOKEN) müssen
    vererbbar sein, damit die Redis-IPC-Bridge und Hugging-Face-Downloads
    im OASIS-Subprozess funktionieren.

    Hintergrund: Ohne REDIS_URL war die Redis-Bridge im Subprozess
    inaktiv; ohne HF_TOKEN schlugen private HF-Modelle fehl.
    """

    def test_safe_env_keys_includes_redis_url(self) -> None:
        """REDIS_URL muss in SAFE_ENV_KEYS sein, sonst bleibt die Redis-Bridge im Subprozess stumm."""
        assert "REDIS_URL" in SAFE_ENV_KEYS, (
            "REDIS_URL fehlt in SAFE_ENV_KEYS — Redis-Bridge im OASIS-Subprozess funktioniert nicht"
        )

    def test_safe_env_keys_includes_hf_token(self) -> None:
        """HF_TOKEN muss in SAFE_ENV_KEYS sein, sonst scheitern private HF-Modell-Loads."""
        assert "HF_TOKEN" in SAFE_ENV_KEYS, (
            "HF_TOKEN fehlt in SAFE_ENV_KEYS — private Hugging-Face-Modelle laden nicht"
        )

    def test_subprocess_env_includes_redis_url(self, tmp_path, monkeypatch) -> None:
        """REDIS_URL aus os.environ landet via Whitelist im Subprozess-Env."""
        monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
        captured = _run_start_simulation(tmp_path, monkeypatch)
        assert captured.get("REDIS_URL") == "redis://redis:6379/0"

    def test_subprocess_env_includes_hf_token(self, tmp_path, monkeypatch) -> None:
        """HF_TOKEN aus os.environ landet via Whitelist im Subprozess-Env."""
        monkeypatch.setenv("HF_TOKEN", "hf_testtoken123")
        captured = _run_start_simulation(tmp_path, monkeypatch)
        assert captured.get("HF_TOKEN") == "hf_testtoken123"
