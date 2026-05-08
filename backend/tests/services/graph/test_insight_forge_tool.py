"""Smoke-tests for app.services.graph.insight_forge_tool (M11 Phase 5b PR 3).

Each test exercises one module-level function in isolation.
GraphStorage and LLMClient are replaced by MagicMock with spec so that only
real interface methods can be called.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.graph.graph_dtos import (
    InsightForgeResult,
    PanoramaResult,
    SearchResult,
)
from app.services.graph.insight_forge_tool import (
    generate_sub_queries,
    insight_forge,
    panorama_search,
    quick_search,
)
from app.storage.graph_storage import GraphStorage
from app.utils.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_storage() -> MagicMock:
    """Return a MagicMock bound to the real GraphStorage interface."""
    return MagicMock(spec=GraphStorage)


def _make_llm() -> MagicMock:
    """Return a MagicMock bound to the real LLMClient interface."""
    return MagicMock(spec=LLMClient)


def _empty_search_result(query: str = "q") -> SearchResult:
    return SearchResult(facts=[], edges=[], nodes=[], query=query, total_count=0)


# ---------------------------------------------------------------------------
# Test: generate_sub_queries
# ---------------------------------------------------------------------------


class TestGenerateSubQueries:
    def test_calls_llm_and_parses_sub_queries(self) -> None:
        """LLM returns a valid JSON response; parsed sub-queries are forwarded."""
        llm = _make_llm()
        llm.chat_json.return_value = {
            "sub_queries": [
                "Who are the main actors?",
                "What caused the event?",
                "When did it start?",
            ]
        }

        result = generate_sub_queries(
            "What happened in the simulation?",
            "A DACH market scenario",
            llm=llm,
            max_queries=5,
        )

        llm.chat_json.assert_called_once()
        assert len(result) == 3
        assert result[0] == "Who are the main actors?"

    def test_respects_max_queries_cap(self) -> None:
        """Only the first max_queries entries are returned."""
        llm = _make_llm()
        llm.chat_json.return_value = {
            "sub_queries": ["q1", "q2", "q3", "q4", "q5", "q6"]
        }

        result = generate_sub_queries("base query", "sim req", llm=llm, max_queries=3)

        assert len(result) == 3

    def test_falls_back_on_llm_failure(self) -> None:
        """When the LLM call raises, a default list is returned without raising."""
        llm = _make_llm()
        llm.chat_json.side_effect = RuntimeError("LLM unavailable")

        result = generate_sub_queries("my question", "sim req", llm=llm, max_queries=4)

        assert isinstance(result, list)
        assert len(result) >= 1
        # The original query is always first in the fallback list
        assert result[0] == "my question"


# ---------------------------------------------------------------------------
# Test: insight_forge (multi-step pipeline)
# ---------------------------------------------------------------------------


class TestInsightForge:
    def test_aggregates_search_results_from_sub_queries(self) -> None:
        """insight_forge must call search_graph for each sub-query and aggregate facts."""
        storage = _make_storage()
        llm = _make_llm()

        # LLM generates 2 sub-questions
        llm.chat_json.return_value = {"sub_queries": ["sub-q-1", "sub-q-2"]}

        # Storage returns edges with distinct facts per search call
        def _search_side_effect(graph_id, query, limit=10, scope="edges"):
            if "sub-q-1" in query:
                return MagicMock(
                    edges=[{"source_node_uuid": "u1", "target_node_uuid": "u2", "name": "REL", "fact": "fact-A"}],
                    facts=["fact-A"],
                    nodes=[],
                )
            if "sub-q-2" in query:
                return MagicMock(
                    edges=[{"source_node_uuid": "u3", "target_node_uuid": "u4", "name": "REL2", "fact": "fact-B"}],
                    facts=["fact-B"],
                    nodes=[],
                )
            # main query search
            return MagicMock(edges=[], facts=[], nodes=[])

        storage.search.side_effect = _search_side_effect
        # get_node returns None for all UUIDs (entity enrichment step)
        storage.get_node.return_value = None

        result = insight_forge(
            "graph-1",
            "What is happening?",
            "DACH scenario",
            storage=storage,
            llm=llm,
        )

        assert isinstance(result, InsightForgeResult)
        assert result.query == "What is happening?"
        assert result.total_facts >= 2
        assert "fact-A" in result.semantic_facts
        assert "fact-B" in result.semantic_facts

    def test_returns_empty_result_on_empty_graph(self) -> None:
        """insight_forge must succeed (no exception) when the graph is empty."""
        storage = _make_storage()
        llm = _make_llm()

        llm.chat_json.return_value = {"sub_queries": ["sub-q-1"]}
        storage.search.return_value = MagicMock(edges=[], facts=[], nodes=[])

        result = insight_forge(
            "empty-graph",
            "Any question",
            "Any requirement",
            storage=storage,
            llm=llm,
        )

        assert isinstance(result, InsightForgeResult)
        assert result.total_facts == 0
        assert result.total_entities == 0


# ---------------------------------------------------------------------------
# Test: panorama_search
# ---------------------------------------------------------------------------


class TestPanoramaSearch:
    def test_returns_active_and_historical_facts(self) -> None:
        """panorama_search must split edges into active vs. historical facts."""
        storage = _make_storage()
        llm = _make_llm()

        storage.get_all_nodes.return_value = []
        storage.get_all_edges.return_value = [
            {
                "uuid": "e1",
                "name": "KNOWS",
                "fact": "Alice knows Bob",
                "source_node_uuid": "n1",
                "target_node_uuid": "n2",
                "valid_at": None,
                "invalid_at": None,
                "expired_at": None,
                "created_at": None,
            },
            {
                "uuid": "e2",
                "name": "WORKED_AT",
                "fact": "Alice worked at ACME",
                "source_node_uuid": "n1",
                "target_node_uuid": "n3",
                "valid_at": "2020-01-01",
                "invalid_at": "2022-01-01",
                "expired_at": None,
                "created_at": None,
            },
        ]

        result = panorama_search(
            "graph-1", "Alice", storage=storage, llm=llm, include_expired=True
        )

        assert isinstance(result, PanoramaResult)
        assert result.active_count >= 1
        # The edge with invalid_at set is treated as historical
        assert result.historical_count >= 1

    def test_handles_empty_clusters(self) -> None:
        """panorama_search must handle an empty graph without raising."""
        storage = _make_storage()
        storage.get_all_nodes.return_value = []
        storage.get_all_edges.return_value = []

        result = panorama_search(
            "empty-graph", "anything", storage=storage, include_expired=True
        )

        assert isinstance(result, PanoramaResult)
        assert result.total_nodes == 0
        assert result.total_edges == 0
        assert result.active_count == 0
        assert result.historical_count == 0

    def test_exclude_expired_omits_historical_facts(self) -> None:
        """When include_expired=False, historical_facts must be empty."""
        storage = _make_storage()
        storage.get_all_nodes.return_value = []
        storage.get_all_edges.return_value = [
            {
                "uuid": "e1",
                "name": "OLD_REL",
                "fact": "old fact",
                "source_node_uuid": "n1",
                "target_node_uuid": "n2",
                "valid_at": "2019-01-01",
                "invalid_at": "2020-06-01",
                "expired_at": None,
                "created_at": None,
            }
        ]

        result = panorama_search(
            "graph-1", "q", storage=storage, include_expired=False
        )

        assert result.historical_facts == []


# ---------------------------------------------------------------------------
# Test: quick_search
# ---------------------------------------------------------------------------


class TestQuickSearch:
    def test_delegates_to_search_graph_and_returns_search_result(self) -> None:
        """quick_search must call storage.search and return a SearchResult."""
        storage = _make_storage()
        llm = _make_llm()

        storage.search.return_value = MagicMock(
            edges=[{"uuid": "e1", "name": "R", "fact": "found fact", "source_node_uuid": "s", "target_node_uuid": "t"}],
            facts=["found fact"],
            nodes=[],
        )

        result = quick_search("graph-1", "my query", storage=storage, llm=llm, limit=5)

        assert isinstance(result, SearchResult)
        assert "found fact" in result.facts
