"""Tests für POST /api/runs/<id>/resume und POST /api/runs/<id>/stop.

Sub-Slice 35 / Task 28 / Layer 7 — Closes #64.

Abgedeckte Szenarien (Negativpfade; keine echten Dispatcher-Calls):
  1  POST /api/runs/does-not-exist/resume → 404
  2  POST /api/runs/<id>/resume mit unbekanntem run_type → 409
  3  POST /api/runs/none/stop → 400 (ungültiges Format) bzw. 404
  4  POST /api/runs/<id>/stop mit run_type="graph_build" → 409
  5  POST /api/runs/<id>/stop mit simulation_run aber ohne linked simulation_id → 409
  6  Resume 409-Pfad liefert {success:false, error:...}-Envelope
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
        "artifact_store": artifact_store,
    }

    RunRegistry._instance = None


def _create_run(
    registry: RunRegistry,
    *,
    run_type: str = "simulation_run",
    entity_id: str = "sim_test",
    simulation_id: str | None = "sim_test",
    project_id: str = "proj_test",
    status: str = "completed",
    message: str = "ok",
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
# Test 1: Resume auf nicht-existierenden Run → 404
# ---------------------------------------------------------------------------

def test_resume_unknown_run_returns_404(env):
    # run_[12 hex chars] — gültiges Format, aber kein solcher Eintrag im Registry
    resp = env["client"].post("/api/runs/run_000000000000/resume")

    assert resp.status_code == 404
    payload = resp.get_json()
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# Test 2: Resume mit unbekanntem run_type → 409
# ---------------------------------------------------------------------------

def test_resume_unsupported_run_type_returns_409(env):
    run = _create_run(env["registry"], run_type="custom_xyz", status="stopped")

    resp = env["client"].post(f"/api/runs/{run['run_id']}/resume")

    assert resp.status_code == 409
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Unsupported run type" in payload.get("error", "")


# ---------------------------------------------------------------------------
# Test 3: Stop auf nicht-existierenden Run
# ---------------------------------------------------------------------------

def test_stop_unknown_run_returns_404(env):
    # Ungültiges ID-Format → 400; gültiges Format aber kein Eintrag → 404.
    # Wir testen beides: einmal ungültiges Format, einmal gültiges aber fehlendes.
    resp_bad_format = env["client"].post("/api/runs/none/stop")
    assert resp_bad_format.status_code == 400

    resp_missing = env["client"].post("/api/runs/run_aabbccddeeff/stop")
    assert resp_missing.status_code == 404
    payload = resp_missing.get_json()
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# Test 4: Stop auf run_type != simulation_run → 409
# ---------------------------------------------------------------------------

def test_stop_non_simulation_run_returns_409(env):
    run = _create_run(env["registry"], run_type="graph_build", status="processing")

    resp = env["client"].post(f"/api/runs/{run['run_id']}/stop")

    assert resp.status_code == 409
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Stop is only supported for simulation_run" in payload.get("error", "")


# ---------------------------------------------------------------------------
# Test 5: Stop auf simulation_run ohne linked simulation_id → 409
# ---------------------------------------------------------------------------

def test_stop_simulation_run_without_simulation_id_returns_409(env):
    run = _create_run(
        env["registry"],
        run_type="simulation_run",
        status="processing",
        linked_ids={"project_id": "proj_test"},  # deliberate: kein simulation_id
    )

    resp = env["client"].post(f"/api/runs/{run['run_id']}/stop")

    assert resp.status_code == 409
    payload = resp.get_json()
    assert payload["success"] is False
    assert "missing simulation_id linkage" in payload.get("error", "")


# ---------------------------------------------------------------------------
# Test 6: Resume-Fehler liefert {success:false, error:...}-Envelope
# ---------------------------------------------------------------------------

def test_resume_response_uses_json_success_envelope(env):
    """Prüft, dass der handle_api_errors-Decorator auf /resume greift.

    Wir triggern den 409-Pfad (unbekannter run_type), da dieser von
    resume_run() als json_error zurückgegeben wird und dennoch das
    Standard-Envelope nutzt — ohne einen echten Dispatcher zu starten.
    """
    run = _create_run(env["registry"], run_type="unsupported_type", status="failed")

    resp = env["client"].post(f"/api/runs/{run['run_id']}/resume")

    assert resp.status_code == 409
    payload = resp.get_json()
    # Pflicht-Envelope-Felder
    assert "success" in payload
    assert payload["success"] is False
    assert "error" in payload
    # Kein Leer-String
    assert payload["error"]
