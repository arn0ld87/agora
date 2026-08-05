"""Regression-Tests fuer Issue #1110: das Transport-Security-Gate aus
Issue #1103 (``ensure_credentialed_transport_security``) muss vor jedem
credential-behafteten Embedding-Request laufen.

Deckt die vier Aufrufstellen ab:

* ``_OpenAICompatibleAdapter.probe`` (Discovery-Probe, OpenAI-kompatibel)
* ``_OllamaAdapter.probe`` (Discovery-Probe, Ollama/Ollama Cloud)
* ``embedding_ollama_pull.pull_model`` (Onboarding-Download)
* ``EmbeddingService._request_headers`` (Legacy-Storage-Pfad)

Struktur und Mock-Stil analog ``tests/llm/test_transport_security.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.contracts.ai_provider_contract import ProviderConnection
from app.contracts.provider_types import ProviderConnectionKind
from app.llm.transport_security import InsecureTransportError
from app.services.embedding_configurations.adapters import (
    _OllamaAdapter,
    _OpenAICompatibleAdapter,
)
from app.services.embedding_ollama_pull import pull_model
from app.storage.embedding_service import EmbeddingService

API_KEY = "sk-test"


def _make_connection(
    *, base_url: str, kind: ProviderConnectionKind = "openai_compatible"
) -> ProviderConnection:
    now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    return ProviderConnection(
        id=f"conn-{kind}",
        provider_kind=kind,
        display_name=kind,
        transport="local" if kind == "ollama" else "http",
        auth_mode="api_key",
        base_url=base_url,
        enabled=True,
        status="unknown",
        secret_ref="secret-ref",
        capabilities={},
        created_at=now,
        updated_at=now,
    )


class _NeverCalledSession:
    """Session-Factory, die einen Fehler wirft, wenn sie tatsaechlich
    aufgerufen wird — belegt, dass das Gate VOR dem Request greift."""

    def __call__(self) -> "_NeverCalledSession":
        raise AssertionError(
            "Session-Factory wurde aufgerufen — das Transport-Security-Gate "
            "haette den Request vorher blockieren muessen"
        )


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def post(self, url: str, json: dict, headers: dict, timeout: float) -> _FakeResponse:
        return self._response


def _openai_probe_response() -> _FakeResponse:
    return _FakeResponse({"data": [{"embedding": [0.1, 0.2, 0.3]}]})


def _ollama_probe_response() -> _FakeResponse:
    return _FakeResponse({"embeddings": [[0.1, 0.2, 0.3]]})


# ---------------------------------------------------------------------------
# _OpenAICompatibleAdapter.probe
# ---------------------------------------------------------------------------


def test_openai_adapter_probe_blocks_public_http_with_key() -> None:
    adapter = _OpenAICompatibleAdapter(session=_NeverCalledSession())
    connection = _make_connection(base_url="http://api.example.com/v1")

    result = adapter.probe(connection, "text-embedding-3-small", API_KEY)

    assert result.status == "unavailable"
    assert result.status_message is not None
    assert API_KEY not in result.status_message


def test_openai_adapter_probe_allows_https_with_key() -> None:
    adapter = _OpenAICompatibleAdapter(
        session=lambda: _FakeSession(_openai_probe_response())
    )
    connection = _make_connection(base_url="https://api.example.com/v1")

    result = adapter.probe(connection, "text-embedding-3-small", API_KEY)

    assert result.status == "available"


def test_openai_adapter_probe_allows_localhost_http_with_key() -> None:
    adapter = _OpenAICompatibleAdapter(
        session=lambda: _FakeSession(_openai_probe_response())
    )
    connection = _make_connection(base_url="http://localhost:11434", kind="ollama")

    result = adapter.probe(connection, "text-embedding-3-small", API_KEY)

    assert result.status == "available"


def test_openai_adapter_probe_allows_public_http_without_key() -> None:
    adapter = _OpenAICompatibleAdapter(
        session=lambda: _FakeSession(_openai_probe_response())
    )
    connection = _make_connection(base_url="http://api.example.com/v1")

    result = adapter.probe(connection, "text-embedding-3-small", None)

    assert result.status == "available"


# ---------------------------------------------------------------------------
# _OllamaAdapter.probe
# ---------------------------------------------------------------------------


def test_ollama_adapter_probe_blocks_public_http_with_key() -> None:
    adapter = _OllamaAdapter(session=_NeverCalledSession())
    connection = _make_connection(
        base_url="http://api.example.com/v1", kind="ollama_cloud"
    )

    result = adapter.probe(connection, "nomic-embed-text", API_KEY)

    assert result.status == "unavailable"
    assert result.status_message is not None
    assert API_KEY not in result.status_message


def test_ollama_adapter_probe_allows_https_with_key() -> None:
    adapter = _OllamaAdapter(session=lambda: _FakeSession(_ollama_probe_response()))
    connection = _make_connection(
        base_url="https://ollama.example.com", kind="ollama_cloud"
    )

    result = adapter.probe(connection, "nomic-embed-text", API_KEY)

    assert result.status == "available"


def test_ollama_adapter_probe_allows_localhost_http_with_key() -> None:
    adapter = _OllamaAdapter(session=lambda: _FakeSession(_ollama_probe_response()))
    connection = _make_connection(base_url="http://localhost:11434", kind="ollama")

    result = adapter.probe(connection, "nomic-embed-text", API_KEY)

    assert result.status == "available"


def test_ollama_adapter_probe_allows_public_http_without_key() -> None:
    adapter = _OllamaAdapter(session=lambda: _FakeSession(_ollama_probe_response()))
    connection = _make_connection(
        base_url="http://api.example.com/v1", kind="ollama_cloud"
    )

    result = adapter.probe(connection, "nomic-embed-text", None)

    assert result.status == "available"


# ---------------------------------------------------------------------------
# embedding_ollama_pull.pull_model
# ---------------------------------------------------------------------------


def test_pull_model_blocks_public_http_with_key() -> None:
    with pytest.raises(InsecureTransportError):
        pull_model(
            model="nomic-embed-text",
            base_url="http://api.example.com",
            api_key=API_KEY,
            session_factory=_NeverCalledSession(),
        )


def test_pull_model_allows_https_with_key() -> None:
    class _PullFakeResponse:
        status_code = 200
        text = ""

        def iter_lines(self) -> list[bytes]:
            return [b'{"status": "success", "digest": "sha256:abc"}']

    class _PullFakeSession:
        def __enter__(self) -> "_PullFakeSession":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def post(self, url: str, json: dict, headers: dict, timeout: float, stream: bool):
            return _PullFakeResponse()

    report = pull_model(
        model="nomic-embed-text",
        base_url="https://ollama.example.com",
        api_key=API_KEY,
        session_factory=lambda: _PullFakeSession(),
    )
    assert report.status == "success"


def test_pull_model_allows_localhost_http_with_key() -> None:
    class _PullFakeResponse:
        status_code = 200
        text = ""

        def iter_lines(self) -> list[bytes]:
            return [b'{"status": "success", "digest": "sha256:abc"}']

    class _PullFakeSession:
        def __enter__(self) -> "_PullFakeSession":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def post(self, url: str, json: dict, headers: dict, timeout: float, stream: bool):
            return _PullFakeResponse()

    report = pull_model(
        model="nomic-embed-text",
        base_url="http://localhost:11434",
        api_key=API_KEY,
        session_factory=lambda: _PullFakeSession(),
    )
    assert report.status == "success"


def test_pull_model_allows_public_http_without_key() -> None:
    class _PullFakeResponse:
        status_code = 200
        text = ""

        def iter_lines(self) -> list[bytes]:
            return [b'{"status": "success", "digest": "sha256:abc"}']

    class _PullFakeSession:
        def __enter__(self) -> "_PullFakeSession":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def post(self, url: str, json: dict, headers: dict, timeout: float, stream: bool):
            return _PullFakeResponse()

    report = pull_model(
        model="nomic-embed-text",
        base_url="http://api.example.com",
        api_key=None,
        session_factory=lambda: _PullFakeSession(),
    )
    assert report.status == "success"


# ---------------------------------------------------------------------------
# EmbeddingService._request_headers (Legacy-Storage-Pfad)
# ---------------------------------------------------------------------------


def test_embedding_service_request_headers_blocks_public_http_with_key() -> None:
    service = EmbeddingService(
        model="text-embedding-3-small",
        base_url="http://api.example.com/v1",
        api_key=API_KEY,
    )

    with pytest.raises(InsecureTransportError):
        service._request_headers()


def test_embedding_service_request_headers_allows_https_with_key() -> None:
    service = EmbeddingService(
        model="text-embedding-3-small",
        base_url="https://api.example.com/v1",
        api_key=API_KEY,
    )

    headers = service._request_headers()

    assert headers["Authorization"] == f"Bearer {API_KEY}"


def test_embedding_service_request_headers_allows_localhost_http_with_key() -> None:
    service = EmbeddingService(
        model="nomic-embed-text",
        base_url="http://localhost:11434",
        api_key=API_KEY,
    )

    headers = service._request_headers()

    assert "Authorization" not in headers


def test_embedding_service_request_headers_allows_public_http_without_key() -> None:
    service = EmbeddingService(
        model="nomic-embed-text",
        base_url="http://api.example.com",
        api_key="",
    )

    headers = service._request_headers()

    assert "Authorization" not in headers
