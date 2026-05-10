from __future__ import annotations

from unittest.mock import MagicMock

from app.services.sim import process_manager


def test_process_manager_applies_runtime_env_without_persisting_secret(tmp_path, monkeypatch):
    script_path = tmp_path / "run_parallel_simulation.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    sim_dir = tmp_path / "sim_runtime"
    sim_dir.mkdir()
    (sim_dir / "simulation_config.json").write_text("{}", encoding="utf-8")

    captured_env = {}

    class FakeProcess:
        pid = 12345

    def fake_popen(*args, **kwargs):
        captured_env.update(kwargs["env"])
        return FakeProcess()

    monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

    state = process_manager.start_simulation(
        "sim_runtime",
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
        runtime_env={
            "LLM_API_KEY": "runtime-secret",
            "OPENAI_API_KEY": "runtime-secret",
            "LLM_BASE_URL": "https://example.test/v1",
        },
    )

    assert state.process_pid == 12345
    assert captured_env["LLM_API_KEY"] == "runtime-secret"
    assert captured_env["OPENAI_API_KEY"] == "runtime-secret"
    assert captured_env["LLM_BASE_URL"] == "https://example.test/v1"
    assert "runtime-secret" not in (sim_dir / "simulation_config.json").read_text(encoding="utf-8")
