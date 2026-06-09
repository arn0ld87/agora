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


def _enqueue_thread(
    job_id: str,
    job_name: str,
    target: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    """Launch *target* in a daemon thread.  Errors are caught and logged."""

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
        run_id:   Optional run-registry ID for correlation (unused today,
                  will be forwarded to the RQ job context in Wave 2).
        **kwargs: Keyword arguments forwarded to *target*.

    Returns:
        A stable ``job_id`` of the form ``job_<12-hex-chars>``.
    """
    job_id = f"job_{uuid.uuid4().hex[:12]}"

    logger.info(
        "enqueued job=%s job_id=%s backend=%s run_id=%s",
        job_name,
        job_id,
        _BACKEND,
        run_id,
    )

    if _BACKEND == "thread":
        _enqueue_thread(job_id, job_name, target, args, kwargs)
    else:
        raise NotImplementedError(f"Unknown job backend: {_BACKEND!r}")

    return job_id
