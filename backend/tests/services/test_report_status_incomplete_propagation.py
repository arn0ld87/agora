"""Regressionstests für ``ReportStatusService.get_status`` — Issue #1277-2.

Der terminale Progress-Event aus ``generate_report`` schreibt seit #1277-2
``stage="incomplete"`` in ``progress.json``, wenn der Report INCOMPLETE ist.
Der Polling-Pfad über ``/api/report/generate/status`` las den Status aber aus
der Run-Registry — und ``run_generate`` schreibt den Registry-Status auch bei
INCOMPLETE auf ``"completed"`` (Teilergebnis, kein Fehlschlag, siehe #1006).
Folglich sah der Consumer (``useReportGeneration``) ``status="completed"`` und
nahm den completed-Branch, obwohl der Report unvollständig war.

``get_status`` muss den Report-Status durch den Public-Contract propagieren,
wenn der Run terminal ist.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from unittest.mock import MagicMock, patch

from app.models.report import ReportStatus
from app.services import report_status as report_status_module
from app.services.report_status import ReportStatusService


def _fake_run(run_id: str, status: str, message: str, sim_id: str) -> dict:
    return {
        "run_id": run_id,
        "status": status,
        "progress": 100,
        "message": message,
        "linked_ids": {"simulation_id": sim_id},
    }


def _fake_report(report_status: ReportStatus) -> MagicMock:
    report = MagicMock()
    report.status = report_status
    report.outline = None
    report.missing_sections = []
    return report


@contextmanager
def _patch_status_layer(run: dict, report: MagicMock, progress: dict) -> Iterator[None]:
    with patch.object(
        report_status_module.run_registry,
        "get_latest_by_linked_id",
        return_value=run,
    ), patch.object(
        report_status_module.ReportManager, "get_progress", return_value=progress,
    ), patch.object(
        report_status_module.ReportManager, "get_report", return_value=report,
    ), patch.object(
        report_status_module.ReportManager, "get_generated_sections", return_value=[],
    ):
        yield


def test_get_status_propagates_incomplete_report_status() -> None:
    """#1277-2: Run-Registry 'completed' + Report INCOMPLETE → status='incomplete'.

    Vor dem Fix las ``get_status`` den Status nur aus der Run-Registry; der
    Polling-Consumer sah 'completed' und nahm den completed-Branch, obwohl der
    Report unvollständig war.
    """
    report_id = "report_test_incomplete"
    run = _fake_run("run_1", "completed", "Report generated with degraded claims", "sim_1")
    report = _fake_report(ReportStatus.INCOMPLETE)

    with _patch_status_layer(run, report, {"message": "Report generation incomplete"}):
        result = ReportStatusService.get_status(report_id=report_id)

    assert result["status"] == "incomplete", (
        f"INCOMPLETE-Report muss als 'incomplete' propagiert werden, war {result['status']!r}"
    )
    assert result["report_id"] == report_id
    assert result["run_id"] == "run_1"


def test_get_status_keeps_completed_for_completed_report() -> None:
    """Guard: COMPLETED-Report → status='completed' (kein false incomplete)."""
    report_id = "report_test_completed"
    run = _fake_run("run_2", "completed", "Report generated", "sim_2")
    report = _fake_report(ReportStatus.COMPLETED)

    with _patch_status_layer(run, report, {"message": "Report generated"}):
        result = ReportStatusService.get_status(report_id=report_id)

    assert result["status"] == "completed"


def test_get_status_keeps_failed_run_status_for_failed_report() -> None:
    """Guard: FAILED-Report → Run-Registry 'failed' → status='failed'.

    Der INCOMPLETE-Fix darf den failed-Pfad nicht verstellen; FAILED bleibt
    'failed' (Run-Registry und Report-Status stimmen hier überein).
    """
    report_id = "report_test_failed"
    run = _fake_run("run_3", "failed", "Report generation failed", "sim_3")
    report = _fake_report(ReportStatus.FAILED)

    with _patch_status_layer(run, report, {"message": "Report generation failed"}):
        result = ReportStatusService.get_status(report_id=report_id)

    assert result["status"] == "failed"