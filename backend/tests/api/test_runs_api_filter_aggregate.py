"""Tests für erweiterte GET /api/runs-Filterung, Pagination und Status-Aggregation.

Sub-Slice 33 / Task 26 / Layer 7 — Closes #62.

Abgedeckte Szenarien:
  1  List ohne Parameter → Default-Limit, RunsListResponse-konform
  2  ?status=processing → nur Runs mit Status processing
  3  ?simulation_id=<id> → nur Runs einer Sim
  4  ?since=<iso> → Filter greift, ältere Runs nicht im Result
  5  ?aggregate=status → aggregation.counts vorhanden, total stimmt
  6  ?limit=5&offset=10 → Pagination
  7  ?limit=999 → 400 (Pydantic-Cap auf 200)
  8  GET /api/runs/<id> → RunDetail-konform, eta_seconds/metrics vorhanden (auch null)
  9  ?status=banane → 400 mit Validierungsfehler
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
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
    simulation_id: str = "sim_test",
    project_id: str = "proj_test",
    status: str = "completed",
    message: str = "ok",
    metadata: dict[str, Any] | None = None,
    updated_at_override: str | None = None,
) -> dict[str, Any]:
    run = registry.create_run(
        run_type=run_type,
        entity_id=entity_id,
        status=status,
        message=message,
        linked_ids={"simulation_id": simulation_id, "project_id": project_id},
        metadata=metadata or {},
    )
    if updated_at_override:
        # Patch the file directly for time-based tests.
        import json
        path = os.path.join(registry.REGISTRY_DIR, f"{run['run_id']}.json")
        with open(path) as fh:
            data = json.load(fh)
        data["updated_at"] = updated_at_override
        from app.utils.json_io import write_json_atomic
        write_json_atomic(path, data)
        # Invalidate cache entry so list_runs picks up the patched value.
        registry._cache.pop(run["run_id"], None)
        run["updated_at"] = updated_at_override
    return run


# ---------------------------------------------------------------------------
# Test 1: List ohne Parameter
# ---------------------------------------------------------------------------

def test_list_default_returns_runs_list_response_shape(env):
    _create_run(env["registry"], status="completed")
    _create_run(env["registry"], entity_id="sim2", simulation_id="sim2", status="processing")

    resp = env["client"].get("/api/runs")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    data = payload["data"]
    # RunsListResponse shape
    assert "runs" in data
    assert "total" in data
    assert data["aggregation"] is None
    assert len(data["runs"]) == data["total"]
    assert data["total"] == 2


# ---------------------------------------------------------------------------
# Test 2: ?status=processing
# ---------------------------------------------------------------------------

def test_filter_by_single_status(env):
    _create_run(env["registry"], status="completed")
    _create_run(env["registry"], entity_id="sim2", simulation_id="sim2", status="processing")

    resp = env["client"].get("/api/runs?status=processing")

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["total"] == 1
    assert data["runs"][0]["status"] == "processing"


# ---------------------------------------------------------------------------
# Test 3: ?simulation_id=<id>
# ---------------------------------------------------------------------------

def test_filter_by_simulation_id(env):
    _create_run(env["registry"], simulation_id="sim_a", entity_id="sim_a")
    _create_run(env["registry"], simulation_id="sim_b", entity_id="sim_b")
    _create_run(env["registry"], simulation_id="sim_a", entity_id="sim_a")

    resp = env["client"].get("/api/runs?simulation_id=sim_a")

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["total"] == 2
    for run in data["runs"]:
        assert run["linked_ids"]["simulation_id"] == "sim_a"


# ---------------------------------------------------------------------------
# Test 4: ?since=<iso>
# ---------------------------------------------------------------------------

def test_filter_by_since(env):
    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=10)).isoformat()
    new_ts = (now + timedelta(seconds=1)).isoformat()

    _create_run(env["registry"], entity_id="old", simulation_id="old", updated_at_override=old_ts)
    _create_run(env["registry"], entity_id="new", simulation_id="new", updated_at_override=new_ts)

    from urllib.parse import urlencode
    cutoff = now.isoformat()
    qs = urlencode({"since": cutoff})
    resp = env["client"].get(f"/api/runs?{qs}")

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["total"] == 1
    # The new run's entity_id should be "new"
    assert data["runs"][0]["entity_id"] == "new"


# ---------------------------------------------------------------------------
# Test 5: ?aggregate=status
# ---------------------------------------------------------------------------

def test_aggregate_status_returns_counts(env):
    _create_run(env["registry"], status="completed", entity_id="r1", simulation_id="r1")
    _create_run(env["registry"], status="completed", entity_id="r2", simulation_id="r2")
    _create_run(env["registry"], status="processing", entity_id="r3", simulation_id="r3")
    _create_run(env["registry"], status="failed", entity_id="r4", simulation_id="r4")

    resp = env["client"].get("/api/runs?aggregate=status")

    assert resp.status_code == 200
    payload = resp.get_json()
    data = payload["data"]
    agg = data["aggregation"]
    assert agg is not None
    counts = agg["counts"]
    # All canonical statuses must be present.
    for key in ("pending", "processing", "paused", "completed", "failed", "stopped"):
        assert key in counts
    assert counts["completed"] == 2
    assert counts["processing"] == 1
    assert counts["failed"] == 1
    # total is sum of all counts
    assert agg["total"] == sum(counts.values())


# ---------------------------------------------------------------------------
# Test 6: ?limit=5&offset=10
# ---------------------------------------------------------------------------

def test_pagination_limit_offset(env):
    for i in range(20):
        _create_run(env["registry"], entity_id=f"sim_{i:02d}", simulation_id=f"sim_{i:02d}")

    resp = env["client"].get("/api/runs?limit=5&offset=10")

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert len(data["runs"]) == 5
    assert data["total"] == 5


# ---------------------------------------------------------------------------
# Test 7: ?limit=999 → 400
# ---------------------------------------------------------------------------

def test_limit_cap_returns_400(env):
    resp = env["client"].get("/api/runs?limit=999")

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# Test 8: GET /api/runs/<id> → RunDetail + live metrics
# ---------------------------------------------------------------------------

def test_get_run_detail_has_live_metric_fields(env):
    run = _create_run(
        env["registry"],
        metadata={"eta_seconds": 42, "phase": "generating"},
    )

    resp = env["client"].get(f"/api/runs/{run['run_id']}")

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    # Fields must always be present (even if null).
    assert "eta_seconds" in data
    assert "log_tail" in data
    assert "metrics" in data
    # eta_seconds was set in metadata.
    assert data["eta_seconds"] == 42
    # log_tail: at least one event ("created") message should be present.
    assert isinstance(data["log_tail"], list)
    # metrics should contain phase.
    assert data["metrics"] is not None
    assert data["metrics"]["phase"] == "generating"


def test_get_run_detail_null_live_metrics_when_absent(env):
    run = _create_run(env["registry"])  # no metadata for live metrics

    resp = env["client"].get(f"/api/runs/{run['run_id']}")

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["eta_seconds"] is None
    # metrics may be None or minimal; no crash expected.
    # log_tail has at least the "created" event message.
    assert "log_tail" in data


# ---------------------------------------------------------------------------
# Test 9: invalid status → 400
# ---------------------------------------------------------------------------

def test_invalid_status_returns_400(env):
    resp = env["client"].get("/api/runs?status=banane")

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
