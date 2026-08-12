"""Tests für POST /api/runs/<run_id>/replay (Issue #763, Ticket 4)."""

from __future__ import annotations

import os
from typing import Any

import pytest
from flask import Flask

from app.api import runs_bp
from app.config import Config
from app.services.artifact_store import InMemoryArtifactStore
from app.services.manifest_capture import ManifestCapture
from app.services.run_registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Flask-Test-App mit RunRegistry und ArtifactStore."""
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(upload_root / "run_registry"))
    monkeypatch.setenv("AGORA_INSTANCE_DIR", str(tmp_path))
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
        "tmp_path": tmp_path,
    }

    RunRegistry._instance = None


def _create_run_with_manifest(
    registry: RunRegistry,
    tmp_path: Any,
    *,
    run_id_override: str | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    """Erzeugt einen Run mit Draft-Manifest im Run-Verzeichnis."""
    run = registry.create_run(
        run_type="simulation_run",
        entity_id="sim_test",
        status=status,
        message="Test run",
        linked_ids={"simulation_id": "sim_test", "project_id": "proj_test"},
        metadata={},
    )
    run_id = run_id_override or run["run_id"]

    # Manifest im Run-Verzeichnis schreiben
    run_dir = tmp_path / "runs" / run_id
    ManifestCapture.capture_draft(
        run_id=run_id,
        run_dir=str(run_dir),
        seed_document_hash="sha256:abc",
        seed_document_filename="test.md",
        simulation_config_hash="sha256:def",
        graph_id="graph_001",
        agora_version="0.9.5",
        schema_version="1.0.0",
        random_seed=42,
        simulation_id_seed="sim_test",
    )

    return run


# ---------------------------------------------------------------------------
# Test 1: 202 bei identischem Replay
# ---------------------------------------------------------------------------


def _stub_replay_infra(monkeypatch, *, new_simulation_id: str = "sim_branch_default"):
    """Stubbt SimulationManager/StageModelRouter/SimulationRunner für den
    tatsächlichen Klon-und-Start-Flow von replay_run."""
    from unittest.mock import MagicMock

    from app.contracts.llm_routing_contract import ResolvedRoute

    branched_state = MagicMock()
    branched_state.simulation_id = new_simulation_id
    branched_state.project_id = "proj_test"
    branched_state.graph_id = "graph_001"
    branched_state.branch_name = "replay-branch"

    manager = MagicMock()
    manager.create_branch.return_value = branched_state
    manager.get_simulation.return_value = branched_state
    monkeypatch.setattr("app.api.runs.SimulationManager", lambda: manager)

    resolved = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="conn-local",
        model="qwen3",
        base_url_sanitized="http://localhost:1234/v1",
        routing_version=1,
        provider_options={},
    )
    router = MagicMock()
    router.resolve.return_value = resolved
    router.lock_stage.return_value = resolved
    monkeypatch.setattr("app.api.runs.StageModelRouter", lambda _rid: router)
    monkeypatch.setattr("app.api.runs.resolve_route_api_key", lambda _r, _rt: "sk-local")
    monkeypatch.setattr(
        "app.api.runs.build_route_subprocess_env", lambda _r, _k, _rid: {}
    )
    monkeypatch.setattr("app.api.runs.seed_run_stage_routing", MagicMock())

    runner = MagicMock()
    runner.start_simulation.return_value = MagicMock(
        to_dict=MagicMock(return_value={"simulation_id": new_simulation_id})
    )
    monkeypatch.setattr("app.api.runs.SimulationRunner", runner)
    return manager, runner


def test_replay_returns_202_with_new_run_id(env, monkeypatch):
    """S1: Identisches Replay gibt 202 und neue run_id zurück."""
    _stub_replay_infra(monkeypatch)
    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    run_id = run["run_id"]

    resp = env["client"].post(f"/api/runs/{run_id}/replay")

    assert resp.status_code == 202, (
        f"Erwartet 202, erhalten: {resp.status_code} — {resp.get_json()}"
    )
    payload = resp.get_json()
    assert "run_id" in payload
    assert payload["run_id"] != run_id


# ---------------------------------------------------------------------------
# Test 2: 404 bei unbekanntem Run
# ---------------------------------------------------------------------------


def test_replay_unknown_run_returns_404(env):
    """S2: Replay eines nicht existierenden Runs gibt 404."""
    resp = env["client"].post("/api/runs/run_000000000000/replay")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 3: replayed_from_run_id ist im neuen Run gesetzt
# ---------------------------------------------------------------------------


def test_replay_sets_replayed_from_run_id(env, monkeypatch):
    """S3: Der neue Run hat replayed_from_run_id = Original-Run-ID."""
    _stub_replay_infra(monkeypatch)
    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    run_id = run["run_id"]

    resp = env["client"].post(f"/api/runs/{run_id}/replay")
    assert resp.status_code == 202

    payload = resp.get_json()
    new_run_id = payload["run_id"]

    new_run = env["registry"].get_run(new_run_id)
    assert new_run is not None
    assert new_run.get("replayed_from_run_id") == run_id


def test_replay_accepts_envelope_body_with_overrides(env, monkeypatch):
    """Bug_002: Frontend sendet {overrides: {...}} — nicht die flachen Felder."""
    _stub_replay_infra(monkeypatch)
    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    run_id = run["run_id"]

    resp = env["client"].post(
        f"/api/runs/{run_id}/replay",
        json={"overrides": {"random_seed": 42}},
    )

    assert resp.status_code == 202, resp.get_json()
    payload = resp.get_json()
    new_run = env["registry"].get_run(payload["run_id"])
    assert new_run["metadata"]["replay_overrides"]["random_seed"] == 42


def test_replay_starts_a_worker_not_just_a_pending_record(env, monkeypatch):
    """Bug_005: Replay legte bisher nur einen pending-Record an und liess ihn
    dort liegen — kein Branch, kein Worker-Start. Diese Regression prüft,
    dass tatsächlich ein neuer Simulationslauf geklont und gestartet wird."""
    from unittest.mock import MagicMock

    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    run_id = run["run_id"]

    branched_state = MagicMock()
    branched_state.simulation_id = "sim_branch_001"
    branched_state.project_id = "proj_test"
    branched_state.graph_id = "graph_001"
    branched_state.branch_name = "replay-of-" + run_id

    manager = MagicMock()
    manager.create_branch.return_value = branched_state
    manager.get_simulation.return_value = branched_state
    monkeypatch.setattr("app.api.runs.SimulationManager", lambda: manager)

    from app.contracts.llm_routing_contract import ResolvedRoute

    resolved = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="conn-local",
        model="qwen3",
        base_url_sanitized="http://localhost:1234/v1",
        routing_version=1,
        provider_options={},
    )
    router = MagicMock()
    router.resolve.return_value = resolved
    router.lock_stage.return_value = resolved
    monkeypatch.setattr("app.api.runs.StageModelRouter", lambda _rid: router)
    monkeypatch.setattr("app.api.runs.resolve_route_api_key", lambda _r, _rt: "sk-local")
    monkeypatch.setattr(
        "app.api.runs.build_route_subprocess_env", lambda _r, _k, _rid: {}
    )
    monkeypatch.setattr("app.api.runs.seed_run_stage_routing", MagicMock())

    runner = MagicMock()
    runner.start_simulation.return_value = MagicMock(
        to_dict=MagicMock(return_value={"simulation_id": "sim_branch_001"})
    )
    monkeypatch.setattr("app.api.runs.SimulationRunner", runner)

    resp = env["client"].post(f"/api/runs/{run_id}/replay")

    assert resp.status_code == 202, resp.get_json()
    assert manager.create_branch.called, "Replay muss die Original-Simulation klonen"
    assert runner.start_simulation.called, (
        "Replay muss den Worker tatsächlich starten, nicht nur einen "
        "pending-Record anlegen"
    )


def test_replay_new_run_has_fresh_linked_ids_not_original(env, monkeypatch):
    """Bug_010: Der Replay-Run darf NICHT auf die simulation_id des Originals
    zeigen — sonst treffen Stop/Cancel/Resume auf dem neuen Run die alte
    Simulation."""
    from unittest.mock import MagicMock

    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    run_id = run["run_id"]

    branched_state = MagicMock()
    branched_state.simulation_id = "sim_branch_fresh"
    branched_state.project_id = "proj_test"
    branched_state.graph_id = "graph_001"
    branched_state.branch_name = "replay-of-" + run_id

    manager = MagicMock()
    manager.create_branch.return_value = branched_state
    manager.get_simulation.return_value = branched_state
    monkeypatch.setattr("app.api.runs.SimulationManager", lambda: manager)

    from app.contracts.llm_routing_contract import ResolvedRoute

    resolved = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="conn-local",
        model="qwen3",
        base_url_sanitized="http://localhost:1234/v1",
        routing_version=1,
        provider_options={},
    )
    router = MagicMock()
    router.resolve.return_value = resolved
    router.lock_stage.return_value = resolved
    monkeypatch.setattr("app.api.runs.StageModelRouter", lambda _rid: router)
    monkeypatch.setattr("app.api.runs.resolve_route_api_key", lambda _r, _rt: "sk-local")
    monkeypatch.setattr(
        "app.api.runs.build_route_subprocess_env", lambda _r, _k, _rid: {}
    )
    monkeypatch.setattr("app.api.runs.seed_run_stage_routing", MagicMock())

    runner = MagicMock()
    runner.start_simulation.return_value = MagicMock(
        to_dict=MagicMock(return_value={"simulation_id": "sim_branch_fresh"})
    )
    monkeypatch.setattr("app.api.runs.SimulationRunner", runner)

    resp = env["client"].post(f"/api/runs/{run_id}/replay")
    assert resp.status_code == 202, resp.get_json()

    new_run_id = resp.get_json()["run_id"]
    new_run = env["registry"].get_run(new_run_id)
    assert new_run["linked_ids"]["simulation_id"] == "sim_branch_fresh"
    assert new_run["linked_ids"]["simulation_id"] != "sim_test"


def test_replay_rejects_seed_document_override_not_yet_supported(env):
    """seed_document_id-Overrides sind noch nicht implementiert — klare 400
    statt stillschweigend das Original-Dokument weiterzuverwenden."""
    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    run_id = run["run_id"]

    resp = env["client"].post(
        f"/api/runs/{run_id}/replay",
        json={"overrides": {"seed_document_id": "doc_other"}},
    )

    assert resp.status_code == 400
    assert resp.get_json()["code"] == "seed_document_override_unsupported"


def test_replay_non_simulation_run_returns_409(env):
    """Replay ist aktuell nur für simulation_run implementiert."""
    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    env["registry"].update_run(run["run_id"], status="completed")
    # run_type auf etwas anderes als simulation_run umbiegen:
    manifest_path = os.path.join(
        RunRegistry.REGISTRY_DIR, f"{run['run_id']}.json"
    )
    import json as _json

    with open(manifest_path) as f:
        data = _json.load(f)
    data["run_type"] = "report_generate"
    with open(manifest_path, "w") as f:
        _json.dump(data, f)

    resp = env["client"].post(f"/api/runs/{run['run_id']}/replay")
    assert resp.status_code == 409


def test_replay_rejects_unknown_override_key_in_envelope(env):
    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    run_id = run["run_id"]

    resp = env["client"].post(
        f"/api/runs/{run_id}/replay",
        json={"overrides": {"geheim_feld": "x"}},
    )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /manifest (Ticket 8)
# ---------------------------------------------------------------------------


def test_get_manifest_returns_200(env):
    """Bug_001: json war nicht importiert — jeder erfolgreiche Aufruf crashte 500."""
    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    run_id = run["run_id"]

    resp = env["client"].get(f"/api/runs/{run_id}/manifest")

    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    assert payload["data"]["run_id"] == run_id


# ---------------------------------------------------------------------------
# Export-Endpoint (Ticket 5)
# ---------------------------------------------------------------------------


def test_export_returns_200_with_zip(env):
    """S1: Export-Endpoint gibt 200 mit ZIP-Content-Type."""
    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    run_id = run["run_id"]

    resp = env["client"].get(f"/api/runs/{run_id}/export")

    assert resp.status_code == 200, (
        f"Erwartet 200, erhalten: {resp.status_code}"
    )
    assert resp.content_type == "application/zip"
    assert resp.headers.get("Content-Disposition", "").startswith(
        f"attachment; filename=agora-run-{run_id}"
    )


def test_export_zip_contains_manifest(env):
    """S2: ZIP enthält manifest.json."""
    import io
    import zipfile

    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    run_id = run["run_id"]

    resp = env["client"].get(f"/api/runs/{run_id}/export")
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    names = zf.namelist()
    assert "manifest.json" in names


def test_export_unknown_run_returns_404(env):
    """S3: Export eines nicht existierenden Runs gibt 404."""
    resp = env["client"].get("/api/runs/run_000000000000/export")
    assert resp.status_code == 404


def test_export_zip_includes_subdirectory_files(env):
    """Bug_019: os.listdir+isfile dropte stages/ — die eingefrorenen
    Routing-Snapshots fehlten im Export."""
    import io
    import zipfile

    run = _create_run_with_manifest(env["registry"], env["tmp_path"])
    run_id = run["run_id"]

    run_dir = os.path.join(str(env["tmp_path"]), "runs", run_id)
    stages_dir = os.path.join(run_dir, "stages")
    os.makedirs(stages_dir, exist_ok=True)
    with open(os.path.join(stages_dir, "persona_generation_ai_route_snapshot.json"), "w") as f:
        f.write("{}")

    resp = env["client"].get(f"/api/runs/{run_id}/export")
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    names = zf.namelist()
    assert "stages/persona_generation_ai_route_snapshot.json" in names
