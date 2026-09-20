"""SIGTERM/Worker-Exit-Hook für In-Process-Jobs (Issue #1472a).

Beim Worker-Exit erhalten alle laufenden In-Process-Jobs (simulation_prepare,
report_generate, graph_build, ontology_generate) einen ehrlichen terminalen
Zustand (failed/process_restart), statt auf die Reconciliation beim nächsten
Start zu warten.

Die Logik spiegelt die Schreibreihenfolge von ``reconcile_stale_jobs``:
1. Cancel-Flag setzen (kooperativer Abbruch für Jobs, die es prüfen)
2. SimulationState (für simulation_prepare) *vor* Manifest schreiben (F1-Invariante)
3. RunRegistry-Manifest auf failed/process_restart setzen

Kein neuer TerminationReason-Wert — ``process_restart`` wird wiederverwendet.

Slice 1.1 P1-Fund (Codex-Review, PR #1528, 2026-09-20): diese lock-nehmende
Arbeit darf NICHT im Signal-Handler selbst laufen. Belegt am installierten
gevent ``26.4.0`` (Pin in ``uv.lock``, Prod läuft unter ``-k gevent`` mit
``gevent.monkey.patch_all()`` in ``wsgi.py``):

1. ``gevent.signal.signal()`` delegiert für jedes Signal außer SIGCHLD an die
   *ungepatchte* stdlib-Funktion. Der SIGTERM-Handler läuft deshalb im echten
   CPython-Signalkontext, nicht als vom Hub geplantes Greenlet — er wird an
   der nächsten Bytecode-Prüfstelle synchron in das gerade laufende Greenlet
   hineingespritzt.
2. Nach ``patch_all()`` ist ``threading.Lock`` ein kooperatives
   gevent-``BoundedSemaphore``, kein pthread-Mutex.
3. Daraus folgt das eigentliche Risiko (aus dem gevent-Code abgeleitet, nicht
   per Laufzeit-Repro beobachtet): unterbricht das Signal ausgerechnet das
   Greenlet, das ``RunRegistry._lock`` (oder ``cancel_flag._lock``) hält,
   läuft der Handler oberhalb dieses Greenlets im Aufrufstack. Ein
   ``acquire()`` auf dasselbe Semaphore kann darin nicht erfolgreich sein —
   das haltende Greenlet kommt unterhalb des Handler-Frames nie wieder zum
   Zug. Je nach Hub-Zustand endet das als stiller Hänger oder als
   ``LoopExit`` aus dem Signalpfad. Beide Ausgänge verhindern, dass gunicorns
   verkettetes ``handle_exit`` je erreicht wird — der Worker hängt beim
   Shutdown, statt sauber zu terminieren.

Deshalb tut der Signal-Handler ab dieser Version nur noch zwei Dinge: ein
Modul-Flag setzen und die zuvor registrierte Handler-Kette weiterrufen
(zwingend, sonst erreicht gunicorns ``handle_exit`` den Worker nie). Die
eigentliche Terminalisierung läuft über ``atexit`` — außerhalb jedes
Signalkontexts, im normalen Greenlet-Ablauf des Interpreter-Shutdowns, wo
``acquire()`` auf ein von einem anderen (bereits beendeten) Greenlet
gehaltenes Semaphore kein Deadlock-Risiko mehr trägt. Dasselbe Muster nutzt
bereits ``process_manager.register_cleanup`` für den Subprozess-Cleanup.

Ehrliche Grenze dieses Hooks: ``atexit``-Callbacks laufen nur bei einem
regulären Interpreter-Shutdown. Wird der Worker nach Ablauf von
``graceful_timeout`` (30 s, siehe ``gunicorn.conf.py``) per SIGKILL beendet,
läuft kein ``atexit`` — der Prozess stirbt hart, ohne dass dieser Hook je
zum Zug kommt. In diesem Fall bleibt weiterhin die Startup-Reconciliation
beim nächsten Prozessstart (``reconcile_stale_jobs`` /
``run_startup_reconciliation`` in ``post_fork``) der einzige Mechanismus,
der die verwaisten Jobs terminalisiert.
"""

from __future__ import annotations

import atexit
import os
import signal
import threading
from typing import Any, Callable, Dict, List, Optional, Protocol

from ...jobs.identity import owns_run
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

# Rein informativ (Diagnose/Logging) — die eigentliche Terminalisierung
# haengt NICHT von diesem Flag ab, sie laeuft in jedem Fall ueber den
# atexit-Callback, auch bei einem regulaeren Exit ohne SIGTERM/SIGINT.
_shutdown_signal_received = False

