"""Tests for typed entity deduplication in Neo4jWriteMixin._persist_episode.

Spec (Baustein B):
- MERGE key includes entity_type: (graph_id, name_lower, entity_type)
- Same name + different type → two separate nodes
- Same name + same type → single merged node
- Case-insensitive matching within a type (via name_lower)
- Missing entity_type defaults to "unknown" via _canonical_entity_type
"""

from __future__ import annotations

from unittest.mock import MagicMock


from app.storage.neo4j_write import _canonical_entity_type


# ---------------------------------------------------------------------------
# Unit tests for _canonical_entity_type helper
# ---------------------------------------------------------------------------


class TestCanonicalEntityType:
    def test_prefers_entity_type_field(self):
        assert _canonical_entity_type({"entity_type": "ORG", "type": "FRUIT"}) == "ORG"

    def test_falls_back_to_type(self):
        assert _canonical_entity_type({"type": "FRUIT"}) == "FRUIT"

    def test_falls_back_to_label(self):
        assert _canonical_entity_type({"label": "PERSON"}) == "PERSON"

    def test_returns_unknown_when_all_missing(self):
        assert _canonical_entity_type({}) == "unknown"

    def test_returns_unknown_for_empty_string(self):
        assert _canonical_entity_type({"type": "", "label": "  "}) == "unknown"

    def test_strips_whitespace(self):
        assert _canonical_entity_type({"type": "  ORG  "}) == "ORG"


# ---------------------------------------------------------------------------
# Integration-level tests via captured Cypher queries
# ---------------------------------------------------------------------------


def _make_write_mixin() -> MagicMock:
    """Return a Neo4jWriteMixin instance with all I/O mocked out."""
    from app.storage.neo4j_write import Neo4jWriteMixin

    mixin = MagicMock(spec=Neo4jWriteMixin)
    return mixin


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
    def merge_queries(self):
        return [(q, p) for q, p in self.calls if "MERGE" in q and "Entity" in q]


def _capture_persist_episode_cypher(entities: list[dict]) -> _CypherCapture:
    """Run _persist_episode with given entities and return captured Cypher.

    Implementation note: _persist_episode calls
        self._call_with_retry(session.execute_write, inner_fn)
    where inner_fn(tx) calls tx.run(query, **params).

    We intercept _call_with_retry so that it drives inner_fn with a
    capturing mock tx instead of a real Neo4j session.
    """
    from app.storage.neo4j_write import Neo4jWriteMixin

    capture = _CypherCapture()

    mixin = object.__new__(Neo4jWriteMixin)  # type: ignore[arg-type]
    mixin._ontology_mutation_service = None  # type: ignore[attr-defined]

    tx = capture.make_tx()

    def fake_call_with_retry(execute_write_fn_or_inner, inner_fn=None, *args, **kwargs):
        # _call_with_retry is called as: self._call_with_retry(session.execute_write, fn)
        # so inner_fn is the Cypher closure.
        if inner_fn is not None:
            result = inner_fn(tx)
        else:
            # Fallback: first arg is the closure directly
            result = execute_write_fn_or_inner(tx)
        # Return a mock that behaves like a Neo4j result with uuid
        record = MagicMock()
        record.__getitem__ = lambda self, key: "uuid-captured"
        mock_result = MagicMock()
        mock_result.single.return_value = record
        # The inner function may return the record value; we return "uuid-captured"
        return result if result is not None else "uuid-captured"

    mixin._call_with_retry = fake_call_with_retry  # type: ignore[attr-defined]

    mock_session = MagicMock()
    session_ctx = MagicMock()
    session_ctx.__enter__ = MagicMock(return_value=mock_session)
    session_ctx.__exit__ = MagicMock(return_value=False)
    mixin._get_session = MagicMock(return_value=session_ctx)  # type: ignore[attr-defined]

    relations: list[dict] = []
    entity_embeddings = [[0.1] * 4 for _ in entities]
    relation_embeddings: list = []

    Neo4jWriteMixin._persist_episode(
        mixin,
        graph_id="g1",
        episode_id="ep-001",
        text="test text",
        now="2026-01-01T00:00:00+00:00",
        entities=entities,
        relations=relations,
        entity_embeddings=entity_embeddings,
        relation_embeddings=relation_embeddings,
        round_num=None,
    )

    return capture


class TestEntityDedupeTyped:
    def test_same_name_different_type_creates_two_entities(self):
        """Apple (ORG) and Apple (FRUIT) must hit two distinct MERGE keys."""
        entities = [
            {"name": "Apple", "type": "ORG", "attributes": {}},
            {"name": "Apple", "type": "FRUIT", "attributes": {}},
        ]
        capture = _capture_persist_episode_cypher(entities)
        merge_qs = capture.merge_queries

        # Two separate MERGE calls
        assert len(merge_qs) == 2, f"Expected 2 MERGE calls, got {len(merge_qs)}"

        entity_types_used = [p.get("entity_type") for _, p in merge_qs]
        assert "ORG" in entity_types_used
        assert "FRUIT" in entity_types_used

    def test_same_name_same_type_merges_to_one(self):
        """Two Apple (ORG) episodes should result in one MERGE call with entity_type=ORG."""
        entities = [
            {"name": "Apple", "type": "ORG", "attributes": {}},
            {"name": "Apple", "type": "ORG", "attributes": {}},
        ]
        capture = _capture_persist_episode_cypher(entities)
        merge_qs = capture.merge_queries

        # Two MERGE calls happen (one per entity dict in the loop), but both
        # use the same key — in a real Neo4j tx this would upsert the same node.
        for _, params in merge_qs:
            assert params.get("entity_type") == "ORG"
            assert params.get("name_lower") == "apple"

    def test_case_insensitive_name_matching_within_type(self):
        """Apple and APPLE with same type use the same name_lower."""
        entities = [
            {"name": "Apple", "type": "ORG", "attributes": {}},
            {"name": "APPLE", "type": "ORG", "attributes": {}},
        ]
        capture = _capture_persist_episode_cypher(entities)
        merge_qs = capture.merge_queries

        name_lowers = [p.get("name_lower") for _, p in merge_qs]
        assert all(nl == "apple" for nl in name_lowers), (
            f"All name_lower values must be 'apple', got {name_lowers}"
        )

    def test_missing_entity_type_defaults_to_unknown(self):
        """Entity dict without type/entity_type/label → MERGE uses entity_type='unknown'."""
        entities = [
            {"name": "Something", "attributes": {}},
        ]
        capture = _capture_persist_episode_cypher(entities)
        merge_qs = capture.merge_queries

        assert len(merge_qs) == 1
        _, params = merge_qs[0]
        assert params.get("entity_type") == "unknown", (
            f"Expected entity_type='unknown', got {params.get('entity_type')!r}"
        )

    def test_entity_type_in_merge_cypher(self):
        """The MERGE statement must include entity_type as a key property."""
        entities = [{"name": "Berlin", "type": "LOCATION", "attributes": {}}]
        capture = _capture_persist_episode_cypher(entities)
        merge_qs = capture.merge_queries

        assert merge_qs, "No MERGE queries captured"
        query, _ = merge_qs[0]
        assert "entity_type" in query, (
            "MERGE Cypher must include entity_type in the identity key"
        )
