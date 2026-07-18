from __future__ import annotations

from unittest.mock import MagicMock

from app.contracts.llm_routing_contract import ResolvedRoute
from app.llm.client import LLMClient
from app.services.llm_routing_seed import resolve_route_api_key
from app.services.llm_runtime import RuntimeLlmConfig


def _strict_route() -> ResolvedRoute:
    return ResolvedRoute(
        stage="graph_build",
        provider_id="connection-openai",
        model="gpt-4.1-mini",
        routing_version=1,
        provider_options={
            "secret_ref": "connection-secret",
            "connection_only": True,
        },
    )


def test_strict_profile_route_resolves_only_its_bound_store_secret(monkeypatch):
    secret_store = MagicMock()
    secret_store.get_plaintext.return_value = "connection-key"
    fallback_resolver = MagicMock()
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_provider_secrets_store",
        lambda: secret_store,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.SecretResolver",
        lambda: fallback_resolver,
    )

    api_key = resolve_route_api_key(
        _strict_route(),
        RuntimeLlmConfig(provider="openai", api_key="request-key"),
    )

    assert api_key == "connection-key"
    secret_store.get_plaintext.assert_called_once_with("connection-secret")
    fallback_resolver.get_api_key.assert_not_called()


def test_missing_strict_profile_secret_never_falls_back_to_runtime_or_environment(monkeypatch):
    secret_store = MagicMock()
    secret_store.get_plaintext.return_value = None
    fallback_resolver = MagicMock()
    fallback_resolver.get_api_key.side_effect = AssertionError("fallback is forbidden")
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_provider_secrets_store",
        lambda: secret_store,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.SecretResolver",
        lambda: fallback_resolver,
    )

    api_key = resolve_route_api_key(
        _strict_route(),
        RuntimeLlmConfig(provider="openai", api_key="different-provider-key"),
    )

    assert api_key is None
    secret_store.get_plaintext.assert_called_once_with("connection-secret")
    fallback_resolver.get_api_key.assert_not_called()


def test_llm_client_strict_route_ignores_passed_or_resolver_keys(monkeypatch):
    secret_store = MagicMock()
    secret_store.get_plaintext.return_value = "connection-key"
    fallback_resolver = MagicMock()
    captured = {}

    def capture_init(self, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "app.llm.client.get_llm_provider_secrets_store",
        lambda: secret_store,
        raising=False,
    )
    monkeypatch.setattr(LLMClient, "__init__", capture_init)

    LLMClient.from_route(
        _strict_route(),
        secret_resolver=fallback_resolver,
        api_key_override="runtime-key",
    )

    assert captured["api_key"] == "connection-key"
    secret_store.get_plaintext.assert_called_once_with("connection-secret")
    fallback_resolver.get_api_key.assert_not_called()


def test_llm_client_missing_strict_secret_never_uses_passed_or_resolver_key(monkeypatch):
    secret_store = MagicMock()
    secret_store.get_plaintext.return_value = None
    fallback_resolver = MagicMock()
    fallback_resolver.get_api_key.side_effect = AssertionError("fallback is forbidden")
    captured = {}

    def capture_init(self, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "app.llm.client.get_llm_provider_secrets_store",
        lambda: secret_store,
        raising=False,
    )
    monkeypatch.setattr(LLMClient, "__init__", capture_init)

    LLMClient.from_route(
        _strict_route(),
        secret_resolver=fallback_resolver,
        api_key_override="runtime-key",
    )

    assert captured["api_key"] is None
    secret_store.get_plaintext.assert_called_once_with("connection-secret")
    fallback_resolver.get_api_key.assert_not_called()


def test_non_strict_route_keeps_runtime_key_fallback(monkeypatch):
    route = ResolvedRoute(
        stage="graph_build",
        provider_id="openai",
        model="gpt-4.1-mini",
        routing_version=1,
    )
    fallback_resolver = MagicMock()
    monkeypatch.setattr(
        "app.services.llm_routing_seed.SecretResolver",
        lambda: fallback_resolver,
    )

    api_key = resolve_route_api_key(
        route,
        RuntimeLlmConfig(provider="openai", api_key="runtime-key"),
    )

    assert api_key == "runtime-key"
    fallback_resolver.get_api_key.assert_not_called()
