"""Contract tests for the canonical provider-connection adapter matrix."""
from __future__ import annotations

import pytest

from app.contracts.ai_provider_contract import ProviderConnection
from app.services.model_catalog_service import CatalogHttpResponse
from app.services.provider_connections.adapters import (
    ProviderProbeResult,
    adapter_for_connection,
)
from app.services.llm_provider_registry import LlmProviderRegistry


def _connection(provider_kind: str, base_url: str) -> ProviderConnection:
    """Build a public or loopback connection through the public contract."""
    if provider_kind == "ollama":
        return ProviderConnection(
            id="ollama",
            provider_kind="ollama",
            display_name="Local Ollama",
            transport="local",
            auth_mode="none",
            base_url=base_url,
        )
    return ProviderConnection(
        id=provider_kind,
        provider_kind=provider_kind,
        display_name=provider_kind,
        transport="http",
        auth_mode="api_key",
        base_url=base_url,
    )


@pytest.mark.parametrize(
    ("provider_kind", "base_url", "expected_url", "expected_headers", "payload"),
    [
        ("openai", "https://api.openai.com/v1", "https://api.openai.com/v1/models", {"Authorization": "Bearer test-key"}, {"data": [{"id": "gpt-test"}]}),
        ("anthropic", "https://api.anthropic.com", "https://api.anthropic.com/v1/models", {"X-Api-Key": "test-key", "anthropic-version": "2023-06-01"}, {"data": [{"id": "claude-test"}]}),
        ("google", "https://generativelanguage.googleapis.com/v1beta/openai", "https://generativelanguage.googleapis.com/v1beta/openai/models", {"Authorization": "Bearer test-key"}, {"data": [{"id": "gemini-test"}]}),
        ("minimax", "https://api.minimax.io/v1", "https://api.minimax.io/v1/models", {"Authorization": "Bearer test-key"}, {"data": [{"id": "MiniMax-test"}]}),
        ("ollama_cloud", "https://ollama.com", "https://ollama.com/api/tags", {"Authorization": "Bearer test-key"}, {"models": [{"name": "cloud-test"}]}),
        ("openai_compatible", "https://gateway.example/v1", "https://gateway.example/v1/models", {"Authorization": "Bearer test-key"}, {"data": [{"id": "compat-test"}]}),
        ("ollama", "http://localhost:11434", "http://localhost:11434/api/tags", {}, {"models": [{"name": "local-test"}]}),
    ],
)
def test_adapter_probes_documented_model_endpoint(
    provider_kind: str,
    base_url: str,
    expected_url: str,
    expected_headers: dict[str, str],
    payload: dict[str, object],
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def get_json(url: str, *, headers: dict[str, str]) -> CatalogHttpResponse:
        calls.append((url, headers))
        return CatalogHttpResponse(status_code=200, payload=payload)

    result = adapter_for_connection(provider_kind, get_json=get_json).probe(
        _connection(provider_kind, base_url),
        api_key=None if provider_kind == "ollama" else "test-key",
    )

    assert result.status == "available"
    assert [model.model_id for model in result.models]
    assert calls == [(expected_url, expected_headers)]


@pytest.mark.parametrize(
    ("status_code", "expected_status"),
    [(401, "invalid_credentials"), (403, "invalid_credentials"), (429, "degraded"), (500, "unavailable")],
)
def test_adapter_normalizes_transport_errors(
    status_code: int, expected_status: str
) -> None:
    result = adapter_for_connection(
        "openai",
        get_json=lambda _url, *, headers: CatalogHttpResponse(
            status_code=status_code, payload=None
        ),
    ).probe(_connection("openai", "https://api.openai.com/v1"), "secret-value")

    assert result.status == expected_status
    assert "secret-value" not in (result.status_message or "")
    assert result.models == ()


@pytest.mark.parametrize("provider_kind", ["opencode_go", "github_copilot"])
def test_unsupported_providers_report_a_provider_neutral_message_without_transport_call(
    provider_kind: str,
) -> None:
    def unexpected_call(_url: str, *, headers: dict[str, str]) -> CatalogHttpResponse:
        raise AssertionError("unsupported provider must not contact the network")

    result = adapter_for_connection(provider_kind, get_json=unexpected_call).probe(
        _connection("openai", "https://api.openai.com/v1"), "test-key"
    )

    assert result == ProviderProbeResult(
        status="unsupported", status_message="Dieser Provider ist in diesem Slice nicht unterstützt"
    )


def _codex_cli_connection() -> ProviderConnection:
    return ProviderConnection(
        id="codex_cli",
        provider_kind="codex_cli",
        display_name="Codex CLI (ChatGPT-Abo)",
        transport="cli",
        auth_mode="session",
        base_url=None,
    )


def _no_http(_url: str, *, headers: dict[str, str]) -> CatalogHttpResponse:
    raise AssertionError("codex_cli must not use HTTP discovery")


def test_codex_cli_probe_falls_back_to_sentinel_when_catalog_unavailable(
    monkeypatch,
) -> None:
    """Regression fuer das Codex-Review-Finding: ohne Modelle in der Probe
    kann codex_cli zwar verbunden, aber nie als Modell ausgewaehlt werden
    (``_verify_selected_model`` prueft ausschliesslich ``result.models``).

    Die Discovery wird bewusst gemockt: Der Test darf nicht davon abhaengen,
    ob auf der Maschine eine echte ``codex``-CLI installiert ist.
    """
    monkeypatch.setattr(
        "app.llm.providers.codex_cli.is_codex_cli_available", lambda: True
    )
    monkeypatch.setattr(
        "app.llm.providers.codex_cli.discover_codex_cli_models", lambda: ()
    )

    result = adapter_for_connection("codex_cli", get_json=_no_http).probe(
        _codex_cli_connection(), None
    )

    assert result.status == "available"
    assert result.status_message is None
    assert [m.model_id for m in result.models] == ["codex-cli-default"]


def test_codex_cli_probe_lists_discovered_models_and_keeps_sentinel_last(
    monkeypatch,
) -> None:
    """Der Sentinel darf nicht verschwinden, sobald die Discovery greift —
    eine gespeicherte Routing-Auswahl auf ``codex-cli-default`` wuerde sonst
    von ``_verify_selected_model`` verworfen."""
    monkeypatch.setattr(
        "app.llm.providers.codex_cli.is_codex_cli_available", lambda: True
    )
    monkeypatch.setattr(
        "app.llm.providers.codex_cli.discover_codex_cli_models",
        lambda: ("gpt-5.6-sol", "gpt-5.5"),
    )

    result = adapter_for_connection("codex_cli", get_json=_no_http).probe(
        _codex_cli_connection(), None
    )

    assert result.status == "available"
    assert [m.model_id for m in result.models] == [
        "gpt-5.6-sol",
        "gpt-5.5",
        "codex-cli-default",
    ]


def test_codex_cli_probe_reports_unavailable_when_binary_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.llm.providers.codex_cli.is_codex_cli_available", lambda: False
    )

    result = adapter_for_connection("codex_cli").probe(_codex_cli_connection(), None)

    assert result.status == "unavailable"
    assert "codex-CLI" in (result.status_message or "")


