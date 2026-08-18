"""Tests für ``_restart_graph_build`` (app/api/runs.py) — Cancel-Wiring.

Review-Finding PR #1371, Befund 4 (MITTEL): der Restart-Pfad rief
``builder.add_text_batches(...)`` bisher ohne ``run_id`` auf — das
Cancel-Flag konnte einen frisch neu gestarteten Graph-Build-Restart nie
erreichen. "Abbrechen → Restart → nochmal abbrechen" quittierte 202 (Flag
gesetzt), aber der Restart lief unbeirrt bis zum Ende durch.

Kein bestehender Test deckte ``_restart_graph_build`` vorher überhaupt ab.
"""

from __future__ import annotations

import os
import threading as _threading
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import runs_bp
from app.config import Config
from app.models.project import ProjectManager, ProjectStatus
from app.services.graph_builder import GraphBuildCancelled
from app.services.run_registry import RunRegistry
from app.services.simulation_manager import SimulationManager


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
    app.register_blueprint(runs_bp, url_prefix="/api/runs")

    yield {"app": app, "client": app.test_client(), "registry": RunRegistry()}

    RunRegistry._instance = None


def _create_graph_build_run(registry: RunRegistry) -> dict:
    return registry.create_run(
        run_type="graph_build",
        entity_id="proj_test",
        status="failed",
        message="ok",
        linked_ids={"project_id": "proj_test"},
        metadata={},
    )


def _run_restart_graph_build_sync(run: dict) -> dict:
    """Ruft ``_restart_graph_build(run)`` mit synchronem Thread auf."""
    from app.api.runs import _restart_graph_build

    def capture_start(self):
        self.run()  # inline statt background

    with patch.object(_threading.Thread, "start", capture_start):
        return _restart_graph_build(run)


def _fake_project() -> SimpleNamespace:
    return SimpleNamespace(
        project_id="proj_test",
        name="Test Project",
        status=ProjectStatus.FAILED,
        ontology={"entity_types": []},
        chunk_size=500,
        chunk_overlap=50,
        graph_id=None,
        graph_build_task_id=None,
        error=None,
    )


def _run_with_patched_env(run: dict, project: SimpleNamespace, builder: MagicMock, *, force_cancel: bool = False) -> dict:
    """Fährt ``_restart_graph_build`` mit den nötigen Doubles.

    ``force_cancel`` simuliert einen bereits vor dem Restart-Start
    gesetzten Cancel-Flag (der echte Fall wäre: der Nutzer klickt Abbrechen,
    bevor der Checkpoint erreicht wird — ``is_cancel_requested`` wird dafür
    global auf ``True`` gepatcht, weil die neue run_id erst innerhalb der
    Funktion erzeugt wird und ``request_cancel`` deshalb von außen nicht
    rechtzeitig gesetzt werden kann).
    """
    container = MagicMock()
    container.neo4j_storage = MagicMock()
    container.graph_builder.return_value = builder

    with ExitStack() as stack:
        mock_pm = stack.enter_context(patch("app.api.runs.ProjectManager"))
        stack.enter_context(patch("app.api.runs.get_container", return_value=container))
        mock_tm = stack.enter_context(patch("app.api.runs.TaskManager"))
        if force_cancel:
            stack.enter_context(
                patch("app.services.sim.cancel_flag.is_cancel_requested", return_value=True)
            )

        mock_pm.get_project.return_value = project
        mock_pm.get_extracted_text.return_value = "some extracted text " * 20
        mock_pm._get_project_dir.return_value = "/tmp/proj"
        mock_tm.return_value.create_task.return_value = "task-restart"

        return _run_restart_graph_build_sync(run)


def test_restart_graph_build_passes_run_id_to_add_text_batches(env):
    """add_text_batches muss die neue run_id des Restarts tragen — sonst
    kann is_cancel_requested() sie nie finden."""
    project = _fake_project()
    builder = MagicMock()
    builder.create_graph.return_value = "graph-restart-1"
    builder.get_graph_data.return_value = {"node_count": 5, "edge_count": 3}
    builder.add_text_batches.return_value = ["ep1", "ep2"]

    run = _create_graph_build_run(env["registry"])
    result = _run_with_patched_env(run, project, builder)

    call_kwargs = builder.add_text_batches.call_args.kwargs
    assert call_kwargs.get("run_id") == result["run_id"], (
        "Ohne run_id kann der Restart nie kooperativ abgebrochen werden"
    )


def test_restart_graph_build_cancel_before_add_text_batches_ends_stopped(env):
    """Cancel-Flag schon vor dem Chunk-Durchlauf gesetzt → stopped/user_cancel,
    kein delete_graph, Projekt GRAPH_INCOMPLETE."""
    project = _fake_project()
    builder = MagicMock()
    builder.create_graph.return_value = "graph-restart-2"

    run = _create_graph_build_run(env["registry"])
    result = _run_with_patched_env(run, project, builder, force_cancel=True)

    builder.add_text_batches.assert_not_called()
    builder.delete_graph.assert_not_called()
    builder.mark_graph_incomplete.assert_called_once()
    assert project.status == ProjectStatus.GRAPH_INCOMPLETE

    new_run = env["registry"].get_run(result["run_id"])
    assert new_run["status"] == "stopped"
    assert new_run["termination_reason"] == "user_cancel"


def test_restart_graph_build_cancel_during_add_text_batches_ends_stopped(env):
    """GraphBuildCancelled aus add_text_batches (as_completed-Schleife) →
    derselbe Endzustand, kein delete_graph."""
    project = _fake_project()
    builder = MagicMock()
    builder.create_graph.return_value = "graph-restart-3"
    builder.add_text_batches.side_effect = GraphBuildCancelled(["ep1"])

    run = _create_graph_build_run(env["registry"])
    result = _run_with_patched_env(run, project, builder)

    builder.delete_graph.assert_not_called()
    builder.mark_graph_incomplete.assert_called_once()
    assert project.status == ProjectStatus.GRAPH_INCOMPLETE

    new_run = env["registry"].get_run(result["run_id"])
    assert new_run["status"] == "stopped"
    assert new_run["termination_reason"] == "user_cancel"


def test_restart_graph_build_no_cancel_completes_normally(env):
    """Regressionsnetz: ohne Cancel bleibt der Erfolgspfad unverändert."""
    project = _fake_project()
    builder = MagicMock()
    builder.create_graph.return_value = "graph-restart-4"
    builder.get_graph_data.return_value = {"node_count": 5, "edge_count": 3}
    builder.add_text_batches.return_value = ["ep1", "ep2"]

    run = _create_graph_build_run(env["registry"])
    result = _run_with_patched_env(run, project, builder)

    builder.mark_graph_incomplete.assert_not_called()
    assert project.status == ProjectStatus.GRAPH_COMPLETED

    new_run = env["registry"].get_run(result["run_id"])
    assert new_run["status"] == "completed"
    assert new_run.get("termination_reason") is None
