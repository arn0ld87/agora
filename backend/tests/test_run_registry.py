import json
from pathlib import Path
from types import SimpleNamespace

from app.services.run_registry import RunRegistry


def _reset_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(tmp_path))
    RunRegistry._instance = None
    registry = RunRegistry()
    return registry


def test_create_run_persists_manifest(tmp_path, monkeypatch):
    registry = _reset_registry(tmp_path, monkeypatch)

    run = registry.create_run(
        run_type="simulation_prepare",
        entity_id="sim_123",
        status="ready",
        linked_ids={"simulation_id": "sim_123"},
        message="ready now",
    )

    manifest_path = Path(tmp_path) / f"{run['run_id']}.json"
    assert manifest_path.exists()

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == run["run_id"]
    assert payload["status"] == "completed"
    assert payload["linked_ids"]["simulation_id"] == "sim_123"
    assert payload["events"][0]["type"] == "created"


def test_update_run_appends_event_and_updates_status(tmp_path, monkeypatch):
    registry = _reset_registry(tmp_path, monkeypatch)

    run = registry.create_run(
        run_type="simulation_run",
        entity_id="sim_abc",
        status="pending",
        linked_ids={"simulation_id": "sim_abc"},
    )

    updated = registry.update_run(
        run["run_id"],
        status="running",
        progress=42,
        message="halfway there",
    )

    assert updated is not None
    assert updated["status"] == "processing"
    assert updated["progress"] == 42
    assert updated["message"] == "halfway there"
    assert updated["events"][-1]["type"] == "updated"


def test_get_latest_by_linked_id_returns_most_recent_run(tmp_path, monkeypatch):
    registry = _reset_registry(tmp_path, monkeypatch)

    older = registry.create_run(
        run_type="simulation_run",
        entity_id="sim_same",
        linked_ids={"simulation_id": "sim_same"},
        message="older",
    )
    newer = registry.create_run(
        run_type="simulation_run",
        entity_id="sim_same",
        linked_ids={"simulation_id": "sim_same"},
        message="newer",
    )

    latest = registry.get_latest_by_linked_id(
        "simulation_id",
        "sim_same",
        run_type="simulation_run",
    )

    assert latest is not None
    assert latest["run_id"] == newer["run_id"]
    assert latest["message"] == "newer"
    assert older["run_id"] != newer["run_id"]


def test_sync_task_updates_existing_run(tmp_path, monkeypatch):
    registry = _reset_registry(tmp_path, monkeypatch)

    run = registry.create_run(
        run_type="report_generate",
        entity_id="report_123",
        linked_ids={"report_id": "report_123"},
    )

    task = SimpleNamespace(
        metadata={"run_id": run["run_id"]},
        task_id="task_1",
        task_type="report_generate",
        status=SimpleNamespace(value="processing"),
        progress=65,
        message="working",
        error=None,
    )

    updated = registry.sync_task(task)

    assert updated is not None
    assert updated["status"] == "processing"
    assert updated["progress"] == 65
    assert updated["linked_ids"]["task_id"] == "task_1"
