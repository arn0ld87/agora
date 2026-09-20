"""SIGTERM/Worker-Exit-Hook für In-Process-Jobs (Issue #1472a).

Beim SIGTERM erhalten alle laufenden In-Process-Jobs (simulation_prepare,
report_generate, graph_build, ontology_generate) einen ehrlichen terminalen
Zustand (failed/process_restart), statt auf die Reconciliation beim nächsten
Start zu warten.

Die Logik spiegelt die Schreibreihenfolge von ``reconcile_stale_jobs``:
1. Cancel-Flag setzen (kooperativer Abbruch für Jobs, die es prüfen)
2. SimulationState (für simulation_prepare) *vor* Manifest schreiben (F1-Invariante)
3. RunRegistry-Manifest auf failed/process_restart setzen

Kein neuer TerminationReason-Wert — ``process_restart`` wird wiederverwendet.
"""

from __future__ import annotations

import os
import signal
import threading
from typing import Any, Callable, Dict, List, Optional, Protocol

from ...utils.logger import get_logger
from .cancel_flag import request_cancel
from .reconciliation import (
    _ERROR_MESSAGE,
    _IN_PROCESS_RUN_TYPES,
    _STALE_STATUSES,
    _TERMINATION_REASON,
    ReconciliationResult,
)

logger = get_logger("agora.process_shutdown")

# Prozessgebunden statt ein reines bool (Slice 1.1 Fund, 2026-09-20): unter
# ``preload_app = True`` (gunicorn.conf.py) erbt der geforkte Worker den
# Modul-Zustand des Masters, inklusive eines bereits auf True stehenden
# Flags — eine erneute Registrierung im Worker (nötig, weil init_signals()
# den geerbten Handler ohnehin geloescht hat, siehe gunicorn.conf.py) würde
# damit still übersprungen. Die PID im Vergleich macht die Sperre pro
# Prozess statt pro Modul-Import gültig: ein anderer ``os.getpid()`` als
# beim letzten Erfolg gilt als "noch nicht registriert".
_shutdown_registered_pid: Optional[int] = None
_shutdown_lock = threading.Lock()


class _RunRegistryProtocol(Protocol):
    """Minimale Schnittstelle für die RunRegistry."""

    def list_runs(self, *, statuses: List[str], run_type: str, limit: int) -> List[Dict[str, Any]]: ...

    def update_run(self, run_id: str, **updates: Any) -> Optional[Dict[str, Any]]: ...


def _mark_in_process_jobs_failed(
    registry: _RunRegistryProtocol,
    *,
    fail_simulation_state: Optional[Callable[[str, str], None]] = None,
) -> ReconciliationResult:
    """Markiert alle laufenden In-Process-Jobs dieses Prozesses als failed/process_restart.

    Args:
        registry: RunRegistry-Instanz (oder Test-Stub).
        fail_simulation_state: Callback für simulation_prepare, um auch den
            SimulationState aus preparing zu holen. Default: no-op.

    Returns:
        ReconciliationResult mit den markierten Run-IDs.
    """
    reconciled: List[str] = []
    skipped: List[str] = []

    # Anders als ``reconcile_stale_jobs`` (reconciliation.py, filtert per
    # ``owns()``) wird hier bewusst NICHT nach Ownership gefiltert: die
    # ``workers = 1``-HARDSTOP-Invariante in ``gunicorn.conf.py`` garantiert,
    # dass in Produktion genau ein Prozess In-Process-Jobs besitzen kann.
    # Der SIGTERM, der diesen Handler auslöst, trifft also entweder den
    # Prozess, der die Jobs selbst hält (der gerade stirbt), oder es gibt
    # keinen zweiten Prozess, dessen fremde Jobs verschont werden müssten.
    # Eine Ownership-Prüfung wäre hier reine Attrappe.
    for run_type in _IN_PROCESS_RUN_TYPES:
        for run in registry.list_runs(
            statuses=_STALE_STATUSES, run_type=run_type, limit=100_000
        ):
            run_id = run.get("run_id")
            if not run_id:
                continue

            logger.info(
                "process_shutdown: run=%s (%s) — markiere failed/%s",
                run_id,
                run_type,
                _TERMINATION_REASON,
            )

            # Cancel-Flag setzen für kooperativen Abbruch (Issue #1082)
            request_cancel(run_id)

            # F1-Invariante: SimulationState (für simulation_prepare) VOR Manifest
            simulation_id = None
            if run_type == "simulation_prepare":
                simulation_id = (
                    (run.get("linked_ids") or {}).get("simulation_id") or run.get("entity_id")
                )
                if simulation_id and fail_simulation_state is not None:
                    try:
                        fail_simulation_state(simulation_id, _ERROR_MESSAGE)
                    except Exception as exc:  # noqa: BLE001 — State-Write darf nicht blockieren
                        logger.error(
                            "process_shutdown: fail_simulation_state fehlgeschlagen für %s: %s",
                            simulation_id,
                            exc,
                        )

            # Manifest aktualisieren
            try:
                registry.update_run(
                    run_id,
                    status="failed",
                    termination_reason=_TERMINATION_REASON,
                    error=_ERROR_MESSAGE,
                )
                reconciled.append(run_id)
            except Exception as exc:  # noqa: BLE001 — Registry-Write darf nicht blockieren
                logger.error(
                    "process_shutdown: registry.update_run fehlgeschlagen für %s: %s",
                    run_id,
                    exc,
                )
                skipped.append(run_id)

    return ReconciliationResult(reconciled_run_ids=reconciled, skipped_run_ids=skipped)


