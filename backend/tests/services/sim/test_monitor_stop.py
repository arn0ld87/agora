"""Regressionstests für den B2-Fix (Issue-Review 2026-09-07): Nutzer-Stop
endet als stopped/user_stop statt fälschlich failed/error.

Vor dem Fix schrieb ``process_manager.stop_simulation`` keinen Marker vor
dem Terminieren des Subprozesses. Der Monitor-Thread kannte nur den
cancel_abort-Marker aus dem Cancel-Flag-Konsum (``source="backend-monitor"``)
und klassifizierte einen per SIGTERM beendeten Prozess (returncode -15) im
FAILED-Zweig — der Nutzer sah eine fehlgeschlagene statt eine gestoppte
Simulation, mit ``termination_reason="error"`` statt ``"user_stop"``.

Folgt dem etablierten Registry-/Manifest-Test-Muster aus
test_monitor_cancel.py (echte RunRegistry gegen ein Tempdir statt eines
Mocks, weil monitor.py RunRegistry innerhalb der Funktion importiert) und
test_monitor_manifest_finalize.py (Draft-Manifest + finales manifest.json).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime

import pytest

from app.services.manifest_capture import ManifestCapture
from app.services.run_registry import RunRegistry
from app.services.sim.monitor import monitor_simulation
from app.services.sim.process_manager import stop_simulation
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState

SIM_ID = "sim_stop_1"


@pytest.fixture()
def stop_env(tmp_path, monkeypatch):
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    monkeypatch.setenv("AGORA_INSTANCE_DIR", str(tmp_path))
    RunRegistry._instance = None
    monkeypatch.setattr(
        "app.services.simulation_ipc.write_control_state",
        lambda sim_id, **changes: changes,
    )
    yield tmp_path
    RunRegistry._instance = None


def _create_sim_run_with_draft(tmp_path) -> str:
    """RunRegistry-Eintrag + Draft-Manifest anlegen (Muster aus
    test_monitor_manifest_finalize.py::_create_run_with_draft)."""
    run = RunRegistry().create_run(
        "simulation_run",
        SIM_ID,
        linked_ids={"simulation_id": SIM_ID},
    )
    run_id = run["run_id"]

    run_dir = os.path.join(str(tmp_path), "runs", run_id)
    ManifestCapture.capture_draft(
        run_id=run_id,
        run_dir=run_dir,
        seed_document_hash="sha256:abc",
        seed_document_filename="test.md",
        simulation_config_hash="sha256:def",
        graph_id="graph_001",
        agora_version="0.9.5",
        schema_version="1.0.0",
        random_seed=42,
        simulation_id_seed=SIM_ID,
    )
    return run_id


class _FinishedProcess:
    """Bereits beendeter Prozess mit SIGTERM-typischem Exit-Code."""

    returncode = -15

    def poll(self):
        return self.returncode


class TestStopEndsAsUserStop:
    def test_stop_simulation_ends_as_stopped_with_user_stop_reason(self, stop_env):
        """Kern-Regression B2: echter Subprozess, per SIGTERM gestoppt,
        landet als STOPPED/user_stop — nicht FAILED/error — in Run-State,
        RunRegistry UND dem finalisierten Manifest."""
        tmp_path = stop_env
        run_id = _create_sim_run_with_draft(tmp_path)
        run_state_dir = str(tmp_path / "sims")
        sim_dir = tmp_path / "sims" / SIM_ID
        sim_dir.mkdir(parents=True)

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
        )
        processes = {SIM_ID: proc}
        state = SimulationRunState(
            simulation_id=SIM_ID,
            runner_status=RunnerStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )

        try:
            stop_simulation(
                SIM_ID,
                run_state_dir=run_state_dir,
                processes=processes,
                graph_memory_enabled={},
                get_run_state=lambda sim_id: state,
                save_state=lambda s: None,
                stop_graph_memory_updater=lambda sim_id: None,
            )
            assert state.runner_status == RunnerStatus.STOPPED

            # Monitor sieht den (von stop_simulation bereits per SIGTERM
            # beendeten) Prozess und muss ihn ueber den user_stop-Marker
            # als STOPPED erkennen, nicht als FAILED klassifizieren.
            monitor_simulation(
                SIM_ID,
                run_state_dir=run_state_dir,
                processes=processes,
                graph_memory_enabled={},
                action_queues={},
                stdout_files={},
                stderr_files={},
                get_run_state=lambda sim_id: state,
                save_state=lambda s: None,
            )
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

        assert proc.returncode != 0
        assert state.runner_status == RunnerStatus.STOPPED

        registry_entry = RunRegistry().get_run(run_id)
        assert registry_entry["status"] == "stopped"
        assert registry_entry["termination_reason"] == "user_stop"

        manifest_path = os.path.join(str(tmp_path), "runs", run_id, "manifest.json")
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["status"] == "final"
        assert manifest["runtime"]["termination_reason"] == "user_stop"

    def test_cancel_marker_without_source_still_reports_user_cancel(self, stop_env):
        """Rueckwaertskompatibilitaet: ein Marker ohne (oder mit unbekanntem)
        'source' bleibt beim bisherigen Verhalten user_cancel — deckt sowohl
        fehlende alte Marker als auch source='backend-monitor' ab."""
        tmp_path = stop_env
        run_id = _create_sim_run_with_draft(tmp_path)
        run_state_dir = str(tmp_path / "sims")
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
            run_state_dir=run_state_dir,
            processes={SIM_ID: _FinishedProcess()},
            graph_memory_enabled={},
            action_queues={},
            stdout_files={},
            stderr_files={},
            get_run_state=lambda sim_id: state,
            save_state=lambda s: None,
        )

        assert state.runner_status == RunnerStatus.STOPPED
        registry_entry = RunRegistry().get_run(run_id)
        assert registry_entry["status"] == "stopped"
        assert registry_entry["termination_reason"] == "user_cancel"

        manifest_path = os.path.join(str(tmp_path), "runs", run_id, "manifest.json")
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["runtime"]["termination_reason"] == "user_cancel"
