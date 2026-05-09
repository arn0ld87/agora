"""
TDD-Tests fuer plan_outline() in ReportAgent (Issue #274).

Prueft:
- happy-path: LLM-Response mit description -> ReportOutlineModel-valide Sections
- edge-case leeres description aus LLM -> Default-Fill, kein ValidationError
- fallback-Pfad (LLM raised) -> valides Outline mit description >= 1 Zeichen
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.contracts.report_contract import ReportOutlineModel


# ---------------------------------------------------------------------------
# Helper: minimaler ReportAgent ohne echten LLM-Call
# ---------------------------------------------------------------------------

def _make_agent() -> object:
    from app.services.report_agent import ReportAgent

    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_274"
    agent.simulation_id = "sim_274"
    agent.simulation_requirement = "Test-Outline-Requirement"
    agent.llm = MagicMock()
    agent.web_tools = MagicMock()
    agent.graph_tools = MagicMock()
    agent.graph_tools.get_simulation_context.return_value = {
        "graph_statistics": {
            "total_nodes": 10,
            "total_edges": 5,
            "entity_types": {"Person": 3},
        },
        "total_entities": 10,
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


def _to_contract_dict(outline_dict: dict) -> dict:
    """Mappe ReportOutline.to_dict() auf ReportOutlineModel-konformes Dict.

    ReportSection.to_dict() emittiert 'content' (fuer den Markdown-Generator);
    ReportOutlineSectionModel erwartet 'description' und verbietet 'content'
    (extra='forbid'). Die API-Schicht (_map_outline_for_contract) macht dieselbe
    Umformung. Hier bilden wir sie nach, damit die Tests den Contract-Pfad pruefen.
    """
    sections = []
    for raw in outline_dict.get("sections", []):
        sections.append({
            "title": raw.get("title") or "Section",
            "description": raw.get("description") or raw.get("content") or "—",
        })
    return {
        "title": outline_dict.get("title") or "Report",
        "summary": outline_dict.get("summary") or "—",
        "sections": sections,
    }


# ---------------------------------------------------------------------------
# Test 1: happy-path — LLM liefert title + summary + sections mit description
# ---------------------------------------------------------------------------

def test_plan_outline_happy_path_returns_outline_with_description():
    """plan_outline() muss ReportOutline mit description >= 1 Zeichen liefern."""
    agent = _make_agent()
    agent.llm.chat_json.return_value = {
        "title": "Simulation Analysis Report",
        "summary": "Overview of simulation results",
        "sections": [
            {"title": "Scenario Context", "description": "Describes the scenario background"},
            {"title": "Agent Reactions", "description": "How agents responded to events"},
            {"title": "Risk Assessment", "description": "Potential risks identified"},
        ],
    }

    outline = agent.plan_outline()

    # Direkter Test: to_dict() muss 'description' emittieren
    outline_dict = outline.to_dict()
    for raw_section in outline_dict["sections"]:
        assert "description" in raw_section, (
            f"to_dict() emittiert kein 'description'-Feld: {raw_section}"
        )
        assert raw_section["description"], (
            f"'description' ist leer in {raw_section.get('title')!r}"
        )

    # Contract-Validation via Pydantic
    validated = ReportOutlineModel.model_validate(_to_contract_dict(outline_dict))
    assert validated.title == "Simulation Analysis Report"
    assert len(validated.sections) == 3
    for section in validated.sections:
        assert len(section.description) >= 1, (
            f"Section '{section.title}' hat leere description: {section.description!r}"
        )
    assert validated.sections[0].description == "Describes the scenario background"
    assert validated.sections[1].description == "How agents responded to events"
    assert validated.sections[2].description == "Potential risks identified"


# ---------------------------------------------------------------------------
# Test 2: edge-case — leeres description aus LLM -> Default-Fill "—"
# ---------------------------------------------------------------------------

def test_plan_outline_empty_description_gets_default():
    """Leeres description im LLM-Response wird mit '—' aufgefuellt."""
    agent = _make_agent()
    agent.llm.chat_json.return_value = {
        "title": "Szenario-Analyse",
        "summary": "Kurze Zusammenfassung",
        "sections": [
            {"title": "Einleitung", "description": ""},           # leer
            {"title": "Hauptteil", "description": "   "},         # nur Whitespace
            {"title": "Fazit und Ausblick", "description": None},  # None
        ],
    }

    outline = agent.plan_outline()
    outline_dict = outline.to_dict()

    # to_dict() muss description-Feld emittieren
    for raw_section in outline_dict["sections"]:
        assert "description" in raw_section
        assert raw_section["description"], (
            f"Empty-description-Section '{raw_section.get('title')}' hat kein Default"
        )

    # Muss Pydantic-Validation bestehen (description min_length=1)
    validated = ReportOutlineModel.model_validate(_to_contract_dict(outline_dict))
    for section in validated.sections:
        assert len(section.description) >= 1, (
            f"Section '{section.title}' hat leere description nach Default-Fill: "
            f"{section.description!r}"
        )


# ---------------------------------------------------------------------------
# Test 3: fallback-Pfad — LLM raised -> valides Outline mit description >= 1
# ---------------------------------------------------------------------------

def test_plan_outline_fallback_on_llm_exception():
    """Wenn LLM-Aufruf raised, liefert plan_outline() Default-Outline mit validen descriptions."""
    agent = _make_agent()
    agent.llm.chat_json.side_effect = RuntimeError("Ollama nicht erreichbar")

    outline = agent.plan_outline()
    outline_dict = outline.to_dict()

    # to_dict() muss description-Feld emittieren
    for raw_section in outline_dict["sections"]:
        assert "description" in raw_section
        assert raw_section["description"], (
            f"Fallback-Section '{raw_section.get('title')}' hat kein description"
        )

    validated = ReportOutlineModel.model_validate(_to_contract_dict(outline_dict))
    assert len(validated.sections) >= 2, "Fallback-Outline muss mindestens 2 Sections haben"
    for section in validated.sections:
        assert len(section.description) >= 1, (
            f"Fallback-Section '{section.title}' hat leere description: "
            f"{section.description!r}"
        )


# ---------------------------------------------------------------------------
# Test 3b: M11.8a-Followup — leeres LLM-Outline triggert Fallback
# ---------------------------------------------------------------------------

def test_plan_outline_empty_sections_triggers_fallback():
    """M11.8a-Followup auf Gemini-MEDIUM (PR #335).

    Section-Cap (Min 2 / Max 5) wurde in M11.8a entfernt. Ein leeres
    sections-Array vom LLM darf dadurch NICHT als valide Outline
    durchgehen. plan_outline() muss in den Default-Fallback wechseln,
    statt eine kaputte Zero-Section-Outline zurückzugeben.
    """
    agent = _make_agent()
    agent.llm.chat_json.return_value = {
        "title": "Empty",
        "summary": "Empty",
        "sections": [],
    }

    outline = agent.plan_outline()

    assert len(outline.sections) >= 2, (
        "Empty-Sections-Response muss Fallback-Outline triggern, nicht "
        "leer durchgehen (M11.8a-Followup)."
    )


# ---------------------------------------------------------------------------
# Test 4: Rauch-Test — to_dict() emittiert 'description' fuer jede Section
# ---------------------------------------------------------------------------

def test_plan_outline_to_dict_emits_description_field():
    """
    Rauchtest: plan_outline() baut Sections mit description-Feld.
    Stellt sicher, dass to_dict() das Feld emittiert — so dass _map_outline_for_contract
    in der API-Schicht es korrekt weiterreichen kann.
    """
    agent = _make_agent()
    agent.llm.chat_json.return_value = {
        "title": "Test Report",
        "summary": "Test summary text",
        "sections": [
            {"title": "First Section", "description": "First section detail"},
            {"title": "Second Section", "description": "Second section detail"},
        ],
    }

    outline = agent.plan_outline()
    outline_dict = outline.to_dict()

    for raw_section in outline_dict["sections"]:
        assert "description" in raw_section, (
            f"to_dict() emittiert kein 'description'-Feld fuer Section "
            f"'{raw_section.get('title')}': {raw_section}"
        )
        assert raw_section["description"], (
            f"'description' ist leer in Section '{raw_section.get('title')}'"
        )
