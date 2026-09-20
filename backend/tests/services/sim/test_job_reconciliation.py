"""Tests fuer ``reconcile_stale_jobs`` und ``process_shutdown`` — SIGTERM/Worker-Exit-Hook.

Issue #1472 / #1472a. ``reconcile_stale_runs`` deckt ausschliesslich ``simulation_run``
ab, weil nur dieser Run-Typ eine ``process_pid`` in ``run_state.json`` traegt
und damit eine verifizierbare Liveness hat — der Modulkommentar an
``_RUN_TYPE`` benennt das ausdruecklich als bewusste Slice-Grenze.

Die In-Process-Jobs (``simulation_prepare``, ``report_generate``,
``graph_build``, ``ontology_generate``) laufen als
``threading.Thread(daemon=True)`` im Webprozess. Nach einem SIGTERM existiert
der Thread nicht mehr, das Manifest bleibt aber auf ``processing`` stehen — fuer
immer, weil nichts mehr existiert, das es je wieder aendern wuerde. Genau das
ist der endlos laufende Status aus #1472.

Der SIGTERM-Handler in ``process_shutdown`` markiert diese Jobs sofort als
``failed``/``process_restart`` beim Empfang von SIGTERM, statt auf die
Reconciliation beim nächsten Start zu warten.
"""

from __future__ import annotations

import atexit
import os
import signal

from typing import Any, Dict, List, Optional

import pytest

from app.jobs.identity import current_worker_identity
from app.services.sim import process_shutdown
from app.services.sim.cancel_flag import is_cancel_requested
from app.services.sim.reconciliation import reconcile_stale_jobs
from app.services.sim.process_shutdown import _mark_in_process_jobs_failed

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


class TestWriteOrderMatchesTheF1Invariant:
    """Codex-Befund P2 auf PR #1498.

    ``reconcile_stale_runs`` schreibt seit PR #1476 Runde 5 (Finding F1)
    bewusst ``save_run_state`` *vor* ``registry.update_run``: ein verwaister
    Run gilt als korrigiert, sobald er auch nur EINE der beiden Persistenzen
    erreicht hat, denn das Manifest faellt mit ``failed`` aus
    ``_STALE_STATUSES`` und wird nie wieder aufgegriffen. Steht die Registry
    zuerst und scheitert der zweite Schritt, bleibt eine Halb-Korrektur fuer
    immer stehen — hier: ein Manifest auf ``failed`` neben einem
    ``SimulationState`` auf ``preparing``, also genau der endlose
    Vorbereitungs-Status aus #1472.

    ``reconcile_stale_jobs`` haelt dieselben zwei Persistenzen und damit
    dieselbe Invariante.
    """

    def test_the_simulation_state_is_written_before_the_manifest(self) -> None:
        order: List[str] = []

        class _OrderingRegistry(_FakeRegistry):
            def update_run(self, run_id: str, **updates: Any):
                order.append("manifest")
                return super().update_run(run_id, **updates)

        registry = _OrderingRegistry([_run("run_a", metadata={"worker_token": "gone"})])

        reconcile_stale_jobs(
            registry,
            fail_simulation_state=lambda sid, error: order.append("state"),
        )

        assert order == ["state", "manifest"]

    def test_a_failing_state_write_leaves_the_manifest_stale(self) -> None:
        """Damit der naechste Start denselben Run erneut aufgreift."""

        def _boom(simulation_id: str, error: str) -> None:
            raise OSError("disk full")

        registry = _FakeRegistry([_run("run_a", metadata={"worker_token": "gone"})])

        with pytest.raises(OSError, match="disk full"):
            reconcile_stale_jobs(registry, fail_simulation_state=_boom)

        assert registry.updates == []
        assert registry._runs["run_a"]["status"] == "processing"

    def test_a_run_without_a_simulation_id_still_reaches_the_manifest(self) -> None:
        """Ohne ``simulation_id`` gibt es keinen zweiten Zustand — das Manifest
        allein zu korrigieren ist dann vollstaendig, keine Halb-Korrektur."""
        run = _run("run_a", metadata={"worker_token": "gone"})
        run["entity_id"] = None
        run["linked_ids"] = {}
        registry = _FakeRegistry([run])

        result = reconcile_stale_jobs(registry, fail_simulation_state=lambda *_: None)

        assert result.reconciled_run_ids == ["run_a"]
        assert registry.updates[0]["status"] == "failed"


