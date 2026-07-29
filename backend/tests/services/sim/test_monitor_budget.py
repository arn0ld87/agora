"""Tests für die Budget-Supervision im Simulations-Monitor (Issue #764)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app.services.run_registry import RunRegistry
from app.services.sim.monitor import (
    _budget_supervision,
    monitor_simulation,
)
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState
from app.services.run_usage_ledger import reset_usage_cache


@pytest.fixture()
def budget_env(tmp_path, monkeypatch):
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    RunRegistry._instance = None
    run_dirs = tmp_path / "runs"
    run_dirs.mkdir()
    monkeypatch.setattr(
        "app.services.run_usage_ledger.ArtifactLocator.run_dir",
        staticmethod(lambda run_id: str(run_dirs / run_id)),
    )
    monkeypatch.setattr(
        "app.services.run_budget.ArtifactLocator.run_dir",
        staticmethod(lambda run_id: str(run_dirs / run_id)),
    )
    stop_calls = []
    monkeypatch.setattr(
        "app.services.simulation_ipc.write_control_state",
        lambda sim_id, **changes: stop_calls.append((sim_id, changes)) or changes,
    )
    reset_usage_cache()
    yield tmp_path, stop_calls
    RunRegistry._instance = None
    reset_usage_cache()


def _create_sim_run(started_at: str | None = None, budget: dict | None = None) -> str:
    manifest = RunRegistry().create_run(
        "simulation_run",
        "sim_budget_1",
        linked_ids={"simulation_id": "sim_budget_1"},
        metadata={"budget": budget} if budget else None,
    )
    if started_at:
        raw = RunRegistry().get_run(manifest["run_id"])
        raw["started_at"] = started_at
        RunRegistry()._write_run(raw)
    return manifest["run_id"]


class TestBudgetSupervision:
    def test_existing_abort_marker_triggers_stop(self, budget_env):
        tmp_path, stop_calls = budget_env
        sim_dir = tmp_path / "sims" / "sim_budget_1"
        sim_dir.mkdir(parents=True)
        (sim_dir / "budget_abort.json").write_text(
            json.dumps({"dimension": "tokens", "observed": 5, "threshold": 4})
        )
        info = _budget_supervision("sim_budget_1", str(sim_dir))
        assert info is not None
        assert info["dimension"] == "tokens"
        assert stop_calls[0][1].get("stop_requested") is True

    def test_backend_time_budget_writes_marker(self, budget_env):
        tmp_path, stop_calls = budget_env
        sim_dir = tmp_path / "sims" / "sim_budget_1"
        sim_dir.mkdir(parents=True)
        past = (datetime.now() - timedelta(seconds=120)).isoformat()
        _create_sim_run(
            started_at=past,
            budget={"max_duration_seconds": 60, "enforcement": "hard"},
        )
        info = _budget_supervision("sim_budget_1", str(sim_dir))
        assert info is not None
        assert info["dimension"] == "time"
        marker = json.loads((sim_dir / "budget_abort.json").read_text())
        assert marker["dimension"] == "time"
        assert stop_calls[0][1].get("stop_requested") is True

    def test_no_budget_no_action(self, budget_env):
        tmp_path, stop_calls = budget_env
        sim_dir = tmp_path / "sims" / "sim_budget_1"
        sim_dir.mkdir(parents=True)
        _create_sim_run()
        assert _budget_supervision("sim_budget_1", str(sim_dir)) is None
        assert stop_calls == []


class _FinishedProcess:
    returncode = 0

    def poll(self):
        return self.returncode


class TestMonitorBudgetAbort:
    def test_budget_abort_marks_stopped_with_reason(self, budget_env, monkeypatch):
        tmp_path, _ = budget_env
        run_id = _create_sim_run()
        sim_dir = tmp_path / "sims" / "sim_budget_1"
        sim_dir.mkdir(parents=True)
        (sim_dir / "budget_abort.json").write_text(
            json.dumps({"dimension": "calls", "observed": 3, "threshold": 3})
        )

        state = SimulationRunState(
            simulation_id="sim_budget_1",
            runner_status=RunnerStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )
        saved = []

        monitor_simulation(
            "sim_budget_1",
            run_state_dir=str(tmp_path / "sims"),
            processes={"sim_budget_1": _FinishedProcess()},
            graph_memory_enabled={},
            action_queues={},
            stdout_files={},
            stderr_files={},
            get_run_state=lambda sim_id: state,
            save_state=lambda s: saved.append(s.runner_status),
        )

        assert state.runner_status == RunnerStatus.STOPPED
        assert state.error is None
        manifest = RunRegistry().get_run(run_id)
        assert manifest["status"] == "stopped"
        assert manifest["termination_reason"] == "budget_calls"

    def test_clean_exit_without_abort_stays_completed(self, budget_env):
        tmp_path, _ = budget_env
        _create_sim_run()
        sim_dir = tmp_path / "sims" / "sim_budget_1"
        sim_dir.mkdir(parents=True)

        state = SimulationRunState(
            simulation_id="sim_budget_1",
            runner_status=RunnerStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )
        monitor_simulation(
            "sim_budget_1",
            run_state_dir=str(tmp_path / "sims"),
            processes={"sim_budget_1": _FinishedProcess()},
            graph_memory_enabled={},
            action_queues={},
            stdout_files={},
            stderr_files={},
            get_run_state=lambda sim_id: state,
            save_state=lambda s: None,
        )
        assert state.runner_status == RunnerStatus.COMPLETED
