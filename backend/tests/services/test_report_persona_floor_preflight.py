"""UAT-001 — Report-Start unter der Persona-Schwelle wird vor dem Enqueue abgewiesen.

Produktionsbefund: Report ``report_fe62975999bc`` lief los, plante, kostete —
und endete erst danach im Floor-Gate als ``INCOMPLETE`` ohne Text
(``Persona-Mindestanzahl nicht erreicht: 18/20 Personas vorhanden.``).
Die Vorabpruefung ``_reject_if_persona_floor_not_reached`` zieht dieselbe
Aufloesung (``load_persona_count_for`` / ``load_persona_floor_for``) wie das
Gate heran, damit die Erklaerung vor dem Start nicht von der Schwelle
abweicht, an der der Workflow sonst spaeter abbricht.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.services.report_agent import MIN_PERSONA_TABLE_ROWS
from app.services.report_generation import ReportGenerationService
from app.services.simulation_manager import SimulationManager


@pytest.fixture
def app():
    return Flask(__name__)


def _start_kwargs(simulation_id: str = "sim_0123456789ab") -> dict:
    return {
        "simulation_id": simulation_id,
        "report_mode": "balanced",
        "force_regenerate": False,
        "llm_model_override": None,
        "llm_runtime": MagicMock(enabled=False),
    }


class TestPersonaFloorPreflight:
    def test_unter_der_schwelle_wird_mit_zahlen_abgewiesen(self):
        """Kernfall 18/20: die Meldung nennt Anzahl und wirksame Schwelle."""
        with patch(
            "app.services.report_agent.workflow.load_persona_count_for",
            return_value=18,
        ), patch(
            "app.services.report_agent.workflow.load_persona_floor_for",
            return_value=MIN_PERSONA_TABLE_ROWS,
        ):
            with pytest.raises(ValueError) as excinfo:
                ReportGenerationService._reject_if_persona_floor_not_reached(
                    "sim_0123456789ab"
                )

        message = str(excinfo.value)
        assert "18" in message
        assert str(MIN_PERSONA_TABLE_ROWS) in message

    def test_auf_der_schwelle_passiert(self):
        with patch(
            "app.services.report_agent.workflow.load_persona_count_for",
            return_value=MIN_PERSONA_TABLE_ROWS,
        ), patch(
            "app.services.report_agent.workflow.load_persona_floor_for",
            return_value=MIN_PERSONA_TABLE_ROWS,
        ):
            ReportGenerationService._reject_if_persona_floor_not_reached(
                "sim_0123456789ab"
            )

    def test_nicht_lesbare_anzahl_blockiert_nicht(self):
        """Fail-open: ein Store-Aussetzer darf einen moeglichen Bericht nicht verhindern."""
        with patch(
            "app.services.report_agent.workflow.load_persona_count_for",
            return_value=None,
        ), patch(
            "app.services.report_agent.workflow.load_persona_floor_for",
            return_value=MIN_PERSONA_TABLE_ROWS,
        ):
            ReportGenerationService._reject_if_persona_floor_not_reached(
                "sim_0123456789ab"
            )

    def test_gesenkter_floor_ist_die_schwelle(self):
        """Ein kleineres ``max_agents`` senkt den Floor — die Pruefung folgt ihm.

        Sonst wuerde die Vorabpruefung Laeufe abweisen, die das Gate spaeter
        durchgelassen haette — die Erklaerung wiche von der wirksamen Schwelle ab.
        """
        with patch(
            "app.services.report_agent.workflow.load_persona_count_for",
            return_value=10,
        ), patch(
            "app.services.report_agent.workflow.load_persona_floor_for",
            return_value=10,
        ):
            ReportGenerationService._reject_if_persona_floor_not_reached(
                "sim_0123456789ab"
            )

        with patch(
            "app.services.report_agent.workflow.load_persona_count_for",
            return_value=9,
        ), patch(
            "app.services.report_agent.workflow.load_persona_floor_for",
            return_value=10,
        ):
            with pytest.raises(ValueError) as excinfo:
                ReportGenerationService._reject_if_persona_floor_not_reached(
                    "sim_0123456789ab"
                )
        assert "9" in str(excinfo.value)
        assert "10" in str(excinfo.value)


class TestStartGenerationBlocksBeforeCost:
    """Es darf kein Run und kein Task entstehen — genau das war der Schaden."""

    def test_kein_run_und_kein_task_bei_unterschrittener_schwelle(self, app: Flask):
        with app.app_context():
            with patch("app.services.report_generation.run_registry") as mock_registry:
                mock_registry.list_runs.return_value = []

                with patch.object(SimulationManager, "get_simulation") as mock_get_sim:
                    mock_get_sim.return_value = MagicMock(
                        project_id="proj_123",
                        graph_id="graph_123",
                        simulation_requirement="Test requirement",
                        branch_name=None,
                        source_simulation_id=None,
                        root_simulation_id=None,
                        branch_depth=0,
                    )

                    with patch(
                        "app.services.report_generation.ProjectManager.get_project"
                    ) as mock_get_proj:
                        mock_get_proj.return_value = MagicMock(
                            simulation_requirement="Test requirement",
                            llm_profile_id=None,
                        )

                        with patch(
                            "app.services.report_generation.RunLifecycle.begin"
                        ) as mock_lifecycle, patch(
                            "app.services.report_generation.TaskManager"
                        ) as mock_task_mgr, patch(
                            "app.services.report_agent.workflow.load_persona_count_for",
                            return_value=18,
                        ), patch(
                            "app.services.report_agent.workflow.load_persona_floor_for",
                            return_value=MIN_PERSONA_TABLE_ROWS,
                        ):
                            with pytest.raises(ValueError) as excinfo:
                                ReportGenerationService.start_generation(
                                    **_start_kwargs()
                                )

                            assert "18" in str(excinfo.value)
                            mock_lifecycle.assert_not_called()
                            mock_task_mgr.return_value.create_task.assert_not_called()


class TestSingleSourceOfTruth:
    """Vorabpruefung und Gate duerfen die Schwelle nicht zweimal aufloesen."""

    def test_vorabpruefung_nutzt_die_gate_funktionen(self):
        source = inspect.getsource(
            ReportGenerationService._reject_if_persona_floor_not_reached
        )
        assert "load_persona_count_for" in source
        assert "load_persona_floor_for" in source

    def test_gate_und_vorabpruefung_lesen_denselben_store(self):
        from app.services.report_agent import workflow

        store = MagicMock()
        store.read_json.side_effect = lambda _sid, artifact, default=None: (
            {"persona_floor": 12} if artifact == "state" else [object()] * 13
        )

        with patch.object(workflow, "resolve_default_store", return_value=store):
            agent = MagicMock(simulation_id="sim_same")
            assert workflow._load_persona_floor(agent) == workflow.load_persona_floor_for(
                "sim_same"
            )
            assert workflow._load_persona_count(agent) == workflow.load_persona_count_for(
                "sim_same"
            )
