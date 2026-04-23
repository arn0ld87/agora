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

        Phase A default: :class:`FilePollingEventBus` backed by the container's
        artifact store. Phase B will switch to :class:`RedisEventBus` when
        ``REDIS_URL`` is reachable.
        """
        if self._event_bus is None:
            from .services.event_bus import FilePollingEventBus

            self._event_bus = FilePollingEventBus(store=self.artifact_store)
        return self._event_bus

    # ----- Factories -------------------------------------------------------

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
