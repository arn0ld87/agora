"""Regression fuer konkurrierende Prepare-Laeufe derselben Simulation."""

import threading
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_prepare as mod
from app.services.simulation_manager import SimulationStatus


def test_active_preparing_simulation_rejects_second_prepare_before_run_creation() -> None:
    app = Flask(__name__)
    state = MagicMock(status=SimulationStatus.PREPARING)
    mod._active_prepare_jobs.add("sim_0123456789ab")

    try:
        with app.test_request_context(), pytest.raises(mod._PrepareRejected) as excinfo:
            mod._ensure_prepare_startable(state, "sim_0123456789ab")
    finally:
        mod._active_prepare_jobs.discard("sim_0123456789ab")

    response, status = excinfo.value.response
    payload = response.get_json()
    assert status == 409
    assert payload["code"] == "simulation_prepare_in_progress"


def test_stale_preparing_state_without_live_task_remains_recoverable() -> None:
    state = MagicMock(status=SimulationStatus.PREPARING)

    mod._ensure_prepare_startable(state, "sim_0123456789ab")


def test_active_prepare_marker_is_removed_after_worker_exit() -> None:
    simulation_id = "sim_0123456789ab"

    def crash() -> None:
        raise SystemExit(1)

    tracked = mod._track_active_prepare_job(simulation_id, crash)
    assert simulation_id in mod._active_prepare_jobs

    with pytest.raises(SystemExit):
        tracked()

    assert simulation_id not in mod._active_prepare_jobs


def test_active_prepare_marker_is_discarded_when_enqueue_fails(monkeypatch) -> None:
    simulation_id = "sim_0123456789ab"
    state = MagicMock(
        status=SimulationStatus.CREATED,
        project_id="proj_123",
        graph_id="graph_123",
        source_simulation_id=None,
        root_simulation_id=None,
        branch_name=None,
        branch_depth=0,
        entities_count=1,
        entity_types=["Person"],
    )
    manager = MagicMock()
    manager.get_simulation.return_value = state
    project = MagicMock(simulation_requirement="Discuss the project")
    routing = MagicMock(
        client_requested_override=True,
        llm_runtime=MagicMock(),
        llm_model_override="gpt-4o-mini",
    )
    inputs = MagicMock()
    run = MagicMock()
    run.__enter__.return_value = run
    run.__exit__.return_value = False
    run.record = {"run_id": "run_prepare_1"}
    task_manager = MagicMock()
    task_manager.create_task.return_value = "task_prepare_1"

    monkeypatch.setattr(mod, "SimulationManager", lambda: manager)
    monkeypatch.setattr("app.models.task.TaskManager", lambda: task_manager)
    monkeypatch.setattr(mod, "_load_prepare_project", lambda _state: project)
    monkeypatch.setattr(mod, "_resolve_prepare_routing", lambda *_args: routing)
    monkeypatch.setattr(mod, "_collect_prepare_inputs", lambda *_args: inputs)
    monkeypatch.setattr(mod, "get_simulation_storage", MagicMock())
    monkeypatch.setattr(mod, "_preview_entity_counts", MagicMock())
    monkeypatch.setattr(mod, "_precheck_prepare_ai_model_ref", MagicMock())
    monkeypatch.setattr(mod, "_begin_prepare_run", lambda *_args: run)
    monkeypatch.setattr(mod, "_seed_prepare_routing", MagicMock())
    monkeypatch.setattr(
        mod,
        "_resolve_prepare_route",
        lambda *_args: (MagicMock(model="gpt-4o-mini"), "key"),
    )
    monkeypatch.setattr(mod, "build_runtime_llm_config", MagicMock())
    monkeypatch.setattr(mod, "_make_prepare_job", lambda **_kwargs: lambda: None)

    def fail_enqueue(*_args, **_kwargs):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr("app.jobs.enqueue", fail_enqueue)

    with pytest.raises(RuntimeError, match="queue unavailable"):
        mod._prepare_simulation_under_start_lock({}, simulation_id, None)

    assert simulation_id not in mod._active_prepare_jobs


def test_prepare_start_window_is_serialized_per_simulation(monkeypatch) -> None:
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    calls = 0
    calls_guard = threading.Lock()

    def fake_start(_data, _simulation_id, _ai_model_ref):
        nonlocal calls
        with calls_guard:
            calls += 1
            call_number = calls
        if call_number == 1:
            first_entered.set()
            assert release_first.wait(timeout=1)
        else:
            second_entered.set()
        return "ok"

    monkeypatch.setattr(mod, "_prepare_simulation_under_start_lock", fake_start)
    app = Flask(__name__)
    results: list[str] = []

    def invoke() -> None:
        with app.test_request_context(
            json={"simulation_id": "sim_0123456789ab"}
        ):
            results.append(mod.prepare_simulation())

    first = threading.Thread(target=invoke)
    second = threading.Thread(target=invoke)
    first.start()
    assert first_entered.wait(timeout=1)
    second.start()
    assert not second_entered.wait(timeout=0.1)

    release_first.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert second_entered.is_set()
    assert results == ["ok", "ok"]
    assert "sim_0123456789ab" not in mod._prepare_start_locks


def test_prepare_lock_registry_keeps_entry_until_waiter_finishes() -> None:
    simulation_id = "sim_0123456789ab"
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def first_user() -> None:
        with mod._prepare_start_lock(simulation_id):
            first_entered.set()
            assert release_first.wait(timeout=1)

    def second_user() -> None:
        with mod._prepare_start_lock(simulation_id):
            second_entered.set()

    first = threading.Thread(target=first_user)
    second = threading.Thread(target=second_user)
    first.start()
    assert first_entered.wait(timeout=1)
    second.start()
    assert not second_entered.wait(timeout=0.1)

    with mod._prepare_start_locks_guard:
        assert mod._prepare_start_locks[simulation_id].users == 2

    release_first.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert second_entered.is_set()
    assert simulation_id not in mod._prepare_start_locks
