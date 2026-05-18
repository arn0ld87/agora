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
"""
from __future__ import annotations

import logging

# --- Server socket / process model -----------------------------------------

bind = "0.0.0.0:5001"
worker_class = "gevent"

# HARDSTOP --workers 1 (Code-Review 2026-05-17, Finding 1.2):
# TaskManager, ApiKeysStore and SimulationRunner keep state in process-
# local dicts. Lifted in PR 2/4 of that wave once those move to Redis.
workers = 1

# Preload keeps fork-time short and lets post_fork own pool resets.
preload_app = True

timeout = 60
graceful_timeout = 30

chdir = "/app/backend"
pidfile = "/home/agora/.gunicorn/gunicorn.pid"

# --- Hooks -----------------------------------------------------------------


def post_fork(server, worker) -> None:  # noqa: ARG001 — gunicorn signature
    """Reset pool fds inherited from the preload master.

    Runs in the child process right after the fork, before any request is
    served. Resetting here is deterministic — gevent's ``os.fork`` patch
    does not interfere with gunicorn's hook dispatch.
    """
    logger = logging.getLogger("agora.gunicorn")
    try:
        from app.extensions import reset_pools_after_fork

        reset_pools_after_fork()
        logger.info("post_fork: pools reset in worker pid=%s", worker.pid)
    except Exception as exc:  # noqa: BLE001 — never crash a worker on hook failure
        logger.warning("post_fork pool reset failed (worker pid=%s): %s", worker.pid, exc)
