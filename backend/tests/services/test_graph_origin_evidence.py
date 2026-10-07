"""Manuelle Herkunft im Evidence-Weg des Berichts (ADR-0022, Issue #1808).

Drei Stationen, je ein Block:

1. Graph-Leser: eine von Hand angelegte oder bearbeitete Kante liefert keinen
   Dokumentanker, sondern eine Herkunftsmarke.
2. Report-Agent: die Marke landet als ``graph_origin`` im Evidence-Record;
   der Fakt bleibt ``graph_relation``.
3. Confidence und Herabstufung: solche Evidence wird nicht mitgezählt.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.services.confidence_calculator import (
    compute_claim_confidence,
    compute_confidence,
    compute_confidence_breakdown,
)
from app.services.graph.graph_dtos import InsightForgeResult, SearchResult
from app.services.graph.graph_reader import (
    _resolve_edge_provenance,
    get_all_edges,
    local_search,
    search_graph,
)
from app.services.graph.insight_forge_tool import insight_forge, panorama_search
from app.services.report_agent import ReportAgent
from app.services.report_agent.evidence import (
    auto_downgrade_unsupported_high_claims,
    downgrade_medium_without_agent_grounded,
    has_agent_grounded_evidence,
    init_evidence_map,
)
from app.storage.neo4j_mappings import edge_to_dict, node_to_dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _edge(
    uuid: str,
    fact: str,
    episode_ids: Optional[List[str]] = None,
    *,
    origin: Optional[str] = None,
    raw: bool = False,
) -> Dict[str, Any]:
    """Kanten-Dict in einer der beiden Formen, die der Leser sieht.

    ``raw=False``: Form von ``edge_to_dict`` (``get_all_edges``), Herkunft unter
    ``provenance.origin``. ``raw=True``: rohe Relationship-Properties aus der
    Hybrid-Suche (``search_service``), Herkunft als ``origin`` auf oberster
    Ebene.
    """
    props: Dict[str, Any] = {
        "uuid": uuid,
        "name": "RELATES_TO",
        "fact": fact,
        "episode_ids": episode_ids if episode_ids is not None else [],
    }
    if origin is not None:
        props["origin"] = origin
        props["origin_changed_at"] = "2026-10-07T09:00:00+00:00"
    if raw:
        return props | {"source_node_uuid": f"src-{uuid}", "target_node_uuid": f"tgt-{uuid}"}
    return edge_to_dict(props, f"src-{uuid}", f"tgt-{uuid}")


def _node(uuid: str, name: str, summary: str, *, origin: Optional[str] = None) -> Dict[str, Any]:
    props: Dict[str, Any] = {"uuid": uuid, "name": name, "summary": summary}
    if origin is not None:
        props["origin"] = origin
    return node_to_dict(props, ["Entity", "Organization"])


class _FakeStorage:
    def __init__(
        self,
        edges: Optional[List[Dict[str, Any]]] = None,
        nodes: Optional[List[Dict[str, Any]]] = None,
        provenance: Optional[Dict[str, Dict[str, Any]]] = None,
        *,
        search_fails: bool = False,
    ) -> None:
        self._edges = edges or []
        self._nodes = nodes or []
        self._provenance = provenance or {}
        self._search_fails = search_fails
        self.provenance_calls: List[List[str]] = []

    def search(self, graph_id: str, query: str, limit: int = 10, scope: str = "edges"):
        if self._search_fails:
            raise RuntimeError("vector index offline")
        return {"edges": list(self._edges), "nodes": list(self._nodes), "query": query}

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        return list(self._edges)

    def get_all_nodes(self, graph_id: str, limit: int = 2000) -> List[Dict[str, Any]]:
        return list(self._nodes)

    def get_node(self, node_uuid: str) -> Optional[Dict[str, Any]]:
        return next((n for n in self._nodes if n.get("uuid") == node_uuid), None)

    def get_episode_provenance(self, episode_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        self.provenance_calls.append(list(episode_ids))
        return {
            eid: dict(entry) for eid, entry in self._provenance.items() if eid in episode_ids
        }


_DOC = {"ep-1": {"document_id": "interview-nord", "chunk_id": 7}}


# ---------------------------------------------------------------------------
# 1. Graph-Leser
# ---------------------------------------------------------------------------


class TestReaderRefusesAnchorForHandMadeEdges:
    @pytest.mark.parametrize("raw", [False, True])
    def test_edited_edge_keeps_episodes_but_yields_no_document_anchor(self, raw: bool) -> None:
        """Die Episode zeigt weiter auf das Dokument — der Anker bleibt trotzdem aus."""
        edge = _edge("e1", "Von Hand geänderter Satz.", ["ep-1"], origin="edited", raw=raw)
        storage = _FakeStorage(edges=[edge], provenance=_DOC)

        resolved = _resolve_edge_provenance([edge], storage=storage)

        assert resolved == {"e1": {"graph_origin": "edited"}}
        # Für eine Handänderung wird die Dokumentherkunft gar nicht erst geholt.
        assert storage.provenance_calls == []

    def test_manual_edge_without_episodes_is_marked_not_dropped(self) -> None:
        edge = _edge("e1", "Von Hand angelegte Beziehung.", [], origin="manual")
        resolved = _resolve_edge_provenance([edge], storage=_FakeStorage(edges=[edge]))
        assert resolved == {"e1": {"graph_origin": "manual"}}

    def test_extracted_edge_next_to_edited_edge_keeps_its_anchor(self) -> None:
        edges = [
            _edge("e1", "Extrahierter Satz.", ["ep-1"]),
            _edge("e2", "Geänderter Satz.", ["ep-1"], origin="edited"),
        ]
        storage = _FakeStorage(edges=edges, provenance=_DOC)

        resolved = _resolve_edge_provenance(edges, storage=storage)

        assert resolved["e1"] == {"document_id": "interview-nord", "chunk_id": 7}
        assert resolved["e2"] == {"graph_origin": "edited"}
        assert storage.provenance_calls == [["ep-1"]]

    def test_unknown_origin_value_counts_as_extracted(self) -> None:
        """Ein beschädigter Wert bricht nichts und erfindet keine Handänderung."""
        edge = _edge("e1", "Extrahierter Satz.", ["ep-1"], origin="kaputt", raw=True)
        resolved = _resolve_edge_provenance(
            [edge], storage=_FakeStorage(edges=[edge], provenance=_DOC)
        )
        assert resolved == {"e1": {"document_id": "interview-nord", "chunk_id": 7}}

    def test_marker_survives_a_storage_without_provenance_lookup(self) -> None:
        class _Legacy(_FakeStorage):
            get_episode_provenance = None  # type: ignore[assignment]

        edge = _edge("e1", "Geänderter Satz.", ["ep-1"], origin="edited")
        assert _resolve_edge_provenance([edge], storage=_Legacy(edges=[edge])) == {
            "e1": {"graph_origin": "edited"}
        }

    def test_marker_survives_a_failing_provenance_lookup(self) -> None:
        class _Broken(_FakeStorage):
            def get_episode_provenance(self, episode_ids):  # type: ignore[override]
                raise RuntimeError("neo4j weg")

        edges = [
            _edge("e1", "Extrahierter Satz.", ["ep-1"]),
            _edge("e2", "Geänderter Satz.", ["ep-1"], origin="edited"),
        ]
        assert _resolve_edge_provenance(edges, storage=_Broken(edges=edges)) == {
            "e2": {"graph_origin": "edited"}
        }

    def test_search_graph_carries_marker_instead_of_anchor(self) -> None:
        edge = _edge("e1", "Geänderter Satz.", ["ep-1"], origin="edited", raw=True)
        result = search_graph(
            "g1", "Satz", storage=_FakeStorage(edges=[edge], provenance=_DOC), llm=None
        )

        assert result.facts == ["Geänderter Satz."]
        assert result.fact_provenance == [{"graph_origin": "edited"}]
        assert "document_id" not in result.edges[0]
        assert result.edges[0]["graph_origin"] == "edited"

    def test_local_search_carries_marker_instead_of_anchor(self) -> None:
        edge = _edge("e1", "Geänderter Satz.", ["ep-1"], origin="edited")
        result = local_search("g1", "Satz", storage=_FakeStorage(edges=[edge], provenance=_DOC))

        assert result.fact_provenance == [{"graph_origin": "edited"}]

    def test_summary_of_a_hand_made_entity_carries_the_marker(self) -> None:
        """Die Summary einer manuellen Entität ist von Hand eingegebener Text."""
        nodes = [
            _node("n1", "Verband", "Der Verband unterstützt die Reform.", origin="manual"),
            _node("n2", "Amt", "Das Amt prüft den Antrag."),
        ]
        result = local_search("g1", "Reform Antrag", storage=_FakeStorage(nodes=nodes), scope="nodes")

        assert result.fact_provenance == [{"graph_origin": "manual"}, None]

    def test_get_all_edges_exposes_origin_and_no_document(self) -> None:
        edges = [
            _edge("e1", "Extrahierter Satz.", ["ep-1"]),
            _edge("e2", "Geänderter Satz.", ["ep-1"], origin="edited"),
        ]
        infos = get_all_edges("g1", storage=_FakeStorage(edges=edges, provenance=_DOC))

        assert (infos[0].document_id, infos[0].chunk_id, infos[0].graph_origin) == (
            "interview-nord", 7, None,
        )
        assert (infos[1].document_id, infos[1].chunk_id, infos[1].graph_origin) == (
            None, None, "edited",
        )
        assert "graph_origin" not in infos[0].to_dict()
        assert infos[1].to_dict()["graph_origin"] == "edited"

    def test_panorama_carries_marker(self) -> None:
        edges = [
            _edge("e1", "Extrahierter Satz zur Reform.", ["ep-1"]),
            _edge("e2", "Manueller Satz zur Reform.", [], origin="manual"),
        ]
        result = panorama_search(
            "g1", "Reform", storage=_FakeStorage(edges=edges, provenance=_DOC)
        )

        by_fact = dict(zip(result.active_facts, result.active_facts_provenance))
        assert by_fact["Extrahierter Satz zur Reform."] == {
            "document_id": "interview-nord", "chunk_id": 7,
        }
        assert by_fact["Manueller Satz zur Reform."] == {"graph_origin": "manual"}

    def test_insight_forge_carries_marker_on_facts_entities_and_chains(self) -> None:
        nodes = [
            _node("src-e1", "Verband", "Der Verband unterstützt die Reform.", origin="manual"),
            _node("tgt-e1", "Amt", "Das Amt prüft den Antrag."),
        ]
        edge = _edge("e1", "Der Verband berät das Amt.", [], origin="manual", raw=True)
        result = insight_forge(
            "g1",
            "Reform",
            "Wie reagieren die Gruppen?",
            storage=_FakeStorage(edges=[edge], nodes=nodes),
            llm=None,
        )

        assert result.semantic_facts == ["Der Verband berät das Amt."]
        assert result.semantic_facts_provenance == [{"graph_origin": "manual"}]
        origins = {entity["name"]: entity.get("graph_origin") for entity in result.entity_insights}
        assert origins == {"Verband": "manual", "Amt": None}
        assert result.relationship_chains == ["Verband --[RELATES_TO]--> Amt"]
        assert result.relationship_chains_provenance == [{"graph_origin": "manual"}]


# ---------------------------------------------------------------------------
# 2. Report-Agent: Marke im Evidence-Record
# ---------------------------------------------------------------------------


def _make_agent() -> ReportAgent:
    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_test"
    agent.simulation_id = "sim_test"
    agent.simulation_requirement = "Test-Requirement"
    agent.evidence_map = init_evidence_map(
        report_id="report_test", simulation_id="sim_test", global_evidence=[]
    )
    agent._active_section_evidence = []
    agent._active_section_unresolved_evidence = []
    return agent


def _records(agent: ReportAgent) -> List[Dict[str, Any]]:
    return list(agent.evidence_map["evidence_index"].values())


def _search_result(provenance: List[Optional[Dict[str, Any]]]) -> SearchResult:
    return SearchResult(
        facts=["Der Verband unterstützt die Reform."],
        edges=[],
        nodes=[],
        query="reform",
        total_count=1,
        fact_provenance=provenance,
    )


class TestAgentRecordsGraphOrigin:
    @pytest.mark.parametrize("origin", ["manual", "edited"])
    def test_hand_made_fact_becomes_graph_relation_with_origin(self, origin: str) -> None:
        agent = _make_agent()
        agent._record_tool_evidence(
            tool_name="quick_search",
            parameters={},
            structured_result=_search_result([{"graph_origin": origin}]),
            rendered_result="",
            section_index=1,
        )

        (record,) = _records(agent)
        assert record["graph_origin"] == origin
        assert record["type"] == "graph_fact"
        assert record["source_kind"] == "graph_relation"
        assert record["source_id_anchor"] is None

    def test_origin_wins_over_a_document_reference_in_the_same_provenance(self) -> None:
        """Zweite Verteidigungslinie: selbst wenn ein Aufrufer Marke *und*
        Dokumentbezug mitschickt, entsteht kein ``seed_doc:``-Anker."""
        agent = _make_agent()
        agent._record_tool_evidence(
            tool_name="quick_search",
            parameters={},
            structured_result=_search_result(
                [{"graph_origin": "edited", "document_id": "doc_a1b2c3d4", "chunk_id": 7}]
            ),
            rendered_result="",
            section_index=1,
        )

        (record,) = _records(agent)
        assert record["source_kind"] == "graph_relation"
        assert record["source_id_anchor"] is None
        assert record["graph_origin"] == "edited"

    def test_extracted_fact_keeps_anchor_and_has_no_origin(self) -> None:
        agent = _make_agent()
        agent._record_tool_evidence(
            tool_name="quick_search",
            parameters={},
            structured_result=_search_result([{"document_id": "doc_a1b2c3d4", "chunk_id": 7}]),
            rendered_result="",
            section_index=1,
        )

        (record,) = _records(agent)
        assert record["source_kind"] == "seed_corpus"
        assert record["source_id_anchor"] == "seed_doc:doc_a1b2c3d4#chunk:7"
        assert record["graph_origin"] is None

    def test_hand_made_fact_is_neither_data_gap_nor_unresolved(self) -> None:
        """Kein Anker wegen Handänderung ist kein fehlgeschlagenes Binding."""
        agent = _make_agent()
        agent._record_tool_evidence(
            tool_name="quick_search",
            parameters={},
            structured_result=_search_result([{"graph_origin": "manual"}]),
            rendered_result="",
            section_index=1,
        )

        assert len(_records(agent)) == 1
        assert agent._active_section_unresolved_evidence == []

    def test_insight_forge_entities_and_chains_carry_origin(self) -> None:
        agent = _make_agent()
        result = InsightForgeResult(
            query="reform",
            simulation_requirement="Test-Requirement",
            sub_queries=[],
            semantic_facts=[],
            entity_insights=[
                {
                    "uuid": "n1",
                    "name": "Verband",
                    "type": "Organization",
                    "summary": "Der Verband unterstützt die Reform.",
                    "related_facts": [],
                    "graph_origin": "manual",
                },
                {
                    "uuid": "n2",
                    "name": "Amt",
                    "type": "Organization",
                    "summary": "Das Amt prüft den Antrag.",
                    "related_facts": [],
                },
            ],
            relationship_chains=["Verband --[BERAET]--> Amt", "Amt --[PRUEFT]--> Antrag"],
            relationship_chains_provenance=[{"graph_origin": "manual"}, None],
        )
        agent._record_tool_evidence(
            tool_name="insight_forge",
            parameters={},
            structured_result=result,
            rendered_result="",
            section_index=1,
        )

        origin_by_snippet = {r["snippet"]: r["graph_origin"] for r in _records(agent)}
        assert origin_by_snippet == {
            "Der Verband unterstützt die Reform.": "manual",
            "Das Amt prüft den Antrag.": None,
            "Verband --[BERAET]--> Amt": "manual",
            "Amt --[PRUEFT]--> Antrag": None,
        }


# ---------------------------------------------------------------------------
# 3. Confidence und Herabstufung
# ---------------------------------------------------------------------------


def _fact(score: float, *, origin: Optional[str] = None, source: str = "graph") -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "type": "graph_fact",
        "source": source,
        "source_kind": "graph_relation",
        "match_score": score,
        "entailment": "SUPPORTED",
        "supports_claim": True,
    }
    if origin is not None:
        item["graph_origin"] = origin
    return item


def _quote(group: str, score: float = 0.7, *, supports: bool = True) -> Dict[str, Any]:
    return {
        "type": "agent_interview",
        "source": f"interview-{group}",
        "source_kind": "agent_quote",
        "match_score": score,
        "entailment": "SUPPORTED" if supports else "RELATED_ONLY",
        "supports_claim": supports,
        "persona_stakeholder_group": group,
        "quote": f"Original-Zitat aus {group}.",
        "snippet": "Bla bla",
    }


def _seed() -> Dict[str, Any]:
    return {
        "type": "seed_document",
        "source": "doc",
        "source_kind": "seed_corpus",
        "supports_claim": True,
        "snippet": "Seed-Dokument-Auszug mit genug Text.",
    }


class TestConfidenceIgnoresHandMadeEvidence:
    @pytest.mark.parametrize("origin", ["manual", "edited"])
    def test_hand_made_fact_alone_is_speculative(self, origin: str) -> None:
        """Dieselbe Evidence trägt als extrahierter Fakt ``high``."""
        assert compute_confidence([_fact(0.95)])[1] == "high"
        assert compute_confidence([_fact(0.95, origin=origin)]) == (0.15, "speculative")
        assert compute_claim_confidence([_fact(0.95, origin=origin)]) == (0.15, "speculative", [])

    def test_hand_made_evidence_does_not_change_the_score(self) -> None:
        counted = [_fact(0.9, source="a"), _fact(0.8, source="b")]
        with_manual = [*counted, _fact(0.99, origin="manual", source="c")]

        assert compute_confidence(with_manual) == compute_confidence(counted)
        assert compute_confidence_breakdown(with_manual) == compute_confidence_breakdown(counted)

    def test_hand_made_strong_match_does_not_lift_to_verified(self) -> None:
        """Ohne die Handeingabe gibt es keinen Match >= 0.85 — also kein ``verified``."""
        counted = [_fact(0.84, source="a"), _fact(0.84, source="b"), _fact(0.84, source="c")]
        with_manual = [*counted, _fact(0.99, origin="edited", source="d")]

        assert compute_confidence(with_manual)[1] != "verified"
        assert compute_confidence(with_manual) == compute_confidence(counted)

    def test_hand_made_contradiction_does_not_lower_the_score(self) -> None:
        """Nicht mitgezählt heißt in beide Richtungen: weder hebend noch senkend."""
        counted = [_fact(0.9, source="a"), _fact(0.8, source="b")]
        contradiction = _fact(0.9, origin="manual", source="c") | {
            "entailment": "CONTRADICTED",
            "supports_claim": False,
            "contradicts_claim": True,
        }
        assert compute_claim_confidence([*counted, contradiction]) == compute_claim_confidence(
            counted
        )

    def test_record_without_graph_origin_is_counted_as_before(self) -> None:
        legacy = [{"type": "graph_fact", "source": "graph", "match_score": 0.95}]
        explicit_none = [legacy[0] | {"graph_origin": None}]
        assert compute_confidence(legacy) == compute_confidence(explicit_none)
        assert compute_confidence(legacy)[1] == "high"


class TestDowngradeIgnoresHandMadeEvidence:
    def test_high_stays_high_when_met_without_manual_evidence(self) -> None:
        claim = {
            "claim_id": "claim_01",
            "confidence_label": "high",
            "evidence": [_quote("A"), _quote("B"), _fact(0.9, origin="manual")],
        }
        (result,) = auto_downgrade_unsupported_high_claims([claim])
        assert result["confidence_label"] == "high"
        assert "audit_trail" not in result

    def test_high_resting_on_manual_fact_alone_is_downgraded_to_low(self) -> None:
        claim = {
            "claim_id": "claim_01",
            "confidence_label": "high",
            "evidence": [_fact(0.95, origin="manual")],
        }
        (result,) = auto_downgrade_unsupported_high_claims([claim])
        assert result["confidence_label"] == "low"

    def test_verified_resting_on_manual_strong_match_is_downgraded_to_high(self) -> None:
        """Herabstufen statt abbrechen: der Vertrag würde ``verified`` hier
        ablehnen, also entsteht das Label gar nicht erst — und es steht im
        Audit-Trail, unter welcher Stufe der Wortlaut entstand."""
        claim = {
            "claim_id": "claim_01",
            "confidence_label": "verified",
            "evidence": [_quote("A"), _quote("B"), _fact(0.95, origin="edited")],
        }
        (result,) = auto_downgrade_unsupported_high_claims([claim])

        assert result["confidence_label"] == "high"
        assert result["audit_trail"] == [
            {
                "event": "text_confidence_downgraded",
                "text_confidence_label": "verified",
                "to": "high",
                "issue": "1012",
            }
        ]

    def test_verified_stays_when_strong_match_is_not_hand_made(self) -> None:
        claim = {
            "claim_id": "claim_01",
            "confidence_label": "verified",
            "evidence": [_quote("A", 0.9), _quote("B"), _fact(0.95, origin="edited")],
        }
        (result,) = auto_downgrade_unsupported_high_claims([claim])
        assert result["confidence_label"] == "verified"

    def test_verified_without_hand_made_evidence_is_left_to_the_contract(self) -> None:
        """Altverhalten: ohne Handeingabe greift die neue Stufe nicht ein."""
        claim = {
            "claim_id": "claim_01",
            "confidence_label": "verified",
            "evidence": [_quote("A"), _quote("B"), _fact(0.95)],
        }
        (result,) = auto_downgrade_unsupported_high_claims([claim])
        assert result["confidence_label"] == "verified"

    def test_origin_is_resolved_through_the_evidence_index(self) -> None:
        """Im Schreibpfad trägt der Claim nur Bindings — die Marke steht am Record."""
        index = {
            "ev_a": _quote("A") | {"evidence_id": "ev_a"},
            "ev_b": _quote("B") | {"evidence_id": "ev_b"},
            "ev_m": _fact(0.95, origin="manual") | {"evidence_id": "ev_m"},
        }
        claim = {
            "claim_id": "claim_01",
            "confidence_label": "verified",
            "evidence": [
                _quote("A") | {"evidence_id": "ev_a"},
                _quote("B") | {"evidence_id": "ev_b"},
                {
                    "evidence_id": "ev_m",
                    "match_score": 0.95,
                    "entailment": "SUPPORTED",
                    "supports_claim": True,
                },
            ],
        }
        (untouched,) = auto_downgrade_unsupported_high_claims([dict(claim)])
        assert untouched["confidence_label"] == "verified"

        (result,) = auto_downgrade_unsupported_high_claims([dict(claim)], evidence_index=index)
        assert result["confidence_label"] == "high"

    def test_hand_made_evidence_does_not_make_a_claim_agent_grounded(self) -> None:
        """Ein von Hand markierter Record zählt auch dann nicht, wenn seine
        Quellengattung für ``medium`` reichen würde."""
        grounded = [_quote("A"), _seed()]
        assert has_agent_grounded_evidence(grounded) is True
        assert has_agent_grounded_evidence([_quote("A"), _seed() | {"graph_origin": "edited"}]) is False

        claim = {
            "claim_id": "claim_01",
            "confidence_label": "medium",
            "evidence": [_quote("A"), _fact(0.9, origin="manual")],
        }
        decision = downgrade_medium_without_agent_grounded(claim)
        assert claim["confidence_label"] == "low"
        assert decision is not None and decision["action"] == "downgraded_to_low"
