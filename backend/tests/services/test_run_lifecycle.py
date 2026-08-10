"""Interface-Tests für den RunLifecycle-Kontextmanager.

Ersetzt die Struktur-Tests der früheren Einzel-Helper
(``_register_start_run``/``_mark_run_failed`` in ``simulation_run.py``,
``_register_prepare_run``/``_reject_and_fail_prepare_run`` in
``simulation_prepare.py``) — getestet wird ausschließlich durchs
öffentliche Interface: ``begin`` → ``attach_task``/``succeed`` → Exit.
"""

from __future__ import annotations

import pytest

from app.services.run_lifecycle import (
    FAILURE_MESSAGE_ATTR,
    RunLifecycle,
    RunPersistenceError,
)


class FakeRegistry:
    """Minimaler RunRegistry-Ersatz mit steuerbarem update_run-Verhalten."""

    def __init__(self):
        self.runs: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []
        self.update_returns_none = False
        self.update_raises: Exception | None = None
        self._counter = 0

    def create_run(self, run_type, entity_id, **kwargs):
        self._counter += 1
        run_id = f"run_test_{self._counter}"
        record = {"run_id": run_id, "run_type": run_type, "entity_id": entity_id, **kwargs}
        self.runs[run_id] = record
        self.calls.append(("create_run", dict(record)))
        return record

    def update_run(self, run_id, **updates):
        self.calls.append(("update_run", {"run_id": run_id, **updates}))
        if self.update_raises is not None:
            raise self.update_raises
        if self.update_returns_none:
            return None
        self.runs[run_id].update(updates)
        return self.runs[run_id]


class FakeTaskManager:
    def __init__(self, fail_raises: Exception | None = None):
        self.failed: list[tuple[str, str]] = []
        self.fail_raises = fail_raises
        self.order_log: list[str] | None = None

    def fail_task(self, task_id, message):
        if self.order_log is not None:
            self.order_log.append("fail_task")
        if self.fail_raises is not None:
            raise self.fail_raises
        self.failed.append((task_id, message))


class _Boom(Exception):
    pass


class _Rejected(Exception):
    """Rejection mit sprechender Run-Meldung (wie _StartRejected/_PrepareRejected)."""

    run_failure_message = "start rejected before launch"


def test_begin_creates_pending_run():
    registry = FakeRegistry()
    with RunLifecycle.begin(registry, "simulation_run", "sim-1", linked_ids={"a": 1}) as run:
        assert run.record["status"] == "pending"
        assert run.record["linked_ids"] == {"a": 1}
        assert run.run_id
    # Ohne succeed(): Run bleibt pending (Worker-Übergabe).
    assert registry.runs[run.run_id]["status"] == "pending"


def test_begin_forces_pending_even_if_status_passed():
    registry = FakeRegistry()
    with RunLifecycle.begin(registry, "simulation_run", "sim-1", status="processing") as run:
        pass
    assert registry.runs[run.run_id]["status"] == "pending"


def test_exception_marks_failed_and_reraises():
    registry = FakeRegistry()
    with pytest.raises(_Boom):
        with RunLifecycle.begin(registry, "simulation_run", "sim-1") as run:
            raise _Boom("kaputt")
    record = registry.runs[run.run_id]
    assert record["status"] == "failed"
    assert record["message"] == "simulation_run failed: _Boom"
    assert record["error"] == record["message"]


def test_failure_message_template_is_used():
    registry = FakeRegistry()
    with pytest.raises(_Boom):
        with RunLifecycle.begin(
            registry,
            "simulation_run",
            "sim-1",
            failure_message="Simulation start failed: {exc_type}",
        ) as run:
            raise _Boom()
    assert registry.runs[run.run_id]["message"] == "Simulation start failed: _Boom"


