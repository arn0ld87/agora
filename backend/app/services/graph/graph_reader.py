"""
Storage-Reader functions for Graph Retrieval Tools (M11 Phase 5b PR 2).

Extracted from ``app.services.graph_tools.GraphToolsService`` — all 10
Basic-Tool methods that depend solely on ``GraphStorage`` (and optionally
``LLMClient``) are implemented here as module-level functions.

Backward-compat: ``GraphToolsService`` in ``graph_tools.py`` retains all
10 method names as thin delegation wrappers, so existing call-sites and
Monkeypatch-Stubs in tests continue to work unmodified.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.storage.graph_storage import GraphStorage
from app.services.graph.graph_dtos import EdgeInfo, NodeInfo, SearchResult

logger = logging.getLogger(__name__)


def _resolve_edge_provenance(
    edge_dicts: List[Dict[str, Any]],
    *,
    storage: GraphStorage,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Dokumentherkunft je Kante auflösen (Issue #1152).

    Sammelt die ``episode_ids`` aller übergebenen Kanten ein, holt deren
    Herkunft in *einem* Storage-Aufruf und ordnet sie den Kanten wieder zu.

    Eine Kante bekommt nur dann einen Anker, wenn ihre Episoden auf genau
    ein ``(document_id, chunk_id)``-Paar zeigen. Mehrdeutigkeit führt zu
    ``None`` statt zu einer geratenen Herkunft — Akzeptanzkriterium von
    #1152 und die Voraussetzung dafür, dass #1154 daraus einen
    verifizierten Anker nach ADR-0013 bauen darf.

    Fehler sind hier nie fatal: das Retrieval liefert dann Fakten ohne
    Herkunft, statt auszufallen.
    """
    lookup = getattr(storage, "get_episode_provenance", None)
    if lookup is None:
        return {}

    episode_ids: List[str] = []
    for edge in edge_dicts:
        episode_ids.extend(edge.get("episode_ids") or [])
    if not episode_ids:
        return {}

    try:
        provenance_by_episode = lookup(episode_ids)
    except Exception as exc:  # noqa: BLE001 — Provenance ist optional, Retrieval nicht
        logger.warning("Episode provenance lookup failed: %s", exc)
        return {}

    resolved: Dict[str, Optional[Dict[str, Any]]] = {}
    for edge in edge_dicts:
        edge_uuid = edge.get("uuid", "")
        if not edge_uuid:
            continue
        candidates: set[tuple[Any, Any]] = set()
        for episode_id in edge.get("episode_ids") or []:
            entry = provenance_by_episode.get(episode_id)
            if entry is not None:
                candidates.add((entry.get("document_id"), entry.get("chunk_id")))

        if len(candidates) != 1:
            resolved[edge_uuid] = None
            continue
        document_id, chunk_id = candidates.pop()
        resolved[edge_uuid] = {"document_id": document_id, "chunk_id": chunk_id}

    return resolved


