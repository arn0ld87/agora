"""Issue #1778, Schritt 1.2: Stimme als Feld am Beleg (``voice_key``).

Post und Interview derselben Persona sind eine Stimme: Beide Belege
tragen denselben ``voice_key`` der Form ``agent:<agent_id>``. Belege
ohne Persona (Seed, Graph, Web) tragen ``None``.
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

from app.services.graph.graph_dtos import AgentInterview, InterviewResult, SearchResult
from app.services.report_agent import ReportAgent
from app.services.report_agent.evidence import init_evidence_map


def _make_agent(simulation_id: str = "sim_voice_key") -> ReportAgent:
    """Minimaler ReportAgent-Stub ohne echten LLM-/Graph-Call (Vorlage:
    ``test_report_tool_evidence._make_agent``)."""
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


def test_interview_and_action_item_carry_same_voice_key(monkeypatch) -> None:
    """Interview und Simulationsaktion derselben Persona (agent_id=7)
    erzeugen Belege mit identischem ``voice_key == "agent:7"``."""
    agent = _make_agent()
    result = InterviewResult(
        interview_topic="Positionen",
        interview_questions=["Wie stehen Sie dazu?"],
        interviews=[
            AgentInterview(
                agent_name="Persona Sieben",
                agent_role="Kundin",
                agent_bio="Bio-Text",
                question="Wie stehen Sie dazu?",
                response="Ich lehne die Schließung ab.",
                key_quotes=["Ich lehne die Schließung ab."],
                agent_id=7,
            )
        ],
    )

    agent._record_tool_evidence(
        tool_name="conduct_agent_interview",
        parameters={},
        structured_result=result,
        rendered_result="",
        section_index=1,
    )

    interview_records = [
        r
        for r in (agent.evidence_map or {})["evidence_index"].values()
        if r["type"] == "agent_interview"
    ]
    assert len(interview_records) == 1
    assert interview_records[0]["voice_key"] == "agent:7"

    # Aktions-Beleg derselben Persona über den Sammel-Pfad.
    from app.services.report_agent import agent as agent_module  # noqa: PLC0415

    action_agent = agent_module.ReportAgent.__new__(agent_module.ReportAgent)
    action_agent.simulation_id = "sim_voice_key"
    action_agent.evidence_map = {}

    class _Action:
        def to_dict(self) -> Dict[str, Any]:
            return {
                "action_id": "a007",
                "round_num": 2,
                "action_type": "create_post",
                "platform": "twitter",
                "agent_id": 7,
                "agent_name": "Persona Sieben",
                "action_args": {"content": "Die Schließung verhindern."},
            }

    from app.services.simulation_runner import SimulationRunner  # noqa: PLC0415

    monkeypatch.setattr(
        SimulationRunner,
        "get_all_actions",
        staticmethod(lambda *_a, **_k: [_Action()]),
    )

    items = action_agent._collect_simulation_evidence_items()

    action_items = [item for item in items if item.get("type") == "agent_action"]
    assert action_items, "Die Aktion muss als Evidence-Item auftauchen"
    assert action_items[0]["voice_key"] == "agent:7"


def test_graph_fact_item_has_no_voice_key() -> None:
    """Graph-Fakten stammen von keiner Persona — ``voice_key`` bleibt ``None``."""
    agent = _make_agent()
    result = SearchResult(
        facts=["Fakt eins über den Markt."],
        edges=[],
        nodes=[],
        query="marktanalyse",
        total_count=1,
    )

    agent._record_tool_evidence(
        tool_name="quick_search",
        parameters={},
        structured_result=result,
        rendered_result="",
        section_index=2,
    )

    fact_records = [
        r
        for r in (agent.evidence_map or {})["evidence_index"].values()
        if r["type"] == "graph_fact"
    ]
    assert len(fact_records) == 1
    assert fact_records[0].get("voice_key") is None
