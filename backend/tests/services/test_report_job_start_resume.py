"""Regressionstests: gemeinsamer Report-Job fuer Start und Resume (Issue #1479).

Der Report-Job existierte zweimal (Start-Pfad in services/report_generation.py,
Resume-Pfad in api/runs_resume.py); die Kopien drifteten auseinander:

* Bug A: der Resume-Pfad speicherte ohne report_mode und fiel immer auf
  DEFAULT_REPORT_MODE zurueck.
* Bug B: nur der Resume-Pfad setzte metadata.report_status.
"""
from __future__ import annotations

import os
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import runs_bp
from app.config import Config
from app.contracts.llm_routing_contract import ResolvedRoute
from app.contracts.report_v3 import DEFAULT_REPORT_MODE
from app.llm.client import LLMClient
from app.models.project import ProjectManager
from app.models.report import Report, ReportStatus
from app.services.artifact_store import InMemoryArtifactStore
from app.services.run_registry import RunRegistry
from app.services.simulation_manager import SimulationManager


@pytest.fixture()
def env(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(upload_root / "simulations"))
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(upload_root / "run_registry"))
    RunRegistry._instance = None
    os.makedirs(RunRegistry.REGISTRY_DIR, exist_ok=True)
    app = Flask(__name__)
    app.extensions = {"artifact_store": InMemoryArtifactStore()}
    app.register_blueprint(runs_bp, url_prefix="/api/runs")
    yield {"app": app, "registry": RunRegistry()}
    RunRegistry._instance = None


def _create_report_run(registry, metadata=None):
    return registry.create_run(
        run_type="report_generate",
        entity_id="report_test",
        status="failed",
        message="failed once",
        metadata=metadata if metadata is not None else {"llm_model": "gpt-4o-mini"},
        linked_ids={"report_id": "report_test", "simulation_id": "sim_test", "project_id": "proj_test"},
    )


def _report(status):
    return Report(
        report_id="report_test",
        simulation_id="sim_test",
        graph_id="graph_test",
        simulation_requirement="Test requirement",
        status=status,
    )


def _run_resume_sync(run, fake_report):
    """Ruft _resume_report_generate synchron auf (Worker-Thread inline)."""
    from app.api.runs import _resume_report_generate

    fake_state = MagicMock()
    fake_state.project_id = "proj_test"
    fake_state.graph_id = "graph_test"
    fake_project = MagicMock()
    fake_project.graph_id = "graph_test"
    fake_project.project_id = "proj_test"
    fake_project.simulation_requirement = "Test requirement"
    resolved_route = ResolvedRoute(
        stage="report_generation", provider_id="openai", model="gpt-4o-mini", routing_version=1
    )
    fake_agent = MagicMock()
    fake_agent.generate_report.return_value = fake_report

    def capture_start(self):
        self.run()

    with (
        patch("app.api.runs.SimulationManager") as mock_sm,
        patch("app.api.runs.ProjectManager") as mock_pm,
        patch("app.api.runs.StageModelRouter") as mock_router,
        patch("app.api.runs.GraphToolsService"),
        patch("app.api.runs.ReportAgent", return_value=fake_agent),
        patch("app.api.runs.ReportManager") as mock_rm,
        patch.object(LLMClient, "from_route", return_value=MagicMock()),
        patch.object(threading.Thread, "start", capture_start),
    ):
        mock_router.return_value.resolve.return_value = resolved_route
        mock_sm.return_value.get_simulation.return_value = fake_state
        mock_pm.get_project.return_value = fake_project
        _resume_report_generate(run)
        return mock_rm


def test_resume_uses_report_mode_from_run_metadata(env):
    """Bug A: der Resume-Pfad muss den Modus des Originalstarts verwenden."""
    run = _create_report_run(env["registry"], {"llm_model": "gpt-4o-mini", "report_mode": "strict"})
    with env["app"].app_context():
        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")
        mock_rm = _run_resume_sync(run, _report(ReportStatus.COMPLETED))
    assert mock_rm.save_report.call_args.kwargs["report_mode"] == "strict"