def search_graph(
    graph_id: str,
    query: str,
    *,
    storage: GraphStorage,
    llm: Any,
    limit: int = 10,
    scope: str = "edges",
) -> SearchResult:
    """Graph semantic search (hybrid: vector + BM25 via Neo4j)."""
    logger.info("Graph search: graph_id=%s, query=%s...", graph_id, query[:50])

    try:
        search_results = storage.search(
            graph_id=graph_id,
            query=query,
            limit=limit,
            scope=scope,
        )

        facts: List[str] = []
        # Positionsparallel zu ``facts`` (Issue #1152) — jeder Fakt bekommt
        # genau einen Eintrag, auch wenn er keine Herkunft hat (``None``).
        fact_provenance: List[Optional[Dict[str, Any]]] = []
        edges: List[Dict[str, Any]] = []
        nodes: List[Dict[str, Any]] = []

        # Parse edge results
        if hasattr(search_results, "edges"):
            edge_list = search_results.edges
        elif isinstance(search_results, dict) and "edges" in search_results:
            edge_list = search_results["edges"]
        else:
            edge_list = []

        edge_dicts = [edge for edge in edge_list if isinstance(edge, dict)]
        provenance_by_edge = _resolve_edge_provenance(edge_dicts, storage=storage)

        for edge in edge_dicts:
            fact = edge.get("fact", "")
            provenance = provenance_by_edge.get(edge.get("uuid", ""))
            if fact:
                facts.append(fact)
                fact_provenance.append(provenance)
            projected = {
                "uuid": edge.get("uuid", ""),
                "name": edge.get("name", ""),
                "fact": fact,
                "source_node_uuid": edge.get("source_node_uuid", ""),
                "target_node_uuid": edge.get("target_node_uuid", ""),
            }
            if provenance is not None:
                projected.update(provenance)
            edges.append(projected)

        # Parse node results
        if hasattr(search_results, "nodes"):
            node_list = search_results.nodes
        elif isinstance(search_results, dict) and "nodes" in search_results:
            node_list = search_results["nodes"]
        else:
            node_list = []

        for node in node_list:
            if isinstance(node, dict):
                nodes.append({
                    "uuid": node.get("uuid", ""),
                    "name": node.get("name", ""),
                    "labels": node.get("labels", []),
                    "summary": node.get("summary", ""),
                })
                summary = node.get("summary", "")
                if summary:
                    facts.append(f"[{node.get('name', '')}]: {summary}")
                    # Entity-Summaries sind aggregiert und lassen sich keinem
                    # einzelnen Chunk zuordnen — kein Anker, kein Raten.
                    fact_provenance.append(None)

        logger.info("Search complete: Found %d related facts", len(facts))

        return SearchResult(
            facts=facts,
            edges=edges,
            nodes=nodes,
            query=query,
            total_count=len(facts),
            fact_provenance=fact_provenance,
        )

    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(
            "Graph search failed, degrading to local search: %s", str(exc)
        )
        return local_search(
            graph_id,
            query,
            storage=storage,
            limit=limit,
            scope=scope,
        )



def local_search(
    graph_id: str,
    query: str,
    *,
    storage: GraphStorage,
    limit: int = 10,
    scope: str = "edges",
) -> SearchResult:
    """Local keyword-matching search (fallback approach)."""
    logger.info("Using local search: query=%s...", query[:30])

    facts: List[str] = []
    fact_provenance: List[Optional[Dict[str, Any]]] = []
    edges_result: List[Dict[str, Any]] = []
    nodes_result: List[Dict[str, Any]] = []

    query_lower = query.lower()
    keywords = [
        w.strip()
        for w in query_lower.replace(",", " ").replace("，", " ").split()
        if len(w.strip()) > 1
    ]

    def match_score(text: str) -> int:
        if not text:
            return 0
        text_lower = text.lower()
        if query_lower in text_lower:
            return 100
        score = 0
        for keyword in keywords:
            if keyword in text_lower:
                score += 10
        return score

    try:
        if scope in ["edges", "both"]:
            all_edges = storage.get_all_edges(graph_id)
            scored_edges = []
            for edge in all_edges:
                score = match_score(edge.get("fact", "")) + match_score(
                    edge.get("name", "")
                )
                if score > 0:
                    scored_edges.append((score, edge))

            scored_edges.sort(key=lambda x: x[0], reverse=True)

            top_edges = [edge for _score, edge in scored_edges[:limit]]
            provenance_by_edge = _resolve_edge_provenance(top_edges, storage=storage)

            for edge in top_edges:
                fact = edge.get("fact", "")
                provenance = provenance_by_edge.get(edge.get("uuid", ""))
                if fact:
                    facts.append(fact)
                    fact_provenance.append(provenance)
                projected = {
                    "uuid": edge.get("uuid", ""),
                    "name": edge.get("name", ""),
                    "fact": fact,
                    "source_node_uuid": edge.get("source_node_uuid", ""),
                    "target_node_uuid": edge.get("target_node_uuid", ""),
                }
                if provenance is not None:
                    projected.update(provenance)
                edges_result.append(projected)

        if scope in ["nodes", "both"]:
            all_nodes = storage.get_all_nodes(graph_id)
            scored_nodes = []
            for node in all_nodes:
                score = match_score(node.get("name", "")) + match_score(
                    node.get("summary", "")
                )
                if score > 0:
                    scored_nodes.append((score, node))

            scored_nodes.sort(key=lambda x: x[0], reverse=True)

            for _score, node in scored_nodes[:limit]:
                nodes_result.append({
                    "uuid": node.get("uuid", ""),
                    "name": node.get("name", ""),
                    "labels": node.get("labels", []),
                    "summary": node.get("summary", ""),
                })
                summary = node.get("summary", "")
                if summary:
                    facts.append(f"[{node.get('name', '')}]: {summary}")
                    fact_provenance.append(None)

        logger.info("Local search complete: Found %d related facts", len(facts))

    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.error("Local search failed: %s", str(exc))

    return SearchResult(
        facts=facts,
        edges=edges_result,
        nodes=nodes_result,
        query=query,
        total_count=len(facts),
        fact_provenance=fact_provenance,
    )



def get_all_nodes(graph_id: str, *, storage: GraphStorage) -> List[NodeInfo]:
    """Get all nodes in the graph."""
    logger.info("Getting all nodes in graph %s...", graph_id)

    raw_nodes = storage.get_all_nodes(graph_id)

    result = [
        NodeInfo(
            uuid=node.get("uuid", ""),
            name=node.get("name", ""),
            labels=node.get("labels", []),
            summary=node.get("summary", ""),
            attributes=node.get("attributes", {}),
        )
        for node in raw_nodes
    ]

    logger.info("Retrieved %d nodes", len(result))
    return result



def get_all_edges(
    graph_id: str,
    *,
    storage: GraphStorage,
    include_temporal: bool = True,
) -> List[EdgeInfo]:
    """Get all edges in the graph (with temporal information)."""
    logger.info("Getting all edges in graph %s...", graph_id)

    raw_edges = storage.get_all_edges(graph_id)
    provenance_by_edge = _resolve_edge_provenance(raw_edges, storage=storage)

    result = []
    for edge in raw_edges:
        provenance = provenance_by_edge.get(edge.get("uuid", "")) or {}
        edge_info = EdgeInfo(
            uuid=edge.get("uuid", ""),
            name=edge.get("name", ""),
            fact=edge.get("fact", ""),
            source_node_uuid=edge.get("source_node_uuid", ""),
            target_node_uuid=edge.get("target_node_uuid", ""),
            document_id=provenance.get("document_id"),
            chunk_id=provenance.get("chunk_id"),
        )

        if include_temporal:
            edge_info.created_at = edge.get("created_at")
            edge_info.valid_at = edge.get("valid_at")
            edge_info.invalid_at = edge.get("invalid_at")
            edge_info.expired_at = edge.get("expired_at")

        result.append(edge_info)

    logger.info("Retrieved %d edges", len(result))
    return result



def get_node_detail(node_uuid: str, *, storage: GraphStorage) -> Optional[NodeInfo]:
    """Get detailed information about a single node."""
    logger.info("Getting node details: %s...", node_uuid[:8])

    try:
        node = storage.get_node(node_uuid)
        if not node:
            return None

        return NodeInfo(
            uuid=node.get("uuid", ""),
            name=node.get("name", ""),
            labels=node.get("labels", []),
            summary=node.get("summary", ""),
            attributes=node.get("attributes", {}),
        )
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.error("Failed to get node details: %s", str(exc))
        return None



def get_node_edges(
    graph_id: str,
    node_uuid: str,
    *,
    storage: GraphStorage,
) -> List[EdgeInfo]:
    """Get all edges related to a node.

    Optimised: uses storage.get_node_edges() (O(degree) Cypher)
    instead of loading ALL edges and filtering.
    """
    logger.info("Getting edges related to node %s...", node_uuid[:8])

    try:
        raw_edges = storage.get_node_edges(node_uuid)

        result = [
            EdgeInfo(
                uuid=edge.get("uuid", ""),
                name=edge.get("name", ""),
                fact=edge.get("fact", ""),
                source_node_uuid=edge.get("source_node_uuid", ""),
                target_node_uuid=edge.get("target_node_uuid", ""),
                created_at=edge.get("created_at"),
                valid_at=edge.get("valid_at"),
                invalid_at=edge.get("invalid_at"),
                expired_at=edge.get("expired_at"),
            )
            for edge in raw_edges
        ]

        logger.info("Found %d edges related to the node", len(result))
        return result

    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning("Failed to get node edges: %s", str(exc))
        return []



def get_entities_by_type(
    graph_id: str,
    entity_type: str,
    *,
    storage: GraphStorage,
) -> List[NodeInfo]:
    """Get entities by type."""
    logger.info("Getting entities of type %s...", entity_type)

    raw_nodes = storage.get_nodes_by_label(graph_id, entity_type)

    result = [
        NodeInfo(
            uuid=node.get("uuid", ""),
            name=node.get("name", ""),
            labels=node.get("labels", []),
            summary=node.get("summary", ""),
            attributes=node.get("attributes", {}),
        )
        for node in raw_nodes
    ]

    logger.info("Found %d entities of type %s", len(result), entity_type)
    return result



def get_entity_summary(
    graph_id: str,
    entity_name: str,
    *,
    storage: GraphStorage,
) -> Dict[str, Any]:
    """Get relationship summary for a specific entity."""
    logger.info("Getting relationship summary for entity %s...", entity_name)

    search_result = search_graph(
        graph_id,
        entity_name,
        storage=storage,
        llm=None,
        limit=20,
    )

    all_nodes = get_all_nodes(graph_id, storage=storage)
    entity_node: Optional[NodeInfo] = None
    for node in all_nodes:
        if node.name.lower() == entity_name.lower():
            entity_node = node
            break

    related_edges: List[EdgeInfo] = []
    if entity_node:
        related_edges = get_node_edges(graph_id, entity_node.uuid, storage=storage)

    return {
        "entity_name": entity_name,
        "entity_info": entity_node.to_dict() if entity_node else None,
        "related_facts": search_result.facts,
        "related_edges": [e.to_dict() for e in related_edges],
        "total_relations": len(related_edges),
    }



def get_graph_statistics(graph_id: str, *, storage: GraphStorage) -> Dict[str, Any]:
    """Get statistics for the graph."""
    logger.info("Getting statistics for graph %s...", graph_id)

    nodes = get_all_nodes(graph_id, storage=storage)
    edges = get_all_edges(graph_id, storage=storage)

    entity_types: Dict[str, int] = {}
    for node in nodes:
        for label in node.labels:
            if label not in ["Entity", "Node"]:
                entity_types[label] = entity_types.get(label, 0) + 1

    relation_types: Dict[str, int] = {}
    for edge in edges:
        relation_types[edge.name] = relation_types.get(edge.name, 0) + 1

    return {
        "graph_id": graph_id,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "entity_types": entity_types,
        "relation_types": relation_types,
    }



def get_simulation_context(
    graph_id: str,
    simulation_requirement: str,
    *,
    storage: GraphStorage,
    llm: Any = None,
    limit: int = 30,
) -> Dict[str, Any]:
    """Get simulation-related context information."""
    logger.info(
        "Getting simulation context: %s...", simulation_requirement[:50]
    )

    search_result = search_graph(
        graph_id,
        simulation_requirement,
        storage=storage,
        llm=llm,
        limit=limit,
    )

    stats = get_graph_statistics(graph_id, storage=storage)
    all_nodes = get_all_nodes(graph_id, storage=storage)

    entities = []
    for node in all_nodes:
        custom_labels = [la for la in node.labels if la not in ["Entity", "Node"]]
        if custom_labels:
            entities.append({
                "name": node.name,
                "type": custom_labels[0],
                "summary": node.summary,
            })

    return {
        "simulation_requirement": simulation_requirement,
        "related_facts": search_result.facts,
        "graph_statistics": stats,
        "entities": entities[:limit],
        "total_entities": len(entities),
    }
