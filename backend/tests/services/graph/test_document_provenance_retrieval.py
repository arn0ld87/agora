"""Dokument-Provenance im Retrieval-Pfad (Issue #1152 Slice 1, Teil B, Etappe 2).

Teil B Etappe 1 schreibt ``document_id``/``chunk_id`` auf den Episode-Knoten.
Diese Datei prüft die zweite Hälfte: dass das Retrieval die Herkunft wieder
herausgibt und die drei Fakt-DTOs sie additiv transportieren.

Die vier Akzeptanzkriterien aus #1152, jeweils als Test:

1. Ein Fakt aus einem Seed-Dokument trägt nach dem Retrieval eine stabile
   ``document_id`` und ``chunk_id``.
2. Ein Fakt ohne Dokumentherkunft trägt keine — kein Platzhalter, kein Raten.
   Das gilt auch bei *mehrdeutiger* Herkunft: eine Kante, die auf zwei
   verschiedene Dokumente zeigt, bekommt keinen Anker.
3. Bestandsgraphen ohne Dokumentbezug laufen unverändert weiter — inklusive
   Storage-Implementierungen, die ``get_episode_provenance`` gar nicht kennen.
4. Bestehende Consumer der DTOs brechen nicht: ``facts`` bleibt ``List[str]``,
   ``to_dict()`` liefert ohne Herkunft denselben Payload wie zuvor, und
   ``to_text()`` ist unverändert (ADR-0002 rührt niemand an).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.graph.graph_dtos import PanoramaResult, SearchResult, provenance_at
from app.services.graph.graph_reader import get_all_edges, local_search, search_graph
from app.services.graph.insight_forge_tool import insight_forge, panorama_search


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _edge(
    uuid: str,
    fact: str,
    episode_ids: Optional[List[str]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "uuid": uuid,
        "name": "RELATES_TO",
        "fact": fact,
        "source_node_uuid": f"src-{uuid}",
        "target_node_uuid": f"tgt-{uuid}",
        "episode_ids": episode_ids if episode_ids is not None else [],
    }
    payload.update(extra)
    return payload


class _FakeStorage:
    """Minimaler GraphStorage-Ersatz für den Reader-Pfad.

    Bewusst kein ``MagicMock``: die Provenance-Auflösung hängt daran, dass
    ``get_episode_provenance`` echte Dicts liefert und für unbekannte
    Episoden *nichts* zurückgibt.
    """

    def __init__(
        self,
        edges: Optional[List[Dict[str, Any]]] = None,
        nodes: Optional[List[Dict[str, Any]]] = None,
        provenance: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self._edges = edges or []
        self._nodes = nodes or []
        self._provenance = provenance or {}
        self.provenance_calls: List[List[str]] = []

    def search(self, graph_id: str, query: str, limit: int = 10, scope: str = "edges"):
        return {"edges": list(self._edges), "nodes": list(self._nodes), "query": query}

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        return list(self._edges)

    def get_all_nodes(self, graph_id: str, limit: int = 2000) -> List[Dict[str, Any]]:
        return list(self._nodes)

    def get_episode_provenance(
        self, episode_ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        self.provenance_calls.append(list(episode_ids))
        return {
            eid: dict(entry)
            for eid, entry in self._provenance.items()
            if eid in episode_ids
        }


class _LegacyStorage(_FakeStorage):
    """Bestandsstorage ohne Provenance-Methode (ADR-0013 Punkt 3)."""

    get_episode_provenance = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Akzeptanz 1 — Fakt aus einem Seed-Dokument trägt Herkunft
# ---------------------------------------------------------------------------


class TestSeedFactCarriesProvenance:
    def test_search_graph_returns_document_and_chunk(self) -> None:
        storage = _FakeStorage(
            edges=[_edge("e1", "Kunden nennen den Preis als Hürde.", ["ep-1"])],
            provenance={"ep-1": {"document_id": "interview-nord", "chunk_id": 7}},
        )

        result = search_graph("g1", "Preis", storage=storage, llm=None)

        assert result.facts == ["Kunden nennen den Preis als Hürde."]
        assert result.fact_provenance == [
            {"document_id": "interview-nord", "chunk_id": 7}
        ]
        assert result.edges[0]["document_id"] == "interview-nord"
        assert result.edges[0]["chunk_id"] == 7

    def test_provenance_is_positionally_parallel_to_facts(self) -> None:
        """Node-Summaries hängen hinter den Kanten-Fakten — die Indizes müssen
        trotzdem passen, sonst ordnet #1154 später den falschen Anker zu."""
        storage = _FakeStorage(
            edges=[
                _edge("e1", "Fakt A", ["ep-1"]),
                _edge("e2", "Fakt B", ["ep-2"]),
            ],
            nodes=[{"uuid": "n1", "name": "Preis", "summary": "Zusammenfassung"}],
            provenance={
                "ep-1": {"document_id": "doc-a", "chunk_id": 0},
                "ep-2": {"document_id": "doc-b", "chunk_id": 3},
            },
        )

        result = search_graph("g1", "q", storage=storage, llm=None, scope="both")

        assert len(result.fact_provenance) == len(result.facts)
        assert provenance_at(result.fact_provenance, 0) == {
            "document_id": "doc-a",
            "chunk_id": 0,
        }
        assert provenance_at(result.fact_provenance, 1) == {
            "document_id": "doc-b",
            "chunk_id": 3,
        }
        # Der Node-Summary-Fakt ist aggregiert und keinem Chunk zuzuordnen.
        assert result.facts[2].startswith("[Preis]")
        assert provenance_at(result.fact_provenance, 2) is None

    def test_provenance_is_fetched_in_a_single_lookup(self) -> None:
        storage = _FakeStorage(
            edges=[
                _edge("e1", "Fakt A", ["ep-1"]),
                _edge("e2", "Fakt B", ["ep-2"]),
                _edge("e3", "Fakt C", ["ep-1"]),
            ],
            provenance={"ep-1": {"document_id": "doc-a", "chunk_id": 1}},
        )

        search_graph("g1", "q", storage=storage, llm=None)

        assert len(storage.provenance_calls) == 1

    def test_local_search_fallback_also_resolves_provenance(self) -> None:
        storage = _FakeStorage(
            edges=[_edge("e1", "Preis ist die Hürde", ["ep-1"])],
            provenance={"ep-1": {"document_id": "doc-a", "chunk_id": 2}},
        )

        result = local_search("g1", "Preis", storage=storage)

        assert result.fact_provenance == [{"document_id": "doc-a", "chunk_id": 2}]

    def test_get_all_edges_carries_provenance_into_edge_info(self) -> None:
        storage = _FakeStorage(
            edges=[_edge("e1", "Fakt A", ["ep-1"])],
            provenance={"ep-1": {"document_id": "doc-a", "chunk_id": 4}},
        )

        edges = get_all_edges("g1", storage=storage)

        assert edges[0].document_id == "doc-a"
        assert edges[0].chunk_id == 4
        assert edges[0].to_dict()["document_id"] == "doc-a"