def test_resume_falls_back_to_default_report_mode_for_legacy_run(env):
    """Altlauf ohne report_mode-Feld -> DEFAULT_REPORT_MODE."""
    run = _create_report_run(env["registry"], {"llm_model": "gpt-4o-mini"})
    with env["app"].app_context():
        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")
        mock_rm = _run_resume_sync(run, _report(ReportStatus.COMPLETED))
    assert mock_rm.save_report.call_args.kwargs["report_mode"] == DEFAULT_REPORT_MODE


def test_resume_falls_back_to_default_report_mode_for_unknown_mode(env):
    """Unbekannter Modus -> DEFAULT_REPORT_MODE (kein ungueltiger Modus)."""
    run = _create_report_run(env["registry"], {"llm_model": "gpt-4o-mini", "report_mode": "nuclear"})
    with env["app"].app_context():
        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")
        mock_rm = _run_resume_sync(run, _report(ReportStatus.COMPLETED))
    assert mock_rm.save_report.call_args.kwargs["report_mode"] == DEFAULT_REPORT_MODE


@pytest.mark.parametrize("report_status,expected", [(ReportStatus.COMPLETED, "completed"), (ReportStatus.INCOMPLETE, "incomplete")])
def test_resume_sets_report_status_metadata(env, report_status, expected):
    """Bug B (Resume-Pfad): metadata.report_status wird gesetzt."""
    run = _create_report_run(env["registry"])
    with env["app"].app_context():
        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")
        _run_resume_sync(run, _report(report_status))
    final = env["registry"].get_run(run["run_id"])
    assert final["status"] == "completed"
    assert final.get("metadata", {}).get("report_status") == expected


@pytest.fixture()
def start_env(tmp_path, monkeypatch):
    """Start-Pfad mit gestubbtem Report-Umfeld (kein Netz, kein Neo4j)."""
    from app.services import report_generation as rg

    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    RunRegistry._instance = None
    registry = RunRegistry()
    monkeypatch.setattr(rg, "run_registry", registry)

    state = SimpleNamespace(project_id="proj-1", graph_id="graph-1", source_simulation_id=None, root_simulation_id=None, branch_name=None, branch_depth=0)
    sim_mgr = MagicMock()
    sim_mgr.get_simulation.return_value = state
    monkeypatch.setattr(rg, "SimulationManager", lambda: sim_mgr)
    project = SimpleNamespace(graph_id="graph-1", simulation_requirement="Requirement X", llm_profile_id=None)
    monkeypatch.setattr(rg.ProjectManager, "get_project", staticmethod(lambda pid: project))
    monkeypatch.setattr(rg, "seed_run_stage_routing", lambda *a, **k: None)
    resolved_route = SimpleNamespace(stage="report_generation", provider_id="ollama", model="qwen2.5:32b", base_url_sanitized="http://localhost:11434/v1")
    router = MagicMock()
    router.resolve.return_value = resolved_route
    monkeypatch.setattr(rg, "StageModelRouter", lambda run_id: router)
    monkeypatch.setattr(rg, "resolve_route_api_key", lambda *a, **k: None)
    monkeypatch.setattr(rg, "SecretResolver", MagicMock())
    monkeypatch.setattr(rg.LLMClient, "from_route", staticmethod(lambda *a, **k: MagicMock()))
    monkeypatch.setattr(rg, "GraphToolsService", lambda **kwargs: MagicMock())
    monkeypatch.setattr(rg, "current_app", MagicMock())
    monkeypatch.setattr(rg.ReportGenerationService, "_reject_if_persona_floor_not_reached", staticmethod(lambda simulation_id: None))
    task_mgr = MagicMock()
    task_mgr.create_task.return_value = "task-1"
    monkeypatch.setattr(rg, "TaskManager", lambda: task_mgr)
    monkeypatch.setattr(rg.ReportManager, "save_report", staticmethod(lambda *a, **k: None))
    jobs = []
    monkeypatch.setattr("app.jobs.enqueue", lambda name, fn, **kw: jobs.append(fn) or "job")
    monkeypatch.setattr("app.utils.artifact_locator.ArtifactLocator.run_dir", classmethod(lambda cls, run_id: str(registry_dir)))

    from app.services.llm_runtime import RuntimeLlmConfig

    class _StartEnv(SimpleNamespace):
        pass

    yield SimpleNamespace(rg=rg, registry=registry, jobs=jobs, task_mgr=task_mgr, runtime=RuntimeLlmConfig())
    RunRegistry._instance = None