def test_registry_has_one_canonical_connection_matrix() -> None:
    definitions = LlmProviderRegistry.connection_definitions()

    assert tuple(definition.provider_kind for definition in definitions) == (
        "openai",
        "anthropic",
        "google",
        "minimax",
        "ollama_cloud",
        "openai_compatible",
        "ollama",
        "opencode_go",
        "github_copilot",
        "codex_cli",
        "bedrock",
    )
    assert definitions[2].default_base_url == (
        "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    assert definitions[6].transport == "local"
    assert definitions[7].adapter_kind == "unsupported"
    assert definitions[8].adapter_kind == "unsupported"
    # Issue #1405 — Codex-CLI-Subprozess-Bridge (ChatGPT-Abo).
    assert definitions[9].adapter_kind == "codex_cli"
    assert definitions[9].transport == "cli"
    assert definitions[9].auth_mode == "session"
    assert definitions[9].api_key_ref is None
    assert definitions[9].default_base_url is None
    # Issue #1282 — Amazon Bedrock OpenAI-kompatibler Mantle-Pfad.
    assert definitions[10].adapter_kind == "bedrock"
    assert definitions[10].auth_mode == "api_key"
    assert definitions[10].api_key_ref == "AWS_BEARER_TOKEN_BEDROCK"
    assert definitions[10].supports_tools is True
    # Region eu-central-1 ist an ``fallback_models``/``LLM_MODEL_PRESETS``
    # gekoppelt: die Preset-IDs sind gegen genau diesen mantle-Katalog
    # chat-verifiziert (siehe tests/llm/test_bedrock_model_catalog.py).
    assert definitions[10].default_base_url == "https://bedrock-mantle.eu-central-1.api.aws/v1"
