"""API-Contract: POST /api/simulation/start akzeptiert eine explizite
``AiModelRef`` (ProviderConnection + Modell) und reicht sie an
``seed_run_stage_routing`` weiter, sodass der OASIS-Subprozess Modell, Base-URL
und gebundenen Key derselben Connection erhält (Root Cause des
``404 model MiniMax-M3 not found``).

Die Konflikt-Prüfungen greifen vor der Run-Record-Creation — daher ohne
Storage-/Routing-Stubs testbar. Der Forward-Test patcht die schwere
Sim-Infrastruktur und prüft nur, dass die AiModelRef unverändert durchgereicht
wird und die Legacy-Felder genullt sind.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import simulation_bp

VALID_SIM_ID = "sim_0123456789ab"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.config["TESTING"] = True
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    with app.test_request_context(), app.test_client() as test_client:
        yield test_client


def _ref_body(**extra):
    body = {
        "simulation_id": VALID_SIM_ID,
        "platform": "parallel",
        "ai_model_ref": {
            "provider_connection_id": "conn-minimax",
            "model_id": "MiniMax-M3",
            "source": "explicit",
        },
    }
    body.update(extra)
    return body


def test_ai_model_ref_conflicts_with_llm_model_returns_400(client):
    resp = client.post("/api/simulation/start", json=_ref_body(llm_model="gemini-1.5-pro"))
    assert resp.status_code == 400
    assert b"ai_model_ref" in resp.data


def test_ai_model_ref_conflicts_with_llm_provider_returns_400(client):
    resp = client.post(
        "/api/simulation/start",
        json=_ref_body(llm_provider={"provider": "openai", "base_url": "https://api.openai.com/v1"}),
    )
    assert resp.status_code == 400
    assert b"ai_model_ref" in resp.data


def test_invalid_ai_model_ref_returns_400(client):
    resp = client.post(
        "/api/simulation/start",
        json={"simulation_id": VALID_SIM_ID, "platform": "parallel", "ai_model_ref": {"model_id": "x"}},
    )
    assert resp.status_code == 400


def _stub_start_infra(monkeypatch):
    """Stubbt die schwere Sim-Infrastruktur weg, damit der Endpunkt nach dem
    ``ai_model_ref``-Parsing zu HTTP 200 läuft. ``seed_run_stage_routing`` wird
    NICHT gestubbt — das ist gerade der Aufruf, dessen ``ai_model_ref``-KWArg wir
    verifizieren."""
    from app.services.simulation_manager import SimulationStatus

    fake_state = MagicMock()
    fake_state.status = SimulationStatus.READY
    fake_state.project_id = "proj-x"
    fake_state.graph_id = None
    fake_state.branch_name = None
    fake_state.source_simulation_id = None
    fake_state.root_simulation_id = None
    fake_state.branch_depth = 0
    fake_manager = MagicMock(get_simulation=MagicMock(return_value=fake_state))
    monkeypatch.setattr("app.api.simulation_run.SimulationManager", lambda: fake_manager)

    run_record = {"run_id": "run_minimax_forward"}
    fake_run_registry = MagicMock()
    fake_run_registry.create_run.return_value = run_record
    monkeypatch.setattr("app.api.simulation_run.run_registry", fake_run_registry)

    # Resolve + Key + Env + Start durch Stubs ersetzen; seed_run_stage_routing
    # bleibt echt, damit das ai_model_ref-KWarg nachgewiesen wird.
    from app.contracts.llm_routing_contract import ResolvedRoute

    resolved = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="conn-minimax",
        model="MiniMax-M3",
        base_url_sanitized="https://api.minimax.io/v1",
        routing_version=1,
        provider_options={"base_url": "https://api.minimax.io/v1", "connection_only": True, "secret_ref": "minimax-conn"},
    )
    fake_router = MagicMock()
    fake_router.resolve.return_value = resolved
    fake_router.lock_stage.return_value = resolved
    monkeypatch.setattr("app.api.simulation_run.StageModelRouter", lambda _run_id: fake_router)
    monkeypatch.setattr("app.api.simulation_run.resolve_route_api_key", lambda _r, _rt: "mm-bound-secret")
    monkeypatch.setattr(
        "app.api.simulation_run.build_route_subprocess_env",
        lambda _r, _k, _rid: {"LLM_MODEL_NAME": "MiniMax-M3", "LLM_BASE_URL": "https://api.minimax.io/v1", "LLM_API_KEY": "mm-bound-secret"},
    )
    fake_runner = MagicMock()
    fake_runner.start_simulation.return_value = MagicMock(
        to_dict=MagicMock(return_value={"simulation_id": VALID_SIM_ID})
    )
    monkeypatch.setattr("app.api.simulation_run.SimulationRunner", fake_runner)
    monkeypatch.setattr("app.api.simulation_run.get_artifact_store", lambda: MagicMock(name="ArtifactStore"))
    # ``_simulation_resume_capability`` läuft über simulation_common und dessen
    # eigene ``get_artifact_store``-Importe — ebenfalls stubben.
    monkeypatch.setattr("app.api.simulation_common.get_artifact_store", lambda: MagicMock(name="ArtifactStore"), raising=False)
    # Pre-Check (Connection+Secret-Bindung) wird im Routing-Seed-Unit-Test
    # separat geprüft; hier stubben wir ihn weg, damit der Forward-Pfad
    # fokokussiert auf das ai_model_ref-KWarg bleibt. Der Pre-Check importiert
    # ``prevalidate_ai_model_ref`` lokal aus dem Seed-Modul, deshalb an der
    # Quelle patchen.
    monkeypatch.setattr(
        "app.services.llm_routing_seed.prevalidate_ai_model_ref",
        lambda _ref: MagicMock(name="ProviderConnection"),
        raising=False,
    )
    # persona-review-gate bleibt stumm
    monkeypatch.setattr("app.api.simulation_run.Config.PERSONA_REVIEW_ENABLED", False, raising=False)


def test_valid_ai_model_ref_is_forwarded_to_seed_run_stage_routing(client, monkeypatch):
    _stub_start_infra(monkeypatch)
    with patch("app.api.simulation_run.seed_run_stage_routing", wraps=lambda *a, **kw: MagicMock()) as spy:
        resp = client.post("/api/simulation/start", json=_ref_body())
    assert resp.status_code == 200, resp.data
    assert spy.call_args.kwargs.get("ai_model_ref") is not None
    forwarded = spy.call_args.kwargs["ai_model_ref"]
    assert forwarded.provider_connection_id == "conn-minimax"
    assert forwarded.model_id == "MiniMax-M3"
    # Legacy-Felder werden bei expliziter AiModelRef nicht mitgeschickt.
    assert spy.call_args.kwargs.get("llm_model_override") is None
    assert not (spy.call_args.kwargs.get("llm_runtime") or MagicMock()).enabled