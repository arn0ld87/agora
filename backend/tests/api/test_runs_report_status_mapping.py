"""Tests für die Status-Übersetzung im Report-Resume-Pfad (Issue #1479).

``_resume_report_generate`` (app/api/runs.py) verglich den fertigen
Report-Status bisher exakt gegen ``ReportStatus.COMPLETED`` — ein ehrlicher
``INCOMPLETE``-Teilreport (Cancel-bedingt fehlende Sections, siehe
``run_degradation.py``) fiel dadurch in den ``else``-Zweig und wurde als
technischer Fehlschlag ("failed") an Run und Task gemeldet, obwohl der
Report existiert und ausgeliefert werden kann.

Abgedeckte Szenarien:
  1  INCOMPLETE-Report → Run bleibt "completed", Metadatum report_status
     trägt "incomplete" — kein "failed".
  2  COMPLETED-Report (Baseline) → unverändert "completed",
     report_status="completed".
  3  FAILED-Report (echter Fehlschlag) → weiterhin "failed" — die neue
     Übersetzung darf keinen technischen Fehlschlag verschlucken.
"""

from __future__ import annotations

import os
import threading
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import runs_bp
from app.config import Config
from app.contracts.llm_routing_contract import ResolvedRoute
from app.llm.client import LLMClient
from app.models.project import ProjectManager
from app.models.report import Report, ReportStatus
from app.services.artifact_store import InMemoryArtifactStore
from app.services.run_registry import RunRegistry
from app.services.simulation_manager import SimulationManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))
    monkeypatch.setattr(
        SimulationManager, "SIMULATION_DATA_DIR", str(upload_root / "simulations")
    )
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(upload_root / "run_registry"))
    RunRegistry._instance = None
    os.makedirs(RunRegistry.REGISTRY_DIR, exist_ok=True)

    app = Flask(__name__)
    app.extensions = {"artifact_store": InMemoryArtifactStore()}
    app.register_blueprint(runs_bp, url_prefix="/api/runs")

    registry = RunRegistry()

    yield {"app": app, "registry": registry}

    RunRegistry._instance = None


def _create_report_run(registry: RunRegistry) -> dict:
    return registry.create_run(
        run_type="report_generate",
        entity_id="report_test",
        status="failed",
        message="ok",
        metadata={"llm_model": "gpt-4o-mini", "simulation_id": "sim_test"},
        linked_ids={
            "report_id": "report_test",
            "simulation_id": "sim_test",
            "project_id": "proj_test",
        },
    )


def _run_resume_report_generate_sync(run: dict, fake_report: Report) -> None:
    """Ruft ``_resume_report_generate(run)`` synchron auf — die interne
    ``run_generate``-Closure läuft normalerweise in einem Hintergrund-Thread;
    hier wird sie inline ausgeführt, analog zu
    ``test_runs_resume_stop.py::_run_restart_prepare_sync``."""
    from app.api.runs import _resume_report_generate

    fake_state = MagicMock()
    fake_state.project_id = "proj_test"
    fake_state.graph_id = "graph_test"

    fake_project = MagicMock()
    fake_project.graph_id = "graph_test"
    fake_project.simulation_requirement = "Test requirement"

    resolved_route = ResolvedRoute(
        stage="report_generation",
        provider_id="openai",
        model="gpt-4o-mini",
        routing_version=1,
    )

    fake_agent = MagicMock()
    fake_agent.generate_report.return_value = fake_report

    def capture_start(self):
        self.run()  # inline statt Hintergrund-Thread

    with (
        patch("app.api.runs.SimulationManager") as mock_sm,
        patch("app.api.runs.ProjectManager") as mock_pm,
        patch("app.api.runs.StageModelRouter") as mock_router,
        patch("app.api.runs.GraphToolsService"),
        patch("app.api.runs.ReportAgent", return_value=fake_agent),
        patch("app.api.runs.ReportManager"),
        patch.object(LLMClient, "from_route", return_value=MagicMock()),
        patch.object(threading.Thread, "start", capture_start),
    ):
        mock_router.return_value.resolve.return_value = resolved_route
        mock_sm.return_value.get_simulation.return_value = fake_state
        mock_pm.get_project.return_value = fake_project

        _resume_report_generate(run)


# ---------------------------------------------------------------------------
# Test 1: INCOMPLETE-Report darf nicht als failed ausgeliefert werden
# ---------------------------------------------------------------------------


def test_incomplete_report_status_is_not_mapped_to_failed(env):
    run = _create_report_run(env["registry"])
    fake_report = Report(
        report_id="report_test",
        simulation_id="sim_test",
        graph_id="graph_test",
        simulation_requirement="Test requirement",
        status=ReportStatus.INCOMPLETE,
    )

    with env["app"].app_context():
        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")
        _run_resume_report_generate_sync(run, fake_report)

    final = env["registry"].get_run(run["run_id"])
    assert final["status"] == "completed", (
        f"INCOMPLETE ist ein ehrliches Teilergebnis, kein Fehlschlag — erhalten: {final}"
    )
    assert final.get("metadata", {}).get("report_status") == "incomplete"


# ---------------------------------------------------------------------------
# Test 2: Baseline — COMPLETED bleibt unverändert
# ---------------------------------------------------------------------------


def test_completed_report_status_stays_completed(env):
    run = _create_report_run(env["registry"])
    fake_report = Report(
        report_id="report_test",
        simulation_id="sim_test",
        graph_id="graph_test",
        simulation_requirement="Test requirement",
        status=ReportStatus.COMPLETED,
    )

    with env["app"].app_context():
        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")
        _run_resume_report_generate_sync(run, fake_report)

    final = env["registry"].get_run(run["run_id"])
    assert final["status"] == "completed"
    assert final.get("metadata", {}).get("report_status") == "completed"


# ---------------------------------------------------------------------------
# Test 3: FAILED bleibt ein echter Fehlschlag
# ---------------------------------------------------------------------------


def test_failed_report_status_still_maps_to_failed(env):
    run = _create_report_run(env["registry"])
    fake_report = Report(
        report_id="report_test",
        simulation_id="sim_test",
        graph_id="graph_test",
        simulation_requirement="Test requirement",
        status=ReportStatus.FAILED,
        error="LLM-Aufrufe sind fehlgeschlagen.",
    )

    with env["app"].app_context():
        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")
        _run_resume_report_generate_sync(run, fake_report)

    final = env["registry"].get_run(run["run_id"])
    assert final["status"] == "failed", (
        f"Ein echter Fehlschlag darf nicht als completed gemeldet werden — erhalten: {final}"
    )
