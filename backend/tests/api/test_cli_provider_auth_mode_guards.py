"""Der Key-Guard der CLI-Provider haengt am ``auth_mode``, nicht am Transport.

Beide Endpunkte hatten dieselbe Verwechslung wie ``simulation_prepare``: sie
sprangen fuer jeden Provider mit ``transport="cli"`` am 422-Guard vorbei.
Richtig ist nur ``codex_cli`` keylos (``auth_mode="session"``, lokale
``codex login``-Session). ``claude_cli`` ist ebenfalls ``transport="cli"``,
traegt aber einen echten Langzeit-Token im Provider-Secret-Store — faellt der
Guard fuer ihn aus, startet der Lauf ohne Anmeldung und scheitert erst im
Subprozess.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_history as history_mod
from app.api import simulation_run as run_mod
from app.contracts.llm_routing_contract import ResolvedRoute
from app.services.llm_runtime import RuntimeLlmConfig


@pytest.fixture
def app_ctx():
    """``json_error`` baut echte Flask-Responses."""
    app = Flask(__name__)
    with app.test_request_context():
        yield app


def _cli_route(provider_id: str, stage: str) -> ResolvedRoute:
    return ResolvedRoute(
        stage=stage,
        provider_id=provider_id,
        model="sonnet",
        base_url_sanitized=None,
        routing_version=3,
    )


def _patch_run_router(monkeypatch, route):
    router = MagicMock()
    router.resolve.return_value = route
    router.lock_stage.return_value = route
    monkeypatch.setattr(run_mod, "StageModelRouter", lambda _run_id: router)
    return router


def test_start_route_rejects_claude_cli_without_token(app_ctx, monkeypatch):
    _patch_run_router(monkeypatch, _cli_route("claude_cli", "simulation_rounds"))
    monkeypatch.setattr(run_mod, "resolve_route_api_key", lambda _route, _runtime: None)

    with pytest.raises(run_mod._StartRejected) as excinfo:
        run_mod._resolve_start_route("run-1", RuntimeLlmConfig())

    assert excinfo.value.response[1] == 422
    assert "claude_cli" in excinfo.value.response[0].get_json()["error"]


def test_start_route_passes_resolved_claude_cli_token(app_ctx, monkeypatch):
    route = _cli_route("claude_cli", "simulation_rounds")
    _patch_run_router(monkeypatch, route)
    monkeypatch.setattr(
        run_mod, "resolve_route_api_key", lambda _route, _runtime: "claude-oauth-token"
    )

    resolved, api_key = run_mod._resolve_start_route("run-1", RuntimeLlmConfig())

    assert resolved is route
    assert api_key == "claude-oauth-token"


def test_start_route_accepts_codex_cli_session_without_key(app_ctx, monkeypatch):
    route = _cli_route("codex_cli", "simulation_rounds")
    _patch_run_router(monkeypatch, route)
    monkeypatch.setattr(run_mod, "resolve_route_api_key", lambda _route, _runtime: None)

    resolved, api_key = run_mod._resolve_start_route("run-1", RuntimeLlmConfig())

    assert resolved is route
    assert api_key is None


def test_profile_connection_rejects_claude_cli_without_token(app_ctx, monkeypatch):
    monkeypatch.setattr(
        history_mod, "resolve_route_api_key", lambda _route, _runtime: None
    )

    with pytest.raises(history_mod._ProfileConnectionRejected) as excinfo:
        history_mod._resolve_profile_connection(
            _cli_route("claude_cli", "persona_generation"), RuntimeLlmConfig()
        )

    assert excinfo.value.response[1] == 422
    assert "claude_cli" in excinfo.value.response[0].get_json()["error"]


def test_profile_connection_passes_claude_cli_token_without_base_url(app_ctx, monkeypatch):
    monkeypatch.setattr(
        history_mod, "resolve_route_api_key", lambda _route, _runtime: "claude-oauth-token"
    )

    api_key, base_url, provider_type = history_mod._resolve_profile_connection(
        _cli_route("claude_cli", "persona_generation"), RuntimeLlmConfig()
    )

    assert api_key == "claude-oauth-token"
    assert base_url is None
    assert provider_type == "claude_cli"


def test_profile_connection_accepts_codex_cli_session_without_key(app_ctx, monkeypatch):
    monkeypatch.setattr(
        history_mod, "resolve_route_api_key", lambda _route, _runtime: None
    )

    api_key, base_url, provider_type = history_mod._resolve_profile_connection(
        _cli_route("codex_cli", "persona_generation"), RuntimeLlmConfig()
    )

    assert api_key is None
    assert base_url is None
    assert provider_type == "codex_cli"
