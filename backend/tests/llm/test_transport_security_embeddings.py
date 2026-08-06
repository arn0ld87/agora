"""Regression-Tests für Issue #1110: Transport-Security-Gate (#1103) auch für
Embedding-Pfade.

Dieselbe fail-closed Policy wie für ``LLMClient`` gilt für jeden
credential-behafteten Embedding-Request: ``EmbeddingService``, die
Embedding-Probe-Adapter und den Ollama-Pull. Kein neues Regelwerk — nur
das bestehende ``ensure_credentialed_transport_security``-Gate vor dem
Request.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.contracts.ai_provider_contract import ProviderConnection
from app.llm.transport_security import InsecureTransportError
from app.services.embedding_configurations.adapters import (
    _GeminiAdapter,
    _OllamaAdapter,
    _OpenAICompatibleAdapter,
)
from app.services.embedding_ollama_pull import OllamaPullError, pull_model
from app.storage.embedding_service import EmbeddingService


def _connection(provider_kind: str, base_url: str) -> ProviderConnection:
    return ProviderConnection(
        id="conn-transport-gate-test",
        provider_kind=provider_kind,  # type: ignore[arg-type]
        display_name="Transport-Gate-Test",
        transport="http",
        auth_mode="api_key",
        base_url=base_url,
    )


# ---------------------------------------------------------------------------
# EmbeddingService (Legacy-/Storage-Pfad)
# ---------------------------------------------------------------------------


class TestEmbeddingServiceEnforcesTransportSecurity:
    def test_http_public_host_with_key_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGORA_LLM_ALLOW_INSECURE_HTTP", raising=False)
        with pytest.raises(InsecureTransportError):
            EmbeddingService(
                model="test-model",
                base_url="http://api.example.com/v1",
                api_key="sk-test",
            )

    def test_http_localhost_with_key_ok(self) -> None:
        service = EmbeddingService(
            model="test-model",
            base_url="http://localhost:11434",
            api_key="sk-test",
        )
        assert service.base_url == "http://localhost:11434"

    def test_http_public_host_without_key_ok(self) -> None:
        # Leerer String ist der Default fuer "kein Key" und darf nicht blocken.
        service = EmbeddingService(
            model="test-model",
            base_url="http://api.example.com/v1",
            api_key="",
        )
        assert service.api_key == ""


# ---------------------------------------------------------------------------
# Embedding-Probe-Adapter (ADR-0007-Pfad)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "adapter_cls, provider_kind",
    [
        (_OpenAICompatibleAdapter, "openai_compatible"),
        (_OllamaAdapter, "ollama_cloud"),
        (_GeminiAdapter, "google"),
    ],
)
def test_adapter_blocks_public_http_with_key_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
    adapter_cls: type,
    provider_kind: str,
) -> None:
    monkeypatch.delenv("AGORA_LLM_ALLOW_INSECURE_HTTP", raising=False)
    session_factory = MagicMock()
    adapter = adapter_cls(session=session_factory)
    result = adapter.probe(
        _connection(provider_kind, "http://api.example.com"),
        "model-x",
        "sk-test",
    )
    assert result.status == "unavailable"
    message = result.status_message or ""
    assert "https://" in message
    assert "sk-test" not in message
    session_factory.assert_not_called()


def test_adapter_allows_local_http_with_key() -> None:
    response = MagicMock(status_code=200)
    response.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value.post.return_value = response
    adapter = _OllamaAdapter(session=session_factory)
    result = adapter.probe(
        _connection("ollama", "http://localhost:11434"), "model-x", "sk-test"
    )
    assert result.status == "available"
    assert result.actual_dimensions == 3


# ---------------------------------------------------------------------------
# Ollama-Pull (Onboarding-Download)
# ---------------------------------------------------------------------------


def test_pull_model_blocks_public_http_with_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGORA_LLM_ALLOW_INSECURE_HTTP", raising=False)
    session_factory = MagicMock()
    with pytest.raises(OllamaPullError) as exc_info:
        pull_model(
            model="mistral",
            base_url="http://api.example.com",
            api_key="sk-test",
            session_factory=session_factory,
        )
    assert "sk-test" not in str(exc_info.value)
    session_factory.assert_not_called()


def test_pull_model_allows_local_http_with_key() -> None:
    response = MagicMock(status_code=200)
    response.iter_lines.return_value = [b'{"status": "success"}']
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value.post.return_value = response
    report = pull_model(
        model="mistral",
        base_url="http://localhost:11434",
        api_key="sk-test",
        session_factory=session_factory,
    )
    assert report.status == "success"


def test_pull_model_public_http_without_key_ok() -> None:
    # Ohne Credential gibt es nichts zu schuetzen — Request geht raus.
    response = MagicMock(status_code=200)
    response.iter_lines.return_value = [b'{"status": "success"}']
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value.post.return_value = response
    report = pull_model(
        model="mistral",
        base_url="http://api.example.com",
        api_key=None,
        session_factory=session_factory,
    )
    assert report.status == "success"
