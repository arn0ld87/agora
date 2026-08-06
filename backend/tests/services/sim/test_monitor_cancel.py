"""Regressionstests für den Cancel-Durchgriff auf laufende Simulationen (Issue #1082).

Vor dem Fix setzte ``POST /api/runs/<id>/cancel`` für ``simulation_run`` nur ein
prozesslokales Flag, das kein Consumer las — der OASIS-Subprozess lief weiter.
Diese Tests assertieren Worker-Terminierung, nicht nur das gesetzte Flag.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime

import pytest

from app.services.run_registry import RunRegistry
from app.services.sim.cancel_flag import (
    clear_cancel,
    is_cancel_requested,
    request_cancel,
)
from app.services.sim.monitor import monitor_simulation
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState

SIM_ID = "sim_cancel_1"


@pytest.fixture()
def cancel_env(tmp_path, monkeypatch):
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    RunRegistry._instance = None
    stop_calls = []
    monkeypatch.setattr(
        "app.services.simulation_ipc.write_control_state",
        lambda sim_id, **changes: stop_calls.append((sim_id, changes)) or changes,
    )
    yield tmp_path, stop_calls
    RunRegistry._instance = None


def _create_sim_run() -> str:
    manifest = RunRegistry().create_run(
        "simulation_run",
        SIM_ID,
        linked_ids={"simulation_id": SIM_ID},
    )
    return manifest["run_id"]


class _FinishedProcess:
    """Bereits beendeter Prozess mit SIGTERM-typischem Exit-Code."""

    returncode = -15

    def poll(self):
        return self.returncode


class TestCancelSupervision:
    def test_cancel_terminates_running_subprocess(self, cancel_env):
        """Kern-Regression: Cancel beendet den laufenden Subprozess nachweislich."""
        tmp_path, _ = cancel_env
        run_id = _create_sim_run()
        sim_dir = tmp_path / "sims" / SIM_ID
        sim_dir.mkdir(parents=True)

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(8)"],
            start_new_session=True,
        )
        try:
            request_cancel(run_id)
            state = SimulationRunState(
                simulation_id=SIM_ID,
                runner_status=RunnerStatus.RUNNING,
                started_at=datetime.now().isoformat(),
            )
            monitor_simulation(
                SIM_ID,
                run_state_dir=str(tmp_path / "sims"),
                processes={SIM_ID: proc},
                graph_memory_enabled={},
                action_queues={},
                stdout_files={},
                stderr_files={},
                get_run_state=lambda sim_id: state,
                save_state=lambda s: None,
            )
        finally:
            clear_cancel(run_id)
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

        # Ohne Durchgriff liefe der Prozess bis zum natürlichen Ende
        # (exit 0 → COMPLETED) — genau der Defekt aus #1082.
        assert proc.returncode != 0
        assert state.runner_status == RunnerStatus.STOPPED
        manifest = RunRegistry().get_run(run_id)
        assert manifest["status"] == "stopped"
        assert manifest["termination_reason"] == "user_cancel"
        assert is_cancel_requested(run_id) is False

    def test_cancel_marker_beats_nonzero_exit(self, cancel_env):
        """SIGTERM-Exit wird nicht als FAILED fehlklassifiziert."""
        tmp_path, _ = cancel_env
        run_id = _create_sim_run()
        sim_dir = tmp_path / "sims" / SIM_ID
        sim_dir.mkdir(parents=True)
        (sim_dir / "cancel_abort.json").write_text(
            json.dumps({"run_id": run_id, "source": "backend-monitor"})
        )
        state = SimulationRunState(
            simulation_id=SIM_ID,
            runner_status=RunnerStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )
        monitor_simulation(
            SIM_ID,
            run_state_dir=str(tmp_path / "sims"),
            processes={SIM_ID: _FinishedProcess()},
            graph_memory_enabled={},
            action_queues={},
            stdout_files={},
            stderr_files={},
            get_run_state=lambda sim_id: state,
            save_state=lambda s: None,
        )
        assert state.runner_status == RunnerStatus.STOPPED
        assert state.error is None
        manifest = RunRegistry().get_run(run_id)
        assert manifest["status"] == "stopped"
        assert manifest["termination_reason"] == "user_cancel"
