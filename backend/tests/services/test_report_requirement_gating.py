"""Integrationstests für Issue #1302 — Requirement-Checker in generate_report.

Die Naht liegt im Abschlussblock von ``generate_report()``: nach den
bestehenden Downgrades (#1006, #1299) und vor dem ersten ``save_report``.
Fehlende Pflichtaspekte werden als ``requirement_checker``-Degradationen an
``report.run_degradations`` angehängt und über die bestehende
``apply_run_degradation_downgrade``-Mechanik auf INCOMPLETE abgestuft —
keine zweite parallele Statuslogik.

Strategie identisch zu ``test_report_status_contract_gating.py`` (#1299):
Agent und ReportManager werden gemockt, damit ``generate_report()`` bis zum
Abschlussblock läuft.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.report import ReportStatus
from app.services.report_agent import ReportAgent
from app.services.report_agent.workflow import generate_report


_EVIDENCE_MAP_WITH_ANCHOR = {
    "schema_version": 2,
    "report_id": "report_req_gating_test",
    "simulation_id": "sim_1302",
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


def _make_agent(*, simulation_requirement: str = "Requirement-Checker-Test") -> object:
    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_1302"
    agent.simulation_id = "sim_1302"
    agent.simulation_requirement = simulation_requirement
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
    # MIN_PERSONA_TABLE_ROWS = 50 (Slice P1.2): vollwertiger Persona-Pool,
    # damit generate_report bis zum Section-Loop läuft.
    agent.persona_ids = [f"persona_{i:02d}" for i in range(1, 51)]
    agent.ReportLogger = MagicMock()
    agent.ReportConsoleLogger = MagicMock()
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent._save_evidence_section = MagicMock()
    agent._get_tools_description = MagicMock(return_value="(keine Tools)")
    return agent


def _make_outline_with_section(section_title: str = "Handlungsempfehlung") -> object:
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


#: Abschnittstext, der alle Default-Requirements erfüllt.
COMPLETE_SECTION_TEXT = (
    "Die Simulation zeigt einen klaren Widerspruch zwischen Betriebsrat und "
    "Geschäftsführung; die Konfliktlinie verläuft entlang der Datenerhebung. "
    "Als Frühwarnindikator dient die Quote ungenutzter Auswertefunktionen. "
    "Die Stop-Bedingung greift, wenn die Akzeptanz unter 60 Prozent sinkt; "
    "die Expand-Bedingung sieht eine stufenweise Ausweitung nach erfolgreichem "
    "Pilot vor. Ein Positionswechsel ist bei der mittleren Führungsebene "
    "möglich. Betriebsrat und Jugendvertretung bilden eine Koalition gegen "
    "die automatisierte Protokollierung.\n\n"
    '<simulated_quote persona_id="persona_01" seed_anchor="ev_valid_001">'
    "Das Angebot überzeugt durch seine Klarheit."
    "</simulated_quote>\n\n"
    "Diese Einschätzung basiert auf den Simulationsdaten."
)

#: Abschnittstext ohne Stop-Bedingungen — sonst vollständig.
TEXT_WITHOUT_STOP_CONDITIONS = COMPLETE_SECTION_TEXT.replace(
    "Die Stop-Bedingung greift, wenn die Akzeptanz unter 60 Prozent sinkt; ",
    "",
)


def _base_report_manager_mock(mock_rm: MagicMock, *, assembled_markdown: str) -> None:
    mock_rm.get_report.return_value = None
    mock_rm.get_generated_sections.return_value = []
    mock_rm.assemble_full_report.return_value = assembled_markdown
    mock_rm._ensure_report_folder.return_value = None
    mock_rm.save_report.return_value = None
    mock_rm.save_outline.return_value = None
    mock_rm.save_section.return_value = None
    mock_rm.update_progress.return_value = None
    mock_rm._clean_section_content.side_effect = lambda text: text
    # Kein persistiertes ReportV3 — isoliert vom #1299-Validierungsblock.
    mock_rm.get_report_v3.return_value = None


def _run_generate(agent, report_id: str, *, assembled_markdown: str, config_enabled: bool | None = None):
    """Führt generate_report mit gemocktem Manager aus und liefert (report, saved_statuses)."""
    from contextlib import ExitStack

    with ExitStack() as stack:
        mock_rm = stack.enter_context(
            patch("app.services.report_agent.workflow.ReportManager")
        )
        mock_plan = stack.enter_context(
            patch("app.services.report_agent.workflow.plan_outline_impl")
        )
        mock_gsr = stack.enter_context(
            patch("app.services.report_agent.workflow.generate_section_react")
        )
        mock_meta = stack.enter_context(
            patch("app.services.report_agent.workflow.generate_section_metadata")
        )
        mock_migrate = stack.enter_context(
            patch("app.services.report_agent.workflow.migrate_v1_to_v2")
        )
        stack.enter_context(
            patch(
                "app.services.report_agent.workflow.validate_required_sections",
                return_value=[],
            )
        )
        if config_enabled is not None:
            stack.enter_context(
                patch(
                    "app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED",
                    config_enabled,
                )
            )

        outline, _section = _make_outline_with_section("Handlungsempfehlung")
        mock_plan.return_value = outline
        mock_gsr.return_value = COMPLETE_SECTION_TEXT
        mock_meta.return_value = {}
        mock_migrate.return_value = _EVIDENCE_MAP_WITH_ANCHOR
        mock_rm.get_evidence_map.return_value = _EVIDENCE_MAP_WITH_ANCHOR
        _base_report_manager_mock(mock_rm, assembled_markdown=assembled_markdown)

        saved_statuses: list[ReportStatus] = []
        mock_rm.save_report.side_effect = lambda r: saved_statuses.append(r.status)
        report = generate_report(agent, report_id=report_id)
    return report, saved_statuses


class TestRequirementGatingInGenerateReport:
    def test_complete_report_stays_completed(self):
        """Integration (Testplan): vollständiger Report → completed erlaubt."""
        report, _saved = _run_generate(
            _make_agent(),
            "report_1302_full",
            assembled_markdown=f"# Test-Report\n\n{COMPLETE_SECTION_TEXT}",
        )
        assert report.status == ReportStatus.COMPLETED
        assert not any(
            entry.get("component") == "requirement_checker"
            for entry in report.run_degradations
        )

    def test_missing_stop_conditions_downgrades_to_incomplete(self):
        """Akzeptanzkriterium + Integration (Testplan): Report ohne
        Stop-Bedingungen → incomplete, Fehlerliste persistiert."""
        report, saved_statuses = _run_generate(
            _make_agent(),
            "report_1302_no_stop",
            assembled_markdown=f"# Test-Report\n\n{TEXT_WITHOUT_STOP_CONDITIONS}",
        )
        assert report.status == ReportStatus.INCOMPLETE

        gaps = [
            entry
            for entry in report.run_degradations
            if entry.get("component") == "requirement_checker"
        ]
        assert {entry["reason"] for entry in gaps} == {"stop_bedingungen_missing"}
        assert all(entry["severity"] == "blocking" for entry in gaps)
        assert report.error and "stop_bedingungen" in report.error
        # Persistiert heißt: der Save nach dem Downgrade trägt den
        # abgestuften Status UND die Degradationsliste.
        assert saved_statuses[-1] == ReportStatus.INCOMPLETE

    def test_explorative_intent_is_not_gated(self):
        """#1322-Lesart: explorative Reports behaupten keine Entscheidungsreife;
        der Checker darf sie nicht dauerhaft INCOMPLETE setzen."""
        agent = _make_agent(simulation_requirement="Erkunde das Szenario, was fällt auf?")
        from app.services.report_intent import detect_report_intent

        assert detect_report_intent(agent.simulation_requirement) is not None  # Vorbedingung
        report, _saved = _run_generate(
            agent,
            "report_1302_explorative",
            assembled_markdown="# Test-Report\n\nReine Beobachtung ohne Empfehlungsaspekte.",
        )
        assert report.status == ReportStatus.COMPLETED

    def test_checker_can_be_disabled_via_config(self):
        """Konfigurierbarkeit: ausgeschaltet → keine Prüfung, Status bleibt COMPLETED."""
        report, _saved = _run_generate(
            _make_agent(),
            "report_1302_disabled",
            assembled_markdown="# Test-Report\n\nOhne geforderte Aspekte.",
            config_enabled=False,
        )
        assert report.status == ReportStatus.COMPLETED
