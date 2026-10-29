"""Unit and regression tests for runs lifecycle parity (Findings 4.1, 4.2, 4.3).

Covers:
- Finding 4.1 (runs_resume):
    * Stored platform (e.g. reddit/twitter) carried over into restart/resume
    * Configured max_rounds carried over
    * enable_graph_memory_update and graph_id propagated to start_simulation
    * ManifestCapture.capture_draft_best_effort written and discarded on error
    * Soft-resume checks is_process_alive before unpausing IPC
- Finding 4.2 (runs_restart):
    * Credential scope metadata inherited from original run (_inherited_credential_scope_metadata)
    * Session-auth provider (codex_cli) supported without requiring API key
    * Prepare job tracks active job and clears cancel flag in finally
    * Failure in background prepare job updates SimulationState status to FAILED and sets error
- Finding 4.3 (runs_actions & simulation_run_actions):
    * Cancel on pending run invokes cancel_fn and updates run to failed while returning cancelled
    * execute_stop_simulation sets SimulationStatus.STOPPED instead of PAUSED
    * execute_stop_run sets SimulationStatus.STOPPED via _set_status
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import runs as runs_module
from app.api import runs_actions as runs_actions_module
from app.api import runs_restart as runs_restart_module
from app.api import runs_resume as runs_resume_module
from app.api import simulation_run_actions as sim_actions_module
from app.config import Config
from app.contracts.llm_routing_contract import ResolvedRoute
from app.services.llm_provider_registry import LlmProviderRegistry
from app.services.run_registry import RunRegistry
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState
from app.services.simulation_manager import SimulationManager, SimulationStatus
from app.services.simulation_runner import SimulationRunner


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(upload_root / "run_registry"))
    os.makedirs(RunRegistry.REGISTRY_DIR, exist_ok=True)
    registry = RunRegistry()
    monkeypatch.setattr(runs_module, "run_registry", registry)

    app = Flask(__name__)
    app.config["TESTING"] = True
    with app.app_context():
        yield {"registry": registry, "client": app.test_client(), "tmp_path": tmp_path}

    RunRegistry._instance = None


# ---------------------------------------------------------------------------
# Finding 4.1 Tests
# ---------------------------------------------------------------------------


def test_resume_carries_platform_max_rounds_graph_memory_and_draft_manifest(app_env, monkeypatch):
    registry = app_env["registry"]
    sim_id = "sim_lifecycle_parity_1"

    monkeypatch.setattr(SimulationRunner, "get_run_state", staticmethod(lambda sid: None))

    fake_state = SimpleNamespace(
        project_id="proj_1",
        graph_id="graph_project_1",
        branch_name="test-branch",
        status=SimulationStatus.READY,
    )
    fake_config = {
        "platform": "reddit",
        "max_rounds": 8,
        "enable_graph_memory_update": True,
    }
    monkeypatch.setattr(SimulationManager, "get_simulation", lambda self, sid: fake_state)
    monkeypatch.setattr(SimulationManager, "get_simulation_config", lambda self, sid: fake_config)
    monkeypatch.setattr(SimulationManager, "_save_simulation_state", lambda self, state: None)

    resolved_route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )
    monkeypatch.setattr(runs_module.StageModelRouter, "resolve", lambda self, stage: resolved_route)
    monkeypatch.setattr(runs_module, "resolve_route_api_key", lambda route, runtime, run_id=None: "key-123")
    monkeypatch.setattr(runs_module, "build_route_subprocess_env", lambda route, key, rid: {})

    captured_start = {}

    def _fake_start(**kwargs):
        captured_start.update(kwargs)
        return SimulationRunState(simulation_id=kwargs["simulation_id"], runner_status=RunnerStatus.RUNNING)

    monkeypatch.setattr(SimulationRunner, "start_simulation", _fake_start)

    draft_captured = {}

    def _fake_capture_draft(**kwargs):
        draft_captured.update(kwargs)

    from app.services.manifest_capture import ManifestCapture
    monkeypatch.setattr(ManifestCapture, "capture_draft_best_effort", _fake_capture_draft)

    original_run = registry.create_run(
        run_type="simulation_run",
        entity_id=sim_id,
        status="failed",
        linked_ids={"simulation_id": sim_id, "project_id": "proj_1"},
    )

    result = runs_resume_module._resume_or_restart_simulation_run(original_run)
    assert result["status"] == "running"
    assert captured_start["platform"] == "reddit"
    assert captured_start["max_rounds"] == 8
    assert captured_start["enable_graph_memory_update"] is True
    assert captured_start["graph_id"] == "graph_project_1"
    assert captured_start["requested_run_id"] == original_run["run_id"]

    assert draft_captured.get("platform") == "reddit"
    assert draft_captured.get("max_rounds") == 8
    assert draft_captured.get("enable_graph_memory_update") is True
    assert draft_captured.get("memory_update_graph_id") == "graph_project_1"


def test_resume_discards_manifest_draft_on_start_failure(app_env, monkeypatch):
    registry = app_env["registry"]
    sim_id = "sim_lifecycle_parity_fail"

    monkeypatch.setattr(SimulationRunner, "get_run_state", staticmethod(lambda sid: None))

    fake_state = SimpleNamespace(
        project_id="proj_fail",
        graph_id="graph_fail",
        branch_name="branch",
        status=SimulationStatus.READY,
    )
    monkeypatch.setattr(SimulationManager, "get_simulation", lambda self, sid: fake_state)
    monkeypatch.setattr(SimulationManager, "get_simulation_config", lambda self, sid: {})
    monkeypatch.setattr(SimulationManager, "_save_simulation_state", lambda self, state: None)

    resolved_route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )
    monkeypatch.setattr(runs_module.StageModelRouter, "resolve", lambda self, stage: resolved_route)
    monkeypatch.setattr(runs_module, "resolve_route_api_key", lambda route, runtime, run_id=None: "key-123")
    monkeypatch.setattr(runs_module, "build_route_subprocess_env", lambda route, key, rid: {})

    def _failing_start(**kwargs):
        raise RuntimeError("Subprocess spawn error")

    monkeypatch.setattr(SimulationRunner, "start_simulation", _failing_start)

    from app.services.manifest_capture import ManifestCapture
    discarded = []
    monkeypatch.setattr(ManifestCapture, "discard_draft_best_effort", lambda **kwargs: discarded.append(kwargs))

    original_run = registry.create_run(
        run_type="simulation_run",
        entity_id=sim_id,
        status="failed",
        linked_ids={"simulation_id": sim_id, "project_id": "proj_fail"},
    )

    with pytest.raises(RuntimeError, match="Subprocess spawn error"):
        runs_resume_module._resume_or_restart_simulation_run(original_run)

    assert len(discarded) == 1
    assert "run_id" in discarded[0]


def test_resume_paused_checks_process_alive(app_env, monkeypatch):
    registry = app_env["registry"]
    sim_id = "sim_lifecycle_paused"

    # SimulationState is PAUSED, runner state is PAUSED, but process is dead
    paused_run_state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.PAUSED,
        process_pid=99999,
    )
    monkeypatch.setattr(SimulationRunner, "get_run_state", staticmethod(lambda sid: paused_run_state))

    fake_state = SimpleNamespace(
        project_id="proj_paused",
        graph_id="graph_paused",
        branch_name="branch",
        status=SimulationStatus.PAUSED,
    )
    monkeypatch.setattr(SimulationManager, "get_simulation", lambda self, sid: fake_state)
    monkeypatch.setattr(SimulationManager, "get_simulation_config", lambda self, sid: {})
    monkeypatch.setattr(SimulationManager, "_save_simulation_state", lambda self, state: None)

    # Process is DEAD
    monkeypatch.setattr("app.services.sim.process_manager.is_process_alive", lambda pid: False)

    resolved_route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )
    monkeypatch.setattr(runs_module.StageModelRouter, "resolve", lambda self, stage: resolved_route)
    monkeypatch.setattr(runs_module, "resolve_route_api_key", lambda route, runtime, run_id=None: "key-123")
    monkeypatch.setattr(runs_module, "build_route_subprocess_env", lambda route, key, rid: {})

    started_new = False

    def _fake_start(**kwargs):
        nonlocal started_new
        started_new = True
        return SimulationRunState(simulation_id=kwargs["simulation_id"], runner_status=RunnerStatus.RUNNING)

    monkeypatch.setattr(SimulationRunner, "start_simulation", _fake_start)

    original_run = registry.create_run(
        run_type="simulation_run",
        entity_id=sim_id,
        status="stopped",
        linked_ids={"simulation_id": sim_id, "project_id": "proj_paused"},
    )

    result = runs_resume_module._resume_or_restart_simulation_run(original_run)
    # Because process is dead, it must NOT take the soft IPC-unpause shortcut;
    # it must perform a full restart via start_simulation.
    assert started_new is True
    assert result["status"] == "running"


def test_resume_graph_memory_update_prioritizes_explicit_false_over_true(app_env, monkeypatch):
    registry = app_env["registry"]
    sim_id = "sim_lifecycle_parity_false_memory"

    monkeypatch.setattr(SimulationRunner, "get_run_state", staticmethod(lambda sid: None))

    # state has enable_graph_memory_update = False, config has enable_graph_memory_update = True
    fake_state = SimpleNamespace(
        project_id="proj_fm",
        graph_id="graph_fm",
        branch_name="branch_fm",
        status=SimulationStatus.READY,
        enable_graph_memory_update=False,
    )
    fake_config = {
        "platform": "parallel",
        "max_rounds": 5,
        "enable_graph_memory_update": True,
    }
    monkeypatch.setattr(SimulationManager, "get_simulation", lambda self, sid: fake_state)
    monkeypatch.setattr(SimulationManager, "get_simulation_config", lambda self, sid: fake_config)
    monkeypatch.setattr(SimulationManager, "_save_simulation_state", lambda self, state: None)

    resolved_route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )
    monkeypatch.setattr(runs_module.StageModelRouter, "resolve", lambda self, stage: resolved_route)
    monkeypatch.setattr(runs_module, "resolve_route_api_key", lambda route, runtime, run_id=None: "key-123")
    monkeypatch.setattr(runs_module, "build_route_subprocess_env", lambda route, key, rid: {})

    captured_start = {}
    monkeypatch.setattr(
        SimulationRunner,
        "start_simulation",
        lambda **kwargs: captured_start.update(kwargs) or SimulationRunState(
            simulation_id=kwargs["simulation_id"], runner_status=RunnerStatus.RUNNING
        ),
    )

    draft_captured = {}
    from app.services.manifest_capture import ManifestCapture
    monkeypatch.setattr(ManifestCapture, "capture_draft_best_effort", lambda **kwargs: draft_captured.update(kwargs))

    # Case 1: Run metadata explicitly specifies enable_graph_memory_update=False
    original_run = registry.create_run(
        run_type="simulation_run",
        entity_id=sim_id,
        status="failed",
        linked_ids={"simulation_id": sim_id, "project_id": "proj_fm"},
        metadata={"enable_graph_memory_update": False},
    )

    result = runs_resume_module._resume_or_restart_simulation_run(original_run)
    assert result["status"] == "running"
    # Even though fake_config has enable_graph_memory_update = True, metadata False MUST win
    assert captured_start["enable_graph_memory_update"] is False
    assert captured_start["graph_id"] is None
    assert draft_captured.get("enable_graph_memory_update") is False
    assert draft_captured.get("memory_update_graph_id") is None

    # Direct helper verification:
    # 1. metadata False beats config True
    assert runs_resume_module._resolve_enable_graph_memory_update(
        {"metadata": {"enable_graph_memory_update": False}},
        {"enable_graph_memory_update": True},
        SimpleNamespace(enable_graph_memory_update=True),
    ) is False

    # 2. config False beats state True
    assert runs_resume_module._resolve_enable_graph_memory_update(
        {"metadata": {}},
        {"enable_graph_memory_update": False},
        SimpleNamespace(enable_graph_memory_update=True),
    ) is False

    # 3. state False beats absent
    assert runs_resume_module._resolve_enable_graph_memory_update(
        {"metadata": {}},
        {},
        SimpleNamespace(enable_graph_memory_update=False),
    ) is False


def test_resume_persists_inherited_stage_snapshot_for_replacement_run(app_env, monkeypatch):
    from app.contracts.ai_provider_contract import AiRoute
    from app.services.runtime_run_config import RuntimeRunConfig

    registry = app_env["registry"]
    sim_id = "sim_lifecycle_inherited_snapshot"

    monkeypatch.setattr(SimulationRunner, "get_run_state", staticmethod(lambda sid: None))

    fake_state = SimpleNamespace(
        project_id="proj_snap",
        graph_id="graph_snap",
        branch_name="snap_branch",
        status=SimulationStatus.READY,
    )
    monkeypatch.setattr(SimulationManager, "get_simulation", lambda self, sid: fake_state)
    monkeypatch.setattr(SimulationManager, "get_simulation_config", lambda self, sid: {})
    monkeypatch.setattr(SimulationManager, "_save_simulation_state", lambda self, state: None)

    resolved_route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )
    monkeypatch.setattr(runs_module.StageModelRouter, "resolve", lambda self, stage: resolved_route)
    monkeypatch.setattr(runs_module, "resolve_route_api_key", lambda route, runtime, run_id=None: "key-123")
    monkeypatch.setattr(runs_module, "build_route_subprocess_env", lambda route, key, rid: {})
    monkeypatch.setattr(
        SimulationRunner,
        "start_simulation",
        lambda **kwargs: SimulationRunState(simulation_id=kwargs["simulation_id"], runner_status=RunnerStatus.RUNNING),
    )

    draft_captured = {}
    from app.services.manifest_capture import ManifestCapture
    monkeypatch.setattr(ManifestCapture, "capture_draft_best_effort", lambda **kwargs: draft_captured.update(kwargs))

    # Create original run and persist a canonical AiRoute snapshot on it
    original_run = registry.create_run(
        run_type="simulation_run",
        entity_id=sim_id,
        status="failed",
        linked_ids={"simulation_id": sim_id, "project_id": "proj_snap"},
    )
    orig_route = AiRoute(
        stage="simulation_rounds",
        provider_connection_id="openai",
        model_id="gpt-4o",
        source="run_override",
    )
    RuntimeRunConfig(original_run["run_id"]).save_ai_route_snapshot("simulation_rounds", orig_route)

    result = runs_resume_module._resume_or_restart_simulation_run(original_run)
    new_run_id = result["run_id"]

    # Verify replacement run has the inherited canonical snapshot persisted
    new_snapshot = RuntimeRunConfig(new_run_id).load_ai_route_snapshot("simulation_rounds")
    assert new_snapshot is not None
    assert new_snapshot.model_id == "gpt-4o"
    assert new_snapshot.provider_connection_id == "openai"

    # Verify that draft_captured got the canonical snapshot and did not omit it
    assert draft_captured.get("run_id") == new_run_id
    routing_snapshot = draft_captured["routing"]["simulation_rounds"]["ai_route_snapshot"]
    assert routing_snapshot is not None
    assert routing_snapshot["model_id"] == "gpt-4o"
    assert routing_snapshot["provider_connection_id"] == "openai"


# ---------------------------------------------------------------------------
# Finding 4.2 Tests
# ---------------------------------------------------------------------------


def test_prepare_restart_supports_session_auth_and_inherits_scope(app_env, monkeypatch):
    registry = app_env["registry"]
    sim_id = "sim_prepare_session_auth"

    fake_project = SimpleNamespace(simulation_requirement="test req")
    fake_state = SimpleNamespace(
        project_id="proj_prep",
        graph_id="graph_prep",
        branch_name="prep-branch",
        status=SimulationStatus.FAILED,
    )
    monkeypatch.setattr(runs_module.ProjectManager, "get_project", lambda pid: fake_project)
    monkeypatch.setattr(runs_module.ProjectManager, "get_extracted_text", lambda pid: "doc text")
    monkeypatch.setattr(SimulationManager, "get_simulation", lambda self, sid: fake_state)
    monkeypatch.setattr(SimulationManager, "get_simulation_config", lambda self, sid: {"llm_model": "codex"})
    monkeypatch.setattr(SimulationManager, "_save_simulation_state", lambda self, state: None)

    # Extension neo4j_storage
    current_app = runs_module.current_app
    current_app.extensions["neo4j_storage"] = MagicMock()

    resolved_route = ResolvedRoute(
        stage="persona_generation",
        provider_id="codex_cli",
        model="gpt-5.4",
        base_url_sanitized="",
        routing_version=1,
    )
    monkeypatch.setattr(runs_module.StageModelRouter, "resolve", lambda self, stage: resolved_route)
    monkeypatch.setattr(runs_module.StageModelRouter, "lock_stage", lambda self, stage, r: None)

    # Session auth: uses_session_auth("codex_cli") is True
    assert LlmProviderRegistry.uses_session_auth("codex_cli") is True

    # Track active prepare job
    tracked = []
    from app.api import simulation_prepare

    def _mock_track(simulation_id, target):
        tracked.append(simulation_id)
        return target

    monkeypatch.setattr(simulation_prepare, "_track_active_prepare_job", _mock_track)

    # Prevent thread from executing actual preparation logic
    monkeypatch.setattr("threading.Thread.start", lambda self: None)

    original_run = registry.create_run(
        run_type="simulation_prepare",
        entity_id=sim_id,
        status="failed",
        linked_ids={"simulation_id": sim_id, "project_id": "proj_prep"},
        metadata={"credential_scope": "workspace", "credential_workspace_id": "ws_scope_inherited"},
    )

    result = runs_restart_module._restart_simulation_prepare(original_run)
    assert result["status"] == "processing"
    assert sim_id in tracked

    new_run = registry.get_run(result["run_id"])
    assert new_run["metadata"]["credential_workspace_id"] == "ws_scope_inherited"
    assert new_run["metadata"]["credential_scope"] == "workspace"


def test_prepare_restart_failure_marks_simulation_state_failed(app_env, monkeypatch):
    registry = app_env["registry"]
    sim_id = "sim_prepare_fails"

    fake_project = SimpleNamespace(simulation_requirement="req")
    fake_state = SimpleNamespace(
        project_id="proj_fail",
        graph_id="graph_fail",
        branch_name="prep-branch",
        status=SimulationStatus.PREPARING,
        error=None,
    )
    monkeypatch.setattr(runs_module.ProjectManager, "get_project", lambda pid: fake_project)
    monkeypatch.setattr(runs_module.ProjectManager, "get_extracted_text", lambda pid: "doc text")
    manager = SimulationManager()
    monkeypatch.setattr(SimulationManager, "get_simulation", lambda self, sid: fake_state)
    monkeypatch.setattr(SimulationManager, "get_simulation_config", lambda self, sid: {})
    saved_states = []
    monkeypatch.setattr(SimulationManager, "_save_simulation_state", lambda self, state: saved_states.append(state))

    current_app = runs_module.current_app
    current_app.extensions["neo4j_storage"] = MagicMock()

    resolved_route = ResolvedRoute(
        stage="persona_generation",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )
    monkeypatch.setattr(runs_module.StageModelRouter, "resolve", lambda self, stage: resolved_route)
    monkeypatch.setattr(runs_module.StageModelRouter, "lock_stage", lambda self, stage, r: None)
    monkeypatch.setattr(runs_module, "resolve_route_api_key", lambda route, runtime: "key-xyz")

    # Mock prepare_simulation to raise an error
    def _exploding_prepare(**kwargs):
        raise ValueError("LLM generation quota exhausted")

    monkeypatch.setattr(manager, "prepare_simulation", _exploding_prepare)
    monkeypatch.setattr(runs_module, "SimulationManager", lambda: manager)

    cleared_cancels = []
    monkeypatch.setattr("app.services.sim.cancel_flag.clear_cancel", lambda rid: cleared_cancels.append(rid))

    # Synchronous thread execution for deterministic testing
    def _run_inline(self):
        self._target(*self._args, **self._kwargs)

    monkeypatch.setattr("threading.Thread.start", _run_inline)

    original_run = registry.create_run(
        run_type="simulation_prepare",
        entity_id=sim_id,
        status="failed",
        linked_ids={"simulation_id": sim_id, "project_id": "proj_fail"},
    )

    result = runs_restart_module._restart_simulation_prepare(original_run)
    assert result["status"] == "processing"

    # Verify run updated to failed
    run_record = registry.get_run(result["run_id"])
    assert run_record["status"] == "failed"
    assert "LLM generation quota exhausted" in run_record["error"]

    # Verify simulation state updated to FAILED and error stored
    assert fake_state.status == SimulationStatus.FAILED
    assert "LLM generation quota exhausted" in fake_state.error
    assert result["run_id"] in cleared_cancels


# ---------------------------------------------------------------------------
# Finding 4.3 Tests
# ---------------------------------------------------------------------------


def test_cancel_pending_run_sets_cancel_flag_and_updates_status(app_env, monkeypatch):
    registry = app_env["registry"]
    run = registry.create_run(
        run_type="simulation_run",
        entity_id="sim_cancel_pending",
        status="pending",
        linked_ids={"simulation_id": "sim_cancel_pending"},
    )

    cancel_requested = []
    monkeypatch.setattr("app.api.runs_actions._request_cancel", lambda rid: cancel_requested.append(rid))
    monkeypatch.setattr(runs_module, "_request_cancel", lambda rid: cancel_requested.append(rid))

    resp = runs_actions_module.execute_cancel_run(run["run_id"])
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "cancelled"
    assert data["success"] is True

    # Cancel flag must have been requested
    assert run["run_id"] in cancel_requested

    # Run in DB must be 'failed'
    db_run = registry.get_run(run["run_id"])
    assert db_run["status"] == "failed"


def test_execute_stop_simulation_sets_status_stopped(app_env, monkeypatch):
    registry = app_env["registry"]
    sim_id = "sim_112233445566"

    run = registry.create_run(
        run_type="simulation_run",
        entity_id=sim_id,
        status="processing",
        linked_ids={"simulation_id": sim_id},
    )

    fake_state = SimpleNamespace(
        simulation_id=sim_id,
        status=SimulationStatus.RUNNING,
    )
    monkeypatch.setattr(SimulationManager, "get_simulation", lambda self, sid: fake_state)

    status_transitions = []
    monkeypatch.setattr(
        SimulationManager,
        "_set_status",
        lambda self, st, new_status: status_transitions.append(new_status) or setattr(st, "status", new_status),
    )

    fake_run_state = SimulationRunState(simulation_id=sim_id, runner_status=RunnerStatus.STOPPED)
    monkeypatch.setattr(SimulationRunner, "stop_simulation", lambda sid: fake_run_state)
    from app.api import simulation_run as sim_run_module
    monkeypatch.setattr(sim_run_module, "run_registry", registry)
    monkeypatch.setattr(
        sim_run_module,
        "_simulation_resume_capability",
        lambda sid, st: {"available": True, "action": "resume"},
    )

    with app_env["client"].application.test_request_context(
        "/api/simulation/stop",
        method="POST",
        json={"simulation_id": sim_id},
    ):
        resp = sim_actions_module.execute_stop_simulation()
        status_code = resp.status_code if hasattr(resp, "status_code") else resp[1]
        assert status_code == 200

    # Must transition to STOPPED, not PAUSED!
    assert SimulationStatus.STOPPED in status_transitions
    assert fake_state.status == SimulationStatus.STOPPED

    # Run registry status must be 'stopped'
    updated_run = registry.get_run(run["run_id"])
    assert updated_run["status"] == "stopped"


def test_execute_stop_run_sets_status_stopped_via_set_status(app_env, monkeypatch):
    registry = app_env["registry"]
    sim_id = "sim_112233445577"

    run = registry.create_run(
        run_type="simulation_run",
        entity_id=sim_id,
        status="processing",
        linked_ids={"simulation_id": sim_id},
    )

    fake_state = SimpleNamespace(
        simulation_id=sim_id,
        status=SimulationStatus.RUNNING,
    )
    status_transitions = []
    monkeypatch.setattr(SimulationManager, "get_simulation", lambda self, sid: fake_state)
    monkeypatch.setattr(
        SimulationManager,
        "_set_status",
        lambda self, st, new_status: status_transitions.append(new_status) or setattr(st, "status", new_status),
    )

    fake_run_state = SimulationRunState(simulation_id=sim_id, runner_status=RunnerStatus.STOPPED)
    monkeypatch.setattr(SimulationRunner, "stop_simulation", lambda sid: fake_run_state)
    from app.api import simulation_run as sim_run_module
    monkeypatch.setattr(sim_run_module, "run_registry", registry)
    monkeypatch.setattr(
        sim_run_module,
        "_simulation_resume_capability",
        lambda sid, st: {"available": True, "action": "resume"},
    )

    resp = runs_actions_module.execute_stop_run(run["run_id"])
    status_code = resp.status_code if hasattr(resp, "status_code") else resp[1]
    assert status_code == 200

    assert SimulationStatus.STOPPED in status_transitions
    assert fake_state.status == SimulationStatus.STOPPED
