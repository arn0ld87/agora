"""
GraphStorage — abstract interface for graph storage backends.

All Zep Cloud calls are replaced by this abstraction.
Current implementation: Neo4jStorage (neo4j_storage.py).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable


class GraphStorage(ABC):
    """Abstract interface for graph storage backends."""

    # --- Graph lifecycle ---

    @abstractmethod
    def create_graph(self, name: str, description: str = "") -> str:
        """Create a new graph. Returns graph_id."""

    @abstractmethod
    def delete_graph(self, graph_id: str) -> None:
        """Delete a graph and all its nodes/edges."""

    @abstractmethod
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        """Store ontology (entity types + relation types) for a graph."""

    @abstractmethod
    def get_ontology(self, graph_id: str) -> Dict[str, Any]:
        """Retrieve stored ontology for a graph."""

    # --- Add data ---

    @abstractmethod
    def add_text(self, graph_id: str, text: str, round_num: Optional[int] = None) -> str:
        """
        Process text: NER/RE → create nodes/edges → return episode_id.
        This is synchronous (unlike Zep Cloud's async episodes).

        Issue #10: ``round_num`` stamps newly created RELATION edges with
        ``valid_from_round``. Pass ``0`` for the initial document ingest
        and the current OASIS round for live simulation updates; leave
        ``None`` for legacy callers where temporal tracking is not needed.
        """

    @abstractmethod
    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None,
        round_num: Optional[int] = None,
    ) -> List[str]:
        """Batch-add text chunks. Returns list of episode_ids."""

    @abstractmethod
    def wait_for_processing(
        self,
        episode_ids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600,
    ) -> None:
        """
        Wait for episodes to be processed.
        For Neo4j: no-op (synchronous processing).
        Kept for API compatibility with Zep-era callers.
        """

    # --- Read nodes ---

    @abstractmethod
    def get_all_nodes(self, graph_id: str, limit: int = 2000) -> List[Dict[str, Any]]:
        """Get all nodes in a graph (with optional limit)."""

    # --- Temporal helpers (Issue #10) ---

    def get_edges_at_round(self, graph_id: str, round_num: int) -> List[Dict[str, Any]]:
        """Return edges that were valid at ``round_num``. Default stub: all edges."""
        return self.get_all_edges(graph_id)

    def reinforce_relation(
        self,
        graph_id: str,
        source_uuid: str,
        target_uuid: str,
        rtype: str,
        round_num: int,
    ) -> Optional[Dict[str, Any]]:
        """Bump reinforced_count on an existing edge. Returns None when missing."""
        return None

    def tombstone_relation(
        self, graph_id: str, relation_uuid: str, round_num: int
    ) -> bool:
        """Mark an edge as no longer valid at ``round_num``. Default stub."""
        return False

    def backfill_temporal_defaults(self, graph_id: Optional[str] = None) -> int:
        """Migrate pre-#10 edges to ``valid_from_round=0``. Default stub."""
        return 0

    @abstractmethod
    def get_node(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get a single node by UUID."""

    @abstractmethod
    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """Get all edges connected to a node (O(1) via Cypher, not full scan)."""

    @abstractmethod
    def get_nodes_by_label(self, graph_id: str, label: str) -> List[Dict[str, Any]]:
        """Get nodes filtered by entity type label."""

    @abstractmethod
    def get_filtered_entities_with_edges(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> Dict[str, Any]:
        """
        Push-down variant of the old in-memory filter: return entities that
        carry at least one custom label (not just ``Entity``/``Node``) together
        with their adjacent RELATION edges and linked neighbour nodes.

        Prevents loading every node and every edge of the graph into RAM.

        Returns:
            {
                "entities": List[Dict[str, Any]] — each entry has keys
                    ``uuid``, ``name``, ``labels``, ``summary``, ``attributes``,
                    ``related_edges`` (direction + edge_name + fact + source/target uuid),
                    ``related_nodes`` (uuid + name + labels + summary),
                "total_count": int — all ``Entity`` nodes in the graph, including
                    unlabeled ones, so callers can report a filter ratio.
            }
        """

    # --- Read edges ---

    @abstractmethod
    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """Get all edges in a graph."""

    # --- Search ---

    @abstractmethod
    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ):
        """
        Hybrid search (vector + keyword) over graph data.

        Args:
            graph_id: Graph to search in
            query: Search query text
            limit: Max results
            scope: "edges", "nodes", or "both"

        Returns:
            Dict with 'edges' and/or 'nodes' lists (wrapped by GraphToolsService into SearchResult)
        """

    # --- Graph info ---

    @abstractmethod
    def get_graph_info(self, graph_id: str) -> Dict[str, Any]:
        """Get graph metadata (node count, edge count, entity types)."""

    @abstractmethod
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        Get full graph data (enriched format for frontend).

        Returns dict with:
            graph_id, nodes, edges, node_count, edge_count
        Edge dicts include derived fields: fact_type, source_node_name, target_node_name
        """
