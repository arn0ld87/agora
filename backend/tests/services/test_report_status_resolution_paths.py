"""Charakterisierungstests für ``ReportStatusService.get_status``.

``get_status`` löst den Status über eine Kette von Strategien auf: Run-Registry,
persistierter Report, Live-Task, Simulation, Fallback. Vor diesen Tests war nur
die erste Stufe abgedeckt (``test_report_status_incomplete_propagation.py``,
Issue #1277-2) — bei cyclomatic complexity 41.

Diese Tests beschreiben das Verhalten **wie es ist**, nicht wie es sein sollte.
Sie sind die Absicherung für die Zerlegung des Stage-Branchings; jede Abweichung
nach dem Umbau ist damit ein Befund und keine Meinungsfrage.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.models.report import ReportStatus
from app.services import report_status as report_status_module
from app.services.report_status import ReportStatusService


def _report(status: ReportStatus, **kwargs) -> MagicMock:
    report = MagicMock()
    report.status = status
    report.outline = kwargs.get("outline")
    report.missing_sections = kwargs.get("missing_sections", [])
    report.simulation_id = kwargs.get("simulation_id")
    report.report_id = kwargs.get("report_id")
    if "error" in kwargs:
        report.error = kwargs["error"]
    return report


@contextmanager
def _layer(
    *,
    run: Optional[dict] = None,
    report: Optional[MagicMock] = None,
    report_by_sim: Optional[MagicMock] = None,
    progress: Optional[dict] = None,
    sections: Optional[list] = None,
    tasks: Optional[list] = None,
    task: Optional[MagicMock] = None,
    tasks_raise: Optional[Exception] = None,
) -> Iterator[MagicMock]:
    """Legt die gesamte Umgebung von ``get_status`` still.

    Liefert die ``TaskManager``-Instanz, damit Tests deren Aufrufe prüfen können.
    """
    task_manager = MagicMock()
    task_manager.get_task.return_value = task
    if tasks_raise is not None:
        task_manager.list_tasks.side_effect = tasks_raise
    else:
        task_manager.list_tasks.return_value = tasks or []

    with patch.object(
        report_status_module.run_registry, "get_latest_by_linked_id", return_value=run
    ), patch.object(
        report_status_module.ReportManager, "get_progress", return_value=progress or {}
    ), patch.object(
        report_status_module.ReportManager, "get_report", return_value=report
    ), patch.object(
        report_status_module.ReportManager,
        "get_generated_sections",
        return_value=sections or [],
    ), patch.object(
        report_status_module.ReportManager,
        "get_report_by_simulation",
        return_value=report_by_sim,
    ), patch.object(
        report_status_module, "TaskManager", return_value=task_manager
    ):
        yield task_manager


class TestRunRegistryPath:
    """Stufe 0 — ein Run in der Registry gewinnt, wenn sein Status terminal ist."""

    @pytest.mark.parametrize(
        "run_status", ["completed", "failed", "paused", "stopped", "processing", "pending"]
    )
    def test_terminal_run_status_short_circuits(self, run_status):
        run = {
            "run_id": "run_1",
            "status": run_status,
            "progress": 42,
            "message": "from run",
            "linked_ids": {"simulation_id": "sim_1"},
        }
        with _layer(run=run, report=_report(ReportStatus.GENERATING)):
            result = ReportStatusService.get_status(report_id="rep_1")

        assert result["status"] == run_status
        assert result["run_id"] == "run_1"
        assert result["simulation_id"] == "sim_1"
        assert result["progress"] == 42

    def test_unknown_run_status_falls_through_to_later_stages(self):
        """Ein Status außerhalb der bekannten Menge beendet die Kette *nicht*."""
        run = {"run_id": "r", "status": "some_new_status", "linked_ids": {}}
        with _layer(run=run, report=_report(ReportStatus.COMPLETED, simulation_id="sim_9")):
            result = ReportStatusService.get_status(report_id="rep_1")

        assert result.get("already_completed") is True
        assert result["status"] == "completed"

    def test_progress_message_wins_over_run_message(self):
        run = {
            "run_id": "r",
            "status": "processing",
            "message": "run message",
            "linked_ids": {},
        }
        with _layer(
            run=run,
            report=_report(ReportStatus.GENERATING),
            progress={"message": "progress message", "completed_sections": [1, 2]},
        ):
            result = ReportStatusService.get_status(report_id="rep_1")

        assert result["message"] == "progress message"
        assert result["current_section_index"] == 2

    def test_generated_sections_are_keyed_by_index(self):
        run = {"run_id": "r", "status": "processing", "linked_ids": {}}
        sections = [
            {"section_index": 1, "content": "eins"},
            {"section_index": 2, "content": "zwei"},
        ]
        with _layer(run=run, report=_report(ReportStatus.GENERATING), sections=sections):
            result = ReportStatusService.get_status(report_id="rep_1")

        assert result["sections"] == {1: {"content": "eins"}, 2: {"content": "zwei"}}

    def test_simulation_id_argument_is_fallback_when_run_has_none(self):
        run = {"run_id": "r", "status": "processing", "linked_ids": {}}
        with _layer(run=run, report=_report(ReportStatus.GENERATING)):
            result = ReportStatusService.get_status(
                report_id="rep_1", simulation_id="sim_arg"
            )

        assert result["simulation_id"] == "sim_arg"


class TestPersistedReportPath:
    """Stufe 1 — ohne Run entscheidet der persistierte Report."""

    def test_completed_report_returns_already_completed(self):
        report = _report(ReportStatus.COMPLETED, simulation_id="sim_2")
        with _layer(report=report):
            result = ReportStatusService.get_status(report_id="rep_2")

        assert result == {
            "simulation_id": "sim_2",
            "report_id": "rep_2",
            "status": "completed",
            "progress": 100,
            "message": "Report generated",
            "already_completed": True,
        }

    def test_failed_report_carries_the_error(self):
        report = _report(ReportStatus.FAILED, simulation_id="sim_3", error="boom")
        with _layer(report=report):
            result = ReportStatusService.get_status(report_id="rep_3")

        assert result["status"] == "failed"
        assert result["error"] == "boom"
        assert result["progress"] == 0

    def test_non_terminal_report_continues_to_task_lookup(self):
        """GENERATING beendet die Kette nicht — es wird nach einem Task gesucht."""
        report = _report(ReportStatus.GENERATING, simulation_id="sim_4")
        task = MagicMock()
        task.to_dict.return_value = {"status": "running", "progress": 50}
        tasks = [{"task_id": "task_7", "metadata": {"report_id": "rep_4"}}]

        with _layer(report=report, tasks=tasks, task=task):
            result = ReportStatusService.get_status(report_id="rep_4")

        assert result["status"] == "running"
        assert result["report_id"] == "rep_4"
        assert result["simulation_id"] == "sim_4"

    def test_task_metadata_supplies_simulation_id_when_report_has_none(self):
        task = MagicMock()
        task.to_dict.return_value = {"status": "running"}
        tasks = [
            {"task_id": "task_8", "metadata": {"report_id": "rep_5", "simulation_id": "sim_meta"}}
        ]

        with _layer(report=None, tasks=tasks, task=task):
            result = ReportStatusService.get_status(report_id="rep_5")

        assert result["simulation_id"] == "sim_meta"

    def test_failing_task_lookup_is_swallowed_and_logged(self):
        """Ein kaputter Task-Store darf den Status-Endpunkt nicht umbringen."""
        with _layer(report=None, tasks_raise=RuntimeError("task store down")):
            result = ReportStatusService.get_status(report_id="rep_6")

        assert result["status"] == "generating"
        assert result["report_id"] == "rep_6"


class TestTaskPath:
    """Stufe 2 — ein lebender Task ist maßgeblich."""

    def test_task_payload_is_enriched_with_ids(self):
        task = MagicMock()
        task.to_dict.return_value = {"status": "running", "progress": 10}

        with _layer(task=task):
            result = ReportStatusService.get_status(
                task_id="task_1", simulation_id="sim_7", report_id="rep_7"
            )

        assert result["status"] == "running"
        assert result["simulation_id"] == "sim_7"
        assert result["report_id"] == "rep_7"

    def test_existing_simulation_id_in_payload_is_not_overwritten(self):
        task = MagicMock()
        task.to_dict.return_value = {"status": "running", "simulation_id": "sim_from_task"}

        with _layer(task=task):
            result = ReportStatusService.get_status(
                task_id="task_2", simulation_id="sim_arg"
            )

        assert result["simulation_id"] == "sim_from_task"

    def test_stale_task_id_falls_through_to_fallback(self):
        """Nach einem Serverneustart ist die Task-ID tot — kein Fehler, weiterpollen."""
        with _layer(task=None):
            result = ReportStatusService.get_status(task_id="gone", report_id="rep_8")

        assert result["status"] == "generating"


class TestSimulationPath:
    """Stufe 3 — nur die Simulation ist bekannt."""

    def test_completed_report_for_simulation(self):
        found = _report(ReportStatus.COMPLETED, report_id="rep_9")
        with _layer(report_by_sim=found):
            result = ReportStatusService.get_status(simulation_id="sim_9")

        assert result["report_id"] == "rep_9"
        assert result["already_completed"] is True

    def test_incomplete_report_for_simulation_falls_back(self):
        found = _report(ReportStatus.GENERATING, report_id="rep_10")
        with _layer(report_by_sim=found):
            result = ReportStatusService.get_status(simulation_id="sim_10")

        assert result["status"] == "generating"
        assert result["report_id"] is None

    def test_simulation_path_is_skipped_when_report_id_is_known(self):
        """Mit report_id greift Stufe 3 nicht — sonst käme ein fremder Report."""
        found = _report(ReportStatus.COMPLETED, report_id="other")
        with _layer(report=None, report_by_sim=found):
            result = ReportStatusService.get_status(
                simulation_id="sim_11", report_id="rep_11"
            )

        assert result["report_id"] == "rep_11"
        assert result["status"] == "generating"


class TestFallbackAndValidation:
    """Stufe 4 — Acknowledge oder Fehler."""

    def test_fallback_acknowledges_polling(self):
        with _layer():
            result = ReportStatusService.get_status(report_id="rep_12")

        assert result == {
            "simulation_id": None,
            "report_id": "rep_12",
            "status": "generating",
            "progress": 0,
            "message": "Task handle unknown — waiting for report completion",
        }

    def test_without_any_identifier_it_raises(self):
        with _layer():
            with pytest.raises(ValueError):
                ReportStatusService.get_status()
