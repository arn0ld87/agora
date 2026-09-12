"""Tests fuer ``reconcile_stale_jobs`` — Startup-Reconciliation der In-Process-Jobs.

Issue #1472. ``reconcile_stale_runs`` deckt ausschliesslich ``simulation_run``
ab, weil nur dieser Run-Typ eine ``process_pid`` in ``run_state.json`` traegt
und damit eine verifizierbare Liveness hat — der Modulkommentar an
``_RUN_TYPE`` benennt das ausdruecklich als bewusste Slice-Grenze.

Die In-Process-Jobs (``simulation_prepare``, ``report_generate``,
``graph_build``, ``ontology_generate``) laufen als
``threading.Thread(daemon=True)`` im Webprozess. Nach einem SIGTERM existiert
der Thread nicht mehr, das Manifest bleibt aber auf ``processing`` stehen — fuer
immer, weil nichts mehr existiert, das es je wieder aendern wuerde. Genau das
ist der endlos laufende Status aus #1472.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.jobs.identity import current_worker_identity
from app.services.sim.reconciliation import reconcile_stale_jobs

IN_PROCESS_RUN_TYPES = [
    "simulation_prepare",
    "report_generate",
    "graph_build",
    "ontology_generate",
]


class _FakeRegistry:
    def __init__(self, runs: List[Dict[str, Any]]) -> None:
        self._runs = {r["run_id"]: r for r in runs}
        self.updates: List[Dict[str, Any]] = []

    def list_runs(self, *, statuses, run_type, limit) -> List[Dict[str, Any]]:
        return [
            r
            for r in self._runs.values()
            if r.get("status") in statuses and r.get("run_type") == run_type
        ]

    def update_run(self, run_id: str, **updates: Any) -> Optional[Dict[str, Any]]:
        run = self._runs.get(run_id)
        if run is None:
            return None
        run.update(updates)
        self.updates.append({"run_id": run_id, **updates})
        return run


def _run(
    run_id: str,
    *,
    run_type: str = "simulation_prepare",
    status: str = "processing",
    metadata: Optional[Dict[str, Any]] = None,
    simulation_id: str = "sim_0123456789ab",
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "run_type": run_type,
        "status": status,
        "entity_id": simulation_id,
        "linked_ids": {"simulation_id": simulation_id},
        "metadata": metadata if metadata is not None else {},
    }


class TestOrphanedJobsAreMarkedFailed:
    @pytest.mark.parametrize("run_type", IN_PROCESS_RUN_TYPES)
    def test_run_from_a_dead_process_is_reconciled(self, run_type: str) -> None:
        registry = _FakeRegistry(
            [_run("run_a", run_type=run_type, metadata={"worker_token": "gone"})]
        )

        result = reconcile_stale_jobs(registry)

        assert result.reconciled_run_ids == ["run_a"]
        assert registry.updates[0]["status"] == "failed"
        assert registry.updates[0]["termination_reason"] == "process_restart"

    @pytest.mark.parametrize("status", ["pending", "processing", "paused"])
    def test_every_non_terminal_status_is_covered(self, status: str) -> None:
        registry = _FakeRegistry(
            [_run("run_a", status=status, metadata={"worker_token": "gone"})]
        )

        assert reconcile_stale_jobs(registry).reconciled_run_ids == ["run_a"]

    def test_manifest_without_a_token_counts_as_orphaned(self) -> None:
        """Manifeste aus der Zeit vor diesem Mechanismus. Ein Job eines
        *laufenden* Prozesses traegt immer ein Token, weil ``enqueue`` es setzt,
        bevor der Thread startet — fehlt es, ist der Eigentuemer weg."""
        registry = _FakeRegistry([_run("run_a", metadata={})])

        assert reconcile_stale_jobs(registry).reconciled_run_ids == ["run_a"]


class TestLiveJobsAreLeftAlone:
    def test_run_owned_by_this_process_is_skipped(self) -> None:
        """Der Hauptfehler, den dieses Gate vermeiden muss: einen gerade
        laufenden Prepare-Job als gescheitert zu markieren."""
        registry = _FakeRegistry([_run("run_a", metadata=current_worker_identity())])

        result = reconcile_stale_jobs(registry)

        assert result.reconciled_run_ids == []
        assert result.skipped_run_ids == ["run_a"]
        assert registry.updates == []

    @pytest.mark.parametrize("status", ["completed", "failed", "stopped"])
    def test_terminal_runs_are_not_touched(self, status: str) -> None:
        registry = _FakeRegistry(
            [_run("run_a", status=status, metadata={"worker_token": "gone"})]
        )

        assert reconcile_stale_jobs(registry).reconciled_run_ids == []
        assert registry.updates == []

    def test_simulation_run_stays_with_the_subprocess_reconciler(self) -> None:
        """``simulation_run`` hat eine echte Subprozess-PID und gehoert
        weiterhin ``reconcile_stale_runs`` — eine Doppelbehandlung wuerde einen
        laufenden OASIS-Lauf abschiessen."""
        registry = _FakeRegistry(
            [_run("run_a", run_type="simulation_run", metadata={"worker_token": "gone"})]
        )

        assert reconcile_stale_jobs(registry).reconciled_run_ids == []
        assert registry.updates == []

    def test_disabled_flag_touches_nothing(self) -> None:
        registry = _FakeRegistry([_run("run_a", metadata={"worker_token": "gone"})])

        assert reconcile_stale_jobs(registry, enabled=False).reconciled_run_ids == []
        assert registry.updates == []


class TestSimulationStateFollows:
    """Der Prepare-Job haelt zwei Zustaende: das Registry-Manifest und den
    ``SimulationState``. Bleibt letzterer auf ``preparing``, zeigt die
    Oberflaeche weiter eine laufende Vorbereitung an."""

    def test_prepare_run_pushes_the_simulation_state_out_of_preparing(self) -> None:
        seen: List[tuple] = []
        registry = _FakeRegistry([_run("run_a", metadata={"worker_token": "gone"})])

        reconcile_stale_jobs(
            registry,
            fail_simulation_state=lambda sid, error: seen.append((sid, error)),
        )

        assert len(seen) == 1
        assert seen[0][0] == "sim_0123456789ab"

    def test_other_run_types_do_not_touch_the_simulation_state(self) -> None:
        seen: List[tuple] = []
        registry = _FakeRegistry(
            [_run("run_a", run_type="report_generate", metadata={"worker_token": "gone"})]
        )

        reconcile_stale_jobs(
            registry,
            fail_simulation_state=lambda sid, error: seen.append((sid, error)),
        )

        assert seen == []

    def test_a_failing_state_write_does_not_abort_the_reconciliation(self) -> None:
        """Das Manifest zu korrigieren ist wichtiger als der Folgeschritt."""

        def _boom(simulation_id: str, error: str) -> None:
            raise OSError("disk full")

        registry = _FakeRegistry([_run("run_a", metadata={"worker_token": "gone"})])

        result = reconcile_stale_jobs(registry, fail_simulation_state=_boom)

        assert result.reconciled_run_ids == ["run_a"]
