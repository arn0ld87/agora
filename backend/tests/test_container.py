"""Pilot tests for AgoraContainer (Issue #14).

The whole point of the container is constructor-injection of dependencies
so services become testable without a Flask app context. These tests
demonstrate that contract — no ``flask.current_app``, no
``app.extensions``, no app factory.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.container import AgoraContainer, get_container
from app.services.artifact_store import (
    InMemoryArtifactStore,
    LocalFilesystemArtifactStore,
    SimulationArtifactStore,
)


# ---------------------------------------------------------------------------
# Constructor injection (no Flask context needed)
# ---------------------------------------------------------------------------


def test_explicit_dependencies_are_returned_verbatim():
    fake_neo4j = MagicMock(name="Neo4jStorage")
    fake_store = InMemoryArtifactStore()
    container = AgoraContainer(neo4j_storage=fake_neo4j, artifact_store=fake_store)

    assert container.neo4j_storage is fake_neo4j
    assert container.artifact_store is fake_store


def test_explicit_singletons_are_idempotent():
    fake_neo4j = MagicMock(name="Neo4jStorage")
    container = AgoraContainer(neo4j_storage=fake_neo4j)

    # Property access must not re-construct or replace the injected dependency.
    assert container.neo4j_storage is container.neo4j_storage
    assert container.neo4j_storage is fake_neo4j


def test_lazy_artifact_store_default_is_local_adapter():
    container = AgoraContainer()  # no overrides
    assert isinstance(container.artifact_store, LocalFilesystemArtifactStore)
    # And it satisfies the port contract.
    assert isinstance(container.artifact_store, SimulationArtifactStore)


def test_lazy_singleton_caches_first_construction():
    container = AgoraContainer()
    first = container.artifact_store
    second = container.artifact_store
    assert first is second


# ---------------------------------------------------------------------------
# Factory: GraphBuilderService is wired to container's storage
# ---------------------------------------------------------------------------


def test_graph_builder_factory_injects_container_storage():
    fake_neo4j = MagicMock(name="Neo4jStorage")
    container = AgoraContainer(neo4j_storage=fake_neo4j)

    builder = container.graph_builder()

    # The pilot service must receive *our* mock, not a freshly constructed one.
    assert builder.storage is fake_neo4j


def test_graph_builder_is_request_scoped_not_singleton():
    """Factories return fresh instances; only declared singletons are cached."""
    fake_neo4j = MagicMock(name="Neo4jStorage")
    container = AgoraContainer(neo4j_storage=fake_neo4j)

    a = container.graph_builder()
    b = container.graph_builder()

    assert a is not b
    # ...but they share the same underlying storage singleton.
    assert a.storage is b.storage


# ---------------------------------------------------------------------------
# get_container() guard
# ---------------------------------------------------------------------------


def test_get_container_outside_app_context_raises():
    # No Flask app is pushed in these tests — the helper must fail fast
    # rather than silently fall through.
    with pytest.raises(RuntimeError):
        get_container()
