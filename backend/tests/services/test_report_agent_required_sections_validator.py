"""Tests fuer Sub-Slice P1.1 Pflichtabschnitt-Validator im Report-Workflow."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.report import ReportOutline, ReportSection
from app.services.report_agent import ReportAgent, ReportStatus


def _make_agent() -> object:
    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_p11"
    agent.simulation_id = "sim_p11"
    agent.simulation_requirement = "Pflichtabschnitt-Workflow-Test"
    agent.llm = MagicMock()
    agent.web_tools = MagicMock()
    agent.graph_tools = MagicMock()
    agent.tools = {}
    agent.report_logger = None
    agent.console_logger = None
    agent.evidence_map = None
    agent._active_section_evidence = []
    agent._current_section_index = None
    agent._embed_cache = None

    agent.ReportLogger = MagicMock()
    agent.ReportConsoleLogger = MagicMock()
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent._save_evidence_section = MagicMock()
    agent._get_tools_description = MagicMock(return_value="(keine Tools)")
    return agent


def test_generate_report_blocks_incomplete_outline_before_markdown_finalize() -> None:
    """Unvollstaendige Outlines werden als incomplete persistiert, ohne report.md."""
    agent = _make_agent()
    incomplete_outline = ReportOutline(
        title="Unvollstaendig",
        summary="Nur ein Pflichtabschnitt.",
        sections=[
            ReportSection(
                title="Executive Summary",
                description="Stub",
            ),
        ],
    )
    evidence_map = {
        "schema_version": 2,
        "report_id": "report_p11_incomplete",
        "simulation_id": "sim_p11",
        "global_evidence": [],
        "sections": [],
    }
    progress_events: list[tuple[str, int, str]] = []

    with (
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        patch("app.services.report_agent.workflow.plan_outline_impl") as mock_plan,
        patch("app.services.report_agent.workflow.generate_section_react") as mock_gsr,
        patch("app.services.report_agent.workflow.migrate_v1_to_v2") as mock_migrate,
    ):
        mock_plan.return_value = incomplete_outline
        mock_migrate.return_value = evidence_map
        mock_rm.get_evidence_map.return_value = evidence_map
        mock_rm.get_report.return_value = None
        mock_rm.get_generated_sections.return_value = []
        mock_rm._ensure_report_folder.return_value = None
        mock_rm.save_report.return_value = None
        mock_rm.save_outline.return_value = None
        mock_rm.update_progress.return_value = None

        from app.services.report_agent.workflow import generate_report

        report = generate_report(
            agent,
            progress_callback=lambda stage, progress, message: progress_events.append(
                (stage, progress, message)
            ),
            report_id="report_p11_incomplete",
        )

    assert report.status == ReportStatus.INCOMPLETE
    assert report.missing_sections
    assert report.markdown_content == ""
    assert any(event[0] == "incomplete" for event in progress_events)
    mock_gsr.assert_not_called()
    mock_rm.save_section.assert_not_called()
    mock_rm.assemble_full_report.assert_not_called()


def test_generate_report_blocks_when_persona_floor_is_not_met() -> None:
    """P1.2: Vollstaendige Outline reicht nicht, wenn weniger als MIN_PERSONA_TABLE_ROWS Personas existieren."""
    from app.services.report_prompts import DEFAULT_REPORT_SECTIONS

    agent = _make_agent()
    agent.persona_ids = [f"persona_{i}" for i in range(12)]
    complete_outline = ReportOutline(
        title="Vollstaendig",
        summary="Alle Pflichtabschnitte sind vorhanden.",
        sections=[
            ReportSection(title=title, description=description)
            for title, description in DEFAULT_REPORT_SECTIONS
        ],
    )
    evidence_map = {
        "schema_version": 2,
        "report_id": "report_p12_persona_floor",
        "simulation_id": "sim_p11",
        "global_evidence": [],
        "sections": [],
    }

    with (
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        patch("app.services.report_agent.workflow.plan_outline_impl") as mock_plan,
        patch("app.services.report_agent.workflow.generate_section_react") as mock_gsr,
        patch("app.services.report_agent.workflow.migrate_v1_to_v2") as mock_migrate,
    ):
        mock_plan.return_value = complete_outline
        mock_migrate.return_value = evidence_map
        mock_rm.get_evidence_map.return_value = evidence_map
        mock_rm.get_report.return_value = None
        mock_rm.get_generated_sections.return_value = []
        mock_rm._ensure_report_folder.return_value = None
        mock_rm.save_report.return_value = None
        mock_rm.save_outline.return_value = None
        mock_rm.update_progress.return_value = None

        from app.services.report_agent.workflow import generate_report

        report = generate_report(agent, report_id="report_p12_persona_floor")

    assert report.status == ReportStatus.INCOMPLETE
    assert report.markdown_content == ""
    assert report.error is not None
    assert "Persona-Mindestanzahl" in report.error
    assert "12/20" in report.error
    mock_gsr.assert_not_called()
    mock_rm.assemble_full_report.assert_not_called()