# ---------------------------------------------------------------------------
# Akzeptanz 2 — kein Platzhalter, kein Raten
# ---------------------------------------------------------------------------


class TestFactWithoutProvenance:
    def test_unknown_episode_yields_none(self) -> None:
        storage = _FakeStorage(
            edges=[_edge("e1", "Fakt ohne Herkunft", ["ep-unbekannt"])],
            provenance={"ep-1": {"document_id": "doc-a", "chunk_id": 0}},
        )

        result = search_graph("g1", "q", storage=storage, llm=None)

        assert result.fact_provenance == [None]
        assert "document_id" not in result.edges[0]
        assert "chunk_id" not in result.edges[0]

    def test_edge_without_episode_ids_yields_none(self) -> None:
        storage = _FakeStorage(edges=[_edge("e1", "Fakt", [])])

        result = search_graph("g1", "q", storage=storage, llm=None)

        assert result.fact_provenance == [None]

    def test_ambiguous_provenance_yields_none(self) -> None:
        """Zwei Episoden aus verschiedenen Dokumenten: der Anker wäre nicht
        verifizierbar, also gibt es keinen (ADR-0013)."""
        storage = _FakeStorage(
            edges=[_edge("e1", "Fakt", ["ep-1", "ep-2"])],
            provenance={
                "ep-1": {"document_id": "doc-a", "chunk_id": 1},
                "ep-2": {"document_id": "doc-b", "chunk_id": 1},
            },
        )

        result = search_graph("g1", "q", storage=storage, llm=None)

        assert result.fact_provenance == [None]

    def test_identical_provenance_across_episodes_still_resolves(self) -> None:
        storage = _FakeStorage(
            edges=[_edge("e1", "Fakt", ["ep-1", "ep-2"])],
            provenance={
                "ep-1": {"document_id": "doc-a", "chunk_id": 1},
                "ep-2": {"document_id": "doc-a", "chunk_id": 1},
            },
        )

        result = search_graph("g1", "q", storage=storage, llm=None)

        assert result.fact_provenance == [{"document_id": "doc-a", "chunk_id": 1}]