def register_shutdown_handler(
    *,
    get_registry: Callable[[], _RunRegistryProtocol],
    fail_simulation_state: Optional[Callable[[str, str], None]] = None,
) -> None:
    """Registriert SIGTERM/SIGINT-Handler für sauberes Herunterfahren der In-Process-Jobs.

    Args:
        get_registry: Callable, der die RunRegistry-Instanz liefert.
        fail_simulation_state: Optional, wird an _mark_in_process_jobs_failed
            durchgereicht (für simulation_prepare).
    """
    global _shutdown_registered_pid

    with _shutdown_lock:
        current_pid = os.getpid()
        if _shutdown_registered_pid == current_pid:
            return

        # In Flask debug mode (Werkzeug reloader): nur im Child-Prozess registrieren
        is_reloader_process = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
        is_debug_mode = (
            os.environ.get("FLASK_DEBUG") == "1"
            or os.environ.get("WERKZEUG_RUN_MAIN") is not None
        )

        if is_debug_mode and not is_reloader_process:
            _shutdown_registered_pid = current_pid
            return

        def _shutdown_handler(signum: int, frame: Any) -> None:
            """Signal Handler: markiert In-Process-Jobs als failed/process_restart."""
            logger.info("Received signal %s, marking in-process jobs as failed/process_restart", signum)

            try:
                registry = get_registry()
                result = _mark_in_process_jobs_failed(
                    registry, fail_simulation_state=fail_simulation_state
                )
                logger.info(
                    "process_shutdown: %d In-Process-Jobs als failed/%s markiert, %d übersprungen",
                    len(result.reconciled_run_ids),
                    _TERMINATION_REASON,
                    len(result.skipped_run_ids),
                )
            except Exception as exc:  # noqa: BLE001 — Handler darf nicht crashen
                logger.error("process_shutdown: Fehler beim Markieren der Jobs: %s", exc, exc_info=True)

        # Original-Handler speichern
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)

        def _combined_handler(signum: int, frame: Any) -> None:
            _shutdown_handler(signum, frame)
            # Original-Handler aufrufen (z. B. für Flask-Shutdown)
            if signum == signal.SIGTERM and callable(original_sigterm):
                original_sigterm(signum, frame)
            elif signum == signal.SIGINT and callable(original_sigint):
                original_sigint(signum, frame)
            else:
                # Fallback: hart beenden
                os._exit(1)

        try:
            signal.signal(signal.SIGTERM, _combined_handler)
            signal.signal(signal.SIGINT, _combined_handler)
            _shutdown_registered_pid = current_pid
            logger.info("process_shutdown: SIGTERM/SIGINT handler registered for in-process jobs")
        except ValueError:
            logger.warning(
                "process_shutdown: Cannot register signal handler (not in main thread)"
            )
            _shutdown_registered_pid = current_pid


__all__ = [
    "register_shutdown_handler",
    "_mark_in_process_jobs_failed",
]