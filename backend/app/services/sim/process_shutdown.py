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

_shutdown_registered = False
_shutdown_lock = threading.Lock()


class _RunRegistryProtocol(Protocol):
    """Minimale Schnittstelle für die RunRegistry."""

    def list_runs(self, *, statuses: List[str], run_type: str, limit: int) -> List[Dict[str, Any]]: ...

    def update_run(self, run_id: str, **updates: Any) -> Optional[Dict[str, Any]]: ...


def _is_process_alive(pid: Optional[int]) -> bool:
    """True wenn ``pid`` einen (noch) existierenden Prozess bezeichnet.

    Liveness-Muster wie ``SimulationIPCClient.check_env_alive``
    (``simulation_ipc.py``): ``os.kill(pid, 0)`` sendet kein Signal, prüft
    nur Existenz/Berechtigung.

    ``pid`` fehlend/``None``/``<= 0`` → tot (konservativ: kein PID heißt kein
    verifizierbarer laufender Prozess). ``ProcessLookupError`` → tot.
    ``PermissionError`` → Prozess existiert, gehört aber jemand anderem —
    im Container unwahrscheinlich, wird konservativ als lebend behandelt.
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


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

    current_pid = os.getpid()
    current_token = None
    # Worker-Token für diesen Prozess holen (lazy, damit Import-Zyklen vermieden werden)
    try:
        from ...jobs.identity import worker_token

        current_token = worker_token()
    except Exception as exc:  # noqa: BLE001 — best effort
        logger.warning("process_shutdown: worker_token nicht verfügbar: %s", exc)

    for run_type in _IN_PROCESS_RUN_TYPES:
        for run in registry.list_runs(
            statuses=_STALE_STATUSES, run_type=run_type, limit=100_000
        ):
            run_id = run.get("run_id")
            if not run_id:
                continue

            metadata = run.get("metadata") or {}
            run_token = metadata.get("worker_token")
            run_pid = metadata.get("worker_pid")

            # Prüfen, ob der Job *diesem* Prozess gehört
            owns_job = (
                run_token == current_token and run_pid == current_pid
            ) if current_token else False

            if owns_job:
                logger.info(
                    "process_shutdown: run=%s (%s) gehört zu diesem Prozess — markiere failed/%s",
                    run_id,
                    run_type,
                    _TERMINATION_REASON,
                )
            else:
                logger.info(
                    "process_shutdown: run=%s (%s) gehört NICHT zu diesem Prozess (pid=%s token=%s) — markiere failed/%s",
                    run_id,
                    run_type,
                    run_pid,
                    run_token[:8] if run_token else None,
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
    global _shutdown_registered

    with _shutdown_lock:
        if _shutdown_registered:
            return

        # In Flask debug mode (Werkzeug reloader): nur im Child-Prozess registrieren
        is_reloader_process = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
        is_debug_mode = (
            os.environ.get("FLASK_DEBUG") == "1"
            or os.environ.get("WERKZEUG_RUN_MAIN") is not None
        )

        if is_debug_mode and not is_reloader_process:
            _shutdown_registered = True
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
            _shutdown_registered = True
            logger.info("process_shutdown: SIGTERM/SIGINT handler registered for in-process jobs")
        except ValueError:
            logger.warning(
                "process_shutdown: Cannot register signal handler (not in main thread)"
            )
            _shutdown_registered = True


__all__ = [
    "register_shutdown_handler",
    "_mark_in_process_jobs_failed",
]