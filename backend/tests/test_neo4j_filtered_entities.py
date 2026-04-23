"""
Tests for ``Neo4jStorage.get_filtered_entities_with_edges``.

These are Python-assembly tests, not Cypher tests — we stub the driver so the
tx records look like what Neo4j would return and verify the direction/dedup
logic that wraps the Cypher result.
"""

from unittest.mock import MagicMock

import pytest

from app.storage.neo4j_storage import Neo4jStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeNode(dict):
    """Mimics a neo4j ``Node`` which behaves like a dict of properties."""


def _record(**kwargs):
    rec = MagicMock()
    rec.__getitem__.side_effect = lambda key: kwargs[key]
    return rec


@pytest.fixture
def storage():
    inst = object.__new__(Neo4jStorage)
    inst._is_connected = True
    inst._last_error = None
    inst._last_success_ts = None
    inst._driver = MagicMock()

    # _call_with_retry normally drives neo4j_call_with_retry; short-circuit it
    # so the tests are deterministic and do not need the real retry machinery.
    inst._call_with_retry = lambda func, *a, **kw: func(*a, **kw)
    return inst


def _install_session(storage, tx):
    """Wire ``storage._driver.session().__enter__()`` to return an object
    whose ``execute_read`` simply calls the passed function with our fake tx."""
    session = MagicMock()
    session.execute_read.side_effect = lambda func, *a, **kw: func(tx, *a, **kw)
    cm = MagicMock()
    cm.__enter__.return_value = session
    cm.__exit__.return_value = False
    storage._driver.session.return_value = cm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_total_count_and_entities_shape(storage):
    tx = MagicMock()
    node = _FakeNode({
        "uuid": "u1",
        "name": "Alice",
        "attributes_json": "{}",
        "summary": "",
        "created_at": None,
    })

    def _run(query, **params):
        # Two queries in this flow: the baseline count, then the filtered pull.
        if "count(n)" in query:
            count_record = MagicMock()
            count_record.single.return_value = {"cnt": 7}
            return count_record
        # Filtered query — return one entity with one outgoing edge.
        assert params["gid"] == "g1"
        assert params["types"] is None
        return iter([
            _record(
                n=node,
                node_labels=["Entity", "Person"],
                raw_edges=[{
                    "edge_name": "KNOWS",
                    "fact": "Alice knows Bob",
                    "source_node_uuid": "u1",
                    "target_node_uuid": "u2",
                }],
                raw_related=[{
                    "uuid": "u2",
                    "name": "Bob",
                    "labels": ["Person"],
                    "summary": "",
                }],
            )
        ])

    tx.run.side_effect = _run
    _install_session(storage, tx)

    result = storage.get_filtered_entities_with_edges("g1")

    assert result["total_count"] == 7
    assert len(result["entities"]) == 1
    entity = result["entities"][0]
    assert entity["uuid"] == "u1"
    assert entity["related_edges"] == [{
        "direction": "outgoing",
        "edge_name": "KNOWS",
        "fact": "Alice knows Bob",
        "target_node_uuid": "u2",
    }]
    assert entity["related_nodes"] == [
        {"uuid": "u2", "name": "Bob", "labels": ["Person"], "summary": ""}
    ]


def test_incoming_edges_are_labelled_correctly(storage):
    """Direction must be ``incoming`` when the entity is the edge's endNode."""
    tx = MagicMock()
    node = _FakeNode({
        "uuid": "u1",
        "name": "Alice",
        "attributes_json": "{}",
        "summary": "",
        "created_at": None,
    })

    def _run(query, **params):
        if "count(n)" in query:
            count_record = MagicMock()
            count_record.single.return_value = {"cnt": 1}
            return count_record
        return iter([
            _record(
                n=node,
                node_labels=["Entity", "Person"],
                raw_edges=[{
                    "edge_name": "MENTIONS",
                    "fact": "Bob mentions Alice",
                    "source_node_uuid": "u2",
                    "target_node_uuid": "u1",
                }],
                raw_related=[{
                    "uuid": "u2",
                    "name": "Bob",
                    "labels": ["Person"],
                    "summary": "",
                }],
            )
        ])

    tx.run.side_effect = _run
    _install_session(storage, tx)

    result = storage.get_filtered_entities_with_edges("g1")

    edge = result["entities"][0]["related_edges"][0]
    assert edge["direction"] == "incoming"
    assert edge["source_node_uuid"] == "u2"
    assert "target_node_uuid" not in edge


def test_enrich_with_edges_false_skips_edge_query(storage):
    """Without enrichment we should not request edges at all."""
    tx = MagicMock()
    queries_seen = []
    node = _FakeNode({
        "uuid": "u1",
        "name": "Alice",
        "attributes_json": "{}",
        "summary": "",
        "created_at": None,
    })

    def _run(query, **params):
        queries_seen.append(query)
        if "count(n)" in query:
            count_record = MagicMock()
            count_record.single.return_value = {"cnt": 2}
            return count_record
        return iter([_record(n=node, node_labels=["Entity", "Person"])])

    tx.run.side_effect = _run
    _install_session(storage, tx)

    result = storage.get_filtered_entities_with_edges(
        "g1", enrich_with_edges=False
    )

    assert result["entities"][0]["related_edges"] == []
    assert result["entities"][0]["related_nodes"] == []
    joined = " ".join(queries_seen)
    assert "OPTIONAL MATCH" not in joined
    assert "RELATION" not in joined


def test_type_whitelist_is_passed_as_param(storage):
    """``defined_entity_types`` must arrive as a Cypher parameter, never
    interpolated into the query string (Cypher-injection guard)."""
    tx = MagicMock()
    captured = {}

    def _run(query, **params):
        captured["query"] = query
        captured["params"] = params
        if "count(n)" in query:
            count_record = MagicMock()
            count_record.single.return_value = {"cnt": 0}
            return count_record
        return iter([])

    tx.run.side_effect = _run
    _install_session(storage, tx)

    storage.get_filtered_entities_with_edges(
        "g1", defined_entity_types=["Person", "Organization"]
    )

    assert captured["params"]["types"] == ["Person", "Organization"]
    assert "Person" not in captured["query"]
    assert "Organization" not in captured["query"]
