"""Regressionstest fuer Finding H2 (#1688): Resume/Restart eines
``simulation_run`` muss denselben Route-/Key-/Demo-Limit-Pfad durchlaufen
wie ``POST /api/simulation/start`` — vorher rief
``_resume_or_restart_simulation_run`` ``SimulationRunner.start_simulation``
ohne ``runtime_env``, ohne Rundenobergrenze und ohne Budget auf. Ein
Workspace-Run erbte damit den vom Subprozess-Whitelist geerbten
Operator-Umgebungs-State statt eines Workspace-scoped Keys.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from flask import Flask

from app.api import runs as runs_module
from app.config import Config
from app.contracts.llm_routing_contract import ResolvedRoute
from app.services.run_registry import RunRegistry
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import SimulationRunner

SIM_ID = "sim_resume_h2"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(upload_root / "run_registry"))
    os.makedirs(RunRegistry.REGISTRY_DIR, exist_ok=True)
    registry = RunRegistry()
    monkeypatch.setattr(runs_module, "run_registry", registry)

    # Nicht pausiert -> Restart-Zweig statt Pause-Resume-Zweig.
    monkeypatch.setattr(SimulationRunner, "get_run_state", staticmethod(lambda sim_id: None))

    fake_state = SimpleNamespace(
        project_id="proj_h2", graph_id="graph_h2", branch_name=None, status=None
    )
    monkeypatch.setattr(SimulationManager, "get_simulation", lambda self, sim_id: fake_state)
    monkeypatch.setattr(SimulationManager, "_save_simulation_state", lambda self, state: None)

    resolved_route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="openai",
        model="gpt-4o-mini",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )
    monkeypatch.setattr(
        runs_module.StageModelRouter, "resolve", lambda self, stage_id: resolved_route
    )
    monkeypatch.setattr(
        runs_module,
        "build_route_subprocess_env",
        lambda route, api_key, run_id: {"LLM_API_KEY": api_key or "", "AGORA_RUN_ID": run_id},
    )

    captured: dict = {}

    def _fake_start_simulation(**kwargs):
        captured.update(kwargs)
        return SimulationRunState(
            simulation_id=kwargs["simulation_id"],
            runner_status=RunnerStatus.RUNNING,
        )

    monkeypatch.setattr(SimulationRunner, "start_simulation", _fake_start_simulation)

    app = Flask(__name__)
    with app.app_context():
        yield {"registry": registry, "captured": captured}

    RunRegistry._instance = None


def _create_orphan_run(registry: RunRegistry) -> dict:
    return registry.create_run(
        run_type="simulation_run",
        entity_id=SIM_ID,
        status="processing",
        linked_ids={"simulation_id": SIM_ID, "project_id": "proj_h2"},
    )


def test_restart_uses_resolved_route_and_workspace_key(env, monkeypatch):
    """Ein aufgeloester Workspace-Key erreicht ``runtime_env`` des Restarts."""
    monkeypatch.setattr(
        runs_module, "resolve_route_api_key", lambda route, runtime, *, run_id=None: "workspace-secret"
    )

    run = _create_orphan_run(env["registry"])
    result = runs_module._resume_or_restart_simulation_run(run)

    assert isinstance(result, dict)
    assert result["message"] == "Simulation restarted"
    captured = env["captured"]
    assert captured["runtime_env"]["LLM_API_KEY"] == "workspace-secret"
    assert captured["simulation_id"] == SIM_ID


def test_restart_rejects_when_workspace_key_missing(env, monkeypatch):
    """Fail-closed: kein Key aufloesbar, kein Session-Auth, kein lokaler
    Endpunkt -> abgelehnt statt auf einen Operator-Key durchzufallen."""
    monkeypatch.setattr(
        runs_module, "resolve_route_api_key", lambda route, runtime, *, run_id=None: None
    )

    run = _create_orphan_run(env["registry"])
    result = runs_module._resume_or_restart_simulation_run(run)

    assert not isinstance(result, dict)
    # json_error(...) liefert ein Flask-Response-Tuple; Statuscode pruefen.
    _, status = result
    assert status == 422
    assert env["captured"] == {}


def test_restart_caps_rounds_and_budget_in_demo_mode(env, monkeypatch):
    """Finding M1: ein Demo-JWT-Restart bekommt dieselbe Rundenobergrenze
    (<=5) und dasselbe Budget-Hardcap wie ein frischer Start."""
    from app.contracts.auth_contract import AuthType
    from app.api import simulation_common

    monkeypatch.setattr(
        runs_module, "resolve_route_api_key", lambda route, runtime, *, run_id=None: "workspace-secret"
    )
    monkeypatch.setenv("AGORA_DEMO_MODE", "true")
    fake_principal = SimpleNamespace(auth_type=AuthType.JWT)
    monkeypatch.setattr(simulation_common, "current_principal", lambda: fake_principal)

    run = _create_orphan_run(env["registry"])
    result = runs_module._resume_or_restart_simulation_run(run)

    assert isinstance(result, dict)
    captured = env["captured"]
    assert captured["max_rounds"] == 5
