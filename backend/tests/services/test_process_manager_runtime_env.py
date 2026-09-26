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


def test_process_manager_passes_workspace_secret_via_pipe_not_env(tmp_path, monkeypatch):
    """Finding B1 (#1688): trägt ``runtime_env`` den privaten
    ``WORKSPACE_SECRET_ENV_MARKER`` (wie ``build_route_subprocess_env`` ihn
    für einen Workspace-Run setzt), darf weder der Marker noch der
    Klartext-Key im an ``subprocess.Popen`` übergebenen Env-Block landen —
    stattdessen eine Lese-FD via ``pass_fds``, aus der sich exakt der
    JSON-Payload zurücklesen lässt."""
    import json
    import os

    from app.services.llm_routing_seed import WORKSPACE_SECRET_ENV_MARKER

    script_path = tmp_path / "run_parallel_simulation.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    sim_dir = tmp_path / "sim_secret_pipe"
    sim_dir.mkdir()
    (sim_dir / "simulation_config.json").write_text("{}", encoding="utf-8")

    captured = {}

    class FakeProcess:
        pid = 54321

    def fake_popen(*args, **kwargs):
        captured["env"] = dict(kwargs["env"])
        pass_fds = kwargs.get("pass_fds", ())
        captured["pass_fds"] = pass_fds
        # Wie ein echtes exec()ed Kind: die Pipe-FD hier lesen, BEVOR der
        # Elternprozess (process_manager) seine eigene Kopie schliesst — im
        # echten Ablauf haelt genau das exec() im Kind die FD offen.
        if pass_fds:
            captured["secret_bytes"] = os.read(pass_fds[0], 4096)
        return FakeProcess()

    monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

    secret_payload = json.dumps({"LLM_API_KEY": "ws-secret-key", "OPENAI_API_KEY": "ws-secret-key"})

    process_manager.start_simulation(
        "sim_secret_pipe",
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
            "time_config": {"total_simulation_hours": 1, "minutes_per_round": 60},
        },
        config_exists=lambda _: True,
        setup_graph_memory=MagicMock(),
        runtime_env={
            "LLM_BASE_URL": "https://api.openai.com/v1",
            WORKSPACE_SECRET_ENV_MARKER: secret_payload,
        },
    )

    env = captured["env"]
    pass_fds = captured["pass_fds"]
    assert WORKSPACE_SECRET_ENV_MARKER not in env
    assert "LLM_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    for value in env.values():
        assert "ws-secret-key" not in value
    assert pass_fds, "erwartete eine an pass_fds übergebene Lese-FD"
    assert env["AGORA_SECRET_ENV_FD"] == str(pass_fds[0])
    assert json.loads(captured["secret_bytes"].decode("utf-8")) == {
        "LLM_API_KEY": "ws-secret-key",
        "OPENAI_API_KEY": "ws-secret-key",
    }