# ---------------------------------------------------------------------------
# Akzeptanz 3 — Bestandsgraphen laufen unverändert
# ---------------------------------------------------------------------------


class TestLegacyGraphsUnchanged:
    def test_storage_without_provenance_method_does_not_break(self) -> None:
        storage = _LegacyStorage(edges=[_edge("e1", "Altfakt", ["ep-1"])])

        result = search_graph("g1", "q", storage=storage, llm=None)

        assert result.facts == ["Altfakt"]
        assert result.fact_provenance == [None]

    def test_failing_provenance_lookup_degrades_to_no_anchor(self) -> None:
        class _BrokenStorage(_FakeStorage):
            def get_episode_provenance(self, episode_ids):
                raise RuntimeError("neo4j down")

        storage = _BrokenStorage(edges=[_edge("e1", "Fakt", ["ep-1"])])

        result = search_graph("g1", "q", storage=storage, llm=None)

        assert result.facts == ["Fakt"]
        assert result.fact_provenance == [None]

    def test_default_storage_implementation_returns_empty_map(self) -> None:
        """Die ABC-Default-Implementierung ist bewusst nicht abstrakt."""
        from app.storage.graph_storage import GraphStorage

        assert GraphStorage.get_episode_provenance(object(), ["ep-1"]) == {}


# ---------------------------------------------------------------------------
# Akzeptanz 4 — bestehende Consumer brechen nicht
# ---------------------------------------------------------------------------


class TestConsumerCompatibility:
    def test_to_dict_omits_provenance_when_absent(self) -> None:
        result = SearchResult(
            facts=["Fakt"],
            edges=[],
            nodes=[],
            query="q",
            total_count=1,
            fact_provenance=[None],
        )

        assert result.to_dict() == {
            "facts": ["Fakt"],
            "edges": [],
            "nodes": [],
            "query": "q",
            "total_count": 1,
        }

    def test_to_dict_includes_provenance_when_present(self) -> None:
        provenance = [{"document_id": "doc-a", "chunk_id": 0}]
        result = SearchResult(
            facts=["Fakt"],
            edges=[],
            nodes=[],
            query="q",
            total_count=1,
            fact_provenance=provenance,
        )

        assert result.to_dict()["fact_provenance"] == provenance

    def test_search_result_is_constructible_without_provenance(self) -> None:
        result = SearchResult(facts=[], edges=[], nodes=[], query="q", total_count=0)

        assert result.fact_provenance == []

    def test_to_text_is_unchanged_by_provenance(self) -> None:
        """Der LLM-sichtbare Text bleibt bitgleich — ADR-0002 bleibt unberührt."""
        without = SearchResult(
            facts=["Fakt"], edges=[], nodes=[], query="q", total_count=1
        )
        with_provenance = SearchResult(
            facts=["Fakt"],
            edges=[],
            nodes=[],
            query="q",
            total_count=1,
            fact_provenance=[{"document_id": "doc-a", "chunk_id": 0}],
        )

        assert with_provenance.to_text() == without.to_text()

    def test_provenance_at_tolerates_empty_list(self) -> None:
        assert provenance_at([], 0) is None
        assert provenance_at([None], 5) is None


