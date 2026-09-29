"""Route-Tests fuer ``GET /api/simulation/<id>`` (Issue #1713 Slice S2).

Vor dem Fix lieferte die Route unveraendert ``SimulationState.to_dict()``:
``status`` blieb "running", auch nachdem der Monitor die Simulation laengst
terminalisiert hatte (nur ``run_state.json``'s ``runner_status`` wird
gesetzt). Diese Tests bewachen die Read-Time-Projektion an der API-Grenze.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.services.simulation_manager import SimulationState, SimulationStatus
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState

SIM_ID = "sim_0123456789ab"


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


def _state(status: SimulationStatus) -> SimulationState:
    return SimulationState(
        simulation_id=SIM_ID,
        project_id="proj-1",
        graph_id="graph-1",
        status=status,
    )


def _patch_manager(monkeypatch, state: SimulationState) -> MagicMock:
    fake_manager = MagicMock()
    fake_manager.get_simulation.return_value = state
    fake_manager.get_run_instructions.return_value = {"simulation_dir": "/tmp/x"}
    monkeypatch.setattr(
        "app.api.simulation_lifecycle.SimulationManager",
        lambda *args, **kwargs: fake_manager,
    )
    return fake_manager


def _patch_runner(monkeypatch, runner_status: RunnerStatus | None, *, env_alive: bool = False) -> None:
    run_state = (
        SimulationRunState(simulation_id=SIM_ID, runner_status=runner_status)
        if runner_status is not None
        else None
    )
    monkeypatch.setattr(
        "app.api.simulation_lifecycle.SimulationRunner.get_run_state",
        classmethod(lambda cls, sid: run_state),
    )
    monkeypatch.setattr(
        "app.api.simulation_lifecycle.SimulationRunner.check_env_alive",
        classmethod(lambda cls, sid: env_alive),
    )


def test_running_with_completed_runner_reports_completed(client, monkeypatch):
    _patch_manager(monkeypatch, _state(SimulationStatus.RUNNING))
    _patch_runner(monkeypatch, RunnerStatus.COMPLETED, env_alive=False)

    response = client.get(f"/api/simulation/{SIM_ID}")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["status"] == "completed"
    assert body["runner_status"] == "completed"
    assert body["interview_env_alive"] is False


def test_running_with_failed_runner_reports_failed(client, monkeypatch):
    _patch_manager(monkeypatch, _state(SimulationStatus.RUNNING))
    _patch_runner(monkeypatch, RunnerStatus.FAILED)

    response = client.get(f"/api/simulation/{SIM_ID}")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "failed"


def test_persisted_failed_status_stays_failed_when_runner_completed(client, monkeypatch):
    """Persistierter FAILED-Zustand darf nicht durch einen abweichenden
    Runner-Status (COMPLETED) ueberschrieben werden — nur RUNNING wird
    projiziert."""
    _patch_manager(monkeypatch, _state(SimulationStatus.FAILED))
    _patch_runner(monkeypatch, RunnerStatus.COMPLETED)

    response = client.get(f"/api/simulation/{SIM_ID}")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "failed"


def test_no_run_state_leaves_running_status_unchanged(client, monkeypatch):
    _patch_manager(monkeypatch, _state(SimulationStatus.RUNNING))
    _patch_runner(monkeypatch, None)

    response = client.get(f"/api/simulation/{SIM_ID}")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["status"] == "running"
    assert body["runner_status"] is None


def test_ready_status_still_includes_run_instructions(client, monkeypatch):
    _patch_manager(monkeypatch, _state(SimulationStatus.READY))
    _patch_runner(monkeypatch, None)

    response = client.get(f"/api/simulation/{SIM_ID}")

    assert response.status_code == 200
    body = response.get_json()["data"]
    assert body["status"] == "ready"
    assert body["run_instructions"] == {"simulation_dir": "/tmp/x"}


def test_interview_env_alive_reflects_check_env_alive(client, monkeypatch):
    _patch_manager(monkeypatch, _state(SimulationStatus.RUNNING))
    _patch_runner(monkeypatch, RunnerStatus.RUNNING, env_alive=True)

    response = client.get(f"/api/simulation/{SIM_ID}")

    assert response.status_code == 200
    body = response.get_json()["data"]
    # RunnerStatus.RUNNING ist nicht terminal → status bleibt "running".
    assert body["status"] == "running"
    assert body["interview_env_alive"] is True
