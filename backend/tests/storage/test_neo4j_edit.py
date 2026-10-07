"""Schreibpfad für Handänderungen (Issue #1808, ADR-0022) gegen einen Fake-Driver.

Der Fake führt kein Cypher aus. Er prüft, dass der Mixin die richtigen
Statements in der richtigen Reihenfolge mit den richtigen Parametern
sendet, und bildet für das Anlegen die Eindeutigkeit über UUID und
Identitätsschlüssel nach, damit die Retry-Sicherheit sichtbar wird. Die
Cypher-Semantik selbst prüft nur eine echte Neo4j-Instanz.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Dict, List

import pytest
from neo4j.exceptions import ServiceUnavailable

from app.storage.neo4j_edit import (
    ALIASES_KEY,
    GraphEditConflict,
    GraphEditNotFound,
    Neo4jEditMixin,
)
from app.utils.retry import neo4j_call_with_retry

GID = "11111111-1111-4111-8111-111111111111"
NOW = "2026-10-07T10:00:00+00:00"
U1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"
U2 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"
U3 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3"


class _Result:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows

    def single(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _ScriptedTx:
    """Antwortet der Reihe nach; jeder Schritt nennt ein Merkmal des erwarteten Statements."""

    def __init__(self, steps: List[tuple[str, List[Dict[str, Any]]]]) -> None:
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


class _Storage(Neo4jEditMixin):
    def __init__(self, tx: Any, **session_kw: Any) -> None:
        self.session = _Session(tx, **session_kw)

    @contextmanager
    def _get_session(self, **_kw):
        yield self.session

    def _call_with_retry(self, func, *a, **kw):
        return neo4j_call_with_retry(func, *a, max_retries=3, initial_delay=0.0, **kw)


def _node(uuid_: str, name: str, etype: str = "Person", **extra: Any) -> Dict[str, Any]:
    return {
        "uuid": uuid_,
        "graph_id": GID,
        "name": name,
        "name_lower": name.lower(),
        "entity_type": etype,
        "summary": f"{name} ({etype})",
        "attributes_json": extra.pop("attributes_json", "{}"),
        "created_at": NOW,
        **extra,
    }


# ── Anlegen mit stateful Fake: Eindeutigkeit über UUID und Identitätsschlüssel ──


class _FakeGraph:
    def __init__(self) -> None:
        self.entities: Dict[str, Dict[str, Any]] = {}
        self.labels: Dict[str, set[str]] = {}
        self.relations: Dict[str, Dict[str, Any]] = {}

    def run(self, query: str, **p: Any) -> _Result:
        q = " ".join(query.split())
        if q.startswith("MATCH (n:Entity {uuid: $uuid}) RETURN n"):
            node = self.entities.get(p["uuid"])
            return _Result([{"n": node, "labels": ["Entity", *self.labels.get(p["uuid"], [])]}] if node else [])
        if q.startswith("MERGE (n:Entity"):
            for node in self.entities.values():
                if (node["graph_id"], node["name_lower"], node["entity_type"]) == (
                    p["gid"], p["name_lower"], p["entity_type"],
                ):
                    return _Result([{"uuid": node["uuid"]}])
            self.entities[p["uuid"]] = {
                "uuid": p["uuid"], "graph_id": p["gid"], "name": p["name"],
                "name_lower": p["name_lower"], "entity_type": p["entity_type"],
                "summary": p["summary"], "attributes_json": p["attrs_json"],
                "created_at": p["now"], "origin": "manual", "origin_changed_at": p["now"],
            }
            return _Result([{"uuid": p["uuid"]}])
        if q.startswith("MATCH (n:Entity {uuid: $uuid}) SET n:"):
            label = q.split("SET n:`")[1].rstrip("`")
            self.labels.setdefault(p["uuid"], set()).add(label)
            return _Result([])
        if "MERGE (src)-[r:RELATION" in q:
            self.relations.setdefault(p["uuid"], {"uuid": p["uuid"], "graph_id": p["gid"], "name": p["name"],
                "fact": p["fact"], "episode_ids": [], "origin": "manual", "origin_changed_at": p["now"],
                "src": p["src_uuid"], "tgt": p["tgt_uuid"]})
            r = self.relations[p["uuid"]]
            return _Result([{"r": r, "src_uuid": r["src"], "tgt_uuid": r["tgt"]}])
        if q.startswith("MATCH (src:Entity)-[r:RELATION {uuid: $uuid}]->(tgt:Entity)"):
            r = self.relations.get(p["uuid"])
            return _Result([{"r": r, "src_uuid": r["src"], "tgt_uuid": r["tgt"]}] if r else [])
        raise AssertionError(f"unerwartetes Statement: {q}")


def _create_entity(storage: _Storage, entity_uuid: str, name: str = "Stadtwerke"):
    return storage.edit_create_entity(
        graph_id=GID, entity_uuid=entity_uuid, name=name, entity_type="Organization",
        summary="x", aliases=["SW"], embedding=[0.1, 0.2], property_key="embedding", now=NOW,
    )


class TestCreateEntity:
    def test_creates_manual_entity_with_label_and_aliases(self):
        graph = _FakeGraph()
        node, created = _create_entity(_Storage(graph), U1)

        assert created is True
        assert node["provenance"]["origin"] == "manual"
        assert node["provenance"]["changed_at"] == NOW
        assert node["entity_type"] == "Organization"
        assert node["labels"] == ["Organization"]
        assert node["attributes"] == {ALIASES_KEY: ["SW"]}

    def test_repeat_with_same_uuid_creates_no_second_node(self):
        graph = _FakeGraph()
        storage = _Storage(graph)
        _create_entity(storage, U1)
        node, created = _create_entity(storage, U1)

        assert created is False
        assert len(graph.entities) == 1
        assert node["uuid"] == U1

    def test_lost_commit_ack_does_not_duplicate(self):
        """Der erste Versuch wirkt, meldet aber Verbindungsabbruch; der Retry legt nichts neu an."""
        graph = _FakeGraph()
        storage = _Storage(graph, fail_after_write_on={1})

        node, _created = _create_entity(storage, U1)

        assert storage.session.write_calls == 2
        assert len(graph.entities) == 1
        assert node["uuid"] == U1

    def test_same_name_and_type_with_other_uuid_is_conflict(self):
        graph = _FakeGraph()
        storage = _Storage(graph)
        _create_entity(storage, U1)
        with pytest.raises(GraphEditConflict):
            _create_entity(storage, U2)
        assert len(graph.entities) == 1  # kein stilles Zusammenführen, kein zweiter Knoten

    def test_reused_request_id_for_different_name_is_conflict(self):
        graph = _FakeGraph()
        storage = _Storage(graph)
        _create_entity(storage, U1, name="Stadtwerke")
        with pytest.raises(GraphEditConflict):
            _create_entity(storage, U1, name="Andere GmbH")


class TestCreateRelation:
    def _create(self, storage, rel_uuid=U3, src=U1, tgt=U2):
        return storage.edit_create_relation(
            graph_id=GID, relation_uuid=rel_uuid, source_uuid=src, target_uuid=tgt,
            name="FINANZIERT", fact="A finanziert B.", embedding=[0.3], property_key="fact_embedding",
            now=NOW,
        )

    def test_creates_manual_edge_without_episodes(self):
        graph = _FakeGraph()
        edge, created = self._create(_Storage(graph))
        assert created is True
        assert edge["episode_ids"] == []
        assert edge["provenance"] == {"origin": "manual", "changed_at": NOW, "episode_count": 0}

    def test_repeat_creates_no_second_edge(self):
        graph = _FakeGraph()
        storage = _Storage(graph)
        self._create(storage)
        _edge, created = self._create(storage)
        assert created is False
        assert len(graph.relations) == 1

    def test_reused_request_id_for_other_endpoints_is_conflict(self):
        graph = _FakeGraph()
        storage = _Storage(graph)
        self._create(storage)
        with pytest.raises(GraphEditConflict):
            self._create(storage, src=U2, tgt=U1)

    def test_missing_endpoint_is_not_found(self):
        tx = _ScriptedTx([("MATCH (src:Entity)-[r:RELATION {uuid: $uuid}]", []), ("MERGE (src)-[r:RELATION", [])])
        with pytest.raises(GraphEditNotFound):
            self._create(_Storage(tx))


# ── Ändern ───────────────────────────────────────────────────────────────


class TestUpdateEntity:
    def _update(self, tx, **kw):
        args = dict(
            graph_id=GID, entity_uuid=U1, name=None, entity_type=None, summary=None, aliases=None,
            embedding=None, embedding_text=None, property_key="embedding", now=NOW,
        )
        args.update(kw)
        return _Storage(tx).edit_update_entity(**args)

    def test_extracted_entity_becomes_edited_and_name_lower_follows(self):
        current = _node(U1, "Alex")
        updated = _node(U1, "Alexander", origin="edited", origin_changed_at=NOW)
        tx = _ScriptedTx([
            ("RETURN n, labels(n)", [{"n": current, "labels": ["Entity", "Person"]}]),
            ("WHERE o.uuid <> $uuid", []),
            ("SET n.origin = CASE", []),
            ("RETURN n, labels(n)", [{"n": updated, "labels": ["Entity", "Person"]}]),
        ])
        result = self._update(
            tx, name="Alexander", embedding=[0.5], embedding_text="Alexander (Person)"
        )
        tx.done()

        set_query, params = tx.calls[2]
        assert "n.origin = CASE WHEN n.origin = 'manual' THEN 'manual' ELSE 'edited' END" in set_query
        assert "n.name_lower = $name_lower" in set_query
        assert "n.embedding = $embedding" in set_query
        assert params["name_lower"] == "alexander"
        assert params["embedding"] == [0.5]
        assert result["provenance"]["origin"] == "edited"

    def test_summary_only_change_does_not_touch_identity_or_embedding(self):
        current = _node(U1, "Alex")
        tx = _ScriptedTx([
            ("RETURN n, labels(n)", [{"n": current, "labels": ["Entity", "Person"]}]),
            ("SET n.origin = CASE", []),
            ("RETURN n, labels(n)", [{"n": current, "labels": ["Entity", "Person"]}]),
        ])
        self._update(tx, summary="neu")
        tx.done()
        set_query, params = tx.calls[1]
        assert "n.summary = $summary" in set_query
        assert "embedding" not in set_query
        assert "name_lower" not in set_query
        assert params["summary"] == "neu"

    def test_manual_entity_stays_manual_by_cypher_rule(self):
        """Die Regel steht im Statement: ``manual`` bleibt ``manual``."""
        current = _node(U1, "Alex", origin="manual", origin_changed_at=NOW)
        tx = _ScriptedTx([
            ("RETURN n, labels(n)", [{"n": current, "labels": ["Entity", "Person"]}]),
            ("SET n.origin = CASE", []),
            ("RETURN n, labels(n)", [{"n": current, "labels": ["Entity", "Person"]}]),
        ])
        result = self._update(tx, summary="neu")
        assert result["provenance"]["origin"] == "manual"

    def test_type_change_moves_label_and_entity_type_together(self):
        current = _node(U1, "Alex")
        tx = _ScriptedTx([
            ("RETURN n, labels(n)", [{"n": current, "labels": ["Entity", "Person"]}]),
            ("WHERE o.uuid <> $uuid", []),
            ("SET n.origin = CASE", []),
            ("REMOVE n:`Person`", []),
            ("SET n:`Organization`", []),
            ("RETURN n, labels(n)", [{"n": _node(U1, "Alex", "Organization"), "labels": ["Entity", "Organization"]}]),
        ])
        result = self._update(
            tx, entity_type="Organization", embedding=[0.1], embedding_text="Alex (Organization)"
        )
        tx.done()
        assert "n.entity_type = $entity_type" in tx.calls[2][0]
        assert result["entity_type"] == "Organization"
        assert result["labels"] == ["Organization"]

    def test_collision_is_conflict_and_nothing_is_written(self):
        current = _node(U1, "Alex")
        tx = _ScriptedTx([
            ("RETURN n, labels(n)", [{"n": current, "labels": ["Entity", "Person"]}]),
            ("WHERE o.uuid <> $uuid", [{"uuid": U2}]),
        ])
        with pytest.raises(GraphEditConflict):
            self._update(tx, name="Bob", embedding=[0.5], embedding_text="Bob (Person)")
        tx.done()  # kein SET gesendet

    def test_stale_embedding_text_is_conflict(self):
        current = _node(U1, "Alex")
        tx = _ScriptedTx([
            ("RETURN n, labels(n)", [{"n": current, "labels": ["Entity", "Person"]}]),
            ("WHERE o.uuid <> $uuid", []),
        ])
        with pytest.raises(GraphEditConflict):
            self._update(tx, name="Bob", embedding=[0.5], embedding_text="Anderer Text (Person)")

    def test_unknown_entity_is_not_found(self):
        tx = _ScriptedTx([("RETURN n, labels(n)", [])])
        with pytest.raises(GraphEditNotFound):
            self._update(tx, summary="x")

    def test_aliases_are_replaced_and_empty_list_clears_them(self):
        current = _node(U1, "Alex", attributes_json=json.dumps({ALIASES_KEY: ["Al"], "x": 1}))
        tx = _ScriptedTx([
            ("RETURN n, labels(n)", [{"n": current, "labels": ["Entity", "Person"]}]),
            ("SET n.origin = CASE", []),
            ("RETURN n, labels(n)", [{"n": current, "labels": ["Entity", "Person"]}]),
        ])
        self._update(tx, aliases=[])
        attrs = json.loads(tx.calls[1][1]["attrs_json"])
        assert attrs == {"x": 1}


class TestUpdateRelation:
    def test_keeps_episode_ids_and_marks_edited(self):
        rel = {"uuid": U3, "graph_id": GID, "name": "A", "fact": "neu", "episode_ids": ["ep-1"],
               "origin": "edited", "origin_changed_at": NOW}
        tx = _ScriptedTx([
            ("RETURN r.uuid AS uuid", [{"uuid": U3}]),
            ("SET r.origin = CASE", [{"r": rel, "src_uuid": U1, "tgt_uuid": U2}]),
        ])
        edge = _Storage(tx).edit_update_relation(
            graph_id=GID, relation_uuid=U3, name=None, fact="neu", embedding=[0.9],
            property_key="fact_embedding", now=NOW,
        )
        set_query, params = tx.calls[1]
        assert "r.origin = CASE WHEN r.origin = 'manual' THEN 'manual' ELSE 'edited' END" in set_query
        assert "episode_ids" not in set_query  # bleiben unverändert erhalten
        assert "r.fact_embedding = $embedding" in set_query
        assert params["fact"] == "neu"
        assert edge["episode_ids"] == ["ep-1"]
        assert edge["provenance"] == {"origin": "edited", "changed_at": NOW, "episode_count": 1}

    def test_name_only_change_does_not_touch_embedding(self):
        rel = {"uuid": U3, "graph_id": GID, "name": "NEU", "fact": "f", "episode_ids": []}
        tx = _ScriptedTx([
            ("RETURN r.uuid AS uuid", [{"uuid": U3}]),
            ("SET r.origin = CASE", [{"r": rel, "src_uuid": U1, "tgt_uuid": U2}]),
        ])
        _Storage(tx).edit_update_relation(
            graph_id=GID, relation_uuid=U3, name="NEU", fact=None, embedding=None,
            property_key="fact_embedding", now=NOW,
        )
        assert "embedding" not in tx.calls[1][0]

    def test_unknown_relation_is_not_found(self):
        tx = _ScriptedTx([("RETURN r.uuid AS uuid", [])])
        with pytest.raises(GraphEditNotFound):
            _Storage(tx).edit_update_relation(
                graph_id=GID, relation_uuid=U3, name="x", fact=None, embedding=None,
                property_key="fact_embedding", now=NOW,
            )


# ── Löschen ──────────────────────────────────────────────────────────────


class TestDelete:
    def test_entity_delete_removes_relations_in_one_transaction(self):
        tx = _ScriptedTx([
            ("count(DISTINCT r)", [{"uuid": U1, "relations": 3}]),
            ("DETACH DELETE n", []),
        ])
        storage = _Storage(tx)
        assert storage.edit_delete_entity(GID, U1) == 3
        assert storage.session.write_calls == 1
        tx.done()

    def test_entity_delete_unknown_is_not_found(self):
        tx = _ScriptedTx([("count(DISTINCT r)", [])])
        with pytest.raises(GraphEditNotFound):
            _Storage(tx).edit_delete_entity(GID, U1)

    def test_relation_delete_is_hard_delete(self):
        tx = _ScriptedTx([("DELETE r RETURN count(r)", [{"hit": 1}])])
        _Storage(tx).edit_delete_relation(GID, U3)
        assert "valid_to_round" not in tx.calls[0][0]

    def test_relation_delete_unknown_is_not_found(self):
        tx = _ScriptedTx([("DELETE r RETURN count(r)", [{"hit": 0}])])
        with pytest.raises(GraphEditNotFound):
            _Storage(tx).edit_delete_relation(GID, U3)


# ── Zusammenführen ───────────────────────────────────────────────────────


def _edge_row(uuid_: str, src: str, tgt: str, name: str = "KENNT") -> Dict[str, Any]:
    return {"uuid": uuid_, "src": src, "tgt": tgt, "name": name}


class TestMerge:
    def _merge(self, tx):
        return _Storage(tx).edit_merge_entities(
            graph_id=GID, target_uuid=U1, source_uuids=[U2], now=NOW
        )

    def _nodes(self):
        target = _node(U1, "Stadtwerke", "Organization", attributes_json=json.dumps({ALIASES_KEY: ["SW"]}))
        source = _node(U2, "Stadtwerke AG", "Organization", attributes_json=json.dumps({ALIASES_KEY: ["SWAG"]}))
        return [
            {"n": target, "labels": ["Entity", "Organization"]},
            {"n": source, "labels": ["Entity", "Organization"]},
        ]

    def test_rewires_drops_self_loops_and_duplicates_and_collects_aliases(self):
        other = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa9"
        edges = [
            _edge_row("r-own", U1, other, "KENNT"),           # Kante des Ziels, bleibt
            _edge_row("r-dup", U2, other, "kennt"),           # Dublette zu r-own nach Umhängen
            _edge_row("r-loop", U1, U2, "TEILT"),             # Ziel -> Quelle: Selbstschleife
            _edge_row("r-new", other, U2, "BELIEFERT"),       # wird zu other -> Ziel
            _edge_row("r-out", U2, other, "FINANZIERT"),      # wird zu Ziel -> other
        ]
        merged_target = _node(U1, "Stadtwerke", "Organization", origin="edited", origin_changed_at=NOW)
        tx = _ScriptedTx([
            ("WHERE n.uuid IN $ids", self._nodes()),
            ("MATCH (a:Entity {graph_id: $gid})-[r:RELATION]->", edges),
            ("CREATE (s)-[new:RELATION]->(t)", []),
            ("CREATE (s)-[new:RELATION]->(t)", []),
            ("DETACH DELETE n", []),
            ("SET n.attributes_json = $attrs_json", []),
            ("RETURN n, labels(n)", [{"n": merged_target, "labels": ["Entity", "Organization"]}]),
        ])

        result = self._merge(tx)
        tx.done()

        rewires = [c for c in tx.calls if "CREATE (s)-[new:RELATION]->(t)" in c[0]]
        assert [(c[1]["ruuid"], c[1]["new_src"], c[1]["new_tgt"]) for c in rewires] == [
            ("r-new", other, U1),
            ("r-out", U1, other),
        ]
        assert all("new.origin_changed_at = $now" in c[0] for c in rewires)
        assert result["rewired"] == 2
        assert result["dropped"] == 2
        assert result["merged_source_uuids"] == [U2]

        update_query, update_params = tx.calls[5]
        assert "n.origin = CASE WHEN n.origin = 'manual'" in update_query
        attrs = json.loads(update_params["attrs_json"])
        assert attrs[ALIASES_KEY] == ["SW", "Stadtwerke AG", "SWAG"]
        assert result["node"]["provenance"]["origin"] == "edited"

        delete_params = tx.calls[4][1]
        assert delete_params["sources"] == [U2]

    def test_missing_source_is_not_found_before_any_write(self):
        tx = _ScriptedTx([("WHERE n.uuid IN $ids", self._nodes()[:1])])
        with pytest.raises(GraphEditNotFound):
            self._merge(tx)
        tx.done()

    def test_missing_target_is_not_found(self):
        tx = _ScriptedTx([("WHERE n.uuid IN $ids", self._nodes()[1:])])
        with pytest.raises(GraphEditNotFound):
            self._merge(tx)
