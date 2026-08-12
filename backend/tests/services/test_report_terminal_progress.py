"""Regressionstests für den terminalen Progress-Event von ``generate_report``.

Issue #1277-2: ``generate_report`` hat am Happy Path unterschiedslos
``stage="completed"`` bei 100 % gesendet, auch wenn ``resolve_report_status``
den Report auf ``INCOMPLETE`` gesetzt hatte. Consumers (WebSocket, Polling,
Streaming-UI) lasen Erfolg für einen Report, den die Pipeline selbst als
unvollständig markiert hatte — genau die Fehldarstellung, die #1006 / P0-7
beseitigen sollte. Der terminale Event muss auf ``report.status`` verzweigen.
"""
from __future__ import annotations

import os
import uuid
from typing import List, Tuple
from unittest.mock import MagicMock, patch

from app.models.report import ReportOutline, ReportSection, ReportStatus


def _make_outline(n_sections: int = 3) -> ReportOutline:
    sections = [
        ReportSection(title=f"Section {i + 1}", content="", description="")
        for i in range(n_sections)
    ]
    return ReportOutline(title="Test Report", summary="Test summary", sections=sections)


def test_generate_report_emits_incomplete_stage_when_required_section_fails(tmp_path):
    """Eine fehlgeschlagene Pflichtsection → Report INCOMPLETE → terminaler
    Progress-Event muss ``stage="incomplete"`` sein, nicht ``"completed"``."""
    from app.services.report_agent.workflow import generate_report

    report_id = f"report_{uuid.uuid4().hex[:12]}"
    agent = MagicMock()
    agent.simulation_id = "sim_test"
    agent.graph_id = "graph_test"
    agent.simulation_requirement = "Test requirement"
    agent.report_logger = MagicMock()
    agent.console_logger = MagicMock()
    agent.evidence_map = {}
    agent.ReportLogger = MagicMock(return_value=MagicMock())
    agent.ReportConsoleLogger = MagicMock(return_value=MagicMock())
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent.persona_ids = ["p1", "p2", "p3", "p4", "p5"]

    outline = _make_outline(3)

    # Section 2 lässt generate_section_react eine Exception werfen.
    # _safe_generate_section_react fängt sie → SECTION_FALLBACK_BODY →
    # process_section markiert die Section als failed → failed_section_indices
    # nicht leer → resolve_report_status liefert INCOMPLETE.
    call_count = [0]

    def fake_generate_section_react(ag, section=None, outline=None, previous_sections=None, progress_callback=None, section_index=0, **kw):
        n = call_count[0]
        call_count[0] += 1
        if n == 1:  # zweite Section (section_index 2) scheitern lassen
            raise RuntimeError("LLM-Call fehlgeschlagen (Simuliert)")
        return f"Content for {section.title}"

    progress_events: List[Tuple[str, int, str]] = []

    def progress_callback(stage: str, pct: int, msg: str) -> None:
        progress_events.append((stage, pct, msg))

    report_folder = str(tmp_path / report_id)
    os.makedirs(report_folder, exist_ok=True)

    with (
        patch("app.services.report_agent.workflow.generate_section_react", side_effect=fake_generate_section_react),
        patch("app.services.report_agent.workflow.generate_section_metadata", return_value={}),
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        patch("app.services.report_agent.workflow.plan_outline_impl", return_value=outline),
        patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
        patch("app.services.report_agent.workflow._load_persona_count", return_value=100),
        patch("app.services.report_agent.workflow.MIN_PERSONA_TABLE_ROWS", 0),
        patch("app.services.report_agent.workflow.validate_quote_anchors", return_value=MagicMock(valid=True)),
        patch("app.services.report_agent.workflow.migrate_v1_to_v2", return_value=None),
    ):
        mock_rm._ensure_report_folder.return_value = report_folder
        mock_rm.get_evidence_map.return_value = None
        mock_rm.get_report.return_value = None
        mock_rm.get_generated_sections.return_value = []
        mock_rm.update_progress.return_value = None
        mock_rm.save_report.return_value = None
        mock_rm.save_outline.return_value = None
        mock_rm.save_section.return_value = None
        mock_rm.assemble_full_report.return_value = "## Section 1\n\ncontent1\n\n## Section 3\n\ncontent3"
        mock_rm._write_json_atomic.side_effect = lambda path, data: None

        with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
            mock_em.model_validate.return_value = MagicMock(
                model_dump=MagicMock(return_value={"schema_version": 2, "report_id": report_id, "simulation_id": "sim_test", "global_evidence": [], "sections": []})
            )

            result = generate_report(
                agent,
                progress_callback=progress_callback,
                report_id=report_id,
                cancel_run_id=None,
            )

    # Der Report ist unvollständig.
    assert result.status == ReportStatus.INCOMPLETE

    # Der terminale Progress-Event (letzter über den Callback) muss
    # stage="incomplete" tragen — vor dem Fix war das "completed" bei 100 %.
    assert progress_events, "kein Progress-Event über den Callback gesendet"
    last_stage, last_pct, last_msg = progress_events[-1]
    assert last_stage == "incomplete", (
        f"terminaler Stage muss 'incomplete' sein, war {last_stage!r}"
    )
    assert last_pct == 100
    assert "incomplete" in last_msg.lower() or "fehl" in last_msg.lower() or result.error in last_msg

    # ReportManager.update_progress muss ebenfalls als letztes mit
    # stage="incomplete" aufgerufen worden sein.
    update_calls = mock_rm.update_progress.call_args_list
    assert update_calls, "update_progress wurde nie aufgerufen"
    terminal_update_args = update_calls[-1]
    assert terminal_update_args.args[1] == "incomplete", (
        f"update_progress terminaler stage muss 'incomplete' sein, war {terminal_update_args.args[1]!r}"
    )


