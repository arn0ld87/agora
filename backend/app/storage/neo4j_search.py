"""
Search-Pfad für ``Neo4jStorage``.

Issue #50 (EPIC-08-ST-01), Sub-Slice 3/3: ``Neo4jSearchMixin`` bündelt
den Hybrid-Search-Einstieg. Die eigentliche Vektor-/Keyword-Logik lebt
in ``storage.search_service`` und wird via ``self._search`` (vom
konkreten Storage-Konstruktor injiziert) genutzt.

Mixin-Voraussetzungen am konkreten Storage:

- ``self._driver`` — Neo4j-Driver mit ``.session()``
- ``self._call_with_retry`` — Retry-Wrapper
- ``self._search`` — eine ``SearchService``-Instanz mit
  ``search_edges(session, graph_id, query, limit)`` und
  ``search_nodes(session, graph_id, query, limit)``
"""

from typing import Any, Dict


class Neo4jSearchMixin:
    """Search-Pfad für ``Neo4jStorage``. Siehe Modul-Docstring."""

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ):
        """Hybrid search — returns results matching the scope.

        Returns a dict with 'edges' and/or 'nodes' lists
        (callers like zep_tools will wrap into SearchResult).

        The entire session block is wrapped in ``_call_with_retry`` so a
        transient connection error mid-search causes a clean retry rather
        than a half-filled result being returned.
        """
        result: Dict[str, Any] = {"edges": [], "nodes": [], "query": query}

        def _do_search():
            with self._get_session() as session:
                if scope in ("edges", "both"):
                    result["edges"] = self._search.search_edges(
                        session, graph_id, query, limit
                    )
                if scope in ("nodes", "both"):
                    result["nodes"] = self._search.search_nodes(
                        session, graph_id, query, limit
                    )

        self._call_with_retry(_do_search)
        return result


__all__ = ["Neo4jSearchMixin"]
