"""Unit-Tests der Start-Phasen von ``POST /api/simulation/start`` (#1079).

``start_simulation`` war ein 361-Zeilen-Handler mit radon-Rang F (cc 68). Er ist
jetzt ein Orchestrator über einzeln testbare Phasen; diese Datei deckt jede
Phase direkt ab. Die HTTP-Ebene (Status-Codes, Response-Shape) bleibt in
``test_simulation_api_routes.py`` und ``test_simulation_start_provider_route_api.py``
abgedeckt — hier geht es um das Verhalten der Phasen selbst.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_run as mod
from app.contracts.llm_routing_contract import ResolvedRoute
from app.services.llm_runtime import RuntimeLlmConfig
from app.services.simulation_manager import SimulationStatus

VALID_SIM_ID = "sim_0123456789ab"


@pytest.fixture
def app_ctx():
    """``json_error`` baut echte Flask-Responses und braucht einen App-Kontext."""
    app = Flask(__name__)
    with app.test_request_context():
        yield app


def _status(excinfo) -> int:
    return excinfo.value.response[1]


def _body(excinfo) -> dict:
    return excinfo.value.response[0].get_json()


def _state(status=SimulationStatus.READY, **overrides):
    state = MagicMock()
    state.status = status
    state.project_id = overrides.get("project_id", "proj-x")
    state.graph_id = overrides.get("graph_id")
    state.branch_name = overrides.get("branch_name")
    state.source_simulation_id = None
    state.root_simulation_id = None
    state.branch_depth = 0
    return state


# ---------------------------------------------------------------------------
# Phase 1 — Validierung
# ---------------------------------------------------------------------------

def test_parse_start_request_returns_defaults(app_ctx):
    req = mod._parse_start_request({"simulation_id": VALID_SIM_ID})

    assert req.simulation_id == VALID_SIM_ID
    assert req.platform == "parallel"
    assert req.max_rounds is None
    assert req.simulation_days is None
    assert req.llm_model_override is None
    assert req.ai_model_ref is None
    assert req.budget_config is None
    assert req.enable_graph_memory_update is False
    assert req.force is False


def test_parse_start_request_requires_simulation_id(app_ctx):
    with pytest.raises(mod._StartRejected) as excinfo:
        mod._parse_start_request({})

    assert _status(excinfo) == 400
    assert _body(excinfo)["error"] == "Please provide simulation_id"


def test_parse_start_request_rejects_malformed_id(app_ctx):
    with pytest.raises(mod._StartRejected) as excinfo:
        mod._parse_start_request({"simulation_id": "../etc/passwd"})

    assert _status(excinfo) == 400
    assert _body(excinfo)["code"] == "invalid_id"


def test_parse_start_request_rejects_unknown_platform(app_ctx):
    with pytest.raises(mod._StartRejected) as excinfo:
        mod._parse_start_request({"simulation_id": VALID_SIM_ID, "platform": "mastodon"})

    assert _status(excinfo) == 400
    assert "Invalid platform type" in _body(excinfo)["error"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"max_rounds": 0}, "max_rounds must be a positive integer"),
        ({"max_rounds": "abc"}, "max_rounds must be a valid integer"),
        ({"simulation_days": 366}, "simulation_days must be between 1 and 365"),
        ({"simulation_days": 0}, "simulation_days must be between 1 and 365"),
        ({"simulation_days": "x"}, "simulation_days must be a valid integer"),
    ],
)
def test_parse_start_request_bounded_ints(app_ctx, payload, message):
    with pytest.raises(mod._StartRejected) as excinfo:
        mod._parse_start_request({"simulation_id": VALID_SIM_ID, **payload})

    assert _status(excinfo) == 400
    assert _body(excinfo)["error"] == message


def test_parse_start_request_accepts_numeric_strings(app_ctx):
    req = mod._parse_start_request(
        {"simulation_id": VALID_SIM_ID, "max_rounds": "5", "simulation_days": "7"}
    )

    assert req.max_rounds == 5
    assert req.simulation_days == 7


def test_parse_ai_model_ref_returns_none_when_absent(app_ctx):
    assert mod._parse_ai_model_ref({"simulation_id": VALID_SIM_ID}) is None


def test_parse_ai_model_ref_rejects_invalid_payload(app_ctx):
    with pytest.raises(mod._StartRejected) as excinfo:
        mod._parse_ai_model_ref({"ai_model_ref": {"model_id": "only-model"}})

    assert _status(excinfo) == 400
    assert _body(excinfo)["error"] == "ai_model_ref ist ungültig"


def test_parse_ai_model_ref_rejects_legacy_combination(app_ctx):
    with pytest.raises(mod._StartRejected) as excinfo:
        mod._parse_ai_model_ref(
            {
                "ai_model_ref": {
                    "provider_connection_id": "conn-x",
                    "model_id": "m-1",
                    "source": "explicit",
                },
                "llm_model": "gemini-1.5-pro",
            }
        )

    assert _status(excinfo) == 400
    assert "llm_model" in _body(excinfo)["error"]


def test_parse_start_request_silences_legacy_fields_for_ai_model_ref(app_ctx):
    req = mod._parse_start_request(
        {
            "simulation_id": VALID_SIM_ID,
            "ai_model_ref": {
                "provider_connection_id": "conn-x",
                "model_id": "m-1",
                "source": "explicit",
            },
        }
    )

    assert req.ai_model_ref is not None
    assert req.llm_model_override is None
    assert req.llm_runtime.enabled is False


def test_parse_budget_config_rejects_limit_below_one(app_ctx):
    """`max_tokens` hat `ge=1` — ein negatives Limit ist keine Konfiguration."""
    with pytest.raises(mod._StartRejected) as excinfo:
        mod._parse_budget_config({"budget": {"max_tokens": -5}})

    assert _status(excinfo) == 400
    assert _body(excinfo)["error"].startswith("budget ist ungültig")


def test_parse_budget_config_rejects_unknown_field(app_ctx):
    """`RunBudgetConfig` ist strict — ein vertippter Feldname faellt auf."""
    with pytest.raises(mod._StartRejected) as excinfo:
        mod._parse_budget_config({"budget": {"max_total_tokens": 500}})

    assert _status(excinfo) == 400
    assert _body(excinfo)["error"].startswith("budget ist ungültig")


def test_parse_budget_config_accepts_valid_budget(app_ctx):
    budget = mod._parse_budget_config({"budget": {"max_tokens": 5000}})

    assert budget is not None and budget.max_tokens == 5000


def test_parse_budget_config_returns_none_without_budget(app_ctx):
    assert mod._parse_budget_config({}) is None


# ---------------------------------------------------------------------------
# Phase 2 — Startbarkeit
# ---------------------------------------------------------------------------

def test_ensure_startable_state_passes_ready_state_untouched(app_ctx):
    manager = MagicMock()
    state = _state(SimulationStatus.READY)
    req = mod._parse_start_request({"simulation_id": VALID_SIM_ID})

    assert mod._ensure_startable_state(manager, state, req) is False
    manager._reset_to_ready.assert_not_called()


def test_ensure_startable_state_rejects_unprepared_simulation(app_ctx, monkeypatch):
    monkeypatch.setattr(mod, "_check_simulation_prepared", lambda _sid: (False, {}))
    req = mod._parse_start_request({"simulation_id": VALID_SIM_ID})

    with pytest.raises(mod._StartRejected) as excinfo:
        mod._ensure_startable_state(MagicMock(), _state(SimulationStatus.CREATED), req)

    assert _status(excinfo) == 409
    assert _body(excinfo)["code"] == "simulation_not_prepared"


def test_ensure_startable_state_rejects_running_simulation_without_force(app_ctx, monkeypatch):
    monkeypatch.setattr(mod, "_check_simulation_prepared", lambda _sid: (True, {}))
    runner = MagicMock()
    runner.get_run_state.return_value = MagicMock(runner_status=MagicMock(value="running"))
    monkeypatch.setattr(mod, "SimulationRunner", runner)
    req = mod._parse_start_request({"simulation_id": VALID_SIM_ID})

    with pytest.raises(mod._StartRejected) as excinfo:
        mod._ensure_startable_state(MagicMock(), _state(SimulationStatus.RUNNING), req)

    assert _status(excinfo) == 409
    assert _body(excinfo)["code"] == "simulation_already_running"
    runner.stop_simulation.assert_not_called()


def test_ensure_startable_state_force_restarts_running_simulation(app_ctx, monkeypatch):
    monkeypatch.setattr(mod, "_check_simulation_prepared", lambda _sid: (True, {}))
    runner = MagicMock()
    runner.get_run_state.return_value = MagicMock(runner_status=MagicMock(value="running"))
    runner.cleanup_simulation_logs.return_value = {"success": True}
    monkeypatch.setattr(mod, "SimulationRunner", runner)
    manager = MagicMock()
    req = mod._parse_start_request({"simulation_id": VALID_SIM_ID, "force": True})

    assert mod._ensure_startable_state(manager, _state(SimulationStatus.RUNNING), req) is True
    runner.stop_simulation.assert_called_once_with(VALID_SIM_ID)
    runner.cleanup_simulation_logs.assert_called_once_with(VALID_SIM_ID)
    manager._reset_to_ready.assert_called_once()


def test_stop_running_simulation_ignores_idle_runner(app_ctx, monkeypatch):
    runner = MagicMock()
    runner.get_run_state.return_value = None
    monkeypatch.setattr(mod, "SimulationRunner", runner)

    mod._stop_running_simulation(VALID_SIM_ID, force=False)

    runner.stop_simulation.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 3 — Graph-Memory
# ---------------------------------------------------------------------------

def test_resolve_graph_memory_id_returns_none_when_disabled(app_ctx):
    req = mod._parse_start_request({"simulation_id": VALID_SIM_ID})

    assert mod._resolve_graph_memory_id(_state(graph_id="graph-1"), req) is None


def test_resolve_graph_memory_id_prefers_simulation_graph(app_ctx):
    req = mod._parse_start_request(
        {"simulation_id": VALID_SIM_ID, "enable_graph_memory_update": True}
    )

    assert mod._resolve_graph_memory_id(_state(graph_id="graph-1"), req) == "graph-1"


def test_resolve_graph_memory_id_falls_back_to_project_graph(app_ctx, monkeypatch):
    monkeypatch.setattr(
        mod.ProjectManager, "get_project", staticmethod(lambda _pid: MagicMock(graph_id="graph-proj"))
    )
    req = mod._parse_start_request(
        {"simulation_id": VALID_SIM_ID, "enable_graph_memory_update": True}
    )

    assert mod._resolve_graph_memory_id(_state(), req) == "graph-proj"


def test_resolve_graph_memory_id_rejects_missing_graph(app_ctx, monkeypatch):
    monkeypatch.setattr(mod.ProjectManager, "get_project", staticmethod(lambda _pid: None))
    req = mod._parse_start_request(
        {"simulation_id": VALID_SIM_ID, "enable_graph_memory_update": True}
    )

    with pytest.raises(mod._StartRejected) as excinfo:
        mod._resolve_graph_memory_id(_state(), req)

    assert _status(excinfo) == 400
    assert "graph_id" in _body(excinfo)["error"]


# ---------------------------------------------------------------------------
# Phase 4 — Provider-Prechecks
# ---------------------------------------------------------------------------

def test_precheck_runtime_provider_key_skips_without_override(app_ctx):
    mod._precheck_runtime_provider_key(RuntimeLlmConfig())


def test_precheck_runtime_provider_key_skips_when_key_present(app_ctx):
    mod._precheck_runtime_provider_key(
        RuntimeLlmConfig(provider="openai", api_key="sk-from-payload")
    )


def test_precheck_runtime_provider_key_rejects_remote_without_stored_key(app_ctx, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm_routing_seed.map_runtime_provider_to_route_provider",
        lambda _provider: "openai",
    )
    monkeypatch.setattr(
        "app.services.llm_provider_registry.LlmProviderRegistry",
        lambda: MagicMock(
            get_providers=lambda: [
                MagicMock(id="openai", type="openai", base_url="https://api.openai.com/v1")
            ]
        ),
    )
    monkeypatch.setattr(
        "app.services.secret_resolver.SecretResolver",
        lambda: MagicMock(get_api_key=lambda _pid, _ptype: None),
    )

    with pytest.raises(mod._StartRejected) as excinfo:
        mod._precheck_runtime_provider_key(RuntimeLlmConfig(provider="openai"))

    assert _status(excinfo) == 422
    assert "provider_override" in _body(excinfo)["error"]


def test_precheck_runtime_provider_key_allows_local_endpoint(app_ctx, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm_routing_seed.map_runtime_provider_to_route_provider",
        lambda _provider: "ollama",
    )
    monkeypatch.setattr(
        "app.services.llm_provider_registry.LlmProviderRegistry",
        lambda: MagicMock(
            get_providers=lambda: [
                MagicMock(id="ollama", type="openai_compatible", base_url="http://localhost:11434/v1")
            ]
        ),
    )
    monkeypatch.setattr(
        "app.services.secret_resolver.SecretResolver",
        lambda: MagicMock(get_api_key=lambda _pid, _ptype: None),
    )

    mod._precheck_runtime_provider_key(RuntimeLlmConfig(provider="ollama"))


def test_precheck_ai_model_ref_skips_when_absent(app_ctx):
    mod._precheck_ai_model_ref(None)


def test_precheck_ai_model_ref_maps_value_error_to_422(app_ctx, monkeypatch):
    def _raise(_ref):
        raise ValueError("connection disabled")

    monkeypatch.setattr("app.services.llm_routing_seed.prevalidate_ai_model_ref", _raise)

    with pytest.raises(mod._StartRejected) as excinfo:
        mod._precheck_ai_model_ref(MagicMock(name="AiModelRef"))

    assert _status(excinfo) == 422
    assert _body(excinfo)["error"] == "connection disabled"


# ---------------------------------------------------------------------------
# Phase 5 — Run-Registrierung
# ---------------------------------------------------------------------------

def test_register_start_run_creates_run_and_seeds_routing(app_ctx, monkeypatch):
    registry = MagicMock()
    registry.create_run.return_value = {"run_id": "run-1"}
    monkeypatch.setattr(mod, "run_registry", registry)
    monkeypatch.setattr(mod, "_simulation_run_artifacts", lambda _sid: [])
    monkeypatch.setattr(mod, "_simulation_resume_capability", lambda _sid, _state: {"resumable": False})
    seed = MagicMock()
    monkeypatch.setattr(mod, "seed_run_stage_routing", seed)
    applied = {}
    monkeypatch.setattr(
        mod,
        "_apply_budget_to_simulation",
        lambda sid, rid, budget, _fn: applied.update(sid=sid, rid=rid, budget=budget),
    )
    req = mod._parse_start_request({"simulation_id": VALID_SIM_ID, "platform": "reddit"})

    run_record = mod._register_start_run(req, _state(graph_id="graph-1"))

    assert run_record == {"run_id": "run-1"}
    create_kwargs = registry.create_run.call_args.kwargs
    assert create_kwargs["run_type"] == "simulation_run"
    assert create_kwargs["entity_id"] == VALID_SIM_ID
    assert create_kwargs["metadata"]["platform"] == "reddit"
    assert seed.call_args.args == ("run-1", "simulation_rounds")
    assert applied == {"sid": VALID_SIM_ID, "rid": "run-1", "budget": None}


# ---------------------------------------------------------------------------
# Phase 6 — Routen-Auflösung
# ---------------------------------------------------------------------------

def _resolved_route(base_url="https://api.openai.com/v1"):
    return ResolvedRoute(
        stage="simulation_rounds",
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


def test_resolve_start_route_locks_stage_and_returns_key(app_ctx, monkeypatch):
    route = _resolved_route()
    router = _patch_router(monkeypatch, route)
    monkeypatch.setattr(mod, "resolve_route_api_key", lambda _route, _runtime: "sk-bound")

    resolved, api_key = mod._resolve_start_route("run-1", RuntimeLlmConfig())

    assert resolved is route
    assert api_key == "sk-bound"
    router.lock_stage.assert_called_once_with("simulation_rounds", route)


def test_resolve_start_route_marks_run_failed_when_key_missing(app_ctx, monkeypatch):
    _patch_router(monkeypatch, _resolved_route())
    monkeypatch.setattr(mod, "resolve_route_api_key", lambda _route, _runtime: None)
    registry = MagicMock()
    monkeypatch.setattr(mod, "run_registry", registry)

    with pytest.raises(mod._StartRejected) as excinfo:
        mod._resolve_start_route("run-1", RuntimeLlmConfig())

    assert _status(excinfo) == 422
    assert registry.update_run.call_args.kwargs["status"] == "failed"


def test_resolve_start_route_allows_local_endpoint_without_key(app_ctx, monkeypatch):
    route = _resolved_route(base_url="http://localhost:11434/v1")
    _patch_router(monkeypatch, route)
    monkeypatch.setattr(mod, "resolve_route_api_key", lambda _route, _runtime: None)

    resolved, api_key = mod._resolve_start_route("run-1", RuntimeLlmConfig())

    assert resolved is route
    assert api_key is None


# ---------------------------------------------------------------------------
# Phase 7 — Config-Overrides
# ---------------------------------------------------------------------------

def test_apply_route_to_simulation_config_skips_without_overrides(app_ctx, monkeypatch):
    store = MagicMock()
    monkeypatch.setattr(mod, "get_artifact_store", lambda: store)
    req = mod._parse_start_request({"simulation_id": VALID_SIM_ID})

    mod._apply_route_to_simulation_config(req, _resolved_route())

    store.read_json.assert_not_called()
    store.write_json.assert_not_called()


def test_apply_route_to_simulation_config_writes_simulation_hours(app_ctx, monkeypatch):
    store = MagicMock()
    store.read_json.return_value = {"time_config": {"total_simulation_hours": 24}}
    monkeypatch.setattr(mod, "get_artifact_store", lambda: store)
    req = mod._parse_start_request({"simulation_id": VALID_SIM_ID, "simulation_days": 3})

    mod._apply_route_to_simulation_config(req, _resolved_route())

    written = store.write_json.call_args.args[2]
    assert written["time_config"]["total_simulation_hours"] == 72


def test_apply_route_to_simulation_config_rejects_missing_config(app_ctx, monkeypatch):
    store = MagicMock()
    store.read_json.return_value = None
    monkeypatch.setattr(mod, "get_artifact_store", lambda: store)
    req = mod._parse_start_request({"simulation_id": VALID_SIM_ID, "simulation_days": 3})

    with pytest.raises(mod._StartRejected) as excinfo:
        mod._apply_route_to_simulation_config(req, _resolved_route())

    assert _status(excinfo) == 404
    assert _body(excinfo)["code"] == "simulation_not_prepared"


def test_apply_route_to_simulation_config_writes_model_for_ai_model_ref(app_ctx, monkeypatch):
    store = MagicMock()
    store.read_json.return_value = {"llm_model": "stale-model"}
    monkeypatch.setattr(mod, "get_artifact_store", lambda: store)
    req = mod._parse_start_request(
        {
            "simulation_id": VALID_SIM_ID,
            "ai_model_ref": {
                "provider_connection_id": "conn-x",
                "model_id": "m-1",
                "source": "explicit",
            },
        }
    )

    mod._apply_route_to_simulation_config(req, _resolved_route())

    written = store.write_json.call_args.args[2]
    assert written["llm_model"] == "gpt-4o"
    assert written["llm_base_url"] == "https://api.openai.com/v1"


# ---------------------------------------------------------------------------
# Phase 8 — Response
# ---------------------------------------------------------------------------

def test_build_start_response_carries_applied_overrides(app_ctx):
    req = mod._parse_start_request(
        {
            "simulation_id": VALID_SIM_ID,
            "max_rounds": 4,
            "simulation_days": 2,
            "enable_graph_memory_update": True,
        }
    )
    run_state = MagicMock(to_dict=MagicMock(return_value={"simulation_id": VALID_SIM_ID}))

    payload = mod._build_start_response(req, run_state, "run-1", "graph-1", True)

    assert payload == {
        "simulation_id": VALID_SIM_ID,
        "max_rounds_applied": 4,
        "simulation_days_applied": 2,
        "graph_memory_update_enabled": True,
        "force_restarted": True,
        "run_id": "run-1",
        "graph_id": "graph-1",
    }


def test_build_start_response_omits_unset_overrides(app_ctx):
    req = mod._parse_start_request({"simulation_id": VALID_SIM_ID})
    run_state = MagicMock(to_dict=MagicMock(return_value={"simulation_id": VALID_SIM_ID}))

    payload = mod._build_start_response(req, run_state, "run-1", None, False)

    assert "max_rounds_applied" not in payload
    assert "simulation_days_applied" not in payload
    assert "graph_id" not in payload
    assert payload["graph_memory_update_enabled"] is False
