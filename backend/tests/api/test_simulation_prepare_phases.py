"""Unit-Tests der Prepare-Phasen von ``POST /api/simulation/prepare`` (#1080).

``prepare_simulation`` war ein ~560-Zeilen-Handler mit radon-Rang F (cc 65),
inklusive der kompletten Hintergrund-Job-Closure. Er ist jetzt ein Orchestrator
über einzeln testbare Phasen; diese Datei deckt jede Phase direkt ab. Die
HTTP-Ebene bleibt in ``test_simulation_prepare_routing.py`` und den
benachbarten Endpunkt-Tests abgedeckt.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_prepare as mod
from app.contracts.llm_routing_contract import ResolvedRoute
from app.services.llm_runtime import RuntimeLlmConfig
from app.services.simulation_manager import SimulationStatus

VALID_SIM_ID = "sim_0123456789ab"
AI_MODEL_REF = {
    "provider_connection_id": "conn-x",
    "model_id": "m-1",
    "source": "explicit",
}


@pytest.fixture
def app_ctx():
    """``json_error``/``json_success`` bauen echte Flask-Responses."""
    app = Flask(__name__)
    with app.test_request_context():
        yield app


@pytest.fixture(autouse=True)
def _no_profile_expansion(monkeypatch):
    """Profil-Expansion ist ein eigener Codepfad (Issue #888) und hier stumm."""
    monkeypatch.setattr(
        "app.utils.llm_profile_resolver.expand_profile_in_data", lambda _data: None
    )


def _status(excinfo) -> int:
    return excinfo.value.response[1]


def _body(excinfo) -> dict:
    return excinfo.value.response[0].get_json()


def _project(**overrides):
    return SimpleNamespace(
        llm_profile_id=overrides.get("llm_profile_id"),
        simulation_requirement=overrides.get("simulation_requirement", "Requirement text"),
    )


def _state(**overrides):
    return SimpleNamespace(
        project_id=overrides.get("project_id", "proj-x"),
        graph_id=overrides.get("graph_id", "graph-1"),
        branch_name=None,
        branch_depth=0,
        source_simulation_id=None,
        root_simulation_id=None,
        entities_count=overrides.get("entities_count", 0),
        entity_types=overrides.get("entity_types", []),
        error=None,
    )


def _routing(**overrides) -> mod._PrepareRouting:
    return mod._PrepareRouting(
        llm_model_override=overrides.get("llm_model_override"),
        llm_runtime=overrides.get("llm_runtime", RuntimeLlmConfig()),
        routed_profile_id=overrides.get("routed_profile_id"),
        client_requested_override=overrides.get("client_requested_override", False),
    )


def _inputs(**overrides) -> mod._PrepareInputs:
    return mod._PrepareInputs(
        simulation_requirement=overrides.get("simulation_requirement", "Requirement text"),
        document_text=overrides.get("document_text", ""),
        entity_types=overrides.get("entity_types"),
        use_llm_for_profiles=overrides.get("use_llm_for_profiles", True),
        parallel_profile_count=overrides.get("parallel_profile_count"),
        max_agents=overrides.get("max_agents"),
        quota_plan=overrides.get("quota_plan"),
        agent_language_override=overrides.get("agent_language_override"),
    )


# ---------------------------------------------------------------------------
# Phase 1 — Validierung
# ---------------------------------------------------------------------------

def test_parse_prepare_identity_returns_id_without_ref(app_ctx):
    assert mod._parse_prepare_identity({"simulation_id": VALID_SIM_ID}) == (VALID_SIM_ID, None)


def test_parse_prepare_identity_requires_simulation_id(app_ctx):
    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._parse_prepare_identity({})

    assert _status(excinfo) == 400
    assert _body(excinfo)["error"] == "Please provide simulation_id"


def test_parse_prepare_identity_rejects_malformed_id(app_ctx):
    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._parse_prepare_identity({"simulation_id": "../etc/passwd"})

    assert _status(excinfo) == 400
    assert _body(excinfo)["code"] == "invalid_id"


def test_parse_prepare_identity_rejects_invalid_ai_model_ref(app_ctx):
    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._parse_prepare_identity(
            {"simulation_id": VALID_SIM_ID, "ai_model_ref": {"model_id": "only"}}
        )

    assert _status(excinfo) == 400
    assert _body(excinfo)["error"] == "ai_model_ref ist ungültig"


@pytest.mark.parametrize(
    "legacy_field", ["llm_model", "llm_profile_id", "llm_provider", "llm_runtime"]
)
def test_parse_prepare_identity_rejects_legacy_combination(app_ctx, legacy_field):
    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._parse_prepare_identity(
            {
                "simulation_id": VALID_SIM_ID,
                "ai_model_ref": AI_MODEL_REF,
                legacy_field: "something",
            }
        )

    assert _status(excinfo) == 400
    assert legacy_field in _body(excinfo)["error"]


def test_parse_prepare_identity_accepts_valid_ref(app_ctx):
    simulation_id, ref = mod._parse_prepare_identity(
        {"simulation_id": VALID_SIM_ID, "ai_model_ref": AI_MODEL_REF}
    )

    assert simulation_id == VALID_SIM_ID
    assert ref is not None and ref.model_id == "m-1"


def test_parse_prepare_budget_returns_none_without_budget(app_ctx):
    assert mod._parse_prepare_budget({}) is None


def test_parse_prepare_budget_rejects_invalid_budget(app_ctx):
    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._parse_prepare_budget({"budget": {"max_tokens": -1}})

    assert _status(excinfo) == 400
    assert _body(excinfo)["error"] == "budget ist ungültig"


def test_load_prepare_project_rejects_missing_project(app_ctx, monkeypatch):
    monkeypatch.setattr(mod.ProjectManager, "get_project", staticmethod(lambda _pid: None))

    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._load_prepare_project(_state())

    assert _status(excinfo) == 404
    assert "Project does not exist" in _body(excinfo)["error"]


# ---------------------------------------------------------------------------
# Phase 2 — Routing
# ---------------------------------------------------------------------------

def test_read_client_choice_ignores_default_placeholder(app_ctx):
    choice = mod._read_client_choice({"llm_model": "default"}, _project())

    assert choice.explicit_model_override is False
    assert choice.explicit_runtime_request is False


def test_read_client_choice_detects_explicit_model(app_ctx):
    choice = mod._read_client_choice(
        {"llm_model": "gpt-4o", "llm_provider": {"provider": "openai"}}, _project()
    )

    assert choice.explicit_model_override is True
    assert choice.explicit_runtime_request is True


def test_client_choice_profile_override_only_when_differing(app_ctx):
    same = mod._read_client_choice({"llm_profile_id": "p1"}, _project(llm_profile_id="p1"))
    differing = mod._read_client_choice({"llm_profile_id": "p2"}, _project(llm_profile_id="p1"))

    assert same.explicit_profile_override is False
    assert differing.explicit_profile_override is True


def test_resolve_prepare_routing_falls_back_to_project_profile(app_ctx):
    routing = mod._resolve_prepare_routing({}, _project(llm_profile_id="proj-profile"), None)

    assert routing.routed_profile_id == "proj-profile"
    assert routing.client_requested_override is False


def test_resolve_prepare_routing_prefers_request_profile(app_ctx):
    routing = mod._resolve_prepare_routing(
        {"llm_profile_id": "req-profile"}, _project(llm_profile_id="proj-profile"), None
    )

    assert routing.routed_profile_id == "req-profile"
    assert routing.client_requested_override is True


def test_resolve_prepare_routing_explicit_model_wins_over_profile(app_ctx):
    routing = mod._resolve_prepare_routing(
        {"llm_model": "gpt-4o"}, _project(llm_profile_id="proj-profile"), None
    )

    assert routing.routed_profile_id is None
    assert routing.llm_model_override == "gpt-4o"
    assert routing.client_requested_override is True


def test_resolve_prepare_routing_ai_model_ref_silences_legacy(app_ctx):
    routing = mod._resolve_prepare_routing(
        {}, _project(llm_profile_id="proj-profile"), MagicMock(name="AiModelRef")
    )

    assert routing.routed_profile_id is None
    assert routing.llm_model_override is None
    assert routing.llm_runtime.enabled is False
    assert routing.client_requested_override is True


def test_resolve_prepare_routing_maps_runtime_value_error_to_400(app_ctx):
    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._resolve_prepare_routing({"llm_provider": "not-an-object"}, _project(), None)

    assert _status(excinfo) == 400


# ---------------------------------------------------------------------------
# Phase 3 — Kurzschluss
# ---------------------------------------------------------------------------

def test_already_prepared_response_returns_none_when_unprepared(app_ctx, monkeypatch):
    monkeypatch.setattr(mod, "_check_simulation_prepared", lambda _sid: (False, {"reason": "x"}))

    assert mod._already_prepared_response(VALID_SIM_ID) is None


def test_already_prepared_response_short_circuits(app_ctx, monkeypatch):
    monkeypatch.setattr(
        mod, "_check_simulation_prepared", lambda _sid: (True, {"status": "ready"})
    )

    response, status = mod._already_prepared_response(VALID_SIM_ID)

    assert status == 200
    payload = response.get_json()
    assert payload["data"]["already_prepared"] is True
    assert payload["data"]["status"] == "ready"


# ---------------------------------------------------------------------------
# Phase 4 — Eingaben
# ---------------------------------------------------------------------------

def test_collect_prepare_inputs_requires_simulation_requirement(app_ctx, monkeypatch):
    monkeypatch.setattr(mod.ProjectManager, "get_extracted_text", staticmethod(lambda _pid: ""))

    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._collect_prepare_inputs({}, _project(simulation_requirement=""), _state())

    assert _status(excinfo) == 400
    assert "simulation_requirement" in _body(excinfo)["error"]


def test_collect_prepare_inputs_rejects_invalid_quota_plan(app_ctx, monkeypatch):
    monkeypatch.setattr(mod.ProjectManager, "get_extracted_text", staticmethod(lambda _pid: ""))

    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._collect_prepare_inputs(
            {"quota_plan": {"total": 5, "targets": []}}, _project(), _state()
        )

    assert _status(excinfo) == 400
    assert _body(excinfo)["error"].startswith("Invalid quota_plan")


def test_collect_prepare_inputs_defaults_and_language_guard(app_ctx, monkeypatch):
    monkeypatch.setattr(
        mod.ProjectManager, "get_extracted_text", staticmethod(lambda _pid: "doc text")
    )

    inputs = mod._collect_prepare_inputs({"language": "FR"}, _project(), _state())

    assert inputs.document_text == "doc text"
    assert inputs.use_llm_for_profiles is True
    assert inputs.parallel_profile_count is None
    assert inputs.max_agents is None
    assert inputs.agent_language_override is None


def test_collect_prepare_inputs_keeps_supported_language(app_ctx, monkeypatch):
    monkeypatch.setattr(mod.ProjectManager, "get_extracted_text", staticmethod(lambda _pid: ""))

    inputs = mod._collect_prepare_inputs({"language": " DE "}, _project(), _state())

    assert inputs.agent_language_override == "de"


def test_collect_prepare_inputs_applies_max_agents_floor(app_ctx, monkeypatch):
    monkeypatch.setattr(mod.ProjectManager, "get_extracted_text", staticmethod(lambda _pid: ""))

    inputs = mod._collect_prepare_inputs({"max_agents": 3}, _project(), _state())

    assert inputs.max_agents == mod.MIN_SIMULATION_AGENTS


# ---------------------------------------------------------------------------
# Phase 5 — Entitäten-Vorschau
# ---------------------------------------------------------------------------

def _patch_entity_preview(monkeypatch, *, count=7, types=("Person",), exclusions=()):
    preview = SimpleNamespace(
        entities=[MagicMock() for _ in range(count)],
        filtered_count=count,
        entity_types=set(types),
    )
    reader = MagicMock()
    reader.filter_defined_entities.return_value = preview
    monkeypatch.setattr(mod, "EntityReader", lambda _storage: reader)
    monkeypatch.setattr(
        mod,
        "filter_eligible_entities",
        lambda entities, degradations=None: SimpleNamespace(
            eligible=entities, exclusions=list(exclusions)
        ),
    )
    return preview


def test_preview_entity_counts_writes_state(app_ctx, monkeypatch):
    _patch_entity_preview(monkeypatch, count=7)
    state = _state()

    mod._preview_entity_counts(state, MagicMock(), _inputs())

    assert state.entities_count == 7
    assert state.entity_types == ["Person"]


def test_preview_entity_counts_caps_at_max_agents(app_ctx, monkeypatch):
    _patch_entity_preview(monkeypatch, count=30)
    state = _state()

    mod._preview_entity_counts(state, MagicMock(), _inputs(max_agents=12))

    assert state.entities_count == 12


def test_preview_entity_counts_swallows_reader_errors(app_ctx, monkeypatch):
    def _boom(_storage):
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(mod, "EntityReader", _boom)
    state = _state(entities_count=0)

    mod._preview_entity_counts(state, MagicMock(), _inputs())

    assert state.entities_count == 0


# ---------------------------------------------------------------------------
# Phase 6 — Precheck und Registrierung
# ---------------------------------------------------------------------------

def test_precheck_prepare_ai_model_ref_skips_when_absent(app_ctx):
    mod._precheck_prepare_ai_model_ref(None)


def test_precheck_prepare_ai_model_ref_maps_value_error_to_400(app_ctx, monkeypatch):
    def _raise(_ref):
        raise ValueError("connection disabled")

    monkeypatch.setattr("app.services.llm_routing_seed.prevalidate_ai_model_ref", _raise)

    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._precheck_prepare_ai_model_ref(MagicMock(name="AiModelRef"))

    assert _status(excinfo) == 400
    assert _body(excinfo)["error"] == "connection disabled"


def test_register_prepare_run_creates_run_and_task(app_ctx, monkeypatch):
    registry = MagicMock()
    registry.create_run.return_value = {"run_id": "run-1"}
    monkeypatch.setattr(mod, "run_registry", registry)
    monkeypatch.setattr(mod, "_simulation_run_artifacts", lambda _sid: [])
    task_manager = MagicMock()
    task_manager.create_task.return_value = "task-1"
    req = mod._PrepareRequest(
        simulation_id=VALID_SIM_ID,
        ai_model_ref=None,
        budget_config=None,
        force_regenerate=False,
    )

    run_record, task_id = mod._register_prepare_run(
        req, _state(), _routing(llm_model_override="gpt-4o"), task_manager
    )

    assert run_record == {"run_id": "run-1"}
    assert task_id == "task-1"
    create_kwargs = registry.create_run.call_args.kwargs
    assert create_kwargs["run_type"] == "simulation_prepare"
    assert create_kwargs["metadata"]["llm_model"] == "gpt-4o"
    assert "budget" not in create_kwargs["metadata"]
    assert task_manager.create_task.call_args.kwargs["metadata"]["run_id"] == "run-1"


def test_register_prepare_run_carries_budget_metadata(app_ctx, monkeypatch):
    from app.contracts.run_budget_contract import RunBudgetConfig

    registry = MagicMock()
    registry.create_run.return_value = {"run_id": "run-1"}
    monkeypatch.setattr(mod, "run_registry", registry)
    monkeypatch.setattr(mod, "_simulation_run_artifacts", lambda _sid: [])
    task_manager = MagicMock()
    task_manager.create_task.return_value = "task-1"
    req = mod._PrepareRequest(
        simulation_id=VALID_SIM_ID,
        ai_model_ref=None,
        budget_config=RunBudgetConfig(max_tokens=1000),
        force_regenerate=False,
    )

    mod._register_prepare_run(req, _state(), _routing(), task_manager)

    metadata = registry.create_run.call_args.kwargs["metadata"]
    assert metadata["budget"]["max_tokens"] == 1000


# ---------------------------------------------------------------------------
# Fehlerpfad — Run/Task als failed markieren
# ---------------------------------------------------------------------------

def test_reject_and_fail_prepare_run_marks_run_failed(app_ctx, monkeypatch):
    registry = MagicMock()
    registry.update_run.return_value = {"run_id": "run-1", "status": "failed"}
    monkeypatch.setattr(mod, "run_registry", registry)
    task_manager = MagicMock()

    rejected = mod._reject_and_fail_prepare_run(
        {"run_id": "run-1"}, "task-1", task_manager, "kaputt", status=422, context="im Test"
    )

    assert rejected.response[1] == 422
    task_manager.fail_task.assert_called_once_with("task-1", "kaputt")
    assert registry.update_run.call_args.kwargs["status"] == "failed"


def test_reject_and_fail_prepare_run_returns_500_when_run_vanished(app_ctx, monkeypatch):
    registry = MagicMock()
    registry.update_run.return_value = None
    monkeypatch.setattr(mod, "run_registry", registry)

    rejected = mod._reject_and_fail_prepare_run(
        {"run_id": "run-1"}, "task-1", MagicMock(), "kaputt", status=422, context="im Test"
    )

    assert rejected.response[1] == 500
    assert rejected.response[0].get_json()["code"] == "internal_error"


def test_reject_and_fail_prepare_run_returns_500_on_persistence_error(app_ctx, monkeypatch):
    registry = MagicMock()
    registry.update_run.side_effect = OSError("disk full")
    monkeypatch.setattr(mod, "run_registry", registry)

    rejected = mod._reject_and_fail_prepare_run(
        {"run_id": "run-1"}, "task-1", MagicMock(), "kaputt", status=400, context="im Test"
    )

    assert rejected.response[1] == 500


# ---------------------------------------------------------------------------
# Phase 7 — Routing-Seed
# ---------------------------------------------------------------------------

def test_seed_prepare_routing_without_ref_passes_profile(app_ctx, monkeypatch):
    seed = MagicMock()
    monkeypatch.setattr(mod, "seed_run_stage_routing", seed)

    mod._seed_prepare_routing(
        {"run_id": "run-1"}, "task-1", MagicMock(), _routing(routed_profile_id="p1"), None
    )

    assert seed.call_args.args == ("run-1", "persona_generation")
    assert seed.call_args.kwargs["llm_profile_id"] == "p1"
    assert "ai_model_ref" not in seed.call_args.kwargs


def test_seed_prepare_routing_with_ref_forwards_ref(app_ctx, monkeypatch):
    seed = MagicMock()
    monkeypatch.setattr(mod, "seed_run_stage_routing", seed)
    ref = MagicMock(name="AiModelRef")

    mod._seed_prepare_routing({"run_id": "run-1"}, "task-1", MagicMock(), _routing(), ref)

    assert seed.call_args.kwargs["ai_model_ref"] is ref


def test_seed_prepare_routing_failure_marks_run_failed(app_ctx, monkeypatch):
    def _raise(*_args, **_kwargs):
        raise ValueError("model not on connection")

    monkeypatch.setattr(mod, "seed_run_stage_routing", _raise)
    registry = MagicMock()
    registry.update_run.return_value = {"run_id": "run-1"}
    monkeypatch.setattr(mod, "run_registry", registry)
    task_manager = MagicMock()

    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._seed_prepare_routing(
            {"run_id": "run-1"}, "task-1", task_manager, _routing(), MagicMock()
        )

    assert _status(excinfo) == 400
    assert _body(excinfo)["error"] == "model not on connection"
    task_manager.fail_task.assert_called_once_with("task-1", "model not on connection")


# ---------------------------------------------------------------------------
# Phase 8 — Routen-Auflösung
# ---------------------------------------------------------------------------

def _resolved_route(base_url="https://api.openai.com/v1"):
    return ResolvedRoute(
        stage="persona_generation",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized=base_url,
        routing_version=1,
        provider_options={},
    )


def _patch_router(monkeypatch, route):
    router = MagicMock()
    router.resolve.return_value = route
    router.lock_stage.return_value = route
    monkeypatch.setattr(mod, "StageModelRouter", lambda _run_id: router)
    return router


def test_resolve_prepare_route_locks_stage_and_returns_key(app_ctx, monkeypatch):
    route = _resolved_route()
    router = _patch_router(monkeypatch, route)
    monkeypatch.setattr(mod, "resolve_route_api_key", lambda _route, _runtime: "sk-bound")

    resolved, api_key = mod._resolve_prepare_route(
        {"run_id": "run-1"}, "task-1", MagicMock(), RuntimeLlmConfig()
    )

    assert resolved is route
    assert api_key == "sk-bound"
    router.lock_stage.assert_called_once_with("persona_generation", route)


def test_resolve_prepare_route_guards_missing_key_with_422(app_ctx, monkeypatch):
    _patch_router(monkeypatch, _resolved_route())
    monkeypatch.setattr(mod, "resolve_route_api_key", lambda _route, _runtime: None)
    registry = MagicMock()
    registry.update_run.return_value = {"run_id": "run-1"}
    monkeypatch.setattr(mod, "run_registry", registry)
    task_manager = MagicMock()

    with pytest.raises(mod._PrepareRejected) as excinfo:
        mod._resolve_prepare_route(
            {"run_id": "run-1"}, "task-1", task_manager, RuntimeLlmConfig()
        )

    assert _status(excinfo) == 422
    assert "provider_override" in _body(excinfo)["error"]
    task_manager.fail_task.assert_called_once()


def test_resolve_prepare_route_uses_placeholder_for_local_endpoint(app_ctx, monkeypatch):
    _patch_router(monkeypatch, _resolved_route(base_url="http://localhost:11434/v1"))
    monkeypatch.setattr(mod, "resolve_route_api_key", lambda _route, _runtime: None)

    _resolved, api_key = mod._resolve_prepare_route(
        {"run_id": "run-1"}, "task-1", MagicMock(), RuntimeLlmConfig()
    )

    assert api_key == mod.LOCAL_NO_AUTH_API_KEY


# ---------------------------------------------------------------------------
# Phase 9 — Hintergrund-Job
# ---------------------------------------------------------------------------

def test_progress_callback_scales_stage_progress(app_ctx):
    task_manager = MagicMock()

    callback = mod._build_progress_callback(task_manager, "task-1")
    callback("generating_profiles", 50, "Persona 5", current=5, total=10)

    kwargs = task_manager.update_task.call_args.kwargs
    assert kwargs["progress"] == 45  # 20 + (70-20) * 0.5
    assert kwargs["message"] == "[2/4] GenerateAgentpersona: 5/10 - Persona 5"
    assert kwargs["progress_detail"]["current_stage"] == "generating_profiles"


def test_progress_callback_handles_unknown_stage(app_ctx):
    task_manager = MagicMock()

    callback = mod._build_progress_callback(task_manager, "task-1")
    callback("mystery", 10, "läuft")

    kwargs = task_manager.update_task.call_args.kwargs
    assert kwargs["progress"] == 10
    assert kwargs["message"] == "[1/4] mystery: läuft"


def test_prepare_job_runs_service_and_completes_task(app_ctx):
    manager = MagicMock()
    manager.prepare_simulation.return_value = MagicMock(
        to_simple_dict=MagicMock(return_value={"simulation_id": VALID_SIM_ID})
    )
    task_manager = MagicMock()

    job = mod._make_prepare_job(
        manager=manager,
        task_manager=task_manager,
        task_id="task-1",
        simulation_id=VALID_SIM_ID,
        inputs=_inputs(document_text="doc", max_agents=10),
        storage=MagicMock(),
        llm_model="gpt-4o",
        effective_llm_runtime=RuntimeLlmConfig(),
    )
    job()

    service_kwargs = manager.prepare_simulation.call_args.kwargs
    assert service_kwargs["simulation_id"] == VALID_SIM_ID
    assert service_kwargs["document_text"] == "doc"
    assert service_kwargs["llm_model"] == "gpt-4o"
    assert service_kwargs["max_agents"] == 10
    result = task_manager.complete_task.call_args.kwargs["result"]
    assert result["simulation_id"] == VALID_SIM_ID
    assert result["degradations"] is not None


def test_prepare_job_marks_simulation_failed_on_error(app_ctx):
    manager = MagicMock()
    manager.prepare_simulation.side_effect = RuntimeError("kein Graph")
    failed_state = _state()
    manager.get_simulation.return_value = failed_state
    task_manager = MagicMock()

    job = mod._make_prepare_job(
        manager=manager,
        task_manager=task_manager,
        task_id="task-1",
        simulation_id=VALID_SIM_ID,
        inputs=_inputs(),
        storage=MagicMock(),
        llm_model="gpt-4o",
        effective_llm_runtime=RuntimeLlmConfig(),
    )
    job()

    task_manager.fail_task.assert_called_once_with("task-1", "kein Graph")
    assert failed_state.error == "kein Graph"
    manager._set_status.assert_called_once_with(failed_state, SimulationStatus.FAILED)
    assert "degradations" in task_manager.update_task.call_args.kwargs["result"]


# ---------------------------------------------------------------------------
# Phase 10 — Response
# ---------------------------------------------------------------------------

def test_build_prepare_response_reports_queued_run(app_ctx):
    state = _state(entities_count=12, entity_types=["Person", "Org"])

    payload = mod._build_prepare_response(
        VALID_SIM_ID, "task-1", {"run_id": "run-1"}, state, _inputs()
    )

    assert payload["simulation_id"] == VALID_SIM_ID
    assert payload["task_id"] == "task-1"
    assert payload["run_id"] == "run-1"
    assert payload["status"] == "preparing"
    assert payload["already_prepared"] is False
    assert payload["expected_entities_count"] == 12
    assert payload["entity_types"] == ["Person", "Org"]
    assert payload["persona_target"]["entity_count"] == 12
