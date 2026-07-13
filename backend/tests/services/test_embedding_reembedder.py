"""Tests fuer ``Neo4jReEmbedder`` (Onboarding Slice 4.3.4).

Die Engine wird gegen einen Fake-Neo4j-Driver getestet: der Fake haelt
eine sortierte Entity-Liste im Speicher, beantwortet Count-, Batch- und
Write-Queries und protokolliert alle Schreibzugriffe. So laufen die
Tests ohne Neo4j und ohne echtes Embedding-Backend.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingMigrationProgress,
)
from app.services.embedding_reembedder import Neo4jReEmbedder

# ----------------------------------------------------------------------
# Fakes
# ----------------------------------------------------------------------


class _FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def single(self) -> dict[str, Any]:
        return self._records[0]

    def consume(self) -> None:
        return None

    def __iter__(self):
        return iter(self._records)


class _FakeTx:
    """Beantwortet die drei Query-Formen der Engine."""

    def __init__(self, graph: "_FakeGraph") -> None:
        self._graph = graph

    def run(self, query: str, **params: Any) -> _FakeResult:
        self._graph.queries.append((query, params))
        if "CREATE VECTOR INDEX" in query:
            self._graph.created_indexes.append(query)
            return _FakeResult([])
        if "count(n) AS total" in query:
            return _FakeResult([{"total": len(self._graph.entities)}])
        if "UNWIND $rows" in query:
            self._graph.written.append(
                {"property_key": params["property_key"], "rows": params["rows"]}
            )
            return _FakeResult([{"written": len(params["rows"])}])
        if "ORDER BY n.uuid" in query:
            cursor = params.get("cursor")
            limit = params["limit"]
            remaining = [
                e for e in self._graph.entities if cursor is None or e["uuid"] > cursor
            ]
            return _FakeResult(remaining[:limit])
        raise AssertionError(f"Unerwartete Query: {query}")


class _FakeSession:
    def __init__(self, graph: "_FakeGraph") -> None:
        self._graph = graph

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def execute_read(self, fn: Any) -> Any:
        return fn(_FakeTx(self._graph))

    def execute_write(self, fn: Any) -> Any:
        return fn(_FakeTx(self._graph))


class _FakeGraph:
    """Gemeinsamer Zustand von Driver, Session und Tx."""

    def __init__(self, entities: list[dict[str, Any]]) -> None:
        self.entities = sorted(entities, key=lambda e: e["uuid"])
        self.queries: list[tuple[str, dict[str, Any]]] = []
        self.written: list[dict[str, Any]] = []
        self.created_indexes: list[str] = []
        self.closed = False


class _FakeDriver:
    def __init__(self, graph: _FakeGraph) -> None:
        self._graph = graph

    def session(self) -> _FakeSession:
        return _FakeSession(self._graph)

    def close(self) -> None:
        self._graph.closed = True


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

_DIMS = 4


def _configuration() -> EmbeddingConfiguration:
    from datetime import datetime, timezone

    now = datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc)
    return EmbeddingConfiguration(
        id="emb-1",
        provider_connection_id="conn-1",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=_DIMS,
        scope="global",
        project_id=None,
        index_version=1,
        status="reembedding",
        created_at=now,
        updated_at=now,
    )


def _entities(count: int) -> list[dict[str, Any]]:
    return [
        {"uuid": f"uuid-{i:03d}", "text": f"Entity {i} (ORG)"} for i in range(count)
    ]


def _good_embedder(texts: list[str]) -> list[list[float]]:
    return [[float(len(t))] * _DIMS for t in texts]


def _engine(
    graph: _FakeGraph,
    embedder: Any = _good_embedder,
    batch_size: int = 2,
) -> Neo4jReEmbedder:
    return Neo4jReEmbedder(
        driver_factory=lambda: _FakeDriver(graph),
        embedder_factory=lambda configuration: embedder,
        batch_size=batch_size,
    )


def _run(
    engine: Neo4jReEmbedder,
    progress: EmbeddingMigrationProgress | None = None,
) -> tuple[str, list[EmbeddingMigrationProgress]]:
    checkpoints: list[EmbeddingMigrationProgress] = []
    status = engine.run(
        "entity_embedding_v1",
        "embedding_v1",
        _DIMS,
        progress or EmbeddingMigrationProgress(total=0, processed=0, failed=0),
        configuration=_configuration(),
        checkpoint=checkpoints.append,
    )
    return status, checkpoints


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_run_reembeds_all_entities_in_batches() -> None:
    graph = _FakeGraph(_entities(5))
    status, checkpoints = _run(_engine(graph, batch_size=2))

    assert status == "completed"
    written_uuids = [
        row["uuid"] for batch in graph.written for row in batch["rows"]
    ]
    assert written_uuids == [f"uuid-{i:03d}" for i in range(5)]
    assert all(batch["property_key"] == "embedding_v1" for batch in graph.written)
    assert all(
        len(row["vector"]) == _DIMS
        for batch in graph.written
        for row in batch["rows"]
    )
    # Erster Checkpoint traegt den Total-Count, danach einer pro Batch.
    assert checkpoints[0].total == 5
    assert len(checkpoints) == 1 + 3  # ceil(5/2) Batches
    final = checkpoints[-1]
    assert final.processed == 5
    assert final.failed == 0
    assert final.last_processed_id == "uuid-004"
    assert graph.closed is True


def test_run_creates_versioned_vector_index() -> None:
    graph = _FakeGraph(_entities(1))
    status, _ = _run(_engine(graph))

    assert status == "completed"
    assert len(graph.created_indexes) == 1
    ddl = graph.created_indexes[0]
    assert "entity_embedding_v1" in ddl
    assert "IF NOT EXISTS" in ddl
    assert "n.embedding_v1" in ddl
    assert f"`vector.dimensions`: {_DIMS}" in ddl


def test_run_resumes_from_last_processed_id() -> None:
    graph = _FakeGraph(_entities(5))
    progress = EmbeddingMigrationProgress(
        total=5, processed=3, failed=0, last_processed_id="uuid-002"
    )
    status, checkpoints = _run(_engine(graph, batch_size=2), progress=progress)

    assert status == "completed"
    written_uuids = [
        row["uuid"] for batch in graph.written for row in batch["rows"]
    ]
    assert written_uuids == ["uuid-003", "uuid-004"], "nur Rest nach Cursor"
    final = checkpoints[-1]
    assert final.processed == 5
    assert final.last_processed_id == "uuid-004"


def test_run_counts_dimension_mismatch_as_failed() -> None:
    graph = _FakeGraph(_entities(3))

    def _mixed(texts: list[str]) -> list[list[float]]:
        # Erster Text pro Batch bekommt eine falsche Dimension.
        return [
            ([0.0] * (_DIMS - 1) if i == 0 else [1.0] * _DIMS)
            for i, _ in enumerate(texts)
        ]

    status, checkpoints = _run(_engine(graph, embedder=_mixed, batch_size=3))

    assert status == "failed", "Dimension-Mismatch darf keinen Switch ausloesen"
    final = checkpoints[-1]
    assert final.failed == 1
    assert final.processed == 2
    written_uuids = [
        row["uuid"] for batch in graph.written for row in batch["rows"]
    ]
    assert "uuid-000" not in written_uuids


def test_run_with_empty_graph_completes_without_writes() -> None:
    graph = _FakeGraph([])
    status, checkpoints = _run(_engine(graph))

    assert status == "completed"
    assert graph.written == []
    assert checkpoints[-1].total == 0
    assert checkpoints[-1].processed == 0


def test_run_rejects_invalid_index_or_property_identifier() -> None:
    graph = _FakeGraph(_entities(1))
    engine = _engine(graph)
    progress = EmbeddingMigrationProgress(total=0, processed=0, failed=0)

    with pytest.raises(ValueError):
        engine.run(
            "evil name; DROP INDEX x",
            "embedding_v1",
            _DIMS,
            progress,
            configuration=_configuration(),
            checkpoint=lambda p: None,
        )
    with pytest.raises(ValueError):
        engine.run(
            "entity_embedding_v1",
            "embedding_v1`); MATCH (n) DETACH DELETE n; //",
            _DIMS,
            progress,
            configuration=_configuration(),
            checkpoint=lambda p: None,
        )


def test_run_propagates_embedder_errors() -> None:
    graph = _FakeGraph(_entities(2))

    def _exploding(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding backend down")

    with pytest.raises(RuntimeError, match="embedding backend down"):
        _run(_engine(graph, embedder=_exploding))
    assert graph.closed is True, "Driver wird auch im Fehlerfall geschlossen"
