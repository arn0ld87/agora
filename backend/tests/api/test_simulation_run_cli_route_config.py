"""#1759 C4: eine cli-Route steht nie neben einer stehengebliebenen HTTP-Basis-URL."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.api import simulation_run
from app.contracts.llm_routing_contract import ResolvedRoute


class _FakeStore:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.written: dict | None = None

    def read_json(self, _simulation_id, _name, default=None):
        return dict(self.config)

    def write_json(self, _simulation_id, _name, payload) -> None:
        self.written = payload


def _request() -> simulation_run._StartRequest:
    return simulation_run._StartRequest(
        simulation_id="sim_x",
        platform="parallel",
        max_rounds=None,
        simulation_days=None,
        llm_model_override=None,
        llm_runtime=MagicMock(enabled=False),
        ai_model_ref=MagicMock(),  # explizite Modellwahl -> Override aktiv
        budget_config=None,
        enable_graph_memory_update=False,
        force=False,
    )


def _route(provider_id: str, base_url: str | None) -> ResolvedRoute:
    return ResolvedRoute(
        stage="simulation_rounds",
        provider_id=provider_id,
        model="claude-sonnet-5-5",
        base_url_sanitized=base_url,
        routing_version=1,
    )


def test_cli_route_clears_stale_http_base_url(monkeypatch):
    store = _FakeStore({"llm_model": "old", "llm_base_url": "https://api.openai.com/v1"})
    monkeypatch.setattr(simulation_run, "get_artifact_store", lambda: store)

    simulation_run._apply_route_to_simulation_config(
        _request(), _route("claude_cli", None), "run_x"
    )

    assert store.written is not None
    assert store.written["llm_model"] == "claude-sonnet-5-5"
    assert store.written["llm_base_url"] == ""


def test_http_route_with_base_url_overrides_it(monkeypatch):
    store = _FakeStore({"llm_base_url": "https://api.openai.com/v1"})
    monkeypatch.setattr(simulation_run, "get_artifact_store", lambda: store)

    simulation_run._apply_route_to_simulation_config(
        _request(), _route("openai", "https://api.example.test/v1"), "run_x"
    )

    assert store.written is not None
    assert store.written["llm_base_url"] == "https://api.example.test/v1"


def test_http_route_without_base_url_keeps_existing_value(monkeypatch):
    store = _FakeStore({"llm_base_url": "https://api.openai.com/v1"})
    monkeypatch.setattr(simulation_run, "get_artifact_store", lambda: store)

    simulation_run._apply_route_to_simulation_config(
        _request(), _route("openai", None), "run_x"
    )

    assert store.written is not None
    assert store.written["llm_base_url"] == "https://api.openai.com/v1"
