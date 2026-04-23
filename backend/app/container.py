"""Lightweight DI container for Agora (Issue #14).

Replaces the ``app.extensions[...]``-as-Service-Locator pattern with an
explicit container that:

* owns long-lived **singletons** (Neo4j storage, artifact store) and
  builds them lazily on first access;
* exposes **factories** for request-scoped services (e.g. ``GraphBuilderService``)
  whose dependencies are read off the container.

The pilot for this refactor is :class:`GraphBuilderService` — its ``storage``
dependency is already constructor-injected, so the only thing the container
does there is centralize the wiring. New services should follow the same
pattern: take their dependencies as constructor arguments, never reach
into ``current_app.extensions`` themselves.

Tests can construct ``AgoraContainer(neo4j_storage=mock)`` directly and
exercise services without a Flask app context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .services.artifact_store import SimulationArtifactStore
    from .services.event_bus import SimulationEventBus
    from .services.graph_builder import GraphBuilderService
    from .services.network_analytics import NetworkAnalyticsService  # noqa: F401
    from .services.temporal_graph import TemporalGraphService
    from .storage import Neo4jStorage


class AgoraContainer:
    """Hand-rolled DI container — singletons + factories, no external lib.

    Construct in two ways:

    * ``AgoraContainer()`` — production. Singletons are built lazily on first
      access using the standard production constructors.
    * ``AgoraContainer(neo4j_storage=..., artifact_store=...)`` — tests.
      Provided instances are returned verbatim, no auto-construction.

    Failure modes:

    * If Neo4j is unreachable at startup the application registers
      ``app.extensions['neo4j_storage'] = None`` (handled by ``create_app``).
      Tests should pass an explicit mock instead of relying on that fallback.
    """

    def __init__(
        self,
        *,
        neo4j_storage: "Optional[Neo4jStorage]" = None,
        artifact_store: "Optional[SimulationArtifactStore]" = None,
        event_bus: "Optional[SimulationEventBus]" = None,
    ) -> None:
        self._neo4j_storage = neo4j_storage
        self._artifact_store = artifact_store
        self._event_bus = event_bus
        self._neo4j_storage_explicit = neo4j_storage is not None
        self._artifact_store_explicit = artifact_store is not None
        self._event_bus_explicit = event_bus is not None

    # ----- Singletons ------------------------------------------------------

    @property
    def neo4j_storage(self) -> "Neo4jStorage":
        if self._neo4j_storage is None:
            from .storage import Neo4jStorage

            self._neo4j_storage = Neo4jStorage()
        return self._neo4j_storage

    @property
    def artifact_store(self) -> "SimulationArtifactStore":
        if self._artifact_store is None:
            from .services.artifact_store import LocalFilesystemArtifactStore

            self._artifact_store = LocalFilesystemArtifactStore()
        return self._artifact_store

    @property
    def event_bus(self) -> "SimulationEventBus":
        """Singleton event bus for simulation IPC (Issue #9).

        Backend is picked from :data:`Config.EVENT_BUS_BACKEND`:

        * ``redis`` → :class:`RedisEventBus` (fails loud if unreachable)
        * ``file`` → :class:`FilePollingEventBus` (offline-first fallback)
        * ``auto`` (default) → Redis if ``REDIS_URL`` pings within 500ms,
          otherwise file.
        """
        if self._event_bus is None:
            self._event_bus = self._build_event_bus()
        return self._event_bus

    def _build_event_bus(self) -> "SimulationEventBus":
        from .config import Config
        from .services.event_bus import FilePollingEventBus
        from .utils.logger import get_logger

        logger = get_logger("agora.container")
        backend = (Config.EVENT_BUS_BACKEND or "auto").lower()

        def _file_bus() -> "SimulationEventBus":
            logger.info("SimulationEventBus: using FilePollingEventBus")
            return FilePollingEventBus(store=self.artifact_store)

        if backend == "file":
            return _file_bus()

        if backend in ("redis", "auto"):
            from .services.event_bus_redis import RedisEventBus, is_redis_reachable

            if backend == "auto" and not is_redis_reachable(Config.REDIS_URL):
                logger.info(
                    "SimulationEventBus: REDIS_URL=%s unreachable, falling back to file",
                    Config.REDIS_URL,
                )
                return _file_bus()
            try:
                bus = RedisEventBus(Config.REDIS_URL, artifact_store=self.artifact_store)
                logger.info("SimulationEventBus: RedisEventBus connected to %s", Config.REDIS_URL)
                return bus
            except Exception as exc:
                if backend == "redis":
                    raise RuntimeError(
                        f"EVENT_BUS_BACKEND=redis but Redis unreachable at {Config.REDIS_URL}: {exc}"
                    ) from exc
                logger.warning(
                    "SimulationEventBus: Redis init failed (%s), falling back to file", exc
                )
                return _file_bus()

        raise ValueError(
            f"Unknown EVENT_BUS_BACKEND={Config.EVENT_BUS_BACKEND!r} "
            f"(expected one of: redis, file, auto)"
        )

    # ----- Factories -------------------------------------------------------

    def network_analytics(self) -> "NetworkAnalyticsService":
        """Construct a stateless :class:`NetworkAnalyticsService` (Issue #12)."""
        from .services.network_analytics import NetworkAnalyticsService

        return NetworkAnalyticsService()

    def temporal_graph(self) -> "TemporalGraphService":
        """Construct a :class:`TemporalGraphService` wired to the container's storage.

        Request-scoped because callers often operate on a specific graph and
        the service caches per-graph backfill-state internally.
        """
        from .services.temporal_graph import TemporalGraphService

        return TemporalGraphService(storage=self.neo4j_storage)

    def graph_builder(self) -> "GraphBuilderService":
        """Construct a fresh ``GraphBuilderService`` wired to the container's storage.

        Request-scoped: the service holds a per-task ``TaskManager`` reference
        and its build pipelines should not be shared across concurrent
        requests.
        """
        from .services.graph_builder import GraphBuilderService

        return GraphBuilderService(storage=self.neo4j_storage)


def get_container() -> AgoraContainer:
    """Return the active container from the Flask app context.

    Raises ``RuntimeError`` outside an app context so callers fail fast
    instead of silently falling through. For non-Flask call sites (CLI,
    background workers) construct ``AgoraContainer()`` directly.
    """
    from flask import current_app

    container = current_app.extensions.get("container")
    if container is None:
        raise RuntimeError("AgoraContainer not initialized in app.extensions")
    return container


__all__ = ["AgoraContainer", "get_container"]
