"""HTTP-level tests for ``backend/app/api/runs.py``.

Slice 3.1 (v0.7 Run Dashboard): adds the ``entity_id`` filter and a
read-path ``summary`` block on list/detail responses. The summary aggregates
project + simulation metadata that lives outside the run manifest, so the
tests pin the wiring (project files, simulation config, persona artefact)
through ``Config.UPLOAD_FOLDER`` and ``app.extensions['artifact_store']``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import pytest
from flask import Flask

from app.api import runs_bp
from app.config import Config
from app.models.project import Project, ProjectManager, ProjectStatus
from app.services.artifact_store import InMemoryArtifactStore
from app.services.run_registry import RunRegistry
from app.services.simulation_manager import SimulationManager, SimulationState, SimulationStatus


@pytest.fixture
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


def _make_project(project_id: str = "proj_test", *, name: str = "Klima-Studie") -> Project:
    os.makedirs(ProjectManager._get_project_dir(project_id), exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    project = Project(
        project_id=project_id,
        name=name,
        status=ProjectStatus.GRAPH_COMPLETED,
        created_at=now,
        updated_at=now,
        files=[
            {
                "filename": "abc12345.pdf",
                "original_filename": "klima-studie.pdf",
                "saved_filename": "abc12345.pdf",
                "path": f"projects/{project_id}/files/abc12345.pdf",
                "size": 1024,
            }
        ],
        graph_id="graph_test_001",
        simulation_requirement="Polarisation in Klimadebatten messen",
    )
    ProjectManager.save_project(project)
    return project


def _make_simulation(
    artifact_store: InMemoryArtifactStore,
    *,
    simulation_id: str = "sim_test",
    project_id: str = "proj_test",
    graph_id: str = "graph_test_001",
    branch_name: str = "main",
    llm_model: str = "qwen3-coder-next:cloud",
    persona_count: int = 3,
) -> SimulationState:
    manager = SimulationManager(store=artifact_store)
    state = SimulationState(
        simulation_id=simulation_id,
        project_id=project_id,
        graph_id=graph_id,
        status=SimulationStatus.READY,
        branch_name=branch_name,
    )
    manager._save_simulation_state(state)
    artifact_store.write_json(
        simulation_id,
        "simulation_config",
        {"llm_model": llm_model, "graph_id": graph_id, "language": "de"},
    )
    artifact_store.write_json(
        simulation_id,
        "reddit_profiles",
        [
            {"username": f"persona_{i}", "name": f"Persona {i}"}
            for i in range(persona_count)
        ],
    )
    return state


def _create_run(
    registry: RunRegistry,
    *,
    run_type: str = "simulation_run",
    entity_id: str = "sim_test",
    project_id: str = "proj_test",
    simulation_id: str = "sim_test",
    branch_label: str = "main",
    status: str = "completed",
    message: str = "ok",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return registry.create_run(
        run_type=run_type,
        entity_id=entity_id,
        status=status,
        message=message,
        linked_ids={"simulation_id": simulation_id, "project_id": project_id},
        branch_label=branch_label,
        metadata=metadata or {},
    )


def test_list_runs_returns_envelope_with_summary(env):
    _make_project()
    _make_simulation(env["artifact_store"], persona_count=4)
    _create_run(env["registry"])

    response = env["client"].get("/api/runs")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["count"] == 1
    summary = payload["data"][0]["summary"]
    assert summary["model"] == "qwen3-coder-next:cloud"
    assert summary["document_name"] == "klima-studie.pdf"
    assert summary["persona_count"] == 4
    assert summary["graph_id"] == "graph_test_001"
    assert summary["graph_name"] == "Klima-Studie"
    assert summary["branch_name"] == "main"


def test_list_runs_filters_by_entity_id(env):
    _make_project()
    _make_simulation(env["artifact_store"])
    _create_run(env["registry"], entity_id="sim_test", simulation_id="sim_test")
    _create_run(env["registry"], entity_id="sim_other", simulation_id="sim_other")

    response = env["client"].get("/api/runs?entity_id=sim_test")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["data"][0]["entity_id"] == "sim_test"


def test_list_runs_combines_filters(env):
    _make_project()
    _make_simulation(env["artifact_store"])
    _create_run(env["registry"], run_type="simulation_run", status="completed")
    _create_run(env["registry"], run_type="simulation_prepare", status="failed")

    response = env["client"].get(
        "/api/runs?run_type=simulation_run&status=completed"
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["count"] == 1
    assert payload["data"][0]["run_type"] == "simulation_run"
    assert payload["data"][0]["status"] == "completed"


def test_get_run_returns_summary(env):
    _make_project()
    _make_simulation(env["artifact_store"], persona_count=2)
    run = _create_run(env["registry"])

    response = env["client"].get(f"/api/runs/{run['run_id']}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["run_id"] == run["run_id"]
    assert data["summary"]["persona_count"] == 2
    assert data["summary"]["model"] == "qwen3-coder-next:cloud"


def test_get_run_returns_404_for_unknown_id(env):
    response = env["client"].get("/api/runs/run_000000000000")

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["success"] is False


def test_get_run_returns_400_for_invalid_id(env):
    response = env["client"].get("/api/runs/not-a-run-id")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False


def test_get_run_events_returns_event_list(env):
    _make_project()
    _make_simulation(env["artifact_store"])
    run = _create_run(env["registry"])

    response = env["client"].get(f"/api/runs/{run['run_id']}/events")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert isinstance(payload["data"], list)
    assert payload["data"][0]["type"] == "created"


def test_summary_handles_missing_project_and_simulation(env):
    # Run linked to entities that don't exist on disk → summary stays defensive.
    run = _create_run(
        env["registry"],
        project_id="proj_missing",
        simulation_id="sim_missing",
        entity_id="sim_missing",
    )

    response = env["client"].get(f"/api/runs/{run['run_id']}")

    assert response.status_code == 200
    summary = response.get_json()["data"]["summary"]
    assert summary["model"] is None
    assert summary["document_name"] is None
    assert summary["persona_count"] is None
    # branch_label still bubbles up from the manifest itself.
    assert summary["branch_name"] == "main"
