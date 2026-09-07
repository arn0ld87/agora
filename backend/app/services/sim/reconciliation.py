"""Startup-Reconciliation für verwaiste ``simulation_run``-Runs.

Tech-Review 2026-09-07, Slice B1.

Problem: ``RunRegistry``-Einträge (``uploads/run_registry/*.json``) und
``run_state.json`` kennen den Status eines Simulation-Runs nur so lange, wie
der zugehörige OASIS-Subprozess selbst ihn aktualisiert. Nach einem
Container-Restart existiert dieser Subprozess nicht mehr — die Dateien
bleiben aber auf ``pending``/``processing`` (Registry) bzw.
``STARTING``/``RUNNING`` (``run_state.json``) stehen und werden dem
Frontend fälschlich als „läuft noch" angezeigt, für immer, weil nichts
mehr existiert, das den Zustand jemals wieder ändert.

``reconcile_stale_runs`` läuft einmalig beim App-Start (siehe
``app/__init__.py::create_app``) und korrigiert genau diese verwaisten
Runs anhand der in ``run_state.json`` persistierten ``process_pid``:
existiert der Prozess nicht (mehr), wird der Run als
``failed``/``process_restart`` markiert; existiert er noch (z. B. weil nur
ein Worker-Prozess neu gestartet wurde, der Subprozess aber überlebt hat),
bleibt er unangetastet.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Protocol

from pydantic import BaseModel, ConfigDict

from ...utils.logger import get_logger
from .process_manager import is_process_alive
from .run_state_store import RunnerStatus, load_run_state, save_run_state

logger = get_logger("agora.sim.reconciliation")

#: Registry-Status, die nach einem Neustart nicht mehr vertrauenswürdig
#: sind — es gibt keinen Prozess mehr, der sie aktiv hält.
_STALE_STATUSES = ["pending", "processing"]

#: Nur ``simulation_run`` hat eine ``process_pid`` in ``run_state.json`` und
#: damit eine verifizierbare Liveness. Andere Run-Typen (``report_generate``,
#: ``graph_build``, ...) laufen als In-Process-Threads ohne dieses Muster —
#: sie bleiben bewusst außerhalb dieses Slices (siehe Abschlussbericht).
_RUN_TYPE = "simulation_run"

_TERMINATION_REASON = "process_restart"
_ERROR_MESSAGE = "Prozess-Neustart während des Runs"


class ReconciliationResult(BaseModel):
    """Ergebnis eines ``reconcile_stale_runs``-Laufs."""

    model_config = ConfigDict(extra="forbid")

    reconciled_run_ids: List[str] = []
    skipped_run_ids: List[str] = []


class _RunRegistryProtocol(Protocol):
    """Minimale Schnittstelle, die ``reconcile_stale_runs`` von der Registry
    braucht — erlaubt Tests, eine leichte Stub-Registry statt der echten
    dateibasierten ``RunRegistry`` zu injizieren."""

    def list_runs(self, *, statuses: List[str], run_type: str, limit: int) -> List[dict]: ...

    def update_run(self, run_id: str, **updates: Any) -> Optional[dict]: ...


def reconcile_stale_runs(
    registry: _RunRegistryProtocol,
    run_state_dir: str,
    *,
    is_pid_alive: Callable[[Optional[int]], bool] = is_process_alive,
    enabled: bool = True,
) -> ReconciliationResult:
    """Markiert verwaiste ``simulation_run``-Runs als ``failed``/``process_restart``.

    Args:
        registry: ``RunRegistry``-Instanz (oder Test-Stub mit ``list_runs``/
            ``update_run``).
        run_state_dir: Basisverzeichnis für ``run_state.json``
            (``SimulationRunner.RUN_STATE_DIR``).
        is_pid_alive: Liveness-Prüfung, Default ``process_manager.is_process_alive``
            (``os.kill(pid, 0)``-Muster). Injizierbar für Tests.
        enabled: Schaltet die Reconciliation komplett ab, wenn ``False``
            (``AGORA_STARTUP_RECONCILIATION=false``) — dann bleibt jeder
            Run unangetastet.

    Returns:
        ``ReconciliationResult`` mit den Run-IDs, die als tot markiert
        (``reconciled_run_ids``) bzw. als noch lebend übersprungen wurden
        (``skipped_run_ids``).
    """
    if not enabled:
        return ReconciliationResult()

    reconciled: List[str] = []
    skipped: List[str] = []

    stale_runs = registry.list_runs(
        statuses=_STALE_STATUSES, run_type=_RUN_TYPE, limit=100_000
    )

    for run in stale_runs:
        run_id = run.get("run_id")
        if not run_id:
            continue

        simulation_id = (run.get("linked_ids") or {}).get("simulation_id") or run.get(
            "entity_id"
        )

        state = load_run_state(simulation_id, run_state_dir) if simulation_id else None
        pid = state.process_pid if state is not None else None

        if is_pid_alive(pid):
            logger.info(
                "reconcile_stale_runs: run=%s sim=%s pid=%s noch lebendig — unangetastet",
                run_id, simulation_id, pid,
            )
            skipped.append(run_id)
            continue

        logger.warning(
            "reconcile_stale_runs: run=%s sim=%s pid=%s verwaist — markiere failed/%s",
            run_id, simulation_id, pid, _TERMINATION_REASON,
        )
        registry.update_run(
            run_id,
            status="failed",
            termination_reason=_TERMINATION_REASON,
            error=_ERROR_MESSAGE,
        )

        if state is not None:
            state.runner_status = RunnerStatus.FAILED
            state.error = _ERROR_MESSAGE
            save_run_state(state, run_state_dir)

        reconciled.append(run_id)

    return ReconciliationResult(reconciled_run_ids=reconciled, skipped_run_ids=skipped)
