"""Tests für ``app.services.sim.reconciliation.reconcile_stale_runs``.

Tech-Review 2026-09-07, Slice B1 — Startup-Reconciliation für verwaiste
``simulation_run``-Runs nach einem Container-/Prozess-Neustart.

``load_run_state``/``save_run_state`` werden auf Modulebene gepatcht statt
über den echten Artifact-Store zu gehen — das hält die Tests unabhängig von
Flask-App-Kontext und Dateisystem-Layout, während das Verhalten von
``reconcile_stale_runs`` (die eigentliche Logik dieses Moduls) unverändert
geprüft wird.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from app.services.sim import reconciliation as reconciliation_module
from app.services.sim.reconciliation import ReconciliationResult, reconcile_stale_runs
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState


class _FakeRegistry:
    """Minimaler ``RunRegistry``-Stub: nur ``list_runs``/``update_run``."""

    def __init__(self, runs: List[Dict[str, Any]]) -> None:
        self._runs = {r["run_id"]: r for r in runs}
        self.updates: List[Dict[str, Any]] = []

    def list_runs(self, *, statuses, run_type, limit) -> List[Dict[str, Any]]:
        return [
            r for r in self._runs.values()
            if r.get("status") in statuses and r.get("run_type") == run_type
        ]

    def update_run(self, run_id: str, **updates: Any) -> Optional[Dict[str, Any]]:
        run = self._runs.get(run_id)
        if run is None:
            return None
        run.update(updates)
        self.updates.append({"run_id": run_id, **updates})
        return run


def _make_run(run_id: str, *, status: str, simulation_id: str) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "run_type": "simulation_run",
        "status": status,
        "entity_id": simulation_id,
        "linked_ids": {"simulation_id": simulation_id},
    }


def _dead_pid() -> int:
    """Eine garantiert tote PID: ein bereits beendeter Subprozess."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    pid = proc.pid
    proc.wait(timeout=5)
    return pid


class TestReconcileStaleRuns:
    def test_dead_pid_is_marked_failed_process_restart(self, monkeypatch):
        run = _make_run("run_1", status="processing", simulation_id="sim_1")
        registry = _FakeRegistry([run])

        state = SimulationRunState(
            simulation_id="sim_1",
            runner_status=RunnerStatus.RUNNING,
            process_pid=_dead_pid(),
        )
        saved_states: List[SimulationRunState] = []
        monkeypatch.setattr(reconciliation_module, "load_run_state", lambda sim_id, base: state)
        monkeypatch.setattr(
            reconciliation_module,
            "save_run_state",
            lambda s, base, **kw: saved_states.append(s),
        )

        result = reconcile_stale_runs(registry, "/fake/run-state-dir")

        assert result == ReconciliationResult(
            reconciled_run_ids=["run_1"], skipped_run_ids=[]
        )
        assert registry._runs["run_1"]["status"] == "failed"
        assert registry._runs["run_1"]["termination_reason"] == "process_restart"
        assert registry._runs["run_1"]["error"] == "Prozess-Neustart während des Runs"
        assert saved_states[0].runner_status == RunnerStatus.FAILED
        assert saved_states[0].error == "Prozess-Neustart während des Runs"

    def test_live_pid_is_left_untouched(self, monkeypatch):
        import os

        run = _make_run("run_2", status="processing", simulation_id="sim_2")
        registry = _FakeRegistry([run])

        state = SimulationRunState(
            simulation_id="sim_2",
            runner_status=RunnerStatus.RUNNING,
            process_pid=os.getpid(),
        )
        save_mock = MagicMock()
        monkeypatch.setattr(reconciliation_module, "load_run_state", lambda sim_id, base: state)
        monkeypatch.setattr(reconciliation_module, "save_run_state", save_mock)

        result = reconcile_stale_runs(registry, "/fake/run-state-dir")

        assert result == ReconciliationResult(
            reconciled_run_ids=[], skipped_run_ids=["run_2"]
        )
        assert registry._runs["run_2"]["status"] == "processing"
        assert not registry.updates
        save_mock.assert_not_called()

    def test_missing_run_state_is_marked_failed_process_restart(self, monkeypatch):
        """Kein run_state.json vorhanden (z. B. Run nie richtig gestartet) —
        ohne verifizierbare PID gilt der Run als verwaist."""
        run = _make_run("run_3", status="pending", simulation_id="sim_3")
        registry = _FakeRegistry([run])

        monkeypatch.setattr(reconciliation_module, "load_run_state", lambda sim_id, base: None)
        save_mock = MagicMock()
        monkeypatch.setattr(reconciliation_module, "save_run_state", save_mock)

        result = reconcile_stale_runs(registry, "/fake/run-state-dir")

        assert result == ReconciliationResult(
            reconciled_run_ids=["run_3"], skipped_run_ids=[]
        )
        assert registry._runs["run_3"]["status"] == "failed"
        assert registry._runs["run_3"]["termination_reason"] == "process_restart"
        # Kein run_state.json zum Aktualisieren vorhanden -> save_run_state
        # wird für diesen Run nicht aufgerufen.
        save_mock.assert_not_called()

    def test_disabled_flag_leaves_everything_untouched(self, monkeypatch):
        run = _make_run("run_4", status="processing", simulation_id="sim_4")
        registry = _FakeRegistry([run])

        load_mock = MagicMock(side_effect=AssertionError("should not be called"))
        monkeypatch.setattr(reconciliation_module, "load_run_state", load_mock)

        result = reconcile_stale_runs(registry, "/fake/run-state-dir", enabled=False)

        assert result == ReconciliationResult(reconciled_run_ids=[], skipped_run_ids=[])
        assert registry._runs["run_4"]["status"] == "processing"
        assert not registry.updates
        load_mock.assert_not_called()

    def test_injected_is_pid_alive_is_used_instead_of_os_kill(self, monkeypatch):
        """``is_pid_alive`` ist injizierbar — Tests brauchen keinen echten
        Subprozess, wenn sie nur die Verzweigung prüfen wollen."""
        run = _make_run("run_5", status="processing", simulation_id="sim_5")
        registry = _FakeRegistry([run])

        state = SimulationRunState(
            simulation_id="sim_5", runner_status=RunnerStatus.RUNNING, process_pid=123
        )
        monkeypatch.setattr(reconciliation_module, "load_run_state", lambda sim_id, base: state)
        monkeypatch.setattr(reconciliation_module, "save_run_state", MagicMock())

        result = reconcile_stale_runs(
            registry, "/fake/run-state-dir", is_pid_alive=lambda pid: True
        )

        assert result == ReconciliationResult(reconciled_run_ids=[], skipped_run_ids=["run_5"])

    def test_dead_pid_with_completed_run_state_is_left_untouched_not_propagated(
        self, monkeypatch
    ):
        """F2 (Codex-Review Runde 3, PR #1476): ``run_state.json`` wurde
        bereits erfolgreich als COMPLETED persistiert, aber die
        anschließende RunRegistry-Synchronisation kam nie an (Prozess starb
        dazwischen) — die Registry steht noch auf ``processing``, die PID
        ist tot. ``run_state.json`` trägt keine RunRegistry-``run_id``,
        daher ist NICHT verifizierbar, dass dieser COMPLETED-Zustand zu
        GENAU diesem Manifest gehört (statt z. B. zu einem Ersatzlauf nach
        einem Resume, Finding F1) — der Run bleibt unangetastet, nur
        geloggt/übersprungen, statt fälschlich propagiert zu werden."""
        run = _make_run("run_6", status="processing", simulation_id="sim_6")
        registry = _FakeRegistry([run])

        state = SimulationRunState(
            simulation_id="sim_6",
            runner_status=RunnerStatus.COMPLETED,
            process_pid=_dead_pid(),
        )
        save_mock = MagicMock()
        monkeypatch.setattr(reconciliation_module, "load_run_state", lambda sim_id, base: state)
        monkeypatch.setattr(reconciliation_module, "save_run_state", save_mock)

        result = reconcile_stale_runs(registry, "/fake/run-state-dir")

        assert result == ReconciliationResult(
            reconciled_run_ids=[], skipped_run_ids=["run_6"], synced_terminal_run_ids=[]
        )
        # Unveraendert -- keine stille Datenkorruption durch einen fremden
        # Endzustand.
        assert registry._runs["run_6"]["status"] == "processing"
        assert not registry.updates
        save_mock.assert_not_called()

    def test_dead_pid_with_stopped_run_state_is_left_untouched_not_propagated(
        self, monkeypatch
    ):
        """Analog zu oben, aber STOPPED mit bereits gesetztem
        ``termination_reason`` (z. B. ``user_stop``, seit Slice 1) auf der
        Registry -- auch dieser Zustand wird ohne verifizierbare Run-ID-
        Verknuepfung nicht propagiert."""
        run = _make_run("run_7", status="processing", simulation_id="sim_7")
        run["termination_reason"] = "user_stop"
        registry = _FakeRegistry([run])

        state = SimulationRunState(
            simulation_id="sim_7",
            runner_status=RunnerStatus.STOPPED,
            process_pid=_dead_pid(),
        )
        save_mock = MagicMock()
        monkeypatch.setattr(reconciliation_module, "load_run_state", lambda sim_id, base: state)
        monkeypatch.setattr(reconciliation_module, "save_run_state", save_mock)

        result = reconcile_stale_runs(registry, "/fake/run-state-dir")

        assert result == ReconciliationResult(
            reconciled_run_ids=[], skipped_run_ids=["run_7"], synced_terminal_run_ids=[]
        )
        assert registry._runs["run_7"]["status"] == "processing"
        assert registry._runs["run_7"]["termination_reason"] == "user_stop"
        assert not registry.updates
        save_mock.assert_not_called()

    def test_dead_pid_with_completed_run_state_and_multiple_manifests_is_not_corrupted(
        self, monkeypatch
    ):
        """F2-Kernszenario: zwei RunRegistry-Manifeste fuer dieselbe
        ``simulation_id`` -- ein aelterer, tatsaechlich verwaister Run
        (``run_orphan``, noch ``processing``) neben einem Ersatzlauf, der
        bereits laengst als ``completed`` geschlossen wurde und NICHT mehr
        in der stale-Liste auftaucht. Das geteilte ``run_state.json`` zeigt
        (vom Ersatzlauf) COMPLETED. Ohne Run-ID-Verknuepfung darf dieser
        fremde Endzustand nicht auf ``run_orphan`` durchschlagen."""
        run_orphan = _make_run("run_orphan", status="processing", simulation_id="sim_8")
        registry = _FakeRegistry([run_orphan])

        state = SimulationRunState(
            simulation_id="sim_8",
            runner_status=RunnerStatus.COMPLETED,
            process_pid=_dead_pid(),
        )
        monkeypatch.setattr(reconciliation_module, "load_run_state", lambda sim_id, base: state)
        monkeypatch.setattr(reconciliation_module, "save_run_state", MagicMock())

        result = reconcile_stale_runs(registry, "/fake/run-state-dir")

        assert result == ReconciliationResult(
            reconciled_run_ids=[], skipped_run_ids=["run_orphan"], synced_terminal_run_ids=[]
        )
        assert registry._runs["run_orphan"]["status"] == "processing"

    def test_paused_run_with_dead_pid_is_marked_failed_process_restart(self, monkeypatch):
        """F1 (Codex-Review Runde 4, PR #1476): ``pause_simulation``
        persistiert die Registry als ``paused``, nicht ``processing`` —
        ein solcher Run muss nach einem Prozess-Neustart genauso als
        verwaist erkannt werden wie ein ``processing``-Run."""
        run = _make_run("run_paused", status="paused", simulation_id="sim_paused")
        registry = _FakeRegistry([run])

        state = SimulationRunState(
            simulation_id="sim_paused",
            runner_status=RunnerStatus.PAUSED,
            process_pid=_dead_pid(),
        )
        saved_states: List[SimulationRunState] = []
        monkeypatch.setattr(reconciliation_module, "load_run_state", lambda sim_id, base: state)
        monkeypatch.setattr(
            reconciliation_module,
            "save_run_state",
            lambda s, base, **kw: saved_states.append(s),
        )

        result = reconcile_stale_runs(registry, "/fake/run-state-dir")

        assert result == ReconciliationResult(
            reconciled_run_ids=["run_paused"], skipped_run_ids=[]
        )
        assert registry._runs["run_paused"]["status"] == "failed"
        assert registry._runs["run_paused"]["termination_reason"] == "process_restart"
        assert saved_states[0].runner_status == RunnerStatus.FAILED

    def test_paused_run_with_live_pid_is_left_untouched(self, monkeypatch):
        """Kooperative Pause: der OASIS-Subprozess lebt noch und pausiert
        sich erst nach der laufenden Runde selbst — kein verwaister Run."""
        import os

        run = _make_run("run_paused_alive", status="paused", simulation_id="sim_paused_alive")
        registry = _FakeRegistry([run])

        state = SimulationRunState(
            simulation_id="sim_paused_alive",
            runner_status=RunnerStatus.PAUSED,
            process_pid=os.getpid(),
        )
        save_mock = MagicMock()
        monkeypatch.setattr(reconciliation_module, "load_run_state", lambda sim_id, base: state)
        monkeypatch.setattr(reconciliation_module, "save_run_state", save_mock)

        result = reconcile_stale_runs(registry, "/fake/run-state-dir")

        assert result == ReconciliationResult(
            reconciled_run_ids=[], skipped_run_ids=["run_paused_alive"]
        )
        assert registry._runs["run_paused_alive"]["status"] == "paused"
        save_mock.assert_not_called()

    def test_multiple_manifests_for_same_simulation_are_all_reconciled(self, monkeypatch):
        """F2 (Codex-Review Runde 4, PR #1476): teilen sich zwei stale
        Manifeste (``run_a``, ``run_b``) dieselbe ``simulation_id`` mit
        totem Prozess und nichtterminalem ``run_state.json``, muessen BEIDE
        als verwaist markiert werden — nicht nur das erste, dessen
        Bearbeitung den gemeinsamen Zustand vor der zweiten Iteration
        bereits auf FAILED umschreibt."""
        run_a = _make_run("run_a", status="processing", simulation_id="sim_shared")
        run_b = _make_run("run_b", status="processing", simulation_id="sim_shared")
        registry = _FakeRegistry([run_a, run_b])

        state = SimulationRunState(
            simulation_id="sim_shared",
            runner_status=RunnerStatus.RUNNING,
            process_pid=_dead_pid(),
        )
        saved_states: List[SimulationRunState] = []
        monkeypatch.setattr(reconciliation_module, "load_run_state", lambda sim_id, base: state)
        monkeypatch.setattr(
            reconciliation_module,
            "save_run_state",
            lambda s, base, **kw: saved_states.append(s),
        )

        result = reconcile_stale_runs(registry, "/fake/run-state-dir")

        assert result == ReconciliationResult(
            reconciled_run_ids=["run_a", "run_b"], skipped_run_ids=[]
        )
        assert registry._runs["run_a"]["status"] == "failed"
        assert registry._runs["run_a"]["termination_reason"] == "process_restart"
        assert registry._runs["run_b"]["status"] == "failed"
        assert registry._runs["run_b"]["termination_reason"] == "process_restart"
        # Der gemeinsame run_state.json-Zustand wird nur EINMAL geschrieben,
        # nicht pro Manifest.
        assert len(saved_states) == 1
        assert saved_states[0].runner_status == RunnerStatus.FAILED

    def test_other_run_types_are_not_touched(self, monkeypatch):
        """Nur ``simulation_run`` hat eine verifizierbare Prozess-PID —
        andere Run-Typen bleiben außerhalb dieses Slices unangetastet."""
        other_run = {
            "run_id": "run_report",
            "run_type": "report_generate",
            "status": "processing",
            "entity_id": "sim_6",
            "linked_ids": {"simulation_id": "sim_6"},
        }
        registry = _FakeRegistry([other_run])
        monkeypatch.setattr(
            reconciliation_module,
            "load_run_state",
            MagicMock(side_effect=AssertionError("should not be called")),
        )

        result = reconcile_stale_runs(registry, "/fake/run-state-dir")

        assert result == ReconciliationResult(reconciled_run_ids=[], skipped_run_ids=[])
        assert registry._runs["run_report"]["status"] == "processing"
