"""
Background-job dispatch — single point of change.

Today: ``threading.Thread(daemon=True)`` per job.
Future: RQ (``rq.Queue.enqueue``) — Wave 2 / PR Redis-Queue.

Migration plan:
  1. Add ``redis_url = Config.REDIS_URL`` and ``rq.Queue(connection=...)`` init.
  2. Flip ``_BACKEND = "rq"``.
  3. Implement ``_enqueue_rq()`` with the same signature as ``_enqueue_thread()``.
  4. Remove the thread-backend fallback once the RQ worker is deployed.

Ref: agora_code_review_2026-05-17.md §1.3 — Daemon-Threads im Webprozess.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Callable, Optional

from ..config import Config
from ..contracts.job_lease_contract import HEARTBEAT_AT_KEY, JobLease
from ..utils.logger import get_logger
from .identity import remember_unstamped_run, worker_token

logger = get_logger("agora.jobs")

# Switch to "rq" once the Redis-Queue worker is deployed (Wave 2 / PR 5).
_BACKEND: str = "thread"


def _progress_marker(run: Optional[dict[str, Any]]) -> int:
    """Anzahl der Run-Events — waechst mit jedem Fortschritts-Write des Jobs.

    Jeder Status-/Progress-/Message-/Error-Write ueber ``update_run`` (auch
    der Durchschreibpfad ``TaskManager`` → ``RunRegistry.sync_task``) haengt
    ein Event an. Der Heartbeat selbst schreibt nur ``metadata`` und haengt
    keines an, zaehlt also nie als eigener Fortschritt.
    """
    return len((run or {}).get("events") or [])


def _heartbeat_loop(
    run_id: str,
    stop_event: threading.Event,
    interval_s: float,
    max_stall_s: float,
) -> None:
    """Erneuert ``heartbeat_at``, solange der Job Fortschritt meldet (#1472).

    Laeuft als eigener Daemon-Thread — dasselbe Modell wie der Job-Thread
    selbst (siehe ``_enqueue_thread``): funktioniert unveraendert unter
    gevents ``monkey.patch_all()``, weil ``threading.Event.wait`` dort
    kooperativ auf den Hub wartet statt echt zu blockieren.

    ``stop_event.wait(interval_s)`` ist das Standardmuster fuer einen
    abbrechbaren periodischen Loop: liefert sofort ``True`` sobald
    ``stop_event.set()`` aufgerufen wird (kein Warten auf das naechste
    Intervall), sonst nach ``interval_s`` ``False``.

    Der Heartbeat ist an Fortschritt gekoppelt, nicht nur an die Existenz
    des Threads (Codex-P1, PR #1555): ein haengender ``target``
    (Deadlock, blockierender Call) hielte die Lease sonst ewig am Leben,
    und ``/resume`` lieferte dauerhaft ``409 job_lease_active``. Seit dem
    letzten neuen Run-Event (``_progress_marker``) darf hoechstens
    ``max_stall_s`` vergangen sein; danach bleibt die Erneuerung aus und die
    Lease verfaellt ``lease_ttl_s`` spaeter. ``max_stall_s`` liegt bewusst
    weit ueber der TTL, damit ein einzelner langer LLM-Call ohne
    Zwischenmeldung einen lebenden Job nicht zum Doppelstart freigibt.
    Meldet der Job danach wieder Fortschritt, wird die Lease erneut
    erneuert.

    Best effort: ein Registry-Fehler beendet den Heartbeat nicht, er
    versucht es beim naechsten Intervall erneut — der Job selbst darf davon
    nicht abhaengen.
    """
    last_marker: Optional[int] = None
    last_progress = time.monotonic()
    while not stop_event.wait(interval_s):
        try:
            from ..services.run_registry import RunRegistry

            registry = RunRegistry()
            marker = _progress_marker(registry.get_run(run_id))
            if marker != last_marker:
                last_marker = marker
                last_progress = time.monotonic()
            if time.monotonic() - last_progress > max_stall_s:
                continue
            registry.update_run(
                run_id, metadata={HEARTBEAT_AT_KEY: datetime.now(UTC).isoformat()}
            )
        except Exception as exc:  # noqa: BLE001 - Heartbeat darf den Job nie stoppen
            logger.warning(
                "heartbeat update fehlgeschlagen fuer run_id=%s: %s", run_id, exc
            )


def _enqueue_thread(
    job_id: str,
    job_name: str,
    target: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    run_id: Optional[str] = None,
) -> None:
    """Launch *target* in a daemon thread.  Errors are caught and logged.

    Startet zusaetzlich einen Heartbeat-Thread (Issue #1472), solange
    ``run_id`` gesetzt ist — ohne Run-ID gibt es kein Manifest, dessen Lease
    erneuert werden koennte. Der Heartbeat-Thread wird IMMER beendet, bevor
    ``_wrapper`` zurueckkehrt (``try/finally``), auch wenn ``target`` wirft —
    eine haengenbleibende Lease nach einer Exception waere sonst bis zum
    Ablauf der TTL ein falsches "laeuft noch".

    Der Heartbeat startet nur, wenn ``_wrapper`` tatsaechlich im eigenen
    Job-Thread laeuft. Wird er synchron ausgefuehrt (Tests ersetzen
    ``Thread.start`` durch ``run``), liefe auch der Heartbeat-Loop synchron
    vor ``target`` und kehrte nie zurueck.
    """

    def _wrapper() -> None:
        stop_heartbeat: Optional[threading.Event] = None
        heartbeat_thread: Optional[threading.Thread] = None
        if run_id and thread.is_alive():
            stop_heartbeat = threading.Event()
            heartbeat_thread = threading.Thread(
                target=_heartbeat_loop,
                args=(
                    run_id,
                    stop_heartbeat,
                    Config.AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS,
                    Config.AGORA_JOB_LEASE_MAX_STALL_SECONDS,
                ),
                daemon=True,
                name=f"agora-job-heartbeat-{run_id}",
            )
            heartbeat_thread.start()
        try:
            target(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "job failed job_name=%s job_id=%s error=%s",
                job_name,
                job_id,
                exc,
                exc_info=True,
            )
        finally:
            # Heartbeat endet mit dem Job — sowohl beim normalen Ende als
            # auch nach einer Exception (dieser Block laeuft in beiden
            # Faellen).
            if stop_heartbeat is not None:
                stop_heartbeat.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=5)

    thread = threading.Thread(target=_wrapper, daemon=True)
    thread.start()


def enqueue(
    job_name: str,
    target: Callable[..., Any],
    *args: Any,
    run_id: str | None = None,
    **kwargs: Any,
) -> str:
    """Dispatch *target* as a background job.

    Args:
        job_name: Human-readable name used in logs and future queue routing.
        target:   Callable to execute in the background.
        *args:    Positional arguments forwarded to *target*.
        run_id:   Optional run-registry ID. Wird mit der Prozess-Identitaet
                  dieses Workers gestempelt, damit die Startup-Reconciliation
                  einen nach SIGTERM verwaisten Job erkennt (Issue #1472) —
                  in Wave 2 zusaetzlich der RQ-Job-Kontext.
        **kwargs: Keyword arguments forwarded to *target*.

    Returns:
        A stable ``job_id`` of the form ``job_<12-hex-chars>``.
    """
    job_id = f"job_{uuid.uuid4().hex[:12]}"

    # Issue #1472: In-Process-Jobs haben keine eigene Prozess-ID, an der sich
    # ihre Liveness nach einem Neustart pruefen liesse — sie laufen als Thread
    # IM Webprozess. Der Stempel muss VOR dem Start stehen: startet der Thread
    # zuerst und der Prozess stirbt dazwischen, traegt das Manifest keine
    # Identitaet, und die Reconciliation behandelt es (korrekt) als verwaist.
    # Bookkeeping darf den Job nie verhindern, deshalb best effort.
    #
    # Seit der Architekturentscheidung vom 2026-09-24 schreibt ``enqueue``
    # statt des reinen PID+Token-Stempels eine Lease mit Ablauf
    # (``JobLease``, ``app/contracts/job_lease_contract.py``): ``owner_pid``/
    # ``owner_token`` sind wertgleich mit dem alten Stempel (dieselben
    # Metadata-Keys), zusaetzlich traegt das Manifest ``heartbeat_at`` und
    # ``lease_ttl_s``. Der Heartbeat-Thread (``_heartbeat_loop`` via
    # ``_enqueue_thread``) erneuert ``heartbeat_at``, solange der Job laeuft.
    if run_id:
        try:
            from ..services.run_registry import RunRegistry

            lease = JobLease(
                owner_pid=os.getpid(),
                owner_token=worker_token(),
                heartbeat_at=datetime.now(UTC),
                lease_ttl_s=Config.AGORA_JOB_LEASE_TTL_SECONDS,
            )
            RunRegistry().update_run(run_id, metadata=lease.to_metadata())
        except Exception as exc:  # noqa: BLE001 — Job-Start hat Vorrang
            # Prozesslokal merken: das Manifest traegt kein Token, dieser
            # Prozess weiss aber, dass der Job ihm gehoert. Ohne das behandelte
            # der Worker-Exit-Hook den eigenen laufenden Job als fremd und
            # liesse ihn auf processing stehen (Codex-P2, PR #1532).
            remember_unstamped_run(run_id)
            logger.warning(
                "Lease fuer run_id=%s nicht gestempelt (%s) — ein Abbruch "
                "dieses Jobs waere nach einem Neustart nicht als verwaist "
                "erkennbar",
                run_id, exc,
            )

    logger.info(
        "enqueued job=%s job_id=%s backend=%s run_id=%s",
        job_name,
        job_id,
        _BACKEND,
        run_id,
    )

    if _BACKEND == "thread":
        _enqueue_thread(job_id, job_name, target, args, kwargs, run_id=run_id)
    else:
        raise NotImplementedError(f"Unknown job backend: {_BACKEND!r}")

    return job_id
