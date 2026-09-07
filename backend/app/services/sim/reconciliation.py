"""Startup-Reconciliation für verwaiste ``simulation_run``-Runs.

Tech-Review 2026-09-07, Slice B1. Fixes für Codex-Review-Findings A+B,
2026-09-08 (siehe PR #1476).

Problem: ``RunRegistry``-Einträge (``uploads/run_registry/*.json``) und
``run_state.json`` kennen den Status eines Simulation-Runs nur so lange, wie
der zugehörige OASIS-Subprozess selbst ihn aktualisiert. Nach einem
Container-Restart existiert dieser Subprozess nicht mehr — die Dateien
bleiben aber auf ``pending``/``processing`` (Registry) bzw.
``STARTING``/``RUNNING`` (``run_state.json``) stehen und werden dem
Frontend fälschlich als „läuft noch" angezeigt, für immer, weil nichts
mehr existiert, das den Zustand jemals wieder ändert.

``reconcile_stale_runs`` korrigiert genau diese verwaisten Runs anhand der
in ``run_state.json`` persistierten ``process_pid``: existiert der Prozess
nicht (mehr) UND ist ``run_state.json`` noch in einem unklaren Zustand
(``RUNNING``/``STARTING`` oder gar nicht vorhanden), wird der Run als
``failed``/``process_restart`` markiert. Existiert der Prozess noch (z. B.
weil nur ein Worker-Prozess neu gestartet wurde, der Subprozess aber
überlebt hat), bleibt er unangetastet. Ist ``run_state.json`` dagegen
bereits terminal (``COMPLETED``/``STOPPED``/``FAILED``) — der Prozess also
tot, weil er regulär beendet wurde, nicht weil er verwaist ist —, wird
dieser autoritative Endzustand zur Registry propagiert statt ihn
fälschlich mit ``process_restart`` zu überschreiben (Finding B).

Aufrufer: ``run_startup_reconciliation`` bündelt Config-Flag-Check und
Best-effort-Fehlerbehandlung für zwei Einhängepunkte — ``app/__init__.py::
create_app`` (Entwicklungs-/Testbetrieb ohne gunicorn, einziger
Startup-Hook) und ``gunicorn.conf.py::post_fork`` (Produktion; unter
``preload_app=True`` + ``workers=1`` läuft ``create_app`` nur einmal im
Master VOR dem Fork — nur ``post_fork`` feuert deterministisch bei jedem
Worker-Start, auch nach Timeout/Crash/Replacement des einzigen Workers,
Finding A). Der doppelte Aufruf beim allerersten Boot (Master via
``create_app`` vor dem ersten Fork, dann erneut im frisch geforkten Worker
via ``post_fork``) ist harmlos: der zweite Durchlauf findet keine weiteren
``pending``/``processing``-Runs mehr und ist ein No-op.
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

#: Terminale ``run_state.json``-Status (Finding B): ein toter Prozess ist
#: hier kein Hinweis auf einen verwaisten Run, sondern schlicht der Beweis,
#: dass der Run bereits regulär beendet wurde — die RunRegistry-Sync danach
#: ist nur (noch) nicht angekommen.
_TERMINAL_RUNNER_STATUSES = {
    RunnerStatus.COMPLETED,
    RunnerStatus.STOPPED,
    RunnerStatus.FAILED,
}


class ReconciliationResult(BaseModel):
    """Ergebnis eines ``reconcile_stale_runs``-Laufs."""

    model_config = ConfigDict(extra="forbid")

    reconciled_run_ids: List[str] = []
    skipped_run_ids: List[str] = []
    #: Finding B: Runs, deren bereits terminaler ``run_state.json``-Status
    #: (COMPLETED/STOPPED/FAILED) auf die Registry propagiert wurde, statt
    #: sie fälschlich mit ``process_restart`` zu überschreiben.
    synced_terminal_run_ids: List[str] = []


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
    synced_terminal: List[str] = []

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
            # Finding C (Codex-Review 2026-09-08, bewusst NICHT behoben): eine
            # lebende PID heißt nur, dass der OASIS-Subprozess überlebt hat
            # (``start_new_session=True``) — nicht, dass DIESER (frisch
            # gestartete) Worker-Prozess ihn noch verwaltet. Sein ``Popen``-
            # Objekt und sein Monitor-Thread gehörten dem alten Worker und
            # existieren hier nicht; der Run bleibt "processing", ist aber
            # nicht mehr über die API steuerbar (kein Stop/Cancel-Pfad
            # erreicht ihn). Ein automatisches Terminieren wäre riskant
            # (siehe Abschlussbericht) — daher nur lautes Logging statt
            # Prozess-Kill.
            logger.warning(
                "reconcile_stale_runs: run=%s sim=%s pid=%s lebt noch, wird aber "
                "von diesem (neu gestarteten) Worker nicht mehr verwaltet — "
                "kein Popen-Handle, kein Monitor-Thread; Run bleibt 'processing' "
                "und ist nicht mehr über die API steuerbar",
                run_id, simulation_id, pid,
            )
            skipped.append(run_id)
            continue

        # Finding B (Codex-Review 2026-09-08): ein toter Prozess heißt nicht
        # zwangsläufig "verwaist" — ``run_state.json`` kann bereits einen
        # autoritativen Endzustand tragen, weil der Run regulär fertig wurde
        # oder der Nutzer ihn stoppte, und nur die anschließende
        # RunRegistry-Sync nie ankam (Prozess starb dazwischen). Diesen
        # Zustand NICHT mit ``process_restart`` überschreiben, sondern zur
        # Registry propagieren.
        if state is not None and state.runner_status in _TERMINAL_RUNNER_STATUSES:
            target_status = state.runner_status.value
            termination_reason = run.get("termination_reason")
            updates: dict[str, Any] = {"status": target_status}
            if termination_reason:
                updates["termination_reason"] = termination_reason
            if state.error:
                updates["error"] = state.error

            logger.info(
                "reconcile_stale_runs: run=%s sim=%s pid=%s bereits terminal "
                "(runner_status=%s) — Registry auf %s synchronisiert statt "
                "process_restart",
                run_id, simulation_id, pid, state.runner_status.value, target_status,
            )
            registry.update_run(run_id, **updates)
            synced_terminal.append(run_id)
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

    return ReconciliationResult(
        reconciled_run_ids=reconciled,
        skipped_run_ids=skipped,
        synced_terminal_run_ids=synced_terminal,
    )


def run_startup_reconciliation(
    *, enabled: bool = True, should_log_startup: bool = True
) -> ReconciliationResult:
    """Best-effort-Trigger für :func:`reconcile_stale_runs`.

    Gemeinsamer Einhängepunkt für ``app/__init__.py::create_app`` (einziger
    Startup-Hook in Entwicklungs-/Testbetrieb ohne gunicorn) und
    ``gunicorn.conf.py::post_fork`` (kanonischer Einhängepunkt in
    Produktion, siehe Modul-Docstring / Finding A). Löst Config-Flag-Check
    und Fehlerbehandlung aus dem alten ``create_app``-Inline-Block heraus,
    damit beide Aufrufer exakt dasselbe Verhalten bekommen: ein Fehler in
    der Reconciliation darf weder den App-Start noch den Worker-Start
    verhindern.

    Args:
        enabled: Resultat der ``AGORA_STARTUP_RECONCILIATION``-Prüfung des
            Aufrufers (``app.config.get(...)`` bzw. ``Config.
            AGORA_STARTUP_RECONCILIATION`` — dieses Modul importiert keine
            Flask-/Config-Objekte, um von beiden Aufrufern unabhängig zu
            bleiben).
        should_log_startup: Unterdrückt das Zusammenfassungs-Log (deckt sich
            mit dem bisherigen ``should_log_startup``-Gate in ``create_app``,
            z. B. für Worker-Prozesse mit reduzierter Log-Verbosity).

    Returns:
        ``ReconciliationResult()`` (leer) wenn deaktiviert oder wenn die
        Reconciliation selbst fehlschlägt — der Fehler ist dann bereits
        geloggt.
    """
    if not enabled:
        return ReconciliationResult()

    try:
        from ..run_registry import RunRegistry
        from ..simulation_runner import SimulationRunner

        result = reconcile_stale_runs(RunRegistry(), SimulationRunner.RUN_STATE_DIR)
        if should_log_startup:
            logger.info(
                "Startup-Reconciliation: %d Run(s) als process_restart markiert, "
                "%d terminal synchronisiert, %d unveraendert",
                len(result.reconciled_run_ids),
                len(result.synced_terminal_run_ids),
                len(result.skipped_run_ids),
            )
        return result
    except Exception:  # noqa: BLE001 — App-/Worker-Start darf nie an der Reconciliation scheitern
        logger.error(
            "Startup-Reconciliation fehlgeschlagen — Start läuft trotzdem weiter",
            exc_info=True,
        )
        return ReconciliationResult()
