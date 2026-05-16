"""Tests für POST /api/runs/<run_id>/cancel.

Abgedeckte Szenarien:
  1  202 bei valider Cancel-Request (Run im Status 'processing')
  2  400 wenn Run nicht im Status 'processing'
  3  404 bei unbekannter run_id
  4  409 wenn Run kein simulation_id-Linkage hat
  5  Cancel-Flag wird nach dem Endpoint-Call gesetzt
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from flask import Flask

from app.api import runs_bp
from app.config import Config
from app.models.project import ProjectManager
from app.services.artifact_store import InMemoryArtifactStore
from app.services.run_registry import RunRegistry
from app.services.sim.cancel_flag import clear_cancel, is_cancel_requested
from app.services.simulation_manager import SimulationManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))
    monkeypatch.setattr(
        SimulationManager, "SIMULATION_DATA_DIR", str(upload_root / "simulations")
    )
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(upload_root / "run_registry"))
    RunRegistry._instance = None
    os.makedirs(RunRegistry.REGISTRY_DIR, exist_ok=True)

    artifact_store = InMemoryArtifactStore()

    app = Flask(__name__)
    app.extensions = {"artifact_store": artifact_store}
    app.register_blueprint(runs_bp, url_prefix="/api/runs")

    registry = RunRegistry()

    yield {
        "app": app,
        "client": app.test_client(),
        "registry": registry,
    }

    RunRegistry._instance = None


def _create_run(
    registry: RunRegistry,
    *,
    run_type: str = "simulation_run",
    entity_id: str = "sim_test",
    simulation_id: str | None = "sim_test",
    project_id: str = "proj_test",
    status: str = "processing",
    message: str = "Running",
    metadata: dict[str, Any] | None = None,
    linked_ids: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if linked_ids is None:
        linked_ids = {}
        if simulation_id is not None:
            linked_ids["simulation_id"] = simulation_id
        linked_ids["project_id"] = project_id

    return registry.create_run(
        run_type=run_type,
        entity_id=entity_id,
        status=status,
        message=message,
        linked_ids=linked_ids,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Test 1: 202 bei valider Cancel-Request
# ---------------------------------------------------------------------------


def test_cancel_processing_run_returns_202(env):
    run = _create_run(env["registry"], status="processing")
    run_id = run["run_id"]

    # Sicherstellen, dass kein altes Flag existiert
    clear_cancel(run_id)

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")

    assert resp.status_code == 202, f"Erwartet 202, erhalten: {resp.status_code} — {resp.get_json()}"
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["status"] == "cancel_requested"
    assert payload["run_id"] == run_id


# ---------------------------------------------------------------------------
# Test 2: 400 wenn Run nicht im Status 'processing'
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_status", ["completed", "failed", "stopped", "pending"])
def test_cancel_non_processing_run_returns_400(env, bad_status):
    run = _create_run(env["registry"], status=bad_status)

    resp = env["client"].post(f"/api/runs/{run['run_id']}/cancel")

    assert resp.status_code == 400, f"Erwartet 400 für status={bad_status!r}"
    payload = resp.get_json()
    assert payload["success"] is False
    assert "not in 'processing'" in payload.get("error", "")


# ---------------------------------------------------------------------------
# Test 3: 404 bei unbekannter run_id
# ---------------------------------------------------------------------------


def test_cancel_unknown_run_returns_404(env):
    resp = env["client"].post("/api/runs/run_000000000000/cancel")
    assert resp.status_code == 404
    payload = resp.get_json()
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# Test 4: 409 wenn kein simulation_id-Linkage
# ---------------------------------------------------------------------------


def test_cancel_run_without_simulation_id_returns_409(env):
    run = _create_run(
        env["registry"],
        status="processing",
        linked_ids={"project_id": "proj_test"},  # kein simulation_id
    )

    resp = env["client"].post(f"/api/runs/{run['run_id']}/cancel")

    assert resp.status_code == 409
    payload = resp.get_json()
    assert payload["success"] is False
    assert "simulation_id" in payload.get("error", "")


# ---------------------------------------------------------------------------
# Test 5: Cancel-Flag wird nach Endpoint-Call gesetzt
# ---------------------------------------------------------------------------


def test_cancel_sets_cancel_flag(env):
    run = _create_run(env["registry"], status="processing")
    run_id = run["run_id"]
    clear_cancel(run_id)

    assert not is_cancel_requested(run_id), "Flag darf vor dem Call nicht gesetzt sein"

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 202

    assert is_cancel_requested(run_id), "Flag muss nach dem Call gesetzt sein"

    # Cleanup
    clear_cancel(run_id)