# Referenz auf den zuletzt registrierten atexit-Callback — ausschliesslich
# fuer Tests gedacht, die ihn nach dem Testlauf per ``atexit.unregister``
# wieder abmelden muessen (sonst laeuft er beim Beenden der Testsuite).
_shutdown_atexit_callback: Optional[Callable[[], None]] = None


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

    # Ownership-Filter wie in ``reconcile_stale_jobs`` (reconciliation.py:463).
    #
    # Die vorherige Fassung verzichtete bewusst darauf und berief sich auf die
    # ``workers = 1``-HARDSTOP-Invariante aus ``gunicorn.conf.py``. Diese
    # Begruendung traegt nicht: ``create_app()`` registriert den atexit-Callback
    # auch im preloadenden Master (``app/__init__.py:361``), und bei einem
    # gunicorn-Hot-Upgrade (USR2) ueberlappen alter und neuer Master. Beendet
    # sich der alte, markierte er ohne diesen Filter die Jobs, die im *neuen*
    # Worker gerade laufen, als failed/process_restart — ein laufender Job
    # wuerde also von einem fremden Prozess fuer tot erklaert. ``workers = 1``
    # begrenzt die Worker pro Master, nicht die Zahl der Master.
    #
    # ``owns_run`` ist dafuer belastbar: das Manifest eines laufenden Jobs
    # traegt immer ein Token, weil ``enqueue`` es vor dem Threadstart setzt
    # (``app/jobs/identity.py``).
    for run_type in _IN_PROCESS_RUN_TYPES:
        for run in registry.list_runs(
            statuses=_STALE_STATUSES, run_type=run_type, limit=100_000
        ):
            run_id = run.get("run_id")
            if not run_id:
                continue

            if not owns_run(run.get("metadata") or {}):
                logger.info(
                    "process_shutdown: run=%s (%s) gehoert einem anderen Prozess — uebersprungen",
                    run_id,
                    run_type,
                )
                skipped.append(run_id)
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
    """Registriert Signal-Handler (flag-only) und atexit-Callback (Terminalisierung).

    Der SIGTERM/SIGINT-Handler nimmt bewusst KEIN Lock mehr (siehe
    Moduldocstring, Slice-1.1-P1-Fund) — er setzt nur ``_shutdown_signal_received``
    und ruft die zuvor bestehende Handler-Kette weiter. Die eigentliche
    Terminalisierung der In-Process-Jobs läuft über einen ``atexit``-Callback,
    der außerhalb jedes Signalkontexts läuft.

    Args:
        get_registry: Callable, der die RunRegistry-Instanz liefert.
        fail_simulation_state: Optional, wird an _mark_in_process_jobs_failed
            durchgereicht (für simulation_prepare).
    """
    global _shutdown_registered_pid, _shutdown_atexit_callback

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

        executed = False

        def _atexit_callback() -> None:
            """Terminalisiert die In-Process-Jobs *dieses* Prozesses.

            PID-gebunden: ein via ``fork()`` von einem anderen Prozess
            geerbter atexit-Eintrag (z. B. aus dem preloading Master, siehe
            Moduldocstring) darf hier NICHT laufen — ``current_pid`` ist die
            PID zum Zeitpunkt der Registrierung, nicht zum Zeitpunkt des
            Aufrufs.

            Gegen Doppelausführung geschützt (``executed``): ``atexit`` ruft
            jeden Eintrag nur einmal auf, aber ein Prozess kann mehrere
            Einträge tragen (eigener + geerbter), und dieser Guard hält den
            Callback auch bei einem direkten Zweitaufruf (z. B. in Tests)
            idempotent.
            """
            nonlocal executed

            if os.getpid() != current_pid:
                logger.info(
                    "process_shutdown: atexit-Eintrag aus Prozess %s in Prozess %s "
                    "übersprungen (fremde PID, z. B. vom Master geerbt)",
                    current_pid,
                    os.getpid(),
                )
                return

            if executed:
                return
            executed = True

            try:
                registry = get_registry()
                result = _mark_in_process_jobs_failed(
                    registry, fail_simulation_state=fail_simulation_state
                )
                logger.info(
                    "process_shutdown: atexit — %d In-Process-Jobs als failed/%s markiert, "
                    "%d übersprungen",
                    len(result.reconciled_run_ids),
                    _TERMINATION_REASON,
                    len(result.skipped_run_ids),
                )
            except Exception as exc:  # noqa: BLE001 — atexit darf nichts werfen
                logger.error(
                    "process_shutdown: Fehler beim Markieren der Jobs (atexit): %s",
                    exc,
                    exc_info=True,
                )

        # atexit VOR dem Signal-Handler registrieren: atexit funktioniert
        # unabhängig davon, ob signal.signal() gleich scheitert (ValueError,
        # z. B. wenn dieser Aufruf nicht im Hauptthread läuft).
        atexit.register(_atexit_callback)
        _shutdown_atexit_callback = _atexit_callback

        def _shutdown_handler(signum: int, frame: Any) -> None:
            """Signal-Handler: setzt nur ein Flag, nimmt KEIN Lock.

            Aus dem Signalkontext heraus darf hier nichts laufen, das
            ``RunRegistry._lock`` oder ``cancel_flag._lock`` nimmt (siehe
            Moduldocstring, Slice-1.1-P1-Fund). Die Terminalisierung folgt
            über den atexit-Callback.
            """
            global _shutdown_signal_received
            _shutdown_signal_received = True
            logger.info(
                "process_shutdown: signal %s empfangen, Terminalisierung folgt via atexit",
                signum,
            )

        # Original-Handler speichern
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)

        def _combined_handler(signum: int, frame: Any) -> None:
            _shutdown_handler(signum, frame)
            # Original-Handler aufrufen (z. B. für Flask-Shutdown, gunicorns
            # handle_exit) — zwingend, sonst beendet sich der Worker nie.
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
            logger.info(
                "process_shutdown: SIGTERM/SIGINT handler (flag-only) und atexit-Callback "
                "registriert für in-process jobs"
            )
        except ValueError:
            logger.warning(
                "process_shutdown: Cannot register signal handler (not in main thread)"
            )
            _shutdown_registered_pid = current_pid


__all__ = [
    "register_shutdown_handler",
    "_mark_in_process_jobs_failed",
]