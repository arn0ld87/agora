"""
LLM-backed Retrieval Pipeline for Graph Tools (M11 Phase 5b PR 3).

Extracted from ``app.services.graph_tools.GraphToolsService`` -- the four
Core-Retrieval methods that depend on both ``GraphStorage`` AND ``LLMClient``
are implemented here as module-level functions.

Backward-compat: ``GraphToolsService`` in ``graph_tools.py`` retains all four
method names as thin delegation wrappers, so existing call-sites and
MagicMock-Stubs in tests continue to work unmodified.

Extracted symbols
-----------------
- ``insight_forge``       (formerly ``GraphToolsService.insight_forge``)
- ``generate_sub_queries`` (formerly ``GraphToolsService._generate_sub_queries``)
- ``panorama_search``     (formerly ``GraphToolsService.panorama_search``)
- ``quick_search``        (formerly ``GraphToolsService.quick_search``)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.storage.graph_storage import GraphStorage
from app.utils.llm_client import LLMClient
from app.services.graph.graph_dtos import (
    InsightForgeResult,
    NodeInfo,
    PanoramaResult,
    SearchResult,
)
import app.services.graph.graph_reader as _reader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# generate_sub_queries
# ---------------------------------------------------------------------------


def generate_sub_queries(
    query: str,
    simulation_requirement: str,
    *,
    llm: LLMClient,
    report_context: str = "",
    max_queries: int = 5,
) -> List[str]:
    """Use LLM to decompose a complex query into focused sub-questions.

    Parameters
    ----------
    query:
        The original question to decompose.
    simulation_requirement:
        Background context about the simulation scenario.
    llm:
        LLMClient instance used for the decomposition call.
    report_context:
        Optional excerpt from the ongoing report (used as extra context).
    max_queries:
        Maximum number of sub-questions to return.

    Returns
    -------
    List[str]
        Up to ``max_queries`` sub-questions; falls back to a minimal default
        list if the LLM call fails.
    """
    system_prompt = (
        "You are a professional question analysis expert. Your task is to decompose"
        " a complex question into multiple sub-questions that can be independently"
        " observed in a simulated world.\n\n"
        "Requirements:\n"
        "1. Each sub-question should be specific enough to find related Agent behavior"
        " or events in the simulated world\n"
        "2. Sub-questions should cover different dimensions of the original question"
        " (e.g., who, what, why, how, when, where)\n"
        "3. Sub-questions should be relevant to the simulation scenario\n"
        '4. Return in JSON format: {"sub_queries": ["sub-question 1", "sub-question 2", ...]}'
    )

    user_prompt = (
        f"Simulation requirement background:\n{simulation_requirement}\n\n"
        + (f"Report context: {report_context[:500]}\n\n" if report_context else "")
        + f"Please decompose the following question into {max_queries} sub-questions:\n"
        + f"{query}\n\nReturn the sub-questions as a JSON list."
    )

    try:
        response = llm.chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        sub_queries = response.get("sub_queries", [])
        return [str(sq) for sq in sub_queries[:max_queries]]

    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        # Issue #978: Budgetabbruch (#764) ist kein Generierungsfehler — hart
        # durchreichen, sonst läuft insight_forge mit Default-Sub-Fragen
        # weiter statt den Run mit termination_reason=budget_* zu beenden.
        from ..run_budget import BudgetExceededError

        if isinstance(exc, BudgetExceededError):
            raise
        logger.warning(
            "Failed to generate sub-questions: %s, using default sub-questions", str(exc)
        )
        return [
            query,
            f"Main participants in {query}",
            f"Causes and impacts of {query}",
            f"Development process of {query}",
        ][:max_queries]


# ---------------------------------------------------------------------------
# insight_forge
# ---------------------------------------------------------------------------


def insight_forge(
    graph_id: str,
    query: str,
    simulation_requirement: str,
    *,
    storage: GraphStorage,
    llm: LLMClient,
    report_context: str = "",
    max_sub_queries: int = 5,
) -> InsightForgeResult:
    """Deep Insight Retrieval (InsightForge).

    The most powerful hybrid retrieval function -- automatically decomposes
    the problem and performs multi-dimensional retrieval:

    1. Use LLM to decompose the problem into multiple sub-questions.
    2. Perform semantic search on each sub-question.
    3. Extract related entities and get their detailed information.
    4. Trace relationship chains.
    5. Integrate all results and generate deep insights.

    Parameters
    ----------
    graph_id:
        Identifier of the graph to query.
    query:
        The main retrieval question.
    simulation_requirement:
        Background scenario context.
    storage:
        GraphStorage instance (injected by the caller).
    llm:
        LLMClient instance (injected by the caller).
    report_context:
        Optional excerpt from the ongoing report.
    max_sub_queries:
        Maximum number of sub-questions to generate.
    """
    logger.info("InsightForge deep insight retrieval: %s...", query[:50])

    result = InsightForgeResult(
        query=query,
        simulation_requirement=simulation_requirement,
        sub_queries=[],
    )

    # Step 1: Use LLM to generate sub-questions
    sub_queries = generate_sub_queries(
        query=query,
        simulation_requirement=simulation_requirement,
        llm=llm,
        report_context=report_context,
        max_queries=max_sub_queries,
    )
    result.sub_queries = sub_queries
    logger.info("Generated %d sub-questions", len(sub_queries))

    # Step 2: Perform semantic search on each sub-question
    all_facts: List[str] = []
    all_edges: List[Dict[str, Any]] = []
    seen_facts: set[str] = set()

    for sub_query in sub_queries:
        search_result = _reader.search_graph(
            graph_id,
            sub_query,
            storage=storage,
            llm=llm,
            limit=15,
            scope="edges",
        )
        for fact in search_result.facts:
            if fact not in seen_facts:
                all_facts.append(fact)
                seen_facts.add(fact)
        all_edges.extend(search_result.edges)

    # Also search for the original question
    main_search = _reader.search_graph(
        graph_id,
        query,
        storage=storage,
        llm=llm,
        limit=20,
        scope="edges",
    )
    for fact in main_search.facts:
        if fact not in seen_facts:
            all_facts.append(fact)
            seen_facts.add(fact)

    result.semantic_facts = all_facts
    result.total_facts = len(all_facts)

    # Step 3: Extract related entity UUIDs from edges
    entity_uuids: set[str] = set()
    for edge_data in all_edges:
        if isinstance(edge_data, dict):
            source_uuid = edge_data.get("source_node_uuid", "")
            target_uuid = edge_data.get("target_node_uuid", "")
            if source_uuid:
                entity_uuids.add(source_uuid)
            if target_uuid:
                entity_uuids.add(target_uuid)

    # Get related entity details
    entity_insights: List[Dict[str, Any]] = []
    node_map: Dict[str, NodeInfo] = {}

    for uuid in list(entity_uuids):
        if not uuid:
            continue
        try:
            node = _reader.get_node_detail(uuid, storage=storage)
            if node:
                node_map[uuid] = node
                entity_type = next(
                    (la for la in node.labels if la not in ["Entity", "Node"]),
                    "Entity",
                )
                related_facts = [
                    f for f in all_facts if node.name.lower() in f.lower()
                ]
                entity_insights.append(
                    {
                        "uuid": node.uuid,
                        "name": node.name,
                        "type": entity_type,
                        "summary": node.summary,
                        "related_facts": related_facts,
                    }
                )
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.debug("Failed to get node %s: %s", uuid, exc)
            continue

    result.entity_insights = entity_insights
    result.total_entities = len(entity_insights)

    # Step 4: Build relationship chains
    relationship_chains: List[str] = []
    for edge_data in all_edges:
        if isinstance(edge_data, dict):
            source_uuid = edge_data.get("source_node_uuid", "")
            target_uuid = edge_data.get("target_node_uuid", "")
            relation_name = edge_data.get("name", "")

            source_name = (
                node_map.get(source_uuid, NodeInfo("", "", [], "", {})).name
                or source_uuid[:8]
            )
            target_name = (
                node_map.get(target_uuid, NodeInfo("", "", [], "", {})).name
                or target_uuid[:8]
            )

            chain = f"{source_name} --[{relation_name}]--> {target_name}"
            if chain not in relationship_chains:
                relationship_chains.append(chain)

    result.relationship_chains = relationship_chains
    result.total_relationships = len(relationship_chains)

    logger.info(
        "InsightForge complete: %d facts, %d entities, %d relationships",
        result.total_facts,
        result.total_entities,
        result.total_relationships,
    )
    return result


# ---------------------------------------------------------------------------
# panorama_search
# ---------------------------------------------------------------------------


def panorama_search(
    graph_id: str,
    query: str,
    *,
    storage: GraphStorage,
    llm: Optional[LLMClient] = None,
    include_expired: bool = True,
    limit: int = 50,
) -> PanoramaResult:
    """Breadth Search (PanoramaSearch).

    Retrieves a comprehensive panoramic view including all related content
    and historical / expired information.

    Parameters
    ----------
    graph_id:
        Identifier of the graph to query.
    query:
        The search query string.
    storage:
        GraphStorage instance (injected by the caller).
    llm:
        Optional LLMClient; accepted for interface uniformity but not used
        in the current implementation.
    include_expired:
        When ``True`` (default) also include historical / expired facts.
    limit:
        Maximum number of active and historical facts to return each.
    """
    logger.info("PanoramaSearch breadth search: %s...", query[:50])

    result = PanoramaResult(query=query)

    # Get all nodes
    all_nodes = _reader.get_all_nodes(graph_id, storage=storage)
    result.all_nodes = all_nodes
    result.total_nodes = len(all_nodes)

    # Get all edges (including temporal information)
    all_edges = _reader.get_all_edges(graph_id, storage=storage, include_temporal=True)
    result.all_edges = all_edges
    result.total_edges = len(all_edges)

    # Categorize facts
    active_facts: List[str] = []
    historical_facts: List[str] = []

    for edge in all_edges:
        if not edge.fact:
            continue

        is_historical = edge.is_expired or edge.is_invalid

        if is_historical:
            valid_at = edge.valid_at or "Unknown"
            invalid_at = edge.invalid_at or edge.expired_at or "Unknown"
            fact_with_time = f"[{valid_at} - {invalid_at}] {edge.fact}"
            historical_facts.append(fact_with_time)
        else:
            active_facts.append(edge.fact)

    # Sort by relevance based on query
    query_lower = query.lower()
    keywords = [
        w.strip()
        for w in query_lower.replace(",", " ").replace("，", " ").split()
        if len(w.strip()) > 1
    ]

    def relevance_score(fact: str) -> int:
        fact_lower = fact.lower()
        score = 0
        if query_lower in fact_lower:
            score += 100
        for kw in keywords:
            if kw in fact_lower:
                score += 10
        return score

    active_facts.sort(key=relevance_score, reverse=True)
    historical_facts.sort(key=relevance_score, reverse=True)

    result.active_facts = active_facts[:limit]
    result.historical_facts = historical_facts[:limit] if include_expired else []
    result.active_count = len(active_facts)
    result.historical_count = len(historical_facts)

    logger.info(
        "PanoramaSearch complete: %d valid, %d historical",
        result.active_count,
        result.historical_count,
    )
    return result


# ---------------------------------------------------------------------------
# quick_search
# ---------------------------------------------------------------------------


def quick_search(
    graph_id: str,
    query: str,
    *,
    storage: GraphStorage,
    llm: Optional[LLMClient] = None,
    limit: int = 10,
) -> SearchResult:
    """QuickSearch -- Simple / fast retrieval.

    Thin wrapper around :func:`app.services.graph.graph_reader.search_graph`
    that belongs to the Core Retrieval Tools group (same pipeline tier as
    InsightForge and PanoramaSearch).

    Parameters
    ----------
    graph_id:
        Identifier of the graph to query.
    query:
        The search query string.
    storage:
        GraphStorage instance (injected by the caller).
    llm:
        Optional LLMClient; forwarded to the underlying search call for
        vector-embedding lookups.
    limit:
        Maximum number of results to return.
    """
    logger.info("QuickSearch simple search: %s...", query[:50])

    result = _reader.search_graph(
        graph_id,
        query,
        storage=storage,
        llm=llm,
        limit=limit,
        scope="edges",
    )

    logger.info("QuickSearch complete: %d results", result.total_count)
    return result
