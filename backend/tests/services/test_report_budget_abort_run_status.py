"""Issue #978 — der Budgetabbruch im Report-Pfad muss ``stopped`` bleiben.

``ReportGenerationService.start_generation`` fängt ``BudgetExceededError`` und
ruft ``mark_budget_abort`` (setzt ``status="stopped"`` +
``termination_reason``). Direkt danach folgt ``TaskManager.fail_task`` — und
``TaskManager.update_task`` spiegelt den Task per ``RunRegistry.sync_task``
zurück auf den Run. Ein ``FAILED``-Task überschreibt dabei den soeben
gesetzten ``stopped``-Status wieder mit ``failed`` und der generischen Message
``"Task failed"``.

Dieselbe Reihenfolge-Falle ist in ``api/simulation_prepare.py`` (Issue #841)
bereits dokumentiert: der detaillierte ``update_run``-Aufruf muss **nach**
``fail_task`` laufen.

Der Test fährt den echten Task- und Registry-Pfad (keine Mocks auf
``TaskManager``/``RunRegistry``) und prüft genau das, was der E2E-Smoke
``frontend/tests/e2e/run-budget.spec.ts`` am API-Rand erwartet.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.contracts.run_budget_contract import RunBudgetConfig
from app.services import report_generation as rg
from app.services.llm_runtime import RuntimeLlmConfig
from app.services.run_budget import BudgetExceededError
from app.services.run_registry import RunRegistry


def _ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture()
def budget_abort_env(tmp_path, monkeypatch):
    """Isolierte Registry + gestubbte Report-Umgebung.

    ``TaskManager`` und ``RunRegistry`` bleiben echt — genau ihr Zusammenspiel
    ist der Prüfgegenstand.
    """
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    RunRegistry._instance = None
    # Das Modul hält eine beim Import erzeugte Instanz; ohne diesen Reset
    # arbeiteten Produktionscode und Assertions auf zwei Caches.
    registry = RunRegistry()
    monkeypatch.setattr(rg, "run_registry", registry)

    created: dict[str, str] = {}
    _real_create_run = registry.create_run

    def _capture_create_run(**kwargs):
        record = _real_create_run(**kwargs)
        created["run_id"] = record["run_id"]
        return record

    monkeypatch.setattr(registry, "create_run", _capture_create_run)

    run_root = tmp_path / "runs"
    run_root.mkdir()
    monkeypatch.setattr(
        "app.utils.artifact_locator.ArtifactLocator.run_dir",
        classmethod(lambda cls, run_id: str(_ensure_dir(run_root / run_id))),
    )

    state = SimpleNamespace(
        project_id="proj-1",
        graph_id="graph-1",
        source_simulation_id=None,
        root_simulation_id=None,
        branch_name=None,
        branch_depth=0,
    )
    sim_mgr = MagicMock()
    sim_mgr.get_simulation.return_value = state
    monkeypatch.setattr(rg, "SimulationManager", lambda: sim_mgr)

    project = SimpleNamespace(
        graph_id="graph-1", simulation_requirement="Requirement X", llm_profile_id=None
    )
    monkeypatch.setattr(rg.ProjectManager, "get_project", staticmethod(lambda pid: project))

    monkeypatch.setattr(rg, "seed_run_stage_routing", lambda *a, **k: None)

    resolved_route = SimpleNamespace(
        provider_id="ollama",
        model="qwen2.5:32b",
        base_url_sanitized="http://localhost:11434/v1",
    )
    router = MagicMock()
    router.resolve.return_value = resolved_route
    monkeypatch.setattr(rg, "StageModelRouter", lambda run_id: router)
    monkeypatch.setattr(rg, "resolve_route_api_key", lambda *a, **k: None)
    monkeypatch.setattr(rg, "SecretResolver", MagicMock())
    monkeypatch.setattr(rg.LLMClient, "from_route", staticmethod(lambda *a, **k: MagicMock()))
    monkeypatch.setattr(rg, "GraphToolsService", lambda **kwargs: MagicMock())
    monkeypatch.setattr(rg, "current_app", MagicMock())

    class _BudgetAbortingAgent:
        def __init__(self, **kwargs):
            pass

        def generate_report(self, **kwargs):
            raise BudgetExceededError("calls", 3, 2)

    monkeypatch.setattr(rg, "ReportAgent", _BudgetAbortingAgent)
    monkeypatch.setattr(rg.ReportManager, "save_report", staticmethod(lambda *a, **k: None))

    jobs: list[object] = []
    monkeypatch.setattr("app.jobs.enqueue", lambda name, fn: jobs.append(fn) or "job-test")

    yield SimpleNamespace(jobs=jobs, created=created)

    RunRegistry._instance = None


def _run_generation(env) -> str:
    result = rg.ReportGenerationService.start_generation(
        simulation_id="sim_abc",
        report_mode="balanced",
        force_regenerate=True,
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
        budget=RunBudgetConfig(max_llm_calls=2, enforcement="hard"),
    )
    assert result["status"] == "generating"
    assert len(env.jobs) == 1, "Report-Job wurde nicht eingereiht"
    env.jobs[0]()

    run_id = env.created.get("run_id")
    assert run_id, "create_run wurde nicht aufgerufen"
    return run_id


def test_budget_abort_leaves_run_stopped_not_failed(budget_abort_env):
    """RED ohne den Fix: ``fail_task`` läuft nach ``mark_budget_abort`` und
    spiegelt ``failed`` + ``"Task failed"`` zurück auf den Run."""
    run_id = _run_generation(budget_abort_env)
    run = RunRegistry().get_run(run_id)

    assert run is not None
    assert run["status"] == "stopped", (
        "Budgetabbruch muss stopped bleiben, nicht von fail_task/sync_task "
        f"auf failed zurückgesetzt werden. message={run.get('message')!r}"
    )
    assert run["termination_reason"] == "budget_calls"


def test_budget_abort_keeps_budget_message_on_run(budget_abort_env):
    """Die generische Task-Message darf die Budgetbegründung nicht verdrängen."""
    run_id = _run_generation(budget_abort_env)
    run = RunRegistry().get_run(run_id)

    assert run is not None
    assert "Budgetabbruch" in (run.get("message") or ""), (
        f"Run-Message zeigt nicht den Budgetabbruch: {run.get('message')!r}"
    )
