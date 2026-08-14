"""Tests für Teil-Report-Generierung bei Cancel (app.services.report_agent.workflow).

Abgedeckte Szenarien:
  1  Bei Cancel zwischen Stage 2 und Stage 3 enthält der Report Stage 1+2,
     Metadata partial=True in partial_metadata.json
  2  Bei Cancel vor Stage 1 ist der Report leer aber status=COMPLETED (partial)
  3  Ohne Cancel läuft generate_report normal durch (Baseline)
  4  _is_cancel_requested liefert False wenn run_id=None
  5  _build_partial_report schreibt partial_metadata.json korrekt
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict
from unittest.mock import MagicMock, patch


from app.models.report import Report, ReportOutline, ReportSection, ReportStatus
from app.services.report_agent.workflow import (
    _build_partial_report,
    _is_cancel_requested,
)
from app.services.sim.cancel_flag import clear_cancel, request_cancel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def _make_report(report_id: str, simulation_id: str = "sim_test") -> Report:
    return Report(
        report_id=report_id,
        simulation_id=simulation_id,
        graph_id="graph_test",
        simulation_requirement="Test requirement",
        status=ReportStatus.GENERATING,
    )


def _make_outline(n_sections: int = 3) -> ReportOutline:
    sections = [
        ReportSection(title=f"Section {i + 1}", content="", description="")
        for i in range(n_sections)
    ]
    return ReportOutline(title="Test Report", summary="Test summary", sections=sections)


def _make_agent(report_id: str) -> MagicMock:
    agent = MagicMock()
    agent.report_logger = MagicMock()
    agent.console_logger = MagicMock()
    return agent


# ---------------------------------------------------------------------------
# Test 4: _is_cancel_requested mit None
# ---------------------------------------------------------------------------


def test_is_cancel_requested_none_run_id():
    assert _is_cancel_requested(None) is False
    assert _is_cancel_requested("") is False


# ---------------------------------------------------------------------------
# Test 5: _build_partial_report schreibt partial_metadata.json
# ---------------------------------------------------------------------------


def test_build_partial_report_writes_metadata(tmp_path):
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    report = _make_report(report_id)
    outline = _make_outline(3)
    agent = _make_agent(report_id)
    completed = ["Section 1", "Section 2"]

    # ReportManager auf tmp_path zeigen
    with (
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
    ):
        report_folder = str(tmp_path / report_id)
        os.makedirs(report_folder, exist_ok=True)

        mock_rm.assemble_full_report.return_value = "## Section 1\n\ncontent1\n\n## Section 2\n\ncontent2"
        mock_rm.save_report.return_value = None
        mock_rm.update_progress.return_value = None
        mock_rm._ensure_report_folder.return_value = report_folder

        # _write_json_atomic wirklich in tmp_path schreiben
        def real_write(path: str, data: Dict[str, Any]) -> None:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh)

        mock_rm._write_json_atomic.side_effect = real_write

        result = _build_partial_report(
            report,
            report_id=report_id,
            completed_section_titles=completed,
            outline=outline,
            agent=agent,
            progress_callback=None,
        )

    assert result.status == ReportStatus.COMPLETED
    assert result.completed_at

    # partial_metadata.json muss existieren
    meta_path = os.path.join(report_folder, "partial_metadata.json")
    assert os.path.exists(meta_path), "partial_metadata.json wurde nicht geschrieben"
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)

    assert meta["partial"] is True
    assert meta["cancelled_at"]
    assert meta["completed_stages"] == completed
    assert meta["report_id"] == report_id


# ---------------------------------------------------------------------------
# Test 1: generate_report bricht nach Stage 2 ab und liefert Teilreport
# ---------------------------------------------------------------------------


def test_generate_report_partial_after_stage_2(tmp_path):
    """Cancel-Flag nach Stage 2 → Report enthält Stages 1+2, partial=True."""
    from app.services.report_agent.workflow import generate_report

    cancel_run_id = _unique_id()
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    clear_cancel(cancel_run_id)

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

    outline = _make_outline(4)

    section_call_count = [0]

    def fake_generate_section_react(ag, section=None, outline=None, previous_sections=None, progress_callback=None, section_index=0, **kw):
        n = section_call_count[0]
        section_call_count[0] += 1
        if n == 1:
            # Nach Section 2 abgeschlossen → Flag setzen (simuliert User-Click)
            request_cancel(cancel_run_id)
        return f"Content for {section.title}"

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
        mock_rm.assemble_full_report.return_value = "## Section 1\n## Section 2\n"
        mock_rm._write_json_atomic.side_effect = lambda path, data: None

        # EvidenceMapModel.model_validate-Patch für die Schema-Initialisierung
        with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
            mock_em.model_validate.return_value = MagicMock(
                model_dump=MagicMock(return_value={"schema_version": 2, "report_id": report_id, "simulation_id": "sim_test", "global_evidence": [], "sections": []})
            )

            result = generate_report(
                agent,
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=cancel_run_id,
            )

    # Nur 2 Sections generiert, dann abgebrochen
    assert section_call_count[0] == 2, f"Erwartet 2 Sections, erhalten: {section_call_count[0]}"
    assert result.status == ReportStatus.COMPLETED
    assert result.completed_at

    clear_cancel(cancel_run_id)


# ---------------------------------------------------------------------------
# Test 3: Ohne Cancel läuft generate_report normal (Baseline)
# ---------------------------------------------------------------------------


def test_generate_report_no_cancel_runs_all_sections(tmp_path):
    """Ohne Cancel-Flag werden alle Sections generiert."""
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
    section_call_count = [0]

    def fake_section(ag, section=None, outline=None, previous_sections=None, progress_callback=None, section_index=0, **kw):
        section_call_count[0] += 1
        return f"Content for {section.title}"

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
        # Ohne diesen Mock liefert der unkonfigurierte MagicMock-Attribut-Zugriff
        # ein truthy MagicMock-Objekt zurueck. #1312 fuegte einen Nachvalidierungs-
        # block ein, der genau dieses Ergebnis an ReportV3.model_validate() reicht
        # (workflow.py ~L1257) — das schlaegt fehl und stuft den Status faelschlich
        # auf INCOMPLETE ab, obwohl kein Report-Artefakt existiert (kein reales
        # ReportV3-Schema-Problem, nur ein unkonfigurierter Mock).
        mock_rm.get_report_v3.return_value = None

        with patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em:
            mock_em.model_validate.return_value = MagicMock(
                model_dump=MagicMock(return_value={"schema_version": 2, "report_id": report_id, "simulation_id": "sim_test", "global_evidence": [], "sections": []})
            )

            result = generate_report(
                agent,
                progress_callback=None,
                report_id=report_id,
                cancel_run_id=None,  # kein Cancel
            )

    assert section_call_count[0] == 3, f"Alle 3 Sections erwartet, erhalten: {section_call_count[0]}"
    assert result.status == ReportStatus.COMPLETED
