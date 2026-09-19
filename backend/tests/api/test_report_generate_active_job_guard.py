"""Regression für konkurrierende Report-Generierungen derselben Simulation (Issue #1265)."""

import pytest
from unittest.mock import MagicMock, patch
from flask import Flask

from app.services.report_generation import ReportGenerationService
from app.services.simulation_manager import SimulationManager
from app.utils.api_errors import ApiErrorCode


@pytest.fixture
def app():
    """Flask-App für Test-Context."""
    return Flask(__name__)


class TestReportGenerateActiveJobGuard:
    """Tests für den Active-Job-Guard bei Report-Generierung.

    Die Durchlass-Faelle mocken ``_wire_and_enqueue_generation``: geprueft wird der
    Guard vor der Verdrahtung, nicht die Routenaufloesung dahinter. Ohne den Mock
    laeuft der Test bis ``StageModelRouter.resolve`` und scheitert in Umgebungen
    ohne konfigurierte AI-Route (``NoAiRouteCandidateError``).
    """

    def test_active_report_generate_rejects_second_start(self, app: Flask) -> None:
        """Ein laufender report_generate-Run blockiert einen zweiten Start mit 409."""
        simulation_id = "sim_0123456789ab"

        # Mock: Simulation existiert
        with patch.object(SimulationManager, "get_simulation") as mock_get_sim:
            mock_state = MagicMock(project_id="proj_123")
            mock_get_sim.return_value = mock_state

            # Mock: aktiver Run im RunRegistry
            with patch("app.services.report_generation.run_registry") as mock_registry:
                mock_registry.list_runs.return_value = [
                    {
                        "run_id": "run_report_1",
                        "run_type": "report_generate",
                        "status": "processing",
                        "simulation_id": simulation_id,
                    }
                ]

                with pytest.raises(ValueError) as excinfo:
                    ReportGenerationService.start_generation(
                        simulation_id=simulation_id,
                        report_mode="balanced",
                        force_regenerate=False,
                        llm_model_override=None,
                        llm_runtime=MagicMock(enabled=False),
                    )

                assert excinfo.value.args[0] == ApiErrorCode.REPORT_GENERATE_IN_PROGRESS

    def test_pending_report_generate_rejects_second_start(self, app: Flask) -> None:
        """Ein pending report_generate-Run blockiert ebenfalls mit 409."""
        simulation_id = "sim_0123456789ab"

        with patch.object(SimulationManager, "get_simulation") as mock_get_sim:
            mock_state = MagicMock(project_id="proj_123")
            mock_get_sim.return_value = mock_state

            with patch("app.services.report_generation.run_registry") as mock_registry:
                mock_registry.list_runs.return_value = [
                    {
                        "run_id": "run_report_1",
                        "run_type": "report_generate",
                        "status": "pending",
                        "simulation_id": simulation_id,
                    }
                ]

                with pytest.raises(ValueError) as excinfo:
                    ReportGenerationService.start_generation(
                        simulation_id=simulation_id,
                        report_mode="balanced",
                        force_regenerate=False,
                        llm_model_override=None,
                        llm_runtime=MagicMock(enabled=False),
                    )

                assert excinfo.value.args[0] == ApiErrorCode.REPORT_GENERATE_IN_PROGRESS

    def test_completed_report_generate_allows_new_start(self, app: Flask) -> None:
        """Ein abgeschlossener report_generate-Run blockiert NICHT."""
        simulation_id = "sim_0123456789ab"

        with app.app_context():
            # Mock Neo4j storage
            app.extensions['neo4j_storage'] = MagicMock()

            with patch("app.services.report_generation.run_registry") as mock_registry:
                # list_runs filtert intern nach statuses=["pending", "processing"]
                # Ein completed-Run wird daher nicht zurückgegeben
                mock_registry.list_runs.return_value = []

                # Mock SimulationManager und Dependencies
                with patch.object(SimulationManager, "get_simulation") as mock_get_sim:
                    mock_state = MagicMock(
                        project_id="proj_123",
                        graph_id="graph_123",
                        simulation_requirement="Test requirement",
                        branch_name=None,
                        source_simulation_id=None,
                        root_simulation_id=None,
                        branch_depth=0,
                    )
                    mock_get_sim.return_value = mock_state

                    with patch("app.services.report_generation.ProjectManager.get_project") as mock_get_proj:
                        mock_get_proj.return_value = MagicMock(
                            simulation_requirement="Test requirement",
                            llm_profile_id=None,
                        )

                        with patch("app.services.report_generation.RunLifecycle.begin") as mock_lifecycle:
                            mock_run = MagicMock()
                            mock_run.__enter__.return_value = mock_run
                            mock_run.__exit__.return_value = False
                            mock_run.record = {"run_id": "run_report_new"}
                            mock_lifecycle.return_value = mock_run

                            with patch("app.services.report_generation.TaskManager") as mock_task_mgr, \
                                 patch.object(ReportGenerationService, "_wire_and_enqueue_generation"):
                                mock_task_mgr.return_value.create_task.return_value = "task_123"

                                # Should not raise, proceeds to enqueue
                                result = ReportGenerationService.start_generation(
                                    simulation_id=simulation_id,
                                    report_mode="balanced",
                                    force_regenerate=False,
                                    llm_model_override=None,
                                    llm_runtime=MagicMock(enabled=False),
                                )

                                assert result["status"] == "generating"
                                assert result["run_id"] == "run_report_new"

    def test_failed_report_generate_allows_new_start(self, app: Flask) -> None:
        """Ein fehlgeschlagener report_generate-Run blockiert NICHT."""
        simulation_id = "sim_0123456789ab"

        with app.app_context():
            app.extensions['neo4j_storage'] = MagicMock()

            with patch("app.services.report_generation.run_registry") as mock_registry:
                # failed-Runs werden durch statuses=["pending", "processing"] gefiltert
                mock_registry.list_runs.return_value = []

                with patch.object(SimulationManager, "get_simulation") as mock_get_sim:
                    mock_state = MagicMock(
                        project_id="proj_123",
                        graph_id="graph_123",
                        simulation_requirement="Test requirement",
                        branch_name=None,
                        source_simulation_id=None,
                        root_simulation_id=None,
                        branch_depth=0,
                    )
                    mock_get_sim.return_value = mock_state

                    with patch("app.services.report_generation.ProjectManager.get_project") as mock_get_proj:
                        mock_get_proj.return_value = MagicMock(
                            simulation_requirement="Test requirement",
                            llm_profile_id=None,
                        )

                        with patch("app.services.report_generation.RunLifecycle.begin") as mock_lifecycle:
                            mock_run = MagicMock()
                            mock_run.__enter__.return_value = mock_run
                            mock_run.__exit__.return_value = False
                            mock_run.record = {"run_id": "run_report_new"}
                            mock_lifecycle.return_value = mock_run

                            with patch("app.services.report_generation.TaskManager") as mock_task_mgr, \
                                 patch.object(ReportGenerationService, "_wire_and_enqueue_generation"):
                                mock_task_mgr.return_value.create_task.return_value = "task_123"

                                result = ReportGenerationService.start_generation(
                                    simulation_id=simulation_id,
                                    report_mode="balanced",
                                    force_regenerate=False,
                                    llm_model_override=None,
                                    llm_runtime=MagicMock(enabled=False),
                                )

                                assert result["status"] == "generating"

    def test_stopped_report_generate_allows_new_start(self, app: Flask) -> None:
        """Ein gestoppter report_generate-Run blockiert NICHT."""
        simulation_id = "sim_0123456789ab"

        with app.app_context():
            app.extensions['neo4j_storage'] = MagicMock()

            with patch("app.services.report_generation.run_registry") as mock_registry:
                # stopped-Runs werden durch statuses=["pending", "processing"] gefiltert
                mock_registry.list_runs.return_value = []

                with patch.object(SimulationManager, "get_simulation") as mock_get_sim:
                    mock_state = MagicMock(
                        project_id="proj_123",
                        graph_id="graph_123",
                        simulation_requirement="Test requirement",
                        branch_name=None,
                        source_simulation_id=None,
                        root_simulation_id=None,
                        branch_depth=0,
                    )
                    mock_get_sim.return_value = mock_state

                    with patch("app.services.report_generation.ProjectManager.get_project") as mock_get_proj:
                        mock_get_proj.return_value = MagicMock(
                            simulation_requirement="Test requirement",
                            llm_profile_id=None,
                        )

                        with patch("app.services.report_generation.RunLifecycle.begin") as mock_lifecycle:
                            mock_run = MagicMock()
                            mock_run.__enter__.return_value = mock_run
                            mock_run.__exit__.return_value = False
                            mock_run.record = {"run_id": "run_report_new"}
                            mock_lifecycle.return_value = mock_run

                            with patch("app.services.report_generation.TaskManager") as mock_task_mgr, \
                                 patch.object(ReportGenerationService, "_wire_and_enqueue_generation"):
                                mock_task_mgr.return_value.create_task.return_value = "task_123"

                                result = ReportGenerationService.start_generation(
                                    simulation_id=simulation_id,
                                    report_mode="balanced",
                                    force_regenerate=False,
                                    llm_model_override=None,
                                    llm_runtime=MagicMock(enabled=False),
                                )

                                assert result["status"] == "generating"

    def test_different_simulation_not_blocked(self, app: Flask) -> None:
        """Ein aktiver Run für eine andere Simulation blockiert NICHT."""
        simulation_id = "sim_0123456789ab"

        with app.app_context():
            app.extensions['neo4j_storage'] = MagicMock()

            with patch("app.services.report_generation.run_registry") as mock_registry:
                # list_runs filtert auch nach simulation_id
                mock_registry.list_runs.return_value = []

                with patch.object(SimulationManager, "get_simulation") as mock_get_sim:
                    mock_state = MagicMock(
                        project_id="proj_123",
                        graph_id="graph_123",
                        simulation_requirement="Test requirement",
                        branch_name=None,
                        source_simulation_id=None,
                        root_simulation_id=None,
                        branch_depth=0,
                    )
                    mock_get_sim.return_value = mock_state

                    with patch("app.services.report_generation.ProjectManager.get_project") as mock_get_proj:
                        mock_get_proj.return_value = MagicMock(
                            simulation_requirement="Test requirement",
                            llm_profile_id=None,
                        )

                        with patch("app.services.report_generation.RunLifecycle.begin") as mock_lifecycle:
                            mock_run = MagicMock()
                            mock_run.__enter__.return_value = mock_run
                            mock_run.__exit__.return_value = False
                            mock_run.record = {"run_id": "run_report_new"}
                            mock_lifecycle.return_value = mock_run

                            with patch("app.services.report_generation.TaskManager") as mock_task_mgr, \
                                 patch.object(ReportGenerationService, "_wire_and_enqueue_generation"):
                                mock_task_mgr.return_value.create_task.return_value = "task_123"

                                result = ReportGenerationService.start_generation(
                                    simulation_id=simulation_id,
                                    report_mode="balanced",
                                    force_regenerate=False,
                                    llm_model_override=None,
                                    llm_runtime=MagicMock(enabled=False),
                                )

                                assert result["status"] == "generating"

    def test_existing_completed_report_still_reused_when_no_active_run(self, app: Flask) -> None:
        """Ein bereits fertiger Report wird wiederverwendet, wenn kein aktiver Run läuft."""
        simulation_id = "sim_0123456789ab"

        with app.app_context():
            app.extensions['neo4j_storage'] = MagicMock()

            with patch.object(SimulationManager, "get_simulation") as mock_get_sim:
                mock_state = MagicMock(project_id="proj_123")
                mock_get_sim.return_value = mock_state

                with patch("app.services.report_generation.run_registry") as mock_registry:
                    mock_registry.list_runs.return_value = []

                    with patch("app.services.report_generation.ProjectManager.get_project") as mock_get_proj:
                        mock_get_proj.return_value = MagicMock(
                            simulation_requirement="Test requirement",
                            llm_profile_id=None,
                        )

                        with patch("app.services.report_generation.ReportManager.get_report_by_simulation") as mock_get_report:
                            from app.models.report import ReportStatus
                            mock_report = MagicMock()
                            mock_report.report_id = "report_existing"
                            mock_report.status = ReportStatus.COMPLETED
                            mock_get_report.return_value = mock_report

                            result = ReportGenerationService.start_generation(
                                simulation_id=simulation_id,
                                report_mode="balanced",
                                force_regenerate=False,
                                llm_model_override=None,
                                llm_runtime=MagicMock(enabled=False),
                            )

                            assert result["already_generated"] is True
                            assert result["report_id"] == "report_existing"
                            assert result["status"] == "completed"

    def test_force_regenerate_bypasses_reuse_but_respects_active_guard(self, app: Flask) -> None:
        """force_regenerate umgeht Wiederverwendung, aber NICHT den Active-Job-Guard."""
        simulation_id = "sim_0123456789ab"

        with app.app_context():
            app.extensions['neo4j_storage'] = MagicMock()

            with patch.object(SimulationManager, "get_simulation") as mock_get_sim:
                mock_state = MagicMock(project_id="proj_123")
                mock_get_sim.return_value = mock_state

                with patch("app.services.report_generation.run_registry") as mock_registry:
                    mock_registry.list_runs.return_value = [
                        {
                            "run_id": "run_report_1",
                            "run_type": "report_generate",
                            "status": "processing",
                            "simulation_id": simulation_id,
                        }
                    ]

                    with pytest.raises(ValueError) as excinfo:
                        ReportGenerationService.start_generation(
                            simulation_id=simulation_id,
                            report_mode="balanced",
                            force_regenerate=True,
                            llm_model_override=None,
                            llm_runtime=MagicMock(enabled=False),
                        )

                    assert excinfo.value.args[0] == ApiErrorCode.REPORT_GENERATE_IN_PROGRESS