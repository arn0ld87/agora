"""Kanonische Property-Namen-Aufloesung im Schreibpfad (Issue #1417 Slice 2.1).

``Neo4jWriteMixin._persist_episode`` schrieb Entity- und Fact-Embeddings
bisher fest gegen ``n.embedding`` / ``r.fact_embedding``. Diese Tests
sichern zwei Dinge an der echten Cypher-Konstruktion (nur Driver/Session
sind gemockt, siehe Harness in ``tests/storage/test_document_provenance.py``):

1. Ohne aktive Index-Version bleiben genau die Legacy-Property-Namen
   erhalten — die Rueckwaertskompatibilitaets-Zusage dieses Slices.
2. Mit aktiver Index-Version schreibt der Pfad gegen die im Store
   hinterlegten (Entity) bzw. daraus abgeleiteten (Fact) Namen.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.embedding_configuration_store import EmbeddingConfigurationStore


class _CypherCapture:
    """Captures (query, params) tuples from tx.run() calls."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def make_tx(self):
        tx = MagicMock()
        tx.run.side_effect = self._capture
        return tx

    def _capture(self, query, **params):
        self.calls.append((query, params))
        record = MagicMock()
        record.__getitem__ = lambda self, key: "uuid-captured"
        result = MagicMock()
        result.single.return_value = record
        return result

    @property
    def entity_merges(self):
        return [(q, p) for q, p in self.calls if "MERGE (n:Entity" in q]

    @property
    def relation_merges(self):
        return [(q, p) for q, p in self.calls if ":RELATION" in q]


def _capture_persist_episode_cypher(*, index_store) -> _CypherCapture:
    """Run ``_persist_episode`` mit einem Entity und einer Relation, damit
    beide Merge-Zweige (Entity-Embedding, Fact-Embedding) durchlaufen."""
    from app.storage.neo4j_write import Neo4jWriteMixin

    capture = _CypherCapture()

    mixin = object.__new__(Neo4jWriteMixin)  # type: ignore[arg-type]
    mixin._ontology_mutation_service = None  # type: ignore[attr-defined]
    mixin._embedding_index_store = index_store  # type: ignore[attr-defined]

    tx = capture.make_tx()

    def fake_call_with_retry(execute_write_fn_or_inner, inner_fn=None, *args, **kwargs):
        if inner_fn is not None:
            result = inner_fn(tx)
        else:
            result = execute_write_fn_or_inner(tx)
        return result if result is not None else "uuid-captured"

    mixin._call_with_retry = fake_call_with_retry  # type: ignore[attr-defined]

    mock_session = MagicMock()
    session_ctx = MagicMock()
    session_ctx.__enter__ = MagicMock(return_value=mock_session)
    session_ctx.__exit__ = MagicMock(return_value=False)
    mixin._get_session = MagicMock(return_value=session_ctx)  # type: ignore[attr-defined]

    entities = [{"name": "Alex", "entity_type": "Person", "attributes": {}}]
    relations = [
        {"source": "Alex", "target": "Alex", "type": "SELF", "fact": "Alex ist Alex."}
    ]

    Neo4jWriteMixin._persist_episode(
        mixin,
        graph_id="g1",
        episode_id="ep-001",
        text="test text",
        now="2026-01-01T00:00:00+00:00",
        entities=entities,
        relations=relations,
        entity_embeddings=[[0.1]],
        relation_embeddings=[[0.2]],
        round_num=None,
    )

    return capture


@pytest.fixture
def index_store(tmp_path: Path) -> EmbeddingConfigurationStore:
    return EmbeddingConfigurationStore(data_dir=tmp_path)


def test_entity_write_uses_legacy_property_without_active_version(index_store):
    capture = _capture_persist_episode_cypher(index_store=index_store)

    assert capture.entity_merges, "Entity-MERGE muss ausgeloest worden sein"
    query, _params = capture.entity_merges[0]
    assert "n.embedding = $embedding" in query
    assert "n.embedding_v1" not in query


def test_fact_write_uses_legacy_property_without_active_version(index_store):
    capture = _capture_persist_episode_cypher(index_store=index_store)

    assert capture.relation_merges, "RELATION-MERGE muss ausgeloest worden sein"
    query, _params = capture.relation_merges[0]
    assert "r.fact_embedding = $fact_embedding" in query


def test_entity_write_uses_versioned_property_with_active_version(index_store):
    index_store.upsert_index_version(
        version=None,
        provider_connection_id="conn-1",
        model_id="nomic-embed-text",
        dimensions=768,
        index_name="entity_embedding_v1",
        property_key="embedding_v1",
    )
    capture = _capture_persist_episode_cypher(index_store=index_store)

    query, _params = capture.entity_merges[0]
    assert "n.embedding_v1 = $embedding" in query
    assert "n.embedding = $embedding" not in query


def test_fact_write_uses_versioned_property_with_active_version(index_store):
    index_store.upsert_index_version(
        version=None,
        provider_connection_id="conn-1",
        model_id="nomic-embed-text",
        dimensions=768,
        index_name="entity_embedding_v1",
        property_key="embedding_v1",
    )
    capture = _capture_persist_episode_cypher(index_store=index_store)

    query, _params = capture.relation_merges[0]
    assert "r.fact_embedding_v1 = $fact_embedding" in query
    assert "r.fact_embedding = $fact_embedding" not in query


def test_persist_episode_defaults_to_own_store_when_attribute_missing():
    """Isolierte Mixin-Tests (z. B. ``test_persist_episode_retry_idempotent.py``)
    setzen ``_embedding_index_store`` nicht — der Schreibpfad darf trotzdem
    nicht mit ``AttributeError`` abbrechen, sondern instanziiert sich selbst
    einen Store und faellt (mangels Datei) auf die Legacy-Namen zurueck."""
    from app.storage.neo4j_write import Neo4jWriteMixin

    capture = _CypherCapture()
    mixin = object.__new__(Neo4jWriteMixin)  # type: ignore[arg-type]
    mixin._ontology_mutation_service = None  # type: ignore[attr-defined]
    # _embedding_index_store bewusst NICHT gesetzt.

    tx = capture.make_tx()

    def fake_call_with_retry(execute_write_fn_or_inner, inner_fn=None, *args, **kwargs):
        if inner_fn is not None:
            result = inner_fn(tx)
        else:
            result = execute_write_fn_or_inner(tx)
        return result if result is not None else "uuid-captured"

    mixin._call_with_retry = fake_call_with_retry  # type: ignore[attr-defined]

    mock_session = MagicMock()
    session_ctx = MagicMock()
    session_ctx.__enter__ = MagicMock(return_value=mock_session)
    session_ctx.__exit__ = MagicMock(return_value=False)
    mixin._get_session = MagicMock(return_value=session_ctx)  # type: ignore[attr-defined]

    Neo4jWriteMixin._persist_episode(
        mixin,
        graph_id="g1",
        episode_id="ep-001",
        text="test text",
        now="2026-01-01T00:00:00+00:00",
        entities=[],
        relations=[],
        entity_embeddings=[],
        relation_embeddings=[],
        round_num=None,
    )
    # Kein Fehler bis hierhin ist die eigentliche Aussage dieses Tests.
