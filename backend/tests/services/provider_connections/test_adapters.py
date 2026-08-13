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
        "bedrock",
    )
    assert definitions[2].default_base_url == (
        "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    assert definitions[6].transport == "local"
    assert definitions[7].adapter_kind == "unsupported"
    assert definitions[8].adapter_kind == "unsupported"
    # Issue #1282 — Amazon Bedrock OpenAI-kompatibler Mantle-Pfad.
    assert definitions[9].adapter_kind == "bedrock"
    assert definitions[9].auth_mode == "api_key"
    assert definitions[9].supports_tools is True
    assert definitions[9].default_base_url == "https://bedrock-mantle.eu-central-1.api.aws/v1"