# ---------------------------------------------------------------------------
# InsightForge und Panorama
# ---------------------------------------------------------------------------


class TestInsightForgeProvenance:
    def test_dedup_keeps_fact_and_provenance_aligned(self, monkeypatch) -> None:
        """InsightForge dedupliziert über mehrere Suchen hinweg. Die Herkunft
        muss dabei am Fakt kleben bleiben, nicht am ursprünglichen Index."""
        results = iter(
            [
                SearchResult(
                    facts=["Fakt A", "Fakt B"],
                    edges=[],
                    nodes=[],
                    query="s1",
                    total_count=2,
                    fact_provenance=[
                        {"document_id": "doc-a", "chunk_id": 0},
                        None,
                    ],
                ),
                SearchResult(
                    facts=["Fakt A", "Fakt C"],
                    edges=[],
                    nodes=[],
                    query="s2",
                    total_count=2,
                    fact_provenance=[
                        {"document_id": "doc-a", "chunk_id": 0},
                        {"document_id": "doc-c", "chunk_id": 9},
                    ],
                ),
            ]
        )

        import app.services.graph.insight_forge_tool as module

        monkeypatch.setattr(
            module, "generate_sub_queries", lambda **kwargs: ["s1"]
        )
        monkeypatch.setattr(
            module._reader, "search_graph", lambda *a, **kw: next(results)
        )
        monkeypatch.setattr(module._reader, "get_node_detail", lambda *a, **kw: None)

        result = insight_forge(
            "g1", "q", "sim", storage=_FakeStorage(), llm=None, max_sub_queries=1
        )

        assert result.semantic_facts == ["Fakt A", "Fakt B", "Fakt C"]
        assert result.semantic_facts_provenance == [
            {"document_id": "doc-a", "chunk_id": 0},
            None,
            {"document_id": "doc-c", "chunk_id": 9},
        ]


class TestPanoramaProvenance:
    def test_sorting_keeps_fact_and_provenance_paired(self) -> None:
        """Panorama sortiert die Fakten nach Relevanz — die Herkunft wird
        mitsortiert, sonst zeigt der Anker auf den falschen Fakt."""
        storage = _FakeStorage(
            edges=[
                _edge("e1", "Irrelevanter Fakt", ["ep-1"]),
                _edge("e2", "Preis ist die Hürde", ["ep-2"]),
            ],
            provenance={
                "ep-1": {"document_id": "doc-a", "chunk_id": 1},
                "ep-2": {"document_id": "doc-b", "chunk_id": 2},
            },
        )

        result = panorama_search("g1", "Preis", storage=storage)

        assert isinstance(result, PanoramaResult)
        assert result.active_facts[0] == "Preis ist die Hürde"
        assert result.active_facts_provenance[0] == {
            "document_id": "doc-b",
            "chunk_id": 2,
        }

    def test_to_dict_omits_provenance_for_legacy_graphs(self) -> None:
        storage = _LegacyStorage(edges=[_edge("e1", "Altfakt", ["ep-1"])])

        result = panorama_search("g1", "q", storage=storage)

        assert "active_facts_provenance" not in result.to_dict()
