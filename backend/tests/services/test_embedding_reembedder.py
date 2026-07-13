"""Tests fuer ``Neo4jReEmbedder`` (Onboarding Slice 4.3.4 + 4.4 Fact-Phase).

Die Engine wird gegen einen Fake-Neo4j-Driver getestet: der Fake haelt
sortierte Entity- und Relations-Listen im Speicher, beantwortet Count-,
Batch- und Write-Queries fuer beide Phasen und protokolliert alle
Schreibzugriffe. So laufen die Tests ohne Neo4j und ohne echtes
Embedding-Backend.
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
    """Beantwortet die Query-Formen beider Phasen (entity + fact)."""

    def __init__(self, graph: "_FakeGraph") -> None:
        self._graph = graph

    def run(self, query: str, **params: Any) -> _FakeResult:
        self._graph.queries.append((query, params))
        if "CREATE VECTOR INDEX" in query:
            self._graph.created_indexes.append(query)
            return _FakeResult([])
        if "count(n) AS total" in query:
            return _FakeResult([{"total": len(self._graph.entities)}])
        if "count(r) AS total" in query:
            return _FakeResult([{"total": len(self._graph.relations)}])
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
        if "ORDER BY r.uuid" in query:
            cursor = params.get("cursor")
            limit = params["limit"]
            remaining = [
                r for r in self._graph.relations if cursor is None or r["uuid"] > cursor
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

    def __init__(
        self,
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]] | None = None,
    ) -> None:
        self.entities = sorted(entities, key=lambda e: e["uuid"])
        self.relations = sorted((relations or []), key=lambda r: r["uuid"])
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


def _relations(count: int) -> list[dict[str, Any]]:
    return [
        {"uuid": f"rel-{i:03d}", "text": f"Fact {i}"} for i in range(count)
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
    *,
    fact_target: tuple[str, str] | None = ("fact_embedding_v1", "fact_embedding_v1"),
) -> tuple[str, list[EmbeddingMigrationProgress]]:
    checkpoints: list[EmbeddingMigrationProgress] = []
    kwargs: dict[str, Any] = {}
    if fact_target is not None:
        kwargs["fact_target_index_name"] = fact_target[0]
        kwargs["fact_target_property_key"] = fact_target[1]
    status = engine.run(
        "entity_embedding_v1",
        "embedding_v1",
        _DIMS,
        progress or EmbeddingMigrationProgress(total=0, processed=0, failed=0),
        configuration=_configuration(),
        checkpoint=checkpoints.append,
        **kwargs,
    )
    return status, checkpoints


# ----------------------------------------------------------------------
# Entity-Phase (Slice 4.3.4 — Regressionsschutz)
# ----------------------------------------------------------------------


def test_run_reembeds_all_entities_in_batches() -> None:
    graph = _FakeGraph(_entities(5))
    status, checkpoints = _run(_engine(graph, batch_size=2), fact_target=None)

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
    assert final.phase == "entity"
    assert graph.closed is True


def test_run_creates_versioned_vector_index() -> None:
    graph = _FakeGraph(_entities(1))
    status, _ = _run(_engine(graph), fact_target=None)

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
    status, checkpoints = _run(_engine(graph, batch_size=2), progress=progress, fact_target=None)

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

    status, checkpoints = _run(_engine(graph, embedder=_mixed, batch_size=3), fact_target=None)

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
    status, checkpoints = _run(_engine(graph), fact_target=None)

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


def test_run_aborts_on_vector_count_mismatch() -> None:
    """Gemini-Finding (HIGH): liefert der Embedder weniger Vektoren als
    Texte, ist die Positionszuordnung nicht mehr verlaesslich — weiter-
    machen wuerde falsche Vektoren an falsche Knoten schreiben.
    """
    graph = _FakeGraph(_entities(3))

    def _short(texts: list[str]) -> list[list[float]]:
        return [[1.0] * _DIMS for _ in texts[:-1]]  # ein Vektor fehlt

    with pytest.raises(RuntimeError, match="Alignment"):
        _run(_engine(graph, embedder=_short, batch_size=3), fact_target=None)
    assert graph.written == [], "kein Batch darf teilgeschrieben werden"


def test_run_counts_none_vector_as_failed() -> None:
    graph = _FakeGraph(_entities(2))

    def _with_none(texts: list[str]) -> list[Any]:
        return [None, [1.0] * _DIMS]

    status, checkpoints = _run(_engine(graph, embedder=_with_none, batch_size=2), fact_target=None)

    assert status == "failed"
    assert checkpoints[-1].failed == 1
    assert checkpoints[-1].processed == 1


def test_run_propagates_embedder_errors() -> None:
    graph = _FakeGraph(_entities(2))

    def _exploding(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding backend down")

    with pytest.raises(RuntimeError, match="embedding backend down"):
        _run(_engine(graph, embedder=_exploding), fact_target=None)
    assert graph.closed is True, "Driver wird auch im Fehlerfall geschlossen"


# ----------------------------------------------------------------------
# Fact-Phase (Slice 4.4)
# ----------------------------------------------------------------------


def _writes_for(graph: _FakeGraph, property_key: str) -> list[dict[str, Any]]:
    """Alle geschriebenen Rows fuer einen bestimmten Property-Key."""
    return [
        row for batch in graph.written if batch["property_key"] == property_key
        for row in batch["rows"]
    ]


def test_run_reembeds_fact_phase_after_entity() -> None:
    """Happy Path: Entity-Phase, dann Fact-Phase. Beide Traeger werden
    re-embedded; der Phasenwechsel erscheint im Checkpoint-Stream.
    """
    graph = _FakeGraph(_entities(3), _relations(2))
    status, checkpoints = _run(_engine(graph, batch_size=2))

    assert status == "completed"
    # Entity-Vektoren in entity-Property, Fact-Vektoren in fact-Property.
    assert [r["uuid"] for r in _writes_for(graph, "embedding_v1")] == [
        "uuid-000",
        "uuid-001",
        "uuid-002",
    ]
    assert [r["uuid"] for r in _writes_for(graph, "fact_embedding_v1")] == [
        "rel-000",
        "rel-001",
    ]
    # Phasenwechsel im Checkpoint-Stream sichtbar.
    phases = [c.phase for c in checkpoints]
    assert "entity" in phases and "fact" in phases
    fact_first = next(c for c in checkpoints if c.phase == "fact")
    assert fact_first.total == 2, "Fact-Phase zaehlt die Relations-Menge"
    assert fact_first.processed == 0, "Phasenwechsel resettet processed"
    assert fact_first.last_processed_id is None, "Cursor wird beim Wechsel resettet"
    final = checkpoints[-1]
    assert final.phase == "fact"
    assert final.processed == 2
    assert final.failed == 0
    assert final.last_processed_id == "rel-001"


def test_run_fact_phase_creates_versioned_relationship_index() -> None:
    graph = _FakeGraph(_entities(1), _relations(1))
    status, _ = _run(_engine(graph))

    assert status == "completed"
    # Zwei Indizes: entity + fact.
    assert len(graph.created_indexes) == 2
    fact_ddl = [d for d in graph.created_indexes if "RELATION" in d][0]
    assert "fact_embedding_v1" in fact_ddl
    assert "IF NOT EXISTS" in fact_ddl
    assert "FOR ()-[r:RELATION]-() ON (r.fact_embedding_v1)" in fact_ddl
    assert f"`vector.dimensions`: {_DIMS}" in fact_ddl
    # Kein DROP — additive Indizes nur.
    assert all("DROP" not in ddl for ddl in graph.created_indexes)


def test_run_fact_phase_resumes_from_last_processed_id() -> None:
    """Resume mitten in der Fact-Phase: nur Rest-Relations werden
    geschrieben — kein Doppel-Write der bereits verarbeiteten.
    """
    graph = _FakeGraph(_entities(0), _relations(5))
    progress = EmbeddingMigrationProgress(
        total=5, processed=2, failed=0, last_processed_id="rel-001", phase="fact"
    )
    status, checkpoints = _run(
        _engine(graph, batch_size=2), progress=progress
    )

    assert status == "completed"
    # Entity-Phase uebersprungen (phase=="fact"); nur fact-Property geschrieben.
    assert _writes_for(graph, "embedding_v1") == []
    assert [r["uuid"] for r in _writes_for(graph, "fact_embedding_v1")] == [
        "rel-002",
        "rel-003",
        "rel-004",
    ], "nur Rest nach Cursor, kein Doppel-Write"
    final = checkpoints[-1]
    assert final.phase == "fact"
    assert final.last_processed_id == "rel-004"


def test_run_fact_phase_dimension_mismatch_counts_as_failed() -> None:
    graph = _FakeGraph(_entities(0), _relations(3))

    def _mixed(texts: list[str]) -> list[list[float]]:
        return [
            ([0.0] * (_DIMS - 1) if i == 0 else [1.0] * _DIMS)
            for i, _ in enumerate(texts)
        ]

    status, checkpoints = _run(
        _engine(graph, embedder=_mixed, batch_size=3)
    )

    assert status == "failed", "Fact-Dimension-Mismatch darf keinen Switch ausloesen"
    final = checkpoints[-1]
    assert final.phase == "fact"
    assert final.failed == 1
    assert final.processed == 2
    assert "rel-000" not in [r["uuid"] for r in _writes_for(graph, "fact_embedding_v1")]


def test_run_empty_graph_completes_both_phases_without_writes() -> None:
    """Leerer Graph (keine Entities, keine Relations) ist eine gueltige
    Erst-Migration fuer beide Phasen.
    """
    graph = _FakeGraph([], [])
    status, checkpoints = _run(_engine(graph))

    assert status == "completed"
    assert graph.written == []
    phases = [c.phase for c in checkpoints]
    assert "entity" in phases and "fact" in phases
    final = checkpoints[-1]
    assert final.phase == "fact"
    assert final.total == 0
    assert final.processed == 0
    assert final.failed == 0


def test_run_skips_entity_phase_when_progress_phase_is_fact() -> None:
    """Crash-Recovery: ein Job, der bereits in der Fact-Phase crashed
    ist, resumed *nur* die Fact-Phase — keine Entity-Writes.
    """
    graph = _FakeGraph(_entities(3), _relations(2))
    progress = EmbeddingMigrationProgress(
        total=2, processed=0, failed=0, last_processed_id=None, phase="fact"
    )
    status, checkpoints = _run(_engine(graph), progress=progress)

    assert status == "completed"
    assert _writes_for(graph, "embedding_v1") == [], "Entity-Phase uebersprungen"
    assert [r["uuid"] for r in _writes_for(graph, "fact_embedding_v1")] == [
        "rel-000",
        "rel-001",
    ]
    assert all(c.phase == "fact" for c in checkpoints)


def test_run_entity_failure_skips_fact_phase() -> None:
    """Schlaegt die Entity-Phase fehl, wird die Fact-Phase nicht mehr
    gestartet — kein Switch auf einen unvollstaendigen Index-Satz.
    """
    graph = _FakeGraph(_entities(2), _relations(2))

    def _mixed(texts: list[str]) -> list[list[float]]:
        return [
            ([0.0] * (_DIMS - 1) if i == 0 else [1.0] * _DIMS)
            for i, _ in enumerate(texts)
        ]

    status, checkpoints = _run(_engine(graph, embedder=_mixed, batch_size=2))

    assert status == "failed"
    assert _writes_for(graph, "fact_embedding_v1") == [], "Fact-Phase nicht gestartet"
    final = checkpoints[-1]
    assert final.phase == "entity"


def test_run_without_fact_targets_is_backward_compatible() -> None:
    """Ohne fact_target_* verhaelt sich die Engine wie Slice 4.3.4
    (nur Entity-Phase, kein Phasenwechsel).
    """
    graph = _FakeGraph(_entities(2), _relations(2))
    status, checkpoints = _run(_engine(graph), fact_target=None)

    assert status == "completed"
    assert _writes_for(graph, "fact_embedding_v1") == []
    assert len(graph.created_indexes) == 1, "kein fact-Index angelegt"
    final = checkpoints[-1]
    assert final.phase == "entity"


def test_run_rejects_invalid_fact_identifier() -> None:
    graph = _FakeGraph(_entities(1), _relations(1))
    engine = _engine(graph)
    progress = EmbeddingMigrationProgress(total=0, processed=0, failed=0)

    with pytest.raises(ValueError):
        engine.run(
            "entity_embedding_v1",
            "embedding_v1",
            _DIMS,
            progress,
            configuration=_configuration(),
            checkpoint=lambda p: None,
            fact_target_index_name="evil fact; DROP INDEX x",
            fact_target_property_key="fact_embedding_v1",
        )
    with pytest.raises(ValueError):
        engine.run(
            "entity_embedding_v1",
            "embedding_v1",
            _DIMS,
            progress,
            configuration=_configuration(),
            checkpoint=lambda p: None,
            fact_target_index_name="fact_embedding_v1",
            fact_target_property_key="fact`); DROP INDEX fact; //",
        )