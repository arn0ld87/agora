"""
Tests fuer Smoke-02-Fixes in plan_outline():
- max_tokens=16384 wird an chat_json uebergeben
- force_no_thinking=True wird an chat_json uebergeben
- Retry-Loop bei leerem/invalidem Response (len=0)
- Fehlerpropagation nach zwei aufeinanderfolgenden Fehlern (kein Fallback mehr, #1832)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

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
# Test 4: Fehlerpropagation nach zwei Fehlern (kein Fallback mehr, #1832)
# ---------------------------------------------------------------------------

def test_plan_outline_propagates_after_two_failures():
    """Beide chat_json-Calls raisen -> plan_outline() propagiert den Fehler.

    Seit #1832 plant das Modell die Outline frei; eine Ersatzgliederung gibt es
    nicht mehr. Der zweite Fehler erreicht unveraendert den Aufrufer, damit der
    Workflow in den FAILED-Pfad laeuft statt mit Default-Sections weiterzumachen.
    """
    agent = _make_agent()
    agent.llm.chat_json.side_effect = [
        ValueError("Invalid JSON format from LLM (len=0; likely truncated). Head: "),
        ValueError("Invalid JSON format from LLM (len=0; likely truncated). Head: "),
    ]

    with pytest.raises(ValueError, match="Invalid JSON format from LLM"):
        plan_outline(agent)

    assert agent.llm.chat_json.call_count == 2, (
        f"Erwartet 2 chat_json-Aufrufe (Erstversuch + Retry), erhalten: {agent.llm.chat_json.call_count}"
    )


def test_plan_outline_propagates_section_kind():
    """#1832: Der section_kind aus der LLM-Antwort landet in der Domain-Section.

    Ein unbekanntes Kind wird auf 'generic' normalisiert, statt die Planung zu
    kippen (Bestandsverhalten fuer Consumer bleibt der Titel-Fallback).
    """
    agent = _make_agent()
    agent.llm.chat_json.return_value = {
        "title": "Smoke-02 Report",
        "summary": "Rauchtest Zusammenfassung",
        "sections": [
            {
                "title": "Stimmen aus dem Kreißsaal",
                "description": "Persona-Stimmen",
                "section_kind": "stakeholder_voices",
            },
            {
                "title": "Beliebiger Abschnitt",
                "description": "Ohne bekannten Kind",
                "section_kind": "unbekannt-xyz",
            },
        ],
    }

    outline = plan_outline(agent)

    assert outline.sections[0].kind == "stakeholder_voices"
    assert outline.sections[1].kind == "generic"
