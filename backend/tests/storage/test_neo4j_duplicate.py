"""Kopierpfad für Graphen (Issue #1808, Etappe 8) gegen einen Fake-Driver.

Der Fake führt kein Cypher aus. Er prüft, dass der Mixin die richtigen
Statements mit den richtigen Parametern sendet, dass Eigenschaften
unverändert (als Map-Parameter, nicht im Query-Text) reisen und dass eine
verlorene Commit-Bestätigung beim Wiederholen nichts doppelt schreibt. Die
Cypher-Semantik selbst prüft nur eine echte Neo4j-Instanz.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, List

import pytest
from neo4j.exceptions import ServiceUnavailable

from app.storage.neo4j_duplicate import GraphDuplicateWriteError, Neo4jDuplicateMixin
from app.utils.retry import neo4j_call_with_retry

GID = "11111111-1111-4111-8111-111111111111"
TARGET = "22222222-2222-4222-8222-222222222222"
NOW = "2026-10-07T10:00:00+00:00"


class _Result:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows

    def single(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _ScriptedTx:
    """Antwortet der Reihe nach; jeder Schritt nennt ein Merkmal des erwarteten Statements."""

    def __init__(self, steps: List[tuple[str, Any]]) -> None:
        self._steps = list(steps)
        self.calls: List[tuple[str, Dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> _Result:
        q = " ".join(query.split())
        self.calls.append((q, params))
        assert self._steps, f"unerwartetes Statement: {q}"
        marker, rows = self._steps.pop(0)
        assert marker in q, f"erwartet '{marker}', gesendet '{q}'"
        return _Result(rows)

    def done(self) -> None:
        assert not self._steps, f"Statements nicht gesendet: {[m for m, _ in self._steps]}"


class _Session:
    def __init__(self, tx: Any, fail_after_write_on: set[int] | None = None) -> None:
        self._tx = tx
        self._fail_on = fail_after_write_on or set()
        self.write_calls = 0

    def execute_write(self, func, *a, **kw):
        self.write_calls += 1
        result = func(self._tx, *a, **kw)
        if self.write_calls in self._fail_on:
            raise ServiceUnavailable("Verbindung nach Commit verloren")
        return result

    def execute_read(self, func, *a, **kw):
        return func(self._tx, *a, **kw)


class _Storage(Neo4jDuplicateMixin):
    def __init__(self, tx: Any, **session_kw: Any) -> None:
        self.session = _Session(tx, **session_kw)

    @contextmanager
    def _get_session(self, **_kw):
        yield self.session

    def _call_with_retry(self, func, *a, **kw):
        return neo4j_call_with_retry(func, *a, max_retries=3, initial_delay=0.0, **kw)


def _entity_row(uuid_: str, labels: List[str], **props: Any) -> Dict[str, Any]:
    return {"uuid": uuid_, "labels": labels, "props": {"uuid": uuid_, "graph_id": TARGET, **props}}


# ── Lesen ───────────────────────────────────────────────────────────────


def test_read_graph_returns_properties_or_none():
    found = _Storage(_ScriptedTx([("MATCH (g:Graph {graph_id: $gid})", [{"props": {"name": "Q", "status": "completed"}}])]))
    missing = _Storage(_ScriptedTx([("MATCH (g:Graph {graph_id: $gid})", [])]))

    assert found.duplicate_read_graph(GID) == {"name": "Q", "status": "completed"}
    assert missing.duplicate_read_graph(GID) is None


def test_count_reports_entities_relations_and_episodes():
    tx = _ScriptedTx([
        ("MATCH (n:Entity", [{"c": 5}]),
        ("MATCH ()-[r:RELATION", [{"c": 7}]),
        ("MATCH (ep:Episode", [{"c": 2}]),
    ])

    assert _Storage(tx).duplicate_count(GID) == {"entities": 5, "relations": 7, "episodes": 2}
    tx.done()


def test_read_entities_pages_by_uuid_and_returns_labels():
    tx = _ScriptedTx([("ORDER BY n.uuid LIMIT $limit", [
        {"props": {"uuid": "a", "name": "A"}, "labels": ["Entity", "Person"]},
    ])])

    page = _Storage(tx).duplicate_read_entities(GID, "0", 100)

    assert page == [{"props": {"uuid": "a", "name": "A"}, "labels": ["Entity", "Person"]}]
    query, params = tx.calls[0]
    assert "n.uuid > $after" in query
    assert params == {"gid": GID, "after": "0", "limit": 100}


def test_read_relations_filters_both_endpoints_to_the_graph():
    tx = _ScriptedTx([("RETURN properties(r) AS props", [
        {"props": {"uuid": "r1"}, "src": "s", "tgt": "t"},
    ])])

    rows = _Storage(tx).duplicate_read_relations(GID, ["s"])

    assert rows == [{"props": {"uuid": "r1"}, "source": "s", "target": "t"}]
    query, params = tx.calls[0]
    assert "r.graph_id = $gid AND t.graph_id = $gid" in query
    assert params == {"gid": GID, "uuids": ["s"]}


# ── Schreiben ───────────────────────────────────────────────────────────


def test_create_graph_sets_building_status_and_passes_ontology():
    tx = _ScriptedTx([("MERGE (g:Graph {graph_id: $gid})", [])])

    _Storage(tx).duplicate_create_graph(
        graph_id=TARGET, name="Kopie", description="d", ontology_json='{"a": 1}', now=NOW
    )

    query, params = tx.calls[0]
    assert "g.status = 'building'" in query
    assert params == {"gid": TARGET, "name": "Kopie", "description": "d",
                      "ontology_json": '{"a": 1}', "now": NOW}


def test_write_entities_groups_by_label_combination_and_sends_props_as_parameter():
    tx = _ScriptedTx([
        ("MERGE (n:Entity {uuid: row.uuid})", [{"written": 2}]),
        ("MERGE (n:Entity {uuid: row.uuid})", [{"written": 1}]),
    ])
    rows = [
        _entity_row("a", ["Entity", "Person"], origin="manual", embedding=[0.25, 0.5]),
        _entity_row("b", ["Entity", "Person"]),
        _entity_row("c", ["Entity", "Organization", "Person"]),
    ]

    written = _Storage(tx).duplicate_write_entities(rows)

    assert written == 3
    first_query, first_params = tx.calls[0]
    assert first_query.endswith("ON CREATE SET n = row.props SET n:`Person` RETURN count(n) AS written")
    assert [r["uuid"] for r in first_params["rows"]] == ["a", "b"]
    assert first_params["rows"][0]["props"]["origin"] == "manual"
    assert first_params["rows"][0]["props"]["embedding"] == [0.25, 0.5]
    assert "SET n:`Organization`:`Person`" in tx.calls[1][0]
    assert "manual" not in first_query  # Eigenschaften nie im Query-Text


def test_write_entities_rejects_label_that_cannot_be_written_safely():
    tx = _ScriptedTx([])

    with pytest.raises(GraphDuplicateWriteError):
        _Storage(tx).duplicate_write_entities([_entity_row("a", ["Entity", "Person`) DETACH DELETE n //"])])

    assert tx.calls == []


def test_write_entities_reports_swallowed_rows():
    tx = _ScriptedTx([("MERGE (n:Entity {uuid: row.uuid})", [{"written": 1}])])

    with pytest.raises(GraphDuplicateWriteError, match="1 von 2"):
        _Storage(tx).duplicate_write_entities([
            _entity_row("a", ["Entity"]), _entity_row("b", ["Entity"]),
        ])


def test_write_relations_merges_on_uuid_and_reports_missing_endpoint():
    ok_tx = _ScriptedTx([("MERGE (s)-[r:RELATION {uuid: row.uuid}]->(t)", [{"written": 1}])])
    row = {"uuid": "r1", "source": "s", "target": "t", "props": {"uuid": "r1", "graph_id": TARGET}}

    assert _Storage(ok_tx).duplicate_write_relations([row]) == 1
    assert ok_tx.calls[0][1] == {"rows": [row]}

    short_tx = _ScriptedTx([("MERGE (s)-[r:RELATION", [{"written": 0}])])
    with pytest.raises(GraphDuplicateWriteError, match="0 von 1"):
        _Storage(short_tx).duplicate_write_relations([row])


def test_write_episodes_skips_empty_pages_and_reports_short_writes():
    tx = _ScriptedTx([])
    assert _Storage(tx).duplicate_write_episodes([]) == 0
    assert tx.calls == []

    short = _ScriptedTx([("MERGE (ep:Episode {uuid: row.uuid})", [{"written": 1}])])
    with pytest.raises(GraphDuplicateWriteError, match="1 von 2"):
        _Storage(short).duplicate_write_episodes([
            {"uuid": "e1", "props": {"uuid": "e1"}}, {"uuid": "e2", "props": {"uuid": "e2"}},
        ])


def test_lost_commit_ack_is_retried_with_the_same_merge_statement():
    """Der erste Versuch wirkt, meldet aber Verbindungsabbruch; der Retry sendet dasselbe MERGE."""
    tx = _ScriptedTx([
        ("MERGE (n:Entity {uuid: row.uuid})", [{"written": 1}]),
        ("MERGE (n:Entity {uuid: row.uuid})", [{"written": 1}]),
    ])
    storage = _Storage(tx, fail_after_write_on={1})

    assert storage.duplicate_write_entities([_entity_row("a", ["Entity"])]) == 1

    assert storage.session.write_calls == 2
    assert tx.calls[0] == tx.calls[1]