def test_start_persists_report_mode_in_run_metadata(start_env):
    """Der Start-Pfad schreibt den Modus in die Run-Metadaten."""
    rg = start_env.rg
    result = rg.ReportGenerationService.start_generation(
        simulation_id="sim_abc", report_mode="strict", force_regenerate=True,
        llm_model_override=None, llm_runtime=start_env.runtime,
    )
    assert result["status"] == "generating"
    run = start_env.registry.get_run(result["run_id"])
    assert run["metadata"]["report_mode"] == "strict"


@pytest.mark.parametrize("report_status,expected", [(ReportStatus.COMPLETED, "completed"), (ReportStatus.INCOMPLETE, "incomplete")])
def test_start_sets_report_status_metadata(start_env, report_status, expected):
    """Bug B (Start-Pfad): metadata.report_status wird ebenfalls gesetzt."""
    rg = start_env.rg

    class _Agent:
        def __init__(self, **kwargs):
            pass

        def generate_report(self, **kwargs):
            return Report(
                report_id="report_abc", simulation_id="sim_abc", graph_id="graph-1",
                simulation_requirement="Requirement X", status=report_status,
            )

    start_env.rg.ReportAgent = _Agent
    result = rg.ReportGenerationService.start_generation(
        simulation_id="sim_abc", report_mode="balanced", force_regenerate=True,
        llm_model_override=None, llm_runtime=start_env.runtime,
    )
    assert len(start_env.jobs) == 1
    start_env.jobs[0]()
    run = start_env.registry.get_run(result["run_id"])
    assert run["status"] == "completed"
    assert run.get("metadata", {}).get("report_status") == expected


def test_start_budget_abort_calls_fail_task_before_mark_budget_abort(start_env, monkeypatch):
    """fail_task muss vor mark_budget_abort laufen (Issue #978)."""
    from app.services.run_budget import BudgetExceededError

    order = []
    start_env.task_mgr.fail_task.side_effect = lambda *a, **k: order.append("fail_task")
    monkeypatch.setattr("app.services.run_budget.mark_budget_abort", lambda *a, **k: order.append("mark_budget_abort"))

    class _BudgetAgent:
        def __init__(self, **kwargs):
            pass

        def generate_report(self, **kwargs):
            raise BudgetExceededError("calls", 3, 2)

    start_env.rg.ReportAgent = _BudgetAgent
    rg = start_env.rg
    rg.ReportGenerationService.start_generation(
        simulation_id="sim_abc", report_mode="balanced", force_regenerate=True,
        llm_model_override=None, llm_runtime=start_env.runtime,
    )
    assert len(start_env.jobs) == 1
    start_env.jobs[0]()
    assert order == ["fail_task", "mark_budget_abort"]


def test_shared_job_calls_fail_task_before_mark_budget_abort(monkeypatch):
    """Der gemeinsame Job: fail_task muss vor mark_budget_abort laufen (#978).

    Beide Pfade nutzen dieselbe Funktion -- der Test gilt daher fuer den
    Start- und den Resume-Weg gleichermassen.
    """
    from app.services.report_generation import ReportGenerationService
    from app.services.run_budget import BudgetExceededError

    order = []
    task_mgr = MagicMock()
    task_mgr.fail_task.side_effect = lambda *a, **k: order.append("fail_task")
    monkeypatch.setattr(
        "app.services.run_budget.mark_budget_abort",
        lambda *a, **k: order.append("mark_budget_abort"),
    )

    class _BudgetAgent:
        def __init__(self, **kwargs):
            pass

        def generate_report(self, **kwargs):
            raise BudgetExceededError("calls", 3, 2)

    ReportGenerationService.execute_report_job(
        run_id="run_1",
        task_id="task_1",
        task_manager=task_mgr,
        report_id="report_1",
        simulation_id="sim_1",
        graph_id="graph_1",
        simulation_requirement="req",
        report_mode="balanced",
        model_name=None,
        llm_client=MagicMock(),
        graph_tools=MagicMock(),
        document_roles={},
        agent_factory=_BudgetAgent,
        report_manager=MagicMock(),
        run_registry=MagicMock(),
        finish_completed_run_fn=MagicMock(),
        finish_cancelled_run_fn=MagicMock(),
    )

    assert order == ["fail_task", "mark_budget_abort"]
