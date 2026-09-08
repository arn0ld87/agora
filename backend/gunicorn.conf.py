"""Gunicorn configuration for the Agora backend.

The ``post_fork`` hook is load-bearing: with ``--preload`` the master
opens the Neo4j driver before forking, and the child inherits TCP
sockets that the kernel considers owned by the master process. Without
an explicit reset the first DB write from the worker hits
``Failed to write data to connection neo4j:7687`` and burns ~1.15 s
of transient-retry backoff per call — which is exactly what 10 parallel
persona-generation greenlets surface as "extremely slow".

``os.register_at_fork`` is unreliable under ``-k gevent`` because gevent
monkey-patches ``os.fork``; gunicorn's own ``post_fork`` runs
deterministically in the child after every fork and is the canonical
place to reset pool state.

Codex-Review Finding A (2026-09-08, PR #1476): the same hook is also the
canonical place for the ``simulation_run`` Startup-Reconciliation
(``app.services.sim.reconciliation.run_startup_reconciliation``). With
``preload_app = True`` and ``workers = 1``, ``create_app()`` runs exactly
once in the master process before the first fork. If the single worker is
replaced later (timeout, crash, manual restart) without a master restart,
``create_app()`` never runs again — but ``post_fork`` fires for every
worker start, including that replacement. Reconciliation must therefore
run here to actually cover the failure mode it was built for; the
`create_app()` call stays in place for entrypoints that never go through
gunicorn (dev server, tests) and the resulting double run on cold boot is
a harmless no-op (see ``reconciliation.py`` module docstring).
"""
from __future__ import annotations

import logging

# --- Server socket / process model -----------------------------------------

bind = "0.0.0.0:5001"
worker_class = "gevent"

# HARDSTOP --workers 1 (Code-Review 2026-05-17, Finding 1.2):
# TaskManager, ApiKeysStore and SimulationRunner keep state in process-
# local dicts. Lifted in PR 2/4 of that wave once those move to Redis.
#
# Same reason ``RunRegistry`` and the ``app.services.sim.monitor`` background
# threads are safe: each run's monitor thread and its Monitor-Generation
# counter (see ``monitor.py``) live only in this one worker's memory. With
# more than one worker, a second process would spawn a second monitor for
# the same run — duplicate SSE events, racing writes to run state, and no
# shared generation counter to detect a stale monitor after a force-restart.
workers = 1

# Preload keeps fork-time short and lets post_fork own pool resets.
preload_app = True

timeout = 60
graceful_timeout = 30

chdir = "/app/backend"
pidfile = "/home/agora/.gunicorn/gunicorn.pid"

# --- Hooks -----------------------------------------------------------------


def post_fork(server, worker) -> None:  # noqa: ARG001 — gunicorn signature
    """Reset pool fds inherited from the preload master, then reconcile.

    Runs in the child process right after the fork, before any request is
    served. Resetting here is deterministic — gevent's ``os.fork`` patch
    does not interfere with gunicorn's hook dispatch.

    Also the canonical trigger for the ``simulation_run`` Startup-
    Reconciliation (Finding A, see module docstring): fires on every
    worker start, including replacements of the single ``workers = 1``
    worker that ``create_app()`` (run once, pre-fork, in the master) never
    sees.
    """
    logger = logging.getLogger("agora.gunicorn")
    try:
        from app.extensions import reset_pools_after_fork

        reset_pools_after_fork()
        logger.info("post_fork: pools reset in worker pid=%s", worker.pid)
    except Exception as exc:  # noqa: BLE001 — never crash a worker on hook failure
        logger.warning("post_fork pool reset failed (worker pid=%s): %s", worker.pid, exc)

    try:
        from app.config import Config
        from app.services.sim.reconciliation import run_startup_reconciliation

        run_startup_reconciliation(enabled=Config.AGORA_STARTUP_RECONCILIATION)
        logger.info("post_fork: startup reconciliation ran in worker pid=%s", worker.pid)
    except Exception as exc:  # noqa: BLE001 — never crash a worker on hook failure
        logger.warning(
            "post_fork startup reconciliation failed (worker pid=%s): %s", worker.pid, exc
        )
