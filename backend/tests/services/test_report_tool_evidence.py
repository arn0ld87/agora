"""Regressionstests für Commit 7bac1291.

Deckt zwei Fixes ab:

1. ``ReportAgent._record_tool_evidence`` vergibt deterministische
   ``producer_key``s für ``agent_interview``- und ``graph_fact``-Items, sodass
   ``register_evidence_record`` sie in ``evidence_map["evidence_index"]`` mit
   kanonischen ``ev_<32hex>``-IDs registriert (vorher: still verworfen).
2. ``generate_section_metadata`` kappt den Section-Text erst bei
   ``METADATA_MAX_CONTENT_CHARS`` (24000), nicht mehr bei 6000 Zeichen.
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock

from app.services.graph.graph_dtos import AgentInterview, InterviewResult, SearchResult
from app.services.report_agent import ReportAgent
from app.services.report_agent.evidence import init_evidence_map

EVIDENCE_ID_RE = re.compile(r"^ev_[0-9a-f]{32}$")


def _make_agent(simulation_id: str = "sim_test") -> ReportAgent:
    """Minimaler ReportAgent-Stub ohne echten LLM-/Graph-Call.

    ``_record_tool_evidence`` braucht nur ``evidence_map`` und die beiden
    ``_active_section_*``-Puffer — kein LLM.
    """
    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_test"
    agent.simulation_id = simulation_id
    agent.simulation_requirement = "Test-Requirement"
    agent.llm = MagicMock()
    agent.web_tools = MagicMock()
    agent.graph_tools = MagicMock()
    agent.evidence_map = init_evidence_map(
        report_id="report_test",
        simulation_id=simulation_id,
        global_evidence=[],
    )
    agent._active_section_evidence = []
    agent._active_section_unresolved_evidence = []
    return agent


def _interview(
    agent_name: str = "Agent A",
    agent_role: str = "Kundin",
    question: str = "Was halten Sie davon?",
    response: str = "Ich finde das Produkt überzeugend.",
) -> AgentInterview:
    return AgentInterview(
        agent_name=agent_name,
        agent_role=agent_role,
        agent_bio="Bio-Text",
        question=question,
        response=response,
        key_quotes=[],
    )


def test_placeholder_only_interview_is_skipped() -> None:
    """GraphToolsService-Platzhalter für stumme Plattformen sind keine Evidence."""
    agent = _make_agent()
    result = InterviewResult(
        interview_topic="Produktakzeptanz",
        interview_questions=["Was halten Sie davon?"],
        interviews=[_interview(response=(
            "[Twitter Platform Response]\n(No response from this platform)\n\n"
            "[Reddit Platform Response]\n(No response from this platform)"
        ))],
    )

    agent._record_tool_evidence(
        tool_name="conduct_agent_interview",
        parameters={},
        structured_result=result,
        rendered_result="",
        section_index=1,
    )

    records = list((agent.evidence_map or {})["evidence_index"].values())
    assert [r for r in records if r["type"] == "agent_interview"] == []


def test_interview_cap_registers_at_most_ten() -> None:
    agent = _make_agent()
    result = InterviewResult(
        interview_topic="Produktakzeptanz",
        interview_questions=["Was halten Sie davon?"],
        interviews=[
            _interview(agent_name=f"Agent {i:02d}", response=f"Eigenständige Antwort Nummer {i}.")
            for i in range(11)
        ],
    )

    agent._record_tool_evidence(
        tool_name="conduct_agent_interview",
        parameters={},
        structured_result=result,
        rendered_result="",
        section_index=1,
    )

    records = list((agent.evidence_map or {})["evidence_index"].values())
    assert len([r for r in records if r["type"] == "agent_interview"]) == 10


def test_interview_response_gets_canonical_evidence_id() -> None:
    agent = _make_agent()
    result = InterviewResult(
        interview_topic="Produktakzeptanz",
        interview_questions=["Was halten Sie davon?"],
        interviews=[
            _interview(agent_name="Agent A", response="Antwort von Agent A."),
            _interview(agent_name="Agent B", response="Antwort von Agent B."),
        ],
    )

    agent._record_tool_evidence(
        tool_name="conduct_agent_interview",
        parameters={},
        structured_result=result,
        rendered_result="",
        section_index=1,
    )

    records = list((agent.evidence_map or {})["evidence_index"].values())
    interview_records = [r for r in records if r["type"] == "agent_interview"]
    assert len(interview_records) == 2
    for record in interview_records:
        assert record["source_kind"] == "agent_quote"
        assert EVIDENCE_ID_RE.match(record["evidence_id"]), record["evidence_id"]
        assert record["quote"]
        assert record["persona_stakeholder_group"]


def test_two_questions_same_agent_get_distinct_evidence_ids() -> None:
    agent = _make_agent()
    result = InterviewResult(
        interview_topic="Produktakzeptanz",
        interview_questions=["Frage 1", "Frage 2"],
        interviews=[
            _interview(agent_name="Agent A", question="Frage 1", response="Antwort 1."),
            _interview(agent_name="Agent A", question="Frage 2", response="Antwort 2."),
        ],
    )

    agent._record_tool_evidence(
        tool_name="conduct_agent_interview",
        parameters={},
        structured_result=result,
        rendered_result="",
        section_index=1,
    )

    ids = {r["evidence_id"] for r in agent._active_section_evidence}
    assert len(ids) == 2


def test_same_text_different_agents_not_collapsed() -> None:
    agent = _make_agent()
    result = InterviewResult(
        interview_topic="Produktakzeptanz",
        interview_questions=["Was halten Sie davon?"],
        interviews=[
            _interview(agent_name="Agent A", response="Identischer Antworttext."),
            _interview(agent_name="Agent B", response="Identischer Antworttext."),
        ],
    )

    agent._record_tool_evidence(
        tool_name="conduct_agent_interview",
        parameters={},
        structured_result=result,
        rendered_result="",
        section_index=1,
    )

    ids = {r["evidence_id"] for r in agent._active_section_evidence}
    assert len(ids) == 2


def test_empty_interview_response_is_skipped() -> None:
    agent = _make_agent()
    result = InterviewResult(
        interview_topic="Produktakzeptanz",
        interview_questions=["Was halten Sie davon?"],
        interviews=[
            _interview(agent_name="Agent A", response="   "),
        ],
    )

    agent._record_tool_evidence(
        tool_name="conduct_agent_interview",
        parameters={},
        structured_result=result,
        rendered_result="",
        section_index=1,
    )

    assert agent._active_section_evidence == []
    assert (agent.evidence_map or {})["evidence_index"] == {}


def test_graph_fact_gets_canonical_evidence_id() -> None:
    agent = _make_agent()
    result = SearchResult(
        facts=["Fakt eins über den Markt.", "Fakt zwei über die Zielgruppe."],
        edges=[],
        nodes=[],
        query="marktanalyse",
        total_count=2,
    )

    agent._record_tool_evidence(
        tool_name="quick_search",
        parameters={},
        structured_result=result,
        rendered_result="",
        section_index=2,
    )

    records = [
        r for r in (agent.evidence_map or {})["evidence_index"].values()
        if r["type"] == "graph_fact"
    ]
    assert len(records) == 2
    for record in records:
        assert EVIDENCE_ID_RE.match(record["evidence_id"]), record["evidence_id"]

    # Derselbe Fakt erneut registriert -> Deduplizierung auf 1 Record.
    agent._record_tool_evidence(
        tool_name="quick_search",
        parameters={},
        structured_result=SearchResult(
            facts=["Fakt eins über den Markt."],
            edges=[],
            nodes=[],
            query="andere-query",
            total_count=1,
        ),
        rendered_result="",
        section_index=3,
    )
    records_after = [
        r for r in (agent.evidence_map or {})["evidence_index"].values()
        if r["type"] == "graph_fact"
    ]
    assert len(records_after) == 2


def test_interview_evidence_keeps_simulation_provenance() -> None:
    agent = _make_agent()
    result = InterviewResult(
        interview_topic="Produktakzeptanz",
        interview_questions=["Was halten Sie davon?"],
        interviews=[_interview(agent_name="Agent A", response="Simulierte Stimme.")],
    )

    agent._record_tool_evidence(
        tool_name="conduct_agent_interview",
        parameters={},
        structured_result=result,
        rendered_result="",
        section_index=1,
    )

    record = agent._active_section_evidence[0]
    assert record["source_kind"] == "agent_quote"
    assert record["source_kind"] not in ("seed_corpus", "web_source")
    assert isinstance(record["raw"], dict)
    assert record["raw"]["agent_name"] == "Agent A"


def test_claim_can_reference_interview_evidence() -> None:
    agent = _make_agent()
    result = InterviewResult(
        interview_topic="Produktakzeptanz",
        interview_questions=["Was halten Sie davon?"],
        interviews=[_interview(agent_name="Agent A", response="Referenzierbare Antwort.")],
    )

    agent._record_tool_evidence(
        tool_name="conduct_agent_interview",
        parameters={},
        structured_result=result,
        rendered_result="",
        section_index=1,
    )

    assert len(agent._active_section_evidence) == 1
    binding = {"evidence_id": agent._active_section_evidence[0]["evidence_id"]}

    # Exakter Lookup-Pfad aus _build_claims_for_section.
    current_index = (agent.evidence_map or {}).get("evidence_index") or {}
    resolved = current_index.get(binding["evidence_id"])

    assert resolved is not None
    assert resolved["type"] == "agent_interview"


def test_metadata_sees_full_section_text() -> None:
    from app.services.report_agent.workflow import generate_section_metadata

    agent = ReportAgent.__new__(ReportAgent)
    agent.llm = MagicMock()
    agent.llm.chat_json.return_value = {
        "section_title": "Allgemeine Einleitung",
        "key_takeaways": [],
        "data_gaps": [],
    }

    body = "Wichtiger Datenpunkt. " * 400  # > 8000 Zeichen
    tail_marker = "ENDE-DES-ABSCHNITTS-MARKER-XYZ"
    section_content = body + tail_marker
    assert len(section_content) > 8000

    generate_section_metadata(
        agent,
        section_title="Allgemeine Einleitung",
        section_content=section_content,
        section_index=1,
    )

    assert agent.llm.chat_json.called
    messages = agent.llm.chat_json.call_args.kwargs["messages"]
    user_msg = next(m["content"] for m in messages if m["role"] == "user")
    assert tail_marker in user_msg
    assert section_content[-200:] in user_msg


# ---------------------------------------------------------------------------
# ADR-0013 / Issue #1154: Graph-Fakt mit Dokumentherkunft wird seed_corpus
#
# Slice 1 (#1152) führt document_id/chunk_id bis ins Retrieval. Erst hier
# entsteht daraus ein Dokumentfakt: ohne dieses Mapping blieb jeder Fakt
# graph_relation, has_agent_grounded_evidence war unerfüllbar und Claims
# waren auf low gedeckelt.
# ---------------------------------------------------------------------------


def _search_result_with_provenance(provenance):
    return SearchResult(
        facts=["Die Domain wird seit 2019 unter demselben Namen betrieben."],
        edges=[],
        nodes=[],
        query="domainhistorie",
        total_count=1,
        fact_provenance=provenance,
    )


def _records(agent):
    return list(agent.evidence_map["evidence_index"].values())


def test_fact_with_document_provenance_becomes_seed_corpus_evidence() -> None:
    agent = _make_agent()

    agent._record_tool_evidence(
        tool_name="quick_search",
        parameters={},
        structured_result=_search_result_with_provenance(
            [{"document_id": "doc_a1b2c3d4", "chunk_id": 7}]
        ),
        rendered_result="",
        section_index=1,
    )

    records = _records(agent)
    assert len(records) == 1
    record = records[0]
    assert record["type"] == "seed_document"
    assert record["source_kind"] == "seed_corpus"
    assert record["source_id_anchor"] == "seed_doc:doc_a1b2c3d4#chunk:7"
    assert EVIDENCE_ID_RE.match(record["evidence_id"])


def test_fact_without_document_provenance_stays_graph_relation() -> None:
    """Kein Raten: ohne verifizierte Herkunft bleibt es eine Graph-Relation."""
    agent = _make_agent()

    agent._record_tool_evidence(
        tool_name="quick_search",
        parameters={},
        structured_result=_search_result_with_provenance([]),
        rendered_result="",
        section_index=1,
    )

    records = _records(agent)
    assert len(records) == 1
    assert records[0]["type"] == "graph_fact"
    assert records[0]["source_kind"] == "graph_relation"
    assert records[0].get("source_id_anchor") is None


def test_seed_document_identity_follows_the_chunk_not_the_fact_text() -> None:
    """Derselbe Chunk ist dieselbe Quelle — auch bei anders formuliertem Fakt.

    Der Fakt-Text ist LLM-formuliert und variiert zwischen Abfragen; die
    Dokumentstelle nicht. Hinge die Identität weiter am Text, entstünden für
    denselben Beleg mehrere Evidence-Records.
    """
    agent = _make_agent()
    provenance = [{"document_id": "doc_a1b2c3d4", "chunk_id": 7}]

    agent._record_tool_evidence(
        tool_name="quick_search",
        parameters={},
        structured_result=_search_result_with_provenance(provenance),
        rendered_result="",
        section_index=1,
    )
    first_id = _records(agent)[0]["evidence_id"]

    agent._record_tool_evidence(
        tool_name="quick_search",
        parameters={},
        structured_result=SearchResult(
            facts=["Der Betrieb der Domain läuft seit 2019 unverändert."],
            edges=[],
            nodes=[],
            query="andere-query",
            total_count=1,
            fact_provenance=provenance,
        ),
        rendered_result="",
        section_index=2,
    )

    records = _records(agent)
    assert len(records) == 1, "Gleiche Dokumentstelle darf keinen zweiten Record erzeugen."
    assert records[0]["evidence_id"] == first_id


def test_distinct_chunks_of_one_document_stay_distinct_records() -> None:
    agent = _make_agent()

    agent._record_tool_evidence(
        tool_name="quick_search",
        parameters={},
        structured_result=SearchResult(
            facts=["Fakt aus Abschnitt sieben.", "Fakt aus Abschnitt acht."],
            edges=[],
            nodes=[],
            query="domainhistorie",
            total_count=2,
            fact_provenance=[
                {"document_id": "doc_a1b2c3d4", "chunk_id": 7},
                {"document_id": "doc_a1b2c3d4", "chunk_id": 8},
            ],
        ),
        rendered_result="",
        section_index=1,
    )

    anchors = {record["source_id_anchor"] for record in _records(agent)}
    assert anchors == {
        "seed_doc:doc_a1b2c3d4#chunk:7",
        "seed_doc:doc_a1b2c3d4#chunk:8",
    }


def test_partial_provenance_list_maps_position_wise() -> None:
    """Die Provenance-Liste ist positionsparallel — Lücken verschieben nichts."""
    agent = _make_agent()

    agent._record_tool_evidence(
        tool_name="quick_search",
        parameters={},
        structured_result=SearchResult(
            facts=["Fakt ohne Herkunft.", "Fakt mit Herkunft."],
            edges=[],
            nodes=[],
            query="domainhistorie",
            total_count=2,
            fact_provenance=[None, {"document_id": "doc_a1b2c3d4", "chunk_id": 3}],
        ),
        rendered_result="",
        section_index=1,
    )

    by_snippet = {record["snippet"]: record for record in _records(agent)}
    assert by_snippet["Fakt ohne Herkunft."]["source_kind"] == "graph_relation"
    assert by_snippet["Fakt mit Herkunft."]["source_kind"] == "seed_corpus"
    assert (
        by_snippet["Fakt mit Herkunft."]["source_id_anchor"]
        == "seed_doc:doc_a1b2c3d4#chunk:3"
    )


# ---------------------------------------------------------------------------
# Anker-Bau: Randfälle
# ---------------------------------------------------------------------------


def test_chunk_id_zero_is_a_valid_anchor() -> None:
    """Der erste Chunk eines Dokuments hat die Nummer 0.

    Eine Falsy-Prüfung statt einer Typprüfung würde genau ihn verwerfen und
    ausgerechnet den Dokumentanfang um seinen Beleg bringen.
    """
    from app.services.report_agent.evidence import build_seed_document_anchor

    assert (
        build_seed_document_anchor({"document_id": "doc_a1b2c3d4", "chunk_id": 0})
        == "seed_doc:doc_a1b2c3d4#chunk:0"
    )


def test_incomplete_or_malformed_provenance_yields_no_anchor() -> None:
    from app.services.report_agent.evidence import build_seed_document_anchor

    # Ohne chunk_id zeigte der Anker auf ein ganzes Dokument statt auf die
    # Fundstelle — nicht überprüfbar, also kein Anker.
    assert build_seed_document_anchor({"document_id": "doc_a1b2c3d4"}) is None
    assert build_seed_document_anchor({"chunk_id": 3}) is None
    assert build_seed_document_anchor({"document_id": "  ", "chunk_id": 3}) is None
    assert build_seed_document_anchor(None) is None
    assert build_seed_document_anchor("seed_doc:x#chunk:1") is None
    # bool ist in Python ein int — als Chunk-Nummer trotzdem sinnlos.
    assert build_seed_document_anchor({"document_id": "doc_x", "chunk_id": True}) is None
    # Der Anker ist im Vertrag auf 200 Zeichen begrenzt; gekappt wäre er nicht
    # mehr auflösbar.
    assert build_seed_document_anchor({"document_id": "d" * 200, "chunk_id": 1}) is None


def test_builder_rejects_what_the_reader_would_reject() -> None:
    """Schreib- und Lesepfad teilen dieselbe Regel.

    Ein Record, den der Bau für verankert hält und der Leser nicht, würde bei
    jedem Laden abgestuft und umgeschlüsselt — sein Beleg wechselte dauerhaft
    die Identität (CodeRabbit-Review PR #1166).
    """
    from app.services.report_agent.evidence import (
        build_seed_document_anchor,
        is_verified_seed_document_anchor,
    )

    # Eine Dokument-ID mit '#' zerlegte den Anker an der falschen Stelle.
    assert build_seed_document_anchor({"document_id": "doc#x", "chunk_id": 1}) is None
    # Negative Chunk-Nummern gibt es nicht.
    assert build_seed_document_anchor({"document_id": "doc_x", "chunk_id": -1}) is None

    for provenance in (
        {"document_id": "doc_a1b2c3d4", "chunk_id": 0},
        {"document_id": "doc_a1b2c3d4", "chunk_id": 12345},
    ):
        anchor = build_seed_document_anchor(provenance)
        assert anchor and is_verified_seed_document_anchor(anchor)


def test_is_verified_seed_document_anchor_accepts_only_the_canonical_format() -> None:
    from app.services.report_agent.evidence import is_verified_seed_document_anchor

    assert is_verified_seed_document_anchor("seed_doc:doc_a1b2c3d4#chunk:7")
    assert is_verified_seed_document_anchor("seed_doc:doc_a1b2c3d4#chunk:0")
    assert not is_verified_seed_document_anchor("seed_doc:doc_a1b2c3d4")
    assert not is_verified_seed_document_anchor("seed_doc:doc_a1b2c3d4#chunk:sieben")
    assert not is_verified_seed_document_anchor("web:https://example.com")
    assert not is_verified_seed_document_anchor(None)
    assert not is_verified_seed_document_anchor("")