def test_generate_report_emits_completed_stage_when_all_sections_succeed(tmp_path):
    """Happy Path: alle Sections ok → Report COMPLETED → terminaler Event
    ``stage="completed"``. Verhindert, dass der INCOMPLETE-Fix den Happy Path
    versehentlich auf incomplete umdreht."""
    from app.services.report_agent.workflow import generate_report

    report_id = f"report_{uuid.uuid4().hex[:12]}"
    agent = MagicMock()
    agent.simulation_id = "sim_test"
    agent.graph_id = "graph_test"
    agent.simulation_requirement = "Test requirement"
    agent.report_logger = MagicMock()
    agent.console_logger = MagicMock()
    agent.evidence_map = {}
    agent.ReportLogger = MagicMock(return_value=MagicMock())
    agent.ReportConsoleLogger = MagicMock(return_value=MagicMock())
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])
    agent.persona_ids = ["p1", "p2", "p3", "p4", "p5"]

    outline = _make_outline(3)

    def fake_section(ag, section=None, outline=None, previous_sections=None, progress_callback=None, section_index=0, **kw):
        return f"Content for {section.title}"

    progress_events: List[Tuple[str, int, str]] = []

    def progress_callback(stage: str, pct: int, msg: str) -> None:
        progress_events.append((stage, pct, msg))

    report_folder = str(tmp_path / report_id)
    os.makedirs(report_folder, exist_ok=True)

    with (
        patch("app.services.report_agent.workflow.generate_section_react", side_effect=fake_section),
        patch("app.services.report_agent.workflow.generate_section_metadata", return_value={}),
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        patch("app.services.report_agent.workflow.plan_outline_impl", return_value=outline),
        patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
        patch("app.services.report_agent.workflow._load_persona_count", return_value=100),
        patch("app.services.report_agent.workflow.MIN_PERSONA_TABLE_ROWS", 0),
        patch("app.services.report_agent.workflow.validate_quote_anchors", return_value=MagicMock(valid=True)),
        patch("app.services.report_agent.workflow.migrate_v1_to_v2", return_value=None),
    ):
        mock_rm._ensure_report_folder.return_value = report_folder
        mock_rm.get_evidence_map.return_value = None
        mock_rm.get_report.return_value = None
        mock_rm.get_generated_sections.return_value = []
        mock_rm.update_progress.return_value = None
        mock_rm.save_report.return_value = None
        mock_rm.save_outline.return_value = None
        mock_rm.save_section.return_value = None
        mock_rm.assemble_full_report.return_value = "## Section 1\n## Section 2\n## Section 3"
        mock_rm._write_json_atomic.side_effect = lambda path, data: None

        with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
            mock_em.model_validate.return_value = MagicMock(
                model_dump=MagicMock(return_value={"schema_version": 2, "report_id": report_id, "simulation_id": "sim_test", "global_evidence": [], "sections": []})
            )

            result = generate_report(
                agent,
                progress_callback=progress_callback,
                report_id=report_id,
                cancel_run_id=None,
            )

    assert result.status == ReportStatus.COMPLETED
    assert progress_events, "kein Progress-Event über den Callback gesendet"
    last_stage, last_pct, _ = progress_events[-1]
    assert last_stage == "completed", (
        f"terminaler Stage muss 'completed' sein, war {last_stage!r}"
    )
    assert last_pct == 100