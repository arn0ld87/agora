"""Regressionstest: der Wechsel nach ``generating`` wird sofort persistiert.

Beobachtet an ``report_238ba4371858`` (gns3, 11.10.2026): ``meta.json`` stand
während der gesamten Abschnittserzeugung auf ``planning``. ``generate_report``
setzte ``ReportStatus.GENERATING`` nur am Objekt im Speicher; gespeichert wurde
erst nach dem ersten fertigen Abschnitt. Fassungsliste und Bericht-Reiter lesen
den Status aus ``meta.json`` und zeigten deshalb die falsche Phase.
"""
from __future__ import annotations

import os
import uuid
from typing import List
from unittest.mock import MagicMock, patch

from app.models.report import ReportOutline, ReportSection, ReportStatus


def _make_outline(n_sections: int = 2) -> ReportOutline:
    sections = [
        ReportSection(title=f"Section {i + 1}", content="", description="Szenariobezogene Analyse")
        for i in range(n_sections)
    ]
    return ReportOutline(title="Test Report", summary="Test summary", sections=sections)


def test_generating_status_is_saved_before_first_section(tmp_path):
    from app.services.report_agent.workflow import generate_report

    report_id = f"report_{uuid.uuid4().hex[:12]}"
    agent = MagicMock()
    agent.simulation_id = "sim_test"
    agent.graph_id = "graph_test"
    agent.simulation_requirement = "Test requirement"
    agent.report_logger = MagicMock()
    agent.console_logger = MagicMock()
    agent.evidence_map = {}
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent.persona_ids = ["p1", "p2", "p3", "p4", "p5"]

    # Gemeinsame Zeitleiste: gespeicherte Status und Abschnittsstarts.
    timeline: List[str] = []

    def fake_section(ag, section=None, **kw):
        timeline.append("section")
        return f"Content for {section.title}"

    def record_save(report, **kw):
        timeline.append(f"save:{report.status.value}")

    os.makedirs(tmp_path / report_id, exist_ok=True)

    with (
        patch("app.services.report_agent.workflow.generate_section_react", side_effect=fake_section),
        patch("app.services.report_agent.workflow.generate_section_metadata", return_value={}),
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        patch("app.services.report_agent.workflow.plan_outline_impl", return_value=_make_outline()),
        patch("app.services.report_agent.workflow._load_persona_count", return_value=100),
        patch("app.services.report_agent.workflow.MIN_PERSONA_TABLE_ROWS", 0),
        patch("app.services.report_agent.workflow.validate_quote_anchors", return_value=MagicMock(valid=True)),
        patch("app.services.report_agent.workflow.migrate_v1_to_v2", return_value=None),
        patch("app.services.report_agent.workflow.EvidenceMapModel"),
    ):
        mock_rm._ensure_report_folder.return_value = str(tmp_path / report_id)
        mock_rm.get_evidence_map.return_value = None
        mock_rm.get_report.return_value = None
        mock_rm.get_generated_sections.return_value = []
        mock_rm.save_report.side_effect = record_save
        mock_rm.assemble_full_report.return_value = "## Section 1\n## Section 2\n"
        mock_rm._write_json_atomic.side_effect = lambda path, data: None
        mock_rm.get_report_v3.return_value = None

        generate_report(agent, progress_callback=None, report_id=report_id, cancel_run_id=None)

    assert "section" in timeline, "kein Abschnitt erzeugt — Testaufbau prüfen"
    first_section = timeline.index("section")
    saved_before = timeline[:first_section]
    assert saved_before and saved_before[-1] == f"save:{ReportStatus.GENERATING.value}", (
        f"vor dem ersten Abschnitt muss 'generating' gespeichert sein, Zeitleiste: {timeline}"
    )
