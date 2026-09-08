"""Tests für die ehrliche Status-Ermittlung von Partial-Reports (Issue #1479).

``_build_partial_report`` setzte den Status bislang bedingungslos auf
``COMPLETED`` — ein nach Cancel oder fehlgeschlagenen Sections unvollständiger
Teil-Report ging so als vollständig erfolgreich hinaus. Dieses Modul deckt
die vier Kernszenarien ab:

  1  Fehlgeschlagene Section → INCOMPLETE mit ``section_generation``-Degradation.
  2  Alle Sections vorhanden, kein Mangel → COMPLETED.
  3  Fallback-Outline (LLM-Planung gescheitert) → Warnung im Degradation-Log.
  4  Cancel mit fehlenden Sections → INCOMPLETE mit ``run_cancellation``-Degradation.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

from app.models.report import Report, ReportOutline, ReportSection, ReportStatus
from app.services.report_agent.run_degradation import (
    collect_run_degradations,
    events_for,
    mark_fallback_outline_used,
)
from app.services.report_agent.workflow import _build_partial_report


def _make_report(report_id: str) -> Report:
    return Report(
        report_id=report_id,
        simulation_id="sim_test",
        graph_id="graph_test",
        simulation_requirement="Test requirement",
        status=ReportStatus.GENERATING,
    )


def _make_outline(n_sections: int) -> ReportOutline:
    sections = [
        ReportSection(title=f"Section {i + 1}", content="", description="")
        for i in range(n_sections)
    ]
    return ReportOutline(title="Test Report", summary="Test summary", sections=sections)


def _make_agent() -> MagicMock:
    agent = MagicMock()
    agent.report_logger = MagicMock()
    agent.console_logger = MagicMock()
    return agent


def _run_partial(
    tmp_path,
    *,
    outline_sections: int,
    completed: list[str],
    failed_section_indices=None,
) -> Report:
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    report = _make_report(report_id)
    outline = _make_outline(outline_sections)
    agent = _make_agent()

    with (
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        # Requirement-Checker ist nicht Gegenstand dieser Tests — dieselbe
        # agent.simulation_requirement-Falle wie in test_partial_report.py.
        patch("app.config.Config.REPORT_REQUIREMENT_CHECKER_ENABLED", False),
    ):
        report_folder = str(tmp_path / report_id)
        os.makedirs(report_folder, exist_ok=True)
        mock_rm.assemble_full_report.return_value = "## Section 1"
        mock_rm._ensure_report_folder.return_value = report_folder
        mock_rm._write_json_atomic.side_effect = lambda path, data: None

        return _build_partial_report(
            report,
            report_id=report_id,
            completed_section_titles=completed,
            outline=outline,
            agent=agent,
            progress_callback=None,
            failed_section_indices=failed_section_indices,
        )


# ---------------------------------------------------------------------------
# Szenario 1: fehlgeschlagene Section → INCOMPLETE
# ---------------------------------------------------------------------------


def test_failed_section_makes_partial_report_incomplete(tmp_path):
    result = _run_partial(
        tmp_path,
        outline_sections=2,
        completed=["Section 1", "Section 2"],
        failed_section_indices=[2],
    )

    section_entries = [
        e for e in result.run_degradations if e["component"] == "section_generation"
    ]
    assert len(section_entries) == 1
    assert section_entries[0]["reason"] == "1_sections_failed"
    assert section_entries[0]["severity"] == "blocking"
    assert result.status == ReportStatus.INCOMPLETE


# ---------------------------------------------------------------------------
# Szenario 2: alle Sections vorhanden, kein Mangel → COMPLETED
# ---------------------------------------------------------------------------


def test_all_sections_present_without_degradation_stays_completed(tmp_path):
    result = _run_partial(
        tmp_path,
        outline_sections=2,
        completed=["Section 1", "Section 2"],
    )

    assert result.run_degradations == []
    assert result.status == ReportStatus.COMPLETED


# ---------------------------------------------------------------------------
# Szenario 3: Fallback-Outline hinterlässt eine Warnung
# ---------------------------------------------------------------------------


def test_fallback_outline_used_is_recorded_as_warning():
    found = collect_run_degradations(fallback_outline_used=True)

    assert len(found) == 1
    assert found[0]["component"] == "outline_planning"
    assert found[0]["reason"] == "fallback_outline_used"
    assert found[0]["severity"] == "warning"


def test_mark_fallback_outline_used_sets_the_event_flag():
    agent = MagicMock()
    assert events_for(agent).fallback_outline_used is False

    mark_fallback_outline_used(agent)

    assert events_for(agent).fallback_outline_used is True


def test_plan_outline_marks_fallback_outline_used_on_planning_failure():
    """``plan_outline`` muss den Rückfallpfad am Agenten markieren — sonst
    weiss der spätere Bericht nichts von der Ersatz-Gliederung."""
    from app.services.report_agent.planning import plan_outline

    agent = MagicMock()
    agent.graph_id = "graph_test"
    agent.simulation_requirement = "Test requirement"
    agent.graph_tools.get_simulation_context.return_value = {
        "graph_statistics": {"total_nodes": 0, "total_edges": 0, "entity_types": {}},
        "total_entities": 0,
        "related_facts": [],
    }
    agent.llm.chat_json.side_effect = RuntimeError("LLM nicht erreichbar")

    outline = plan_outline(agent)

    assert len(outline.sections) == 3  # festes Ersatzschema
    assert events_for(agent).fallback_outline_used is True


def test_fallback_outline_warning_does_not_downgrade_status_alone(tmp_path):
    """Eine Warnung allein ist kein blockierender Mangel — anders als
    ``run_cancellation`` oder ``section_generation``."""
    result = _run_partial(
        tmp_path,
        outline_sections=1,
        completed=["Section 1"],
    )
    # Baseline ohne Fallback-Outline bleibt COMPLETED (siehe Szenario 2);
    # hier wird direkt gegen die Aggregationsfunktion geprüft, dass eine
    # Fallback-Outline-Warnung für sich genommen nicht herabstuft.
    from app.services.report_agent.run_degradation import (
        apply_run_degradation_downgrade,
    )

    degradations = collect_run_degradations(fallback_outline_used=True)
    status = apply_run_degradation_downgrade(ReportStatus.COMPLETED, degradations)
    assert status == ReportStatus.COMPLETED
    assert result.status == ReportStatus.COMPLETED


# ---------------------------------------------------------------------------
# Szenario 4: Cancel mit fehlenden Sections → INCOMPLETE
# ---------------------------------------------------------------------------


def test_cancel_with_missing_sections_makes_partial_report_incomplete(tmp_path):
    result = _run_partial(
        tmp_path,
        outline_sections=4,
        completed=["Section 1", "Section 2"],
    )

    cancellation_entries = [
        e for e in result.run_degradations if e["component"] == "run_cancellation"
    ]
    assert len(cancellation_entries) == 1
    assert cancellation_entries[0]["reason"] == "2_sections_missing_after_cancel"
    assert cancellation_entries[0]["severity"] == "blocking"
    assert result.status == ReportStatus.INCOMPLETE


def test_collect_run_degradations_cancellation_helper_ignores_non_positive_counts():
    assert collect_run_degradations(cancelled_missing_section_count=0) == []


# ---------------------------------------------------------------------------
# Bestätigender Test (Fix 5): ein INCOMPLETE-Report — jetzt auch aus Cancel-
# bedingt fehlenden Sections — exportiert die Outline nicht als Contract-
# Bestandteil. ``build_report_contract_model`` behandelte das bereits korrekt;
# kein Codeänderungsbedarf, aber die neu erreichbaren INCOMPLETE-Fälle
# brauchen einen Nachweis, dass die bestehende Weiche weiterhin greift.
# ---------------------------------------------------------------------------


def test_incomplete_partial_report_exports_without_outline(tmp_path):
    from app.services.report_export import ReportExportService

    result = _run_partial(
        tmp_path,
        outline_sections=4,
        completed=["Section 1", "Section 2"],
    )
    assert result.status == ReportStatus.INCOMPLETE

    contract_model = ReportExportService.build_report_contract_model(result)

    assert contract_model.outline is None
