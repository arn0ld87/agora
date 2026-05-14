"""Fork-safe pool management for gunicorn --preload.

register_fork_handlers() must be called in create_app() after all
pool objects are created, before returning the app.
"""
from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .storage.neo4j_storage import Neo4jStorage

logger = logging.getLogger("agora.extensions")


def register_fork_handlers(neo4j_storage: Optional["Neo4jStorage"] = None) -> None:
    """Register os.register_at_fork after_in_child handlers.

    Safe to call on platforms without fork (os.register_at_fork absent).
    """
    if not hasattr(os, "register_at_fork"):
        logger.debug("register_at_fork not available (non-Unix?), skipping")
        return

    # --- Neo4j ---
    if neo4j_storage is not None:
        def _reset_neo4j() -> None:
            try:
                neo4j_storage._reset_driver_after_fork()
            except Exception as exc:
                logger.warning("Neo4j fork-reset failed: %s", exc)

        os.register_at_fork(after_in_child=_reset_neo4j)
        logger.debug("Registered Neo4j after_in_child fork handler")

    # --- Redis signed_ticket ---
    try:
        from .utils.signed_ticket import _reset_seen_for_tests as _reset_redis

        os.register_at_fork(after_in_child=_reset_redis)
        logger.debug("Registered signed_ticket Redis after_in_child fork handler")
    except ImportError:
        pass