def test_exception_attribute_message_wins():
    registry = FakeRegistry()
    with pytest.raises(_Rejected):
        with RunLifecycle.begin(
            registry, "simulation_run", "sim-1", failure_message="fallback {exc_type}"
        ) as run:
            raise _Rejected()
    assert registry.runs[run.run_id]["message"] == "start rejected before launch"
    assert getattr(_Rejected, FAILURE_MESSAGE_ATTR) == "start rejected before launch"


def test_base_exception_is_marked_and_reraised():
    """#1183: SystemExit (Worker-Timeout als Signal-Ableitung) darf keinen
    pending-Phantom hinterlassen."""
    registry = FakeRegistry()
    with pytest.raises(SystemExit):
        with RunLifecycle.begin(registry, "simulation_run", "sim-1") as run:
            raise SystemExit(1)
    assert registry.runs[run.run_id]["status"] == "failed"


def test_task_is_failed_before_run_update():
    """#841: fail_task() zuerst, der detaillierte update_run() zuletzt."""
    registry = FakeRegistry()
    task_manager = FakeTaskManager()
    order: list[str] = []
    task_manager.order_log = order
    original_update = registry.update_run

    def logging_update(run_id, **updates):
        order.append("update_run")
        return original_update(run_id, **updates)

    registry.update_run = logging_update

    with pytest.raises(_Boom):
        with RunLifecycle.begin(registry, "simulation_prepare", "sim-1") as run:
            run.attach_task(task_manager, "task-1")
            raise _Boom()
    assert order == ["fail_task", "update_run"]


def test_task_failure_is_best_effort():
    registry = FakeRegistry()
    task_manager = FakeTaskManager(fail_raises=RuntimeError("task store weg"))
    with pytest.raises(_Boom):
        with RunLifecycle.begin(registry, "simulation_prepare", "sim-1") as run:
            run.attach_task(task_manager, "task-1")
            raise _Boom()
    # Run wurde trotz Task-Fehler markiert.
    assert registry.runs[run.run_id]["status"] == "failed"


def test_persistence_none_raises_run_persistence_error():
    """#844: update_run() → None darf nicht wie eine persistierte Markierung aussehen."""
    registry = FakeRegistry()
    registry.update_returns_none = True
    with pytest.raises(RunPersistenceError) as excinfo:
        with RunLifecycle.begin(registry, "simulation_run", "sim-1"):
            raise _Boom()
    assert isinstance(excinfo.value.__cause__, _Boom)


def test_persistence_exception_raises_run_persistence_error():
    registry = FakeRegistry()
    registry.update_raises = OSError("disk weg")
    with pytest.raises(RunPersistenceError):
        with RunLifecycle.begin(registry, "simulation_run", "sim-1"):
            raise _Boom()


def test_succeed_transitions_and_persists():
    registry = FakeRegistry()
    with RunLifecycle.begin(registry, "simulation_run", "sim-1") as run:
        run.succeed(status="processing", message="Simulation run started")
    record = registry.runs[run.run_id]
    assert record["status"] == "processing"
    assert record["message"] == "Simulation run started"


def test_succeed_persistence_failure_raises_and_is_not_remasked():
    """Ein Persistenzfehler aus succeed() wird nicht durch einen zweiten
    (ebenfalls scheiternden) failed-Markierungsversuch ersetzt."""
    registry = FakeRegistry()
    registry.update_returns_none = True
    with pytest.raises(RunPersistenceError):
        with RunLifecycle.begin(registry, "simulation_run", "sim-1") as run:
            run.succeed(status="processing")
    # Genau ein update_run-Versuch (aus succeed) — __exit__ hat nicht erneut markiert.
    update_calls = [c for c in registry.calls if c[0] == "update_run"]
    assert len(update_calls) == 1


def test_clean_exit_without_succeed_keeps_pending():
    registry = FakeRegistry()
    with RunLifecycle.begin(registry, "graph_build", "proj-1") as run:
        pass
    assert registry.runs[run.run_id]["status"] == "pending"
