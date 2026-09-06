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

import threading
import uuid
from typing import Any, Callable

from ..utils.logger import get_logger

logger = get_logger("agora.jobs")

# Switch to "rq" once the Redis-Queue worker is deployed (Wave 2 / PR 5).
_BACKEND: str = "thread"


def execution_mode() -> str:
    """``"gevent"`` wenn die Sockets monkey-gepatcht sind, sonst ``"thread"``.

    ``backend/wsgi.py`` ruft ``gevent.monkey.patch_all()``, bevor die App
    importiert wird — im Produktionsprozess ist damit jeder Socket ein
    kooperativer gevent-Socket, gebunden an den Hub des Threads, der ihn
    erzeugt hat. Ein echter OS-Thread bringt seinen eigenen Hub mit, greift
    aber auf Connections aus prozessweiten Pools zu (Neo4j-Driver, HTTP-
    Sessions). Produktionsfolge: ``Failed to write data to connection``,
    ``Failed to read from defunct connection``, serverseitig ``Response
    write failure``, und beim LLM-Call ``RemoteDisconnected``. Jeder
    Aufruf kostet dann Retry-Backoff, ohne dass etwas offensichtlich
    kaputt aussieht.

    ``monkey.is_patched()`` ohne Argument liefert seit gevent 23.x keinen
    "socket"-Status mehr; ``is_module_patched(name)`` ist die öffentliche
    API. Der ``ImportError``-Zweig hält den Fallback eng — ohne gevent
    (Tests, CLI-Skripte) bleibt es beim Thread.
    """
    try:
        from gevent import monkey
    except ImportError:
        return "thread"
    return "gevent" if monkey.is_module_patched("socket") else "thread"


def _enqueue_in_process(
    job_id: str,
    job_name: str,
    target: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    mode: str,
) -> None:
    """Launch *target* in the background.  Errors are caught and logged.

    Unter gevent als Greenlet im selben Hub wie der aufrufende Request,
    sonst als Daemon-Thread. Beide sind fire-and-forget: das Greenlet hält
    der Hub am Leben, den Thread der Interpreter — in beiden Fällen endet
    die Arbeit spaetestens mit dem Prozess.
    """

    def _wrapper() -> None:
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

    if mode == "gevent":
        import gevent

        gevent.spawn(_wrapper)
        return

    thread = threading.Thread(target=_wrapper, daemon=True)
    thread.start()


def spawn_background(target: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Fire-and-forget-Hintergrundarbeit, kooperativ wenn gevent aktiv ist.

    Fuer Aufrufer, die bisher direkt ``threading.Thread(target=..., daemon=
    True).start()`` gerufen haben und ihre Fehlerbehandlung selbst mitbringen.
    Sie erben damit dieselbe Weiche wie ``enqueue`` — siehe
    ``execution_mode`` fuer den Grund. Kein ``job_id``, kein Job-Log: das
    hier ist der duenne Ersatz fuer einen nackten Thread, nicht der volle
    Job-Dispatch.

    Nicht geeignet fuer Arbeit, die der Aufrufer spaeter joinen oder
    benennen muss — dafuer bleibt ein expliziter Thread bzw. Greenlet die
    richtige Wahl.
    """
    if execution_mode() == "gevent":
        import gevent

        gevent.spawn(target, *args, **kwargs)
        return

    threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True).start()


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
        run_id:   Optional run-registry ID for correlation (unused today,
                  will be forwarded to the RQ job context in Wave 2).
        **kwargs: Keyword arguments forwarded to *target*.

    Returns:
        A stable ``job_id`` of the form ``job_<12-hex-chars>``.
    """
    job_id = f"job_{uuid.uuid4().hex[:12]}"

    # ``mode`` gehoert zu einer anderen Achse als ``_BACKEND``: letzteres
    # waehlt in-process gegen RQ, ersteres innerhalb von in-process zwischen
    # Greenlet und OS-Thread. Beide im Log, damit aus einer Zeile hervorgeht,
    # wie der Job tatsaechlich laeuft — ``backend=thread`` allein hat in der
    # Praxis den Blick darauf verstellt, dass ein OS-Thread unter gevent die
    # Verbindungen aus den geteilten Pools zerlegt.
    mode = execution_mode()

    logger.info(
        "enqueued job=%s job_id=%s backend=%s mode=%s run_id=%s",
        job_name,
        job_id,
        _BACKEND,
        mode,
        run_id,
    )

    if _BACKEND == "thread":
        _enqueue_in_process(job_id, job_name, target, args, kwargs, mode)
    else:
        raise NotImplementedError(f"Unknown job backend: {_BACKEND!r}")

    return job_id
