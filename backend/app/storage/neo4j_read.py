"""
Read-Pfad für ``Neo4jStorage``.

Issue #50 (EPIC-08-ST-01), Sub-Slice 1/3: ``Neo4jReadMixin`` bündelt
alle reinen Lese-Methoden, die ``Neo4jStorage`` historisch enthielt.
Mixin-Pattern statt Komposition, damit ``self._driver`` und
``self._call_with_retry`` ohne Konstruktor-Refactoring shared bleiben.

Bekannte Mixin-Voraussetzungen (vom konkreten Storage zu liefern):

- ``self._driver`` — ein Neo4j-Driver mit ``.session()``
- ``self._call_with_retry(callable, *args, **kwargs)`` — Retry-Wrapper

Statelose Helfer (``node_to_dict``, ``edge_to_dict``, ``sanitize_label``)
werden direkt aus ``neo4j_mappings`` importiert; das Mixin selbst hat
keine ``self``-gebundenen Mapping-Methoden mehr.
"""

import json
from typing import Any, Dict, List, Optional

from .neo4j_mappings import edge_to_dict, node_to_dict, sanitize_label


class Neo4jReadMixin:
    """Read-Pfad für ``Neo4jStorage``. Siehe Modul-Docstring."""

    def get_ontology(self, graph_id: str) -> Dict[str, Any]:
        def _read(tx):
            result = tx.run(
                "MATCH (g:Graph {graph_id: $gid}) RETURN g.ontology_json AS oj",
                gid=graph_id,
            )
            record = result.single()
            if record and record["oj"]:
                return json.loads(record["oj"])
            return {}

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_all_nodes(self, graph_id: str, limit: int = 2000) -> List[Dict[str, Any]]:
        def _read(tx):
            result = tx.run(
                """
                MATCH (n:Entity {graph_id: $gid})
                RETURN n, labels(n) AS labels
                ORDER BY n.created_at DESC
                LIMIT $limit
                """,
                gid=graph_id,
                limit=limit,
            )
            return [node_to_dict(record["n"], record["labels"]) for record in result]

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_node(self, uuid: str) -> Optional[Dict[str, Any]]:
        def _read(tx):
            result = tx.run(
                "MATCH (n:Entity {uuid: $uuid}) RETURN n, labels(n) AS labels",
                uuid=uuid,
            )
            record = result.single()
            if record:
                return node_to_dict(record["n"], record["labels"])
            return None

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """O(1) Cypher — NOT full scan + filter like the old Zep code."""
        def _read(tx):
            result = tx.run(
                """
                MATCH (n:Entity {uuid: $uuid})-[r:RELATION]-(m:Entity)
                RETURN r, startNode(r).uuid AS src_uuid, endNode(r).uuid AS tgt_uuid
                """,
                uuid=node_uuid,
            )
            return [
                edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])
                for record in result
            ]

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_nodes_by_label(self, graph_id: str, label: str) -> List[Dict[str, Any]]:
        # Sanitize label to prevent Cypher injection
        safe_label = sanitize_label(label)

        if not safe_label:
            return []

        def _read(tx):
            # Dynamic label in query (now sanitized)
            query = f"""
                MATCH (n:Entity:`{safe_label}` {{graph_id: $gid}})
                RETURN n, labels(n) AS labels
            """
            result = tx.run(query, gid=graph_id)
            return [node_to_dict(record["n"], record["labels"]) for record in result]

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_filtered_entities_with_edges(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> Dict[str, Any]:
        # Normalise the type whitelist: empty list → no filter (consistent with
        # the old in-memory version, which treated ``None`` and ``[]`` the same).
        types_param: Optional[List[str]] = (
            list(defined_entity_types) if defined_entity_types else None
        )

        def _read(tx):
            # Baseline count: every Entity node, including ones that only carry
            # the default label. Needed for the ``total_count`` accounting that
            # callers expose as filter ratio.
            total_result = tx.run(
                "MATCH (n:Entity {graph_id: $gid}) RETURN count(n) AS cnt",
                gid=graph_id,
            )
            total_count = total_result.single()["cnt"]

            if enrich_with_edges:
                query = """
                    MATCH (n:Entity {graph_id: $gid})
                    WITH n, [l IN labels(n) WHERE l <> 'Entity' AND l <> 'Node']
                             AS custom_labels
                    WHERE size(custom_labels) > 0
                      AND ($types IS NULL
                           OR any(l IN custom_labels WHERE l IN $types))
                    OPTIONAL MATCH (n)-[r:RELATION {graph_id: $gid}]-(m:Entity)
                    WITH n, labels(n) AS node_labels,
                         collect(DISTINCT CASE WHEN r IS NOT NULL THEN {
                             edge_name: coalesce(r.name, ''),
                             fact: coalesce(r.fact, ''),
                             source_node_uuid: startNode(r).uuid,
                             target_node_uuid: endNode(r).uuid
                         } END) AS raw_edges,
                         collect(DISTINCT CASE WHEN m IS NOT NULL THEN {
                             uuid: m.uuid,
                             name: coalesce(m.name, ''),
                             labels: [l IN labels(m) WHERE l <> 'Entity'],
                             summary: coalesce(m.summary, '')
                         } END) AS raw_related
                    RETURN n, node_labels, raw_edges, raw_related
                """
                records = tx.run(query, gid=graph_id, types=types_param)
                return total_count, [
                    (
                        record["n"],
                        record["node_labels"],
                        list(record["raw_edges"] or []),
                        list(record["raw_related"] or []),
                    )
                    for record in records
                ]

            query = """
                MATCH (n:Entity {graph_id: $gid})
                WITH n, [l IN labels(n) WHERE l <> 'Entity' AND l <> 'Node']
                         AS custom_labels
                WHERE size(custom_labels) > 0
                  AND ($types IS NULL
                       OR any(l IN custom_labels WHERE l IN $types))
                RETURN n, labels(n) AS node_labels
            """
            records = tx.run(query, gid=graph_id, types=types_param)
            return total_count, [
                (record["n"], record["node_labels"], [], [])
                for record in records
            ]

        with self._get_session() as session:
            total_count, rows = self._call_with_retry(session.execute_read, _read)

        entities: List[Dict[str, Any]] = []
        for node, node_labels, raw_edges, raw_related in rows:
            node_dict = node_to_dict(node, node_labels)
            entity_uuid = node_dict["uuid"]

            related_edges: List[Dict[str, Any]] = []
            for edge in raw_edges:
                # ``collect(DISTINCT CASE ... END)`` drops NULL entries in
                # Cypher but can still yield empty maps on some driver
                # versions — defensive check.
                if not edge:
                    continue
                source_uuid = edge.get("source_node_uuid")
                target_uuid = edge.get("target_node_uuid")
                if source_uuid == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge.get("edge_name", ""),
                        "fact": edge.get("fact", ""),
                        "target_node_uuid": target_uuid,
                    })
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge.get("edge_name", ""),
                        "fact": edge.get("fact", ""),
                        "source_node_uuid": source_uuid,
                    })

            related_nodes: List[Dict[str, Any]] = []
            seen_related: set = set()
            for rel in raw_related:
                if not rel:
                    continue
                rel_uuid = rel.get("uuid")
                if not rel_uuid or rel_uuid in seen_related:
                    continue
                seen_related.add(rel_uuid)
                related_nodes.append({
                    "uuid": rel_uuid,
                    "name": rel.get("name", ""),
                    "labels": list(rel.get("labels") or []),
                    "summary": rel.get("summary", ""),
                })

            node_dict["related_edges"] = related_edges
            node_dict["related_nodes"] = related_nodes
            entities.append(node_dict)

        return {
            "entities": entities,
            "total_count": total_count,
        }

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        def _read(tx):
            result = tx.run(
                """
                MATCH (src:Entity)-[r:RELATION {graph_id: $gid}]->(tgt:Entity)
                RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid
                ORDER BY r.created_at DESC
                """,
                gid=graph_id,
            )
            return [
                edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])
                for record in result
            ]

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_episode_provenance(
        self, episode_ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Dokument-/Chunk-Herkunft der genannten Episoden (Issue #1152).

        Ein einziger ``UNWIND``-Lookup für alle Episoden einer Suche statt
        eines Joins im Vektor-/Fulltext-Cypher: der Suchpfad bleibt
        unverändert, und Treffer ohne Dokumentbezug kosten nichts.

        Episoden ohne ``document_id`` fehlen im Ergebnis — Altgraphen vor
        ADR-0013 liefern damit eine leere Map (ADR-0013 Punkt 3).
        """
        unique_ids = [eid for eid in dict.fromkeys(episode_ids) if eid]
        if not unique_ids:
            return {}

        def _read(tx):
            result = tx.run(
                """
                UNWIND $ids AS episode_id
                MATCH (e:Episode {uuid: episode_id})
                WHERE e.document_id IS NOT NULL
                RETURN e.uuid AS uuid,
                       e.document_id AS document_id,
                       e.chunk_id AS chunk_id
                """,
                ids=unique_ids,
            )
            return {
                record["uuid"]: {
                    "document_id": record["document_id"],
                    "chunk_id": record["chunk_id"],
                }
                for record in result
            }

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_edges_at_round(
        self, graph_id: str, round_num: int
    ) -> List[Dict[str, Any]]:
        """Return edges that were valid at the given OASIS round.

        An edge is "valid" at round R if:
          (valid_from_round IS NULL OR valid_from_round <= R)
          AND (valid_to_round IS NULL OR valid_to_round > R)

        Missing ``valid_from_round`` is treated as 0 (present since ingest).
        Missing ``valid_to_round`` is treated as open-ended.
        """

        def _read(tx):
            result = tx.run(
                """
                MATCH (src:Entity)-[r:RELATION {graph_id: $gid}]->(tgt:Entity)
                WHERE coalesce(r.valid_from_round, 0) <= $round
                  AND (r.valid_to_round IS NULL OR r.valid_to_round > $round)
                RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid
                ORDER BY r.created_at DESC
                """,
                gid=graph_id,
                round=round_num,
            )
            return [
                edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])
                for record in result
            ]

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_graph_info(self, graph_id: str) -> Dict[str, Any]:
        def _read(tx):
            # Count nodes
            node_result = tx.run(
                "MATCH (n:Entity {graph_id: $gid}) RETURN count(n) AS cnt",
                gid=graph_id,
            )
            node_count = node_result.single()["cnt"]

            # Count edges
            edge_result = tx.run(
                "MATCH ()-[r:RELATION {graph_id: $gid}]->() RETURN count(r) AS cnt",
                gid=graph_id,
            )
            edge_count = edge_result.single()["cnt"]

            # Distinct entity types
            label_result = tx.run(
                """
                MATCH (n:Entity {graph_id: $gid})
                UNWIND labels(n) AS lbl
                WITH lbl WHERE lbl <> 'Entity'
                RETURN DISTINCT lbl
                """,
                gid=graph_id,
            )
            entity_types = [record["lbl"] for record in label_result]

            return {
                "graph_id": graph_id,
                "node_count": node_count,
                "edge_count": edge_count,
                "entity_types": entity_types,
            }

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        Full graph dump with enriched edge format (for frontend).
        Includes derived fields: fact_type, source_node_name, target_node_name.
        """
        def _read(tx):
            # Get all nodes
            node_result = tx.run(
                """
                MATCH (n:Entity {graph_id: $gid})
                RETURN n, labels(n) AS labels
                """,
                gid=graph_id,
            )
            nodes = []
            for record in node_result:
                nd = node_to_dict(record["n"], record["labels"])
                nodes.append(nd)

            # Get all edges with source/target node names (JOIN)
            edge_result = tx.run(
                """
                MATCH (src:Entity)-[r:RELATION {graph_id: $gid}]->(tgt:Entity)
                RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid,
                       src.name AS src_name, tgt.name AS tgt_name
                """,
                gid=graph_id,
            )
            edges = []
            for record in edge_result:
                ed = edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])
                # Enriched fields for frontend
                ed["fact_type"] = ed["name"]
                ed["source_node_name"] = record["src_name"] or ""
                ed["target_node_name"] = record["tgt_name"] or ""
                # Legacy alias
                ed["episodes"] = ed.get("episode_ids", [])
                edges.append(ed)

            return {
                "graph_id": graph_id,
                "nodes": nodes,
                "edges": edges,
                "node_count": len(nodes),
                "edge_count": len(edges),
            }

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)


__all__ = ["Neo4jReadMixin"]