class TestProcessShutdownHandler:
    """Tests für den SIGTERM-Handler in ``process_shutdown`` (Issue #1472a).

    Seit Slice 1.1 (P1-Fund, Codex-Review PR #1528) ist die Arbeit auf zwei
    Stellen verteilt: der Signal-Handler setzt nur ein Flag und kettet den
    zuvor bestehenden Handler weiter (nimmt KEIN Lock), die eigentliche
    Markierung als failed/process_restart — inklusive Cancel-Flag und
    SimulationState-Update für simulation_prepare — läuft im atexit-Callback.
    """

    def test_marks_all_in_process_jobs_as_failed(self) -> None:
        """Alle vier In-Process-Run-Typen werden markiert."""
        registry = _FakeRegistry([
            _run("run_prepare", run_type="simulation_prepare", metadata={"worker_token": "other"}),
            _run("run_report", run_type="report_generate", metadata={"worker_token": "other"}),
            _run("run_graph", run_type="graph_build", metadata={"worker_token": "other"}),
            _run("run_ontology", run_type="ontology_generate", metadata={"worker_token": "other"}),
        ])

        seen_state: List[tuple] = []
        result = _mark_in_process_jobs_failed(
            registry,
            fail_simulation_state=lambda sid, err: seen_state.append((sid, err)),
        )

        assert set(result.reconciled_run_ids) == {
            "run_prepare", "run_report", "run_graph", "run_ontology"
        }
        assert result.skipped_run_ids == []
        assert len(registry.updates) == 4
        for update in registry.updates:
            assert update["status"] == "failed"
            assert update["termination_reason"] == "process_restart"
            assert update["error"] == "Prozess-Neustart während des Runs"

    def test_sets_cancel_flag_for_each_run(self) -> None:
        """Cancel-Flag wird für jeden Run gesetzt (kooperativer Abbruch)."""
        registry = _FakeRegistry([
            _run("run_a", run_type="simulation_prepare", metadata={"worker_token": "other"}),
            _run("run_b", run_type="report_generate", metadata={"worker_token": "other"}),
        ])

        _mark_in_process_jobs_failed(registry, fail_simulation_state=lambda *_: None)

        assert is_cancel_requested("run_a")
        assert is_cancel_requested("run_b")

    def test_calls_fail_simulation_state_for_prepare_only(self) -> None:
        """fail_simulation_state wird nur für simulation_prepare aufgerufen."""
        seen: List[tuple] = []
        registry = _FakeRegistry([
            _run("run_prepare", run_type="simulation_prepare", metadata={"worker_token": "other"}),
            _run("run_report", run_type="report_generate", metadata={"worker_token": "other"}),
            _run("run_graph", run_type="graph_build", metadata={"worker_token": "other"}),
        ])

        _mark_in_process_jobs_failed(
            registry,
            fail_simulation_state=lambda sid, err: seen.append((sid, err)),
        )

        assert len(seen) == 1
        assert seen[0][0] == "sim_0123456789ab"
        assert seen[0][1] == "Prozess-Neustart während des Runs"

    def test_write_order_state_before_manifest(self) -> None:
        """F1-Invariante: State-Write vor Manifest-Write (wie reconcile_stale_jobs)."""
        order: List[str] = []

        class _OrderingRegistry(_FakeRegistry):
            def update_run(self, run_id: str, **updates: Any):
                order.append("manifest")
                return super().update_run(run_id, **updates)

        registry = _OrderingRegistry([
            _run("run_prepare", run_type="simulation_prepare", metadata={"worker_token": "other"}),
        ])

        _mark_in_process_jobs_failed(
            registry,
            fail_simulation_state=lambda sid, err: order.append("state"),
        )

        assert order == ["state", "manifest"]

    def test_jobs_of_this_process_are_also_marked(self) -> None:
        """Jobs, die *diesem* Prozess gehören, werden AUCH markiert (kein Skip).

        Anders als bei der Startup-Reconciliation (wo laufende Jobs nicht
        angefasst werden), markiert der SIGTERM-Handler ALLE Jobs — auch die
        des eigenen Prozesses —, weil der Prozess ja gerade stirbt.
        """
        my_identity = current_worker_identity()
        registry = _FakeRegistry([
            _run("run_a", metadata=my_identity),
            _run("run_b", run_type="report_generate", metadata=my_identity),
        ])

        result = _mark_in_process_jobs_failed(registry, fail_simulation_state=lambda *_: None)

        # Beide Runs gehören diesem Prozess, werden aber trotzdem markiert
        assert set(result.reconciled_run_ids) == {"run_a", "run_b"}
        assert result.skipped_run_ids == []

    def test_simulation_run_is_not_touched(self) -> None:
        """simulation_run wird nicht angefasst (gehört zu reconcile_stale_runs)."""
        registry = _FakeRegistry([
            _run("run_a", run_type="simulation_run", metadata={"worker_token": "other"}),
        ])

        result = _mark_in_process_jobs_failed(registry, fail_simulation_state=lambda *_: None)

        assert result.reconciled_run_ids == []
        assert registry.updates == []

    def test_terminal_runs_are_not_touched(self) -> None:
        """Bereits terminale Runs (completed/failed/stopped) werden nicht einmal
        von list_runs zurückgegeben (Filter über _STALE_STATUSES)."""
        registry = _FakeRegistry([
            _run("run_a", status="completed", metadata={"worker_token": "other"}),
            _run("run_b", status="failed", metadata={"worker_token": "other"}),
            _run("run_c", status="stopped", metadata={"worker_token": "other"}),
        ])

        result = _mark_in_process_jobs_failed(registry, fail_simulation_state=lambda *_: None)

        # Terminal Runs sind nicht in _STALE_STATUSES → list_runs liefert leer
        # → weder reconciled noch skipped
        assert result.reconciled_run_ids == []
        assert result.skipped_run_ids == []
        assert registry.updates == []

    def test_registry_error_is_logged_not_raised(self) -> None:
        """Fehler bei registry.update_run werden geloggt, nicht geworfen."""
        registry = _FakeRegistry([_run("run_a", metadata={"worker_token": "other"})])

        # Registry update_run zum Fehlschlagen bringen
        def _fail_update(run_id: str, **updates):
            raise RuntimeError("DB down")
        registry.update_run = _fail_update  # type: ignore[method-assign]

        # Sollte nicht werfen
        result = _mark_in_process_jobs_failed(registry, fail_simulation_state=lambda *_: None)

        assert result.reconciled_run_ids == []
        assert result.skipped_run_ids == ["run_a"]

    def test_signal_handler_takes_no_lock(self) -> None:
        """Regressionsschutz gegen den P1-Fund (Codex-Review, PR #1528):
        kommt SIGTERM, während der Hauptthread ``RunRegistry._lock`` hält,
        darf der Signal-Handler selbst KEINE lock-nehmende Registry-Methode
        aufrufen — unter gevent (siehe Moduldocstring von
        ``process_shutdown``) wäre das ein Deadlock-Risiko, weil der
        Handler synchron im unterbrochenen Greenlet läuft. Ein Fake, dessen
        ``list_runs``/``update_run`` hart fehlschlagen, deckt das direkt ab:
        bleibt der Handler bei reiner Signalzustellung ausschließlich
        flag-setzend, wirft dieser Test nie.
        """

        class _ExplodingRegistry:
            def list_runs(self, *, statuses: List[str], run_type: str, limit: int):
                raise AssertionError("Signal-Handler darf list_runs nicht aufrufen")

            def update_run(self, run_id: str, **updates: Any):
                raise AssertionError("Signal-Handler darf update_run nicht aufrufen")

        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_pid = process_shutdown._shutdown_registered_pid
        original_flag = process_shutdown._shutdown_signal_received

        def _foreign_handler(signum: int, frame: Any) -> None:
            """Steht für gunicorns ``Worker.handle_exit``."""

        try:
            signal.signal(signal.SIGTERM, _foreign_handler)
            process_shutdown._shutdown_registered_pid = None
            process_shutdown._shutdown_signal_received = False

            process_shutdown.register_shutdown_handler(get_registry=lambda: _ExplodingRegistry())

            # Darf NICHT werfen — das ist der eigentliche Regressionsschutz.
            signal.raise_signal(signal.SIGTERM)

            assert process_shutdown._shutdown_signal_received is True
        finally:
            signal.signal(signal.SIGTERM, original_sigterm)
            process_shutdown._shutdown_registered_pid = original_pid
            process_shutdown._shutdown_signal_received = original_flag
            if process_shutdown._shutdown_atexit_callback is not None:
                atexit.unregister(process_shutdown._shutdown_atexit_callback)

    def test_foreign_handler_is_chained_after_registration(self) -> None:
        """Chaining-Nachweis: der zuvor gesetzte Fremd-Handler (gunicorns
        ``handle_exit``) wird nach unserem Flag-Setzen ebenfalls noch
        aufgerufen. Ohne diese Kette würde der Worker beim Shutdown hängen,
        weil gunicorns eigener Exit-Pfad nie liefe."""
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_pid = process_shutdown._shutdown_registered_pid
        original_flag = process_shutdown._shutdown_signal_received
        registry = _FakeRegistry([])

        foreign_calls: List[int] = []

        def _foreign_handler(signum: int, frame: Any) -> None:
            foreign_calls.append(signum)

        try:
            signal.signal(signal.SIGTERM, _foreign_handler)
            process_shutdown._shutdown_registered_pid = None

            process_shutdown.register_shutdown_handler(get_registry=lambda: registry)

            signal.raise_signal(signal.SIGTERM)
        finally:
            signal.signal(signal.SIGTERM, original_sigterm)
            process_shutdown._shutdown_registered_pid = original_pid
            process_shutdown._shutdown_signal_received = original_flag
            if process_shutdown._shutdown_atexit_callback is not None:
                atexit.unregister(process_shutdown._shutdown_atexit_callback)

        assert foreign_calls == [signal.SIGTERM]

    def test_atexit_callback_terminalizes_the_jobs(self) -> None:
        """Der atexit-Callback ist seit Slice 1.1 der tatsächliche
        Terminalisierungspfad (siehe Moduldocstring von
        ``process_shutdown``): direkt aufgerufen — ohne jede Signal-
        zustellung — muss er dieselben failed/process_restart-Updates
        schreiben, die vorher der Signal-Handler selbst erledigt hat."""
        original_pid = process_shutdown._shutdown_registered_pid
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)
        registry = _FakeRegistry([
            _run("run_a", run_type="simulation_prepare", metadata={"worker_token": "other"}),
        ])

        try:
            process_shutdown._shutdown_registered_pid = None
            process_shutdown.register_shutdown_handler(get_registry=lambda: registry)

            callback = process_shutdown._shutdown_atexit_callback
            assert callback is not None
            callback()

            assert registry.updates
            assert registry.updates[0]["status"] == "failed"
            assert registry.updates[0]["termination_reason"] == "process_restart"
        finally:
            if process_shutdown._shutdown_atexit_callback is not None:
                atexit.unregister(process_shutdown._shutdown_atexit_callback)
            signal.signal(signal.SIGTERM, original_sigterm)
            signal.signal(signal.SIGINT, original_sigint)
            process_shutdown._shutdown_registered_pid = original_pid

    def test_atexit_callback_is_idempotent(self) -> None:
        """Ein Zweitaufruf des atexit-Callbacks (z. B. weil ein Prozess
        mehrere Einträge trägt) darf die Jobs nicht doppelt markieren."""
        original_pid = process_shutdown._shutdown_registered_pid
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)
        registry = _FakeRegistry([
            _run("run_a", metadata={"worker_token": "other"}),
        ])

        try:
            process_shutdown._shutdown_registered_pid = None
            process_shutdown.register_shutdown_handler(get_registry=lambda: registry)

            callback = process_shutdown._shutdown_atexit_callback
            assert callback is not None
            callback()
            callback()

            assert len(registry.updates) == 1
        finally:
            if process_shutdown._shutdown_atexit_callback is not None:
                atexit.unregister(process_shutdown._shutdown_atexit_callback)
            signal.signal(signal.SIGTERM, original_sigterm)
            signal.signal(signal.SIGINT, original_sigint)
            process_shutdown._shutdown_registered_pid = original_pid

    def test_atexit_callback_skips_a_foreign_pid(self) -> None:
        """PID-Bindung (Moduldocstring von ``process_shutdown``): ein via
        ``fork()`` von einem anderen Prozess geerbter atexit-Eintrag darf
        im aktuellen Prozess keine Jobs terminalisieren. ``os.getpid()``
        wird für die Dauer des Aufrufs gefälscht, um den Lauf in einem
        fremden Prozess nachzustellen, ohne tatsächlich zu forken."""
        original_pid = process_shutdown._shutdown_registered_pid
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)
        registry = _FakeRegistry([
            _run("run_a", metadata={"worker_token": "other"}),
        ])

        try:
            process_shutdown._shutdown_registered_pid = None
            process_shutdown.register_shutdown_handler(get_registry=lambda: registry)

            callback = process_shutdown._shutdown_atexit_callback
            assert callback is not None

            real_getpid = os.getpid
            os.getpid = lambda: real_getpid() + 1  # type: ignore[assignment]
            try:
                callback()
            finally:
                os.getpid = real_getpid  # type: ignore[assignment]

            assert registry.updates == []
        finally:
            if process_shutdown._shutdown_atexit_callback is not None:
                atexit.unregister(process_shutdown._shutdown_atexit_callback)
            signal.signal(signal.SIGTERM, original_sigterm)
            signal.signal(signal.SIGINT, original_sigint)
            process_shutdown._shutdown_registered_pid = original_pid

    def test_registration_is_pid_bound_not_a_plain_bool(self) -> None:
        """Slice 1.1 Fund: unter ``preload_app = True`` erbt der geforkte
        Worker den Modul-Zustand des Masters, inklusive eines bereits auf
        die Master-PID gesetzten Locks. Ein davon abweichendes
        ``os.getpid()`` (wie im geforkten Worker) muss die Registrierung
        erneut zulassen, statt sie stillschweigend zu überspringen."""
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)
        original_pid = process_shutdown._shutdown_registered_pid
        registry = _FakeRegistry([])

        try:
            # Simuliert den geerbten Zustand: "bereits registriert", aber
            # unter einer PID, die nicht die aktuelle ist.
            foreign_pid = os.getpid() + 1
            process_shutdown._shutdown_registered_pid = foreign_pid

            process_shutdown.register_shutdown_handler(get_registry=lambda: registry)

            assert process_shutdown._shutdown_registered_pid == os.getpid()
            assert process_shutdown._shutdown_registered_pid != foreign_pid
        finally:
            if process_shutdown._shutdown_atexit_callback is not None:
                atexit.unregister(process_shutdown._shutdown_atexit_callback)
            signal.signal(signal.SIGTERM, original_sigterm)
            signal.signal(signal.SIGINT, original_sigint)
            process_shutdown._shutdown_registered_pid = original_pid
