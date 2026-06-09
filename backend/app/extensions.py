"""Fork-safe pool management for gunicorn --preload.

Two layers:

1. ``register_fork_handlers(neo4j_storage)`` is called from ``create_app()``
   and stores the live pool references in module-level globals. As a
   defence-in-depth fallback it also wires up ``os.register_at_fork``.

2. ``reset_pools_after_fork()`` is the canonical entry point. Gunicorn's
   ``post_fork`` hook (see ``backend/gunicorn.conf.py``) calls it
   deterministically in the child after every fork, regardless of how
   gevent has patched ``os.fork``. Stale TCP sockets inherited from the
   master through ``--preload`` are closed there; the next real call
   re-opens them inside the worker.

The ``os.register_at_fork`` path is not reliable under
``gunicorn -k gevent --preload``: gevent monkey-patches ``os.fork`` and the
fork handlers registered through CPython's hook are not always invoked,
which leaves the inherited Neo4j driver pool wired to sockets the kernel
considers owned by the master — surfacing as
``Failed to write data to connection`` followed by a 1.15 s transient
retry loop.
"""
from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from .storage.neo4j_storage import Neo4jStorage

logger = logging.getLogger("agora.extensions")

# Live references captured at create_app() time. The Gunicorn post_fork
# hook reaches into these from the child process. With --preload, the
# child inherits the module state (including these refs) via fork.
_REGISTERED_NEO4J_STORAGES: List["Neo4jStorage"] = []

# Buses with a ``reset_after_fork()`` method (currently only
# ``RedisEventBus``; ``InMemoryEventBus`` / ``FilePollingEventBus`` have no
# fork-sensitive state). Kept generic on purpose so any future pool-owning
# bus can opt in just by exposing the method.
_REGISTERED_EVENT_BUSES: List[Any] = []

# Platform-capability flag and one-shot guard for the at-fork fallback.
# ``create_app()`` may run multiple times (pytest fixtures, ad-hoc reloads);
# without the guard each call would stack another at-fork handler and the
# child would invoke ``reset_pools_after_fork`` N times per fork.
_HAS_REGISTER_AT_FORK = hasattr(os, "register_at_fork")
_FORK_HANDLER_REGISTERED = False


def register_fork_handlers(
    neo4j_storage: Optional["Neo4jStorage"] = None,
    event_bus: Optional[Any] = None,
) -> None:
    """Register pool references for post-fork reset.

    Called from ``create_app()`` once all pool-owning objects exist.
    Safe to call multiple times; duplicates are filtered and the
    ``os.register_at_fork`` fallback is wired up exactly once per process.

    A bus is only registered when it exposes ``reset_after_fork()`` —
    this keeps ``InMemoryEventBus`` / ``FilePollingEventBus`` out of the
    reset path automatically.
    """
    if neo4j_storage is not None and neo4j_storage not in _REGISTERED_NEO4J_STORAGES:
        _REGISTERED_NEO4J_STORAGES.append(neo4j_storage)

    if (
        event_bus is not None
        and hasattr(event_bus, "reset_after_fork")
        and event_bus not in _REGISTERED_EVENT_BUSES
    ):
        _REGISTERED_EVENT_BUSES.append(event_bus)

    # Defence-in-depth: also register CPython's at-fork hook so non-gunicorn
    # runtimes (pytest with multiprocessing, ad-hoc scripts) still reset
    # pools when they fork. Under gunicorn-gevent the canonical path is the
    # post_fork hook in gunicorn.conf.py — see reset_pools_after_fork.
    if not _HAS_REGISTER_AT_FORK:
        logger.debug("register_at_fork not available (non-Unix?), skipping")
        return

    global _FORK_HANDLER_REGISTERED
    if _FORK_HANDLER_REGISTERED:
        return

    os.register_at_fork(after_in_child=reset_pools_after_fork)
    _FORK_HANDLER_REGISTERED = True
    logger.debug("Registered reset_pools_after_fork as os.register_at_fork handler")


def reset_pools_after_fork() -> None:
    """Reset every pool that may carry stale fds from the master.

    Idempotent. Exceptions from one pool never block the next reset — a
    half-broken Redis must not stop the Neo4j driver from being reopened.
    """
    for storage in _REGISTERED_NEO4J_STORAGES:
        try:
            storage._reset_driver_after_fork()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Neo4j fork-reset failed: %s", exc)

    for bus in _REGISTERED_EVENT_BUSES:
        try:
            bus.reset_after_fork()
        except Exception as exc:  # noqa: BLE001
            logger.warning("EventBus fork-reset failed: %s", exc)

    try:
        from .utils.signed_ticket import reset_after_fork as _reset_redis

        _reset_redis()
    except Exception as exc:  # noqa: BLE001
        logger.warning("signed_ticket Redis fork-reset failed: %s", exc)

    try:
        import threading
        from .services.model_catalog_service import ModelCatalogService

        # Re-initialize the lock instead of acquiring the inherited one.
        # After os.fork the child is single-threaded, but the inherited lock
        # may be in a "locked" state if another thread held it at fork time —
        # acquiring it here would deadlock forever.  Creating a fresh Lock()
        # is the standard POSIX-safe pattern for post-fork handlers.
        ModelCatalogService._cache_lock = threading.Lock()
        ModelCatalogService._cache.clear()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ModelCatalogService cache fork-reset failed: %s", exc)
