"""
Tests for RunRegistry-Authority: TaskManager.get_task() falls back to
RunRegistry when the in-memory cache is empty (simulates worker restart).

Ref: agora_code_review_2026-05-17.md §1.3 / PR 2 Scope
"""

import os
import pytest

from app.models.task import TaskManager, TaskStatus
from app.services.run_registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures — reset singletons between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singletons(tmp_path, monkeypatch):
    """
    Patch REGISTRY_DIR to tmp_path so tests never touch real disk state.
    Reset both singletons before and after each test.
    """
    registry_dir = str(tmp_path / "run_registry")
    os.makedirs(registry_dir, exist_ok=True)

    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", registry_dir)
    # Also patch Config.UPLOAD_FOLDER so RunRegistry.__new__ uses the same path
    import app.config as cfg_module
    monkeypatch.setattr(cfg_module.Config, "UPLOAD_FOLDER", str(tmp_path))

    # Reset singletons BEFORE test
    RunRegistry._instance = None
    TaskManager._instance = None

    yield

    # Reset singletons AFTER test to avoid cross-test leakage
    RunRegistry._instance = None
    TaskManager._instance = None


# ---------------------------------------------------------------------------
# 1. Cache-first behaviour
# ---------------------------------------------------------------------------

def test_get_task_returns_dict_cache_first():
    tm = TaskManager()
    task_id = tm.create_task("graph_build", metadata={"project_id": "proj_1"})
    tm.update_task(task_id, status=TaskStatus.PROCESSING, progress=55, message="halfway")

    result = tm.get_task(task_id)
    assert result is not None
    assert result.status == TaskStatus.PROCESSING
    assert result.progress == 55
    assert result.message == "halfway"


# ---------------------------------------------------------------------------
# 2. Registry fallback after worker-reset
# ---------------------------------------------------------------------------

def test_get_task_falls_back_to_run_registry_after_reset():
    registry = RunRegistry()
    tm = TaskManager()

    # First create the run (mirrors what API handler does before creating the task)
    run = registry.create_run(
        run_type="report_generate",
        entity_id="proj_x",
        status="pending",
        metadata={"task_type": "report_generate"},
    )
    run_id = run["run_id"]

    # Create task with run_id in metadata — mirrors the API handler pattern
    task_id = tm.create_task("report_generate", metadata={"project_id": "proj_x", "run_id": run_id})

    # Link task_id into the run (mirrors what API handler does after create_task)
    registry.update_run(run_id, linked_ids={"task_id": task_id})

    # Update task — this calls sync_task which updates the run via run_id in metadata
    tm.update_task(task_id, status=TaskStatus.PROCESSING, progress=42, message="halfway")

    # Simulate worker-reset: clear in-memory cache
    TaskManager._instance._tasks.clear()

    # get_task must reconstruct from registry via find_by_linked_id
    result = TaskManager().get_task(task_id)

    assert result is not None, "get_task returned None after cache clear"
    assert result.status == TaskStatus.PROCESSING
    assert result.progress == 42
    assert result.message == "halfway"
    assert result.task_type == "report_generate"


# ---------------------------------------------------------------------------
# 3. Neither cache nor registry → None
# ---------------------------------------------------------------------------

def test_get_task_returns_none_when_neither_cache_nor_registry_has_it():
    import uuid
    tm = TaskManager()
    result = tm.get_task(str(uuid.uuid4()))
    assert result is None


# ---------------------------------------------------------------------------
# 4. TaskStatus canonical round-trip
# ---------------------------------------------------------------------------

def test_canonical_status_round_trip():
    for status in TaskStatus:
        value = status.value
        reconstructed = TaskStatus(value)
        assert reconstructed == status, f"Round-trip failed for {status}"


# ---------------------------------------------------------------------------
# 5. fail_task → reset → get_task preserves error
# ---------------------------------------------------------------------------

def test_failed_status_round_trip_preserves_error_message():
    registry = RunRegistry()
    tm = TaskManager()

    run = registry.create_run(
        run_type="simulation_prepare",
        entity_id="p2",
        status="pending",
        metadata={"task_type": "simulation_prepare"},
    )
    run_id = run["run_id"]

    task_id = tm.create_task("simulation_prepare", metadata={"project_id": "p2", "run_id": run_id})
    registry.update_run(run_id, linked_ids={"task_id": task_id})

    tm.fail_task(task_id, "something went wrong")

    # Worker-reset
    TaskManager._instance._tasks.clear()

    result = TaskManager().get_task(task_id)
    assert result is not None
    assert result.status == TaskStatus.FAILED
    assert result.error == "something went wrong"


# ---------------------------------------------------------------------------
# 6. complete_task → reset → progress == 100
# ---------------------------------------------------------------------------

def test_completed_status_round_trip_preserves_progress_100():
    registry = RunRegistry()
    tm = TaskManager()

    run = registry.create_run(
        run_type="graph_build",
        entity_id="p3",
        status="pending",
        metadata={"task_type": "graph_build"},
    )
    run_id = run["run_id"]

    task_id = tm.create_task("graph_build", metadata={"project_id": "p3", "run_id": run_id})
    registry.update_run(run_id, linked_ids={"task_id": task_id})

    tm.complete_task(task_id, result={"nodes": 42})

    # Worker-reset
    TaskManager._instance._tasks.clear()

    result = TaskManager().get_task(task_id)
    assert result is not None
    assert result.status == TaskStatus.COMPLETED
    assert result.progress == 100
