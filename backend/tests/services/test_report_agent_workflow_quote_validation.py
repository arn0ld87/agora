"""
TDD-Tests für M11.8e — Repair-Retry-Hook in workflow.py::generate_report().

Prüft:
1. generate_report() bei gültigen Quotes → kein Repair-Retry, kein quote_validation_failed-Flag.
2. generate_report() bei ungültigen Quotes → 1× Repair-Retry, danach
   section.metadata["quote_validation_failed"] = True (wenn Repair auch fehlschlägt).

Strategie: generate_section_react() und ReportManager werden komplett gemockt,
so dass generate_report() den Validierungs-Hook sauber durchläuft.
Analog zu test_report_agent_strict_schema.py (M11.8d).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


from app.services.report_agent import ReportAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EVIDENCE_MAP_WITH_ANCHOR = {
    "schema_version": 2,
    "report_id": "report_wf_test",
    "simulation_id": "sim_m118e",
    "global_evidence": [
        {
            "type": "graph_fact",
            "source": "test",
            "snippet": "Snippet",
            "source_id_anchor": "ev_valid_001",
        }
    ],
    "sections": [],
}


def _make_agent() -> object:
    """Minimaler ReportAgent-Stub ohne echten LLM-Call."""
    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_m118e"
    agent.simulation_id = "sim_m118e"
    agent.simulation_requirement = "Quote-Validation-Workflow-Test"
    agent.llm = MagicMock()
    agent.llm.chat_json.return_value = {"section_title": "Test", "key_takeaways": [], "data_gaps": []}
    agent.web_tools = MagicMock()
    agent.graph_tools = MagicMock()
    agent.tools = {}
    agent.report_logger = None
    agent.console_logger = None
    agent.evidence_map = dict(_EVIDENCE_MAP_WITH_ANCHOR)
    agent._active_section_evidence = []
    agent._current_section_index = None
    agent._embed_cache = None
    agent.persona_ids = ["persona_01"]

    # ReportAgent-Klassen und Methoden-Stubs
    agent.ReportLogger = MagicMock()
    agent.ReportConsoleLogger = MagicMock()
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent._save_evidence_section = MagicMock()
    agent._get_tools_description = MagicMock(return_value="(keine Tools)")
    return agent


def _make_outline_with_section(section_title: str = "Persona-Reaktionen") -> object:
    """Minimaler Outline-Stub mit einer Section."""
    section = MagicMock()
    section.title = section_title
    section.content = ""
    section.metadata = {}

    outline = MagicMock()
    outline.title = "Test-Report"
    outline.summary = "Zusammenfassung."
    outline.sections = [section]
    outline.to_dict = MagicMock(return_value={})
    return outline, section


def _valid_section_text(persona_id: str = "persona_01") -> str:
    """Section-Text mit einem gültigen <simulated_quote>-Tag."""
    return (
        f"Die Simulation zeigt klare Reaktionen:\n\n"
        f'<simulated_quote persona_id="{persona_id}" seed_anchor="ev_valid_001">'
        f"Das Angebot überzeugt durch seine Klarheit."
        f"</simulated_quote>\n\n"
        f"Diese Einschätzung basiert auf den Simulationsdaten."
    )


def _invalid_section_text() -> str:
    """Section-Text mit ungültigem Quote (fehlt persona_id)."""
    return (
        "Einige Personas zeigen Skepsis:\n\n"
        '<simulated_quote seed_anchor="ev_valid_001">'
        "Ich bin skeptisch."
        "</simulated_quote>"
    )


# ---------------------------------------------------------------------------
# Test 1: Gültige Quotes → kein Repair-Retry, kein quote_validation_failed
# ---------------------------------------------------------------------------

class TestWorkflowValidQuotes:
    def test_valid_quotes_no_repair_no_flag(self):
        """Bei gültigen Quotes: validate_quote_anchors gibt valid=True zurück,
        kein Repair-Retry (generate_section_react wird genau 1× pro Section aufgerufen),
        section.metadata bekommt KEIN quote_validation_failed-Flag."""
        agent = _make_agent()
        outline, section = _make_outline_with_section("Persona-Reaktionen")
        valid_text = _valid_section_text()

        with (
            patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
            patch("app.services.report_agent.workflow.plan_outline_impl") as mock_plan,
            patch("app.services.report_agent.workflow.generate_section_react") as mock_gsr,
            patch("app.services.report_agent.workflow.generate_section_metadata") as mock_meta,
            patch("app.services.report_agent.workflow.migrate_v1_to_v2") as mock_migrate,
            patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
        ):
            mock_plan.return_value = outline
            mock_gsr.return_value = valid_text
            mock_meta.return_value = {}
            # migrate_v1_to_v2 muss truthy zurückgeben, damit agent.evidence_map
            # nicht durch _collect_simulation_evidence_items() überschrieben wird
            mock_migrate.return_value = _EVIDENCE_MAP_WITH_ANCHOR
            mock_rm.get_evidence_map.return_value = _EVIDENCE_MAP_WITH_ANCHOR
            mock_rm.get_report.return_value = None
            mock_rm.get_generated_sections.return_value = []
            mock_rm.assemble_full_report.return_value = "# Test-Report\n\nInhalt."
            mock_rm._ensure_report_folder.return_value = None
            mock_rm.save_report.return_value = None
            mock_rm.save_outline.return_value = None
            mock_rm.save_section.return_value = None
            mock_rm.update_progress.return_value = None
            mock_rm._clean_section_content.return_value = valid_text

            from app.services.report_agent.workflow import generate_report
            generate_report(agent, report_id="report_wf_valid_01")

        # generate_section_react muss genau 1× aufgerufen worden sein (kein Repair)
        assert mock_gsr.call_count == 1, (
            f"Kein Repair-Retry erwartet, generate_section_react wurde "
            f"{mock_gsr.call_count}× aufgerufen"
        )

        # KEIN quote_validation_failed-Flag
        assert not section.metadata.get("quote_validation_failed", False), (
            f"quote_validation_failed darf bei gültigen Quotes NICHT gesetzt sein. "
            f"Metadata: {section.metadata!r}"
        )


# ---------------------------------------------------------------------------
# Test 2: Ungültige Quotes → Repair-Retry, dann quote_validation_failed=True
# ---------------------------------------------------------------------------

class TestWorkflowInvalidQuotesRepairRetry:
    def test_invalid_quotes_triggers_repair_then_sets_flag(self):
        """Bei ungültigen Quotes: 1× Repair-Retry (generate_section_react 2× aufgerufen),
        nach zwei Fehlschlägen → section.metadata["quote_validation_failed"] = True."""
        agent = _make_agent()
        outline, section = _make_outline_with_section("Persona-Reaktionen")
        invalid_text = _invalid_section_text()

        with (
            patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
            patch("app.services.report_agent.workflow.plan_outline_impl") as mock_plan,
            patch("app.services.report_agent.workflow.generate_section_react") as mock_gsr,
            patch("app.services.report_agent.workflow.generate_section_metadata") as mock_meta,
            patch("app.services.report_agent.workflow.migrate_v1_to_v2") as mock_migrate,
            patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
        ):
            mock_plan.return_value = outline
            # Beide generate_section_react-Aufrufe liefern ungültigen Text
            mock_gsr.return_value = invalid_text
            mock_meta.return_value = {}
            # migrate_v1_to_v2 muss truthy zurückgeben (leere evidence_map)
            empty_evidence_map = {
                "schema_version": 2,
                "report_id": "report_wf_invalid_01",
                "simulation_id": "sim_m118e",
                "global_evidence": [],  # kein ev_valid_001 → unbound → ungültig
                "sections": [],
            }
            mock_migrate.return_value = empty_evidence_map
            mock_rm.get_evidence_map.return_value = empty_evidence_map
            mock_rm.get_report.return_value = None
            mock_rm.get_generated_sections.return_value = []
            mock_rm.assemble_full_report.return_value = "# Test-Report\n\nInhalt."
            mock_rm._ensure_report_folder.return_value = None
            mock_rm.save_report.return_value = None
            mock_rm.save_outline.return_value = None
            mock_rm.save_section.return_value = None
            mock_rm.update_progress.return_value = None
            mock_rm._clean_section_content.return_value = invalid_text

            from app.services.report_agent.workflow import generate_report
            generate_report(agent, report_id="report_wf_invalid_01")

        # generate_section_react muss 2× aufgerufen worden sein (1 initial + 1 repair)
        assert mock_gsr.call_count == 2, (
            f"Genau 1 Repair-Retry erwartet (2 generate_section_react-Aufrufe), "
            f"tatsächlich: {mock_gsr.call_count}×"
        )

        # quote_validation_failed MUSS gesetzt sein
        assert section.metadata.get("quote_validation_failed") is True, (
            f"section.metadata[\"quote_validation_failed\"] muss True sein. "
            f"Tatsächliche Metadata: {section.metadata!r}"
        )
