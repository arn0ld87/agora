"""
Tests fuer Smoke-02-Fixes in plan_outline():
- max_tokens=16384 wird an chat_json uebergeben
- force_no_thinking=True wird an chat_json uebergeben
- Retry-Loop bei leerem/invalidem Response (len=0)
- Fallback nach zwei aufeinanderfolgenden Fehlern liefert 3-Sections-Default
"""
from __future__ import annotations

from unittest.mock import MagicMock


from app.services.report_agent.planning import plan_outline


# ---------------------------------------------------------------------------
# Helper: minimaler ReportAgent analog zu test_report_agent_outline.py
# ---------------------------------------------------------------------------

def _make_agent() -> object:
    from app.services.report_agent import ReportAgent

    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_smoke02"
    agent.simulation_id = "sim_smoke02"
    agent.simulation_requirement = "Smoke-02 Requirement"
    agent.llm = MagicMock()
    agent.web_tools = MagicMock()
    agent.graph_tools = MagicMock()
    agent.graph_tools.get_simulation_context.return_value = {
        "graph_statistics": {
            "total_nodes": 5,
            "total_edges": 3,
            "entity_types": {"Person": 2},
        },
        "total_entities": 5,
        "related_facts": [],
    }
    agent.tools = {}
    agent.report_logger = None
    agent.console_logger = None
    agent.evidence_map = None
    agent._active_section_evidence = []
    agent._current_section_index = None
    agent._embed_cache = None
    return agent


def _valid_outline_response() -> dict:
    return {
        "title": "Smoke-02 Report",
        "summary": "Rauchtest Zusammenfassung",
        "sections": [
            {"title": "Befunde", "description": "Kernbefunde der Simulation"},
            {"title": "Reaktionen", "description": "Persona-Reaktionen auf Ereignisse"},
            {"title": "Ausblick", "description": "Identifizierte Trends und Risiken"},
        ],
    }


# ---------------------------------------------------------------------------
# Test 1: max_tokens=16384 wird uebergeben
# ---------------------------------------------------------------------------

def test_plan_outline_passes_max_tokens_16384():
    """plan_outline() muss chat_json mit max_tokens=16384 aufrufen."""
    agent = _make_agent()
    agent.llm.chat_json.return_value = _valid_outline_response()

    plan_outline(agent)

    agent.llm.chat_json.assert_called_once()
    _, kwargs = agent.llm.chat_json.call_args
    assert kwargs.get("max_tokens") == 16384, (
        f"Erwartet max_tokens=16384, erhalten: {kwargs.get('max_tokens')}"
    )


# ---------------------------------------------------------------------------
# Test 2: force_no_thinking=True wird uebergeben
# ---------------------------------------------------------------------------

def test_plan_outline_passes_force_no_thinking_true():
    """plan_outline() muss chat_json mit force_no_thinking=True aufrufen."""
    agent = _make_agent()
    agent.llm.chat_json.return_value = _valid_outline_response()

    plan_outline(agent)

    agent.llm.chat_json.assert_called_once()
    _, kwargs = agent.llm.chat_json.call_args
    assert kwargs.get("force_no_thinking") is True, (
        f"Erwartet force_no_thinking=True, erhalten: {kwargs.get('force_no_thinking')}"
    )


# ---------------------------------------------------------------------------
# Test 3: Retry bei leerem/invalidem Response
# ---------------------------------------------------------------------------

def test_plan_outline_retries_on_empty_response():
    """Erster chat_json-Call raised ValueError(len=0), zweiter liefert valides Outline.

    Erwartet: chat_json.call_count == 2, zweiter Call hat max_tokens=24576, temperature=0.1.
    """
    agent = _make_agent()
    agent.llm.chat_json.side_effect = [
        ValueError(
            "Invalid JSON format from LLM (len=0; likely truncated). Head: "
        ),
        _valid_outline_response(),
    ]

    outline = plan_outline(agent)

    assert agent.llm.chat_json.call_count == 2, (
        f"Erwartet 2 chat_json-Aufrufe, erhalten: {agent.llm.chat_json.call_count}"
    )
    # Zweiter Call: max_tokens=24576, temperature=0.1
    _, second_kwargs = agent.llm.chat_json.call_args_list[1]
    assert second_kwargs.get("max_tokens") == 24576, (
        f"Retry-Call: erwartet max_tokens=24576, erhalten: {second_kwargs.get('max_tokens')}"
    )
    assert second_kwargs.get("temperature") == 0.1, (
        f"Retry-Call: erwartet temperature=0.1, erhalten: {second_kwargs.get('temperature')}"
    )
    # Ergebnis ist valides Outline
    assert len(outline.sections) >= 1


# ---------------------------------------------------------------------------
# Test 4: Fallback nach zwei Fehlern -> Default-Outline mit 3 Sections
# ---------------------------------------------------------------------------

def test_plan_outline_falls_back_after_two_failures():
    """Beide chat_json-Calls raisen -> plan_outline() liefert Default-Outline (3 Sections)."""
    agent = _make_agent()
    agent.llm.chat_json.side_effect = [
        ValueError("Invalid JSON format from LLM (len=0; likely truncated). Head: "),
        ValueError("Invalid JSON format from LLM (len=0; likely truncated). Head: "),
    ]

    outline = plan_outline(agent)

    assert len(outline.sections) == 3, (
        f"Erwartet Default-Fallback mit 3 Sections, erhalten: {len(outline.sections)}"
    )
    for section in outline.sections:
        assert section.description, (
            f"Fallback-Section '{section.title}' hat leere description"
        )
