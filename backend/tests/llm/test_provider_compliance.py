"""Provider-Compliance-Suite (Issue #590).

Jeder Adapter (Ollama, OpenAI, Gemini) durchlaeuft DIESELBEN Szenarien
gegen einen gemockten OpenAI-kompatiblen Client: Success, 4xx, 5xx,
Network-Drop, Timeout, Rate-Limit und Streaming. Dazu kommen die
provider-spezifischen Payload-Assertions (Token-Limit-Key, extra_body).
"""
from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock

import httpx
import openai
import pytest

from app.contracts.llm_request import ChatMessage, NormalizedLlmRequest, ResponseFormat
from app.llm.errors import LlmProviderError, normalize_provider_error
from app.llm.providers.base import ProviderAdapter
from app.llm.providers.gemini import GeminiAdapter
from app.llm.providers.ollama import OllamaAdapter, build_ollama_extra_body
from app.llm.providers.openai import OpenAIAdapter, uses_max_completion_tokens
from app.llm.providers.registry import get_adapter

# ---------------------------------------------------------------------------
# Fixtures / Helpers
# ---------------------------------------------------------------------------

ADAPTER_FACTORIES = {
    "ollama": lambda: OllamaAdapter(num_ctx=8192, think=False),
    "openai": lambda: OpenAIAdapter(),
    "google": lambda: GeminiAdapter(),
}


@pytest.fixture(params=sorted(ADAPTER_FACTORIES))
def adapter(request: pytest.FixtureRequest) -> ProviderAdapter:
    return ADAPTER_FACTORIES[request.param]()


def _request(model: str = "test-model", **overrides: Any) -> NormalizedLlmRequest:
    payload: dict[str, Any] = {
        "provider": "unknown",
        "model": model,
        "messages": [ChatMessage(role="user", content="hallo")],
        "temperature": 0.5,
        "max_tokens": 256,
    }
    payload.update(overrides)
    return NormalizedLlmRequest(**payload)


def _mock_client(response: Any = None, side_effect: Any = None) -> MagicMock:
    client = MagicMock()
    if side_effect is not None:
        client.chat.completions.create.side_effect = side_effect
    else:
        client.chat.completions.create.return_value = response
    return client


def _completion_response(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _stream_chunks(*texts: str) -> List[MagicMock]:
    chunks = []
    for text in texts:
        delta = MagicMock()
        delta.content = text
        choice = MagicMock()
        choice.delta = delta
        chunk = MagicMock()
        chunk.choices = [choice]
        chunks.append(chunk)
    return chunks


def _http_request() -> httpx.Request:
    return httpx.Request("POST", "https://llm.test/v1/chat/completions")


def _status_error(status: int) -> openai.APIStatusError:
    response = httpx.Response(status, request=_http_request())
    if status == 429:
        return openai.RateLimitError("rate limited", response=response, body=None)
    return openai.APIStatusError(f"http {status}", response=response, body=None)


# ---------------------------------------------------------------------------
# Szenario 1: Success (complete)
# ---------------------------------------------------------------------------


def test_complete_success_returns_content(adapter: ProviderAdapter) -> None:
    client = _mock_client(response=_completion_response("antwort"))

    result = adapter.complete(client, _request())

    assert result == "antwort"
    client.chat.completions.create.assert_called_once()
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["messages"] == [{"role": "user", "content": "hallo"}]
    assert kwargs["temperature"] == 0.5


def test_complete_empty_choices_returns_empty_string(adapter: ProviderAdapter) -> None:
    response = MagicMock()
    response.choices = []
    client = _mock_client(response=response)

    assert adapter.complete(client, _request()) == ""


# ---------------------------------------------------------------------------
# Szenario 2: 4xx — sofortiger Fehler, nicht retryable
# ---------------------------------------------------------------------------


def test_complete_4xx_raises_normalized_error(adapter: ProviderAdapter) -> None:
    client = _mock_client(side_effect=_status_error(400))

    with pytest.raises(LlmProviderError) as excinfo:
        adapter.complete(client, _request())

    normalized = excinfo.value.normalized
    assert normalized.provider == adapter.name
    assert normalized.code == "client_error"
    assert normalized.status == 400
    assert normalized.retryable is False
    assert isinstance(excinfo.value.__cause__, openai.APIStatusError)
    # 4xx ist nicht transient — genau EIN Versuch, kein Retry.
    assert client.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# Szenarien 3-6: Fehler-Normalisierung (5xx, Network-Drop, Timeout, 429)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc_factory", "expected_code", "expected_status", "expected_retryable"),
    [
        (lambda: _status_error(500), "server_error", 500, True),
        (lambda: _status_error(503), "server_error", 503, True),
        (lambda: _status_error(408), "client_error", 408, True),
        (lambda: _status_error(429), "rate_limited", 429, True),
        (lambda: _status_error(401), "client_error", 401, False),
        (lambda: _status_error(422), "client_error", 422, False),
        (lambda: openai.APITimeoutError(request=_http_request()), "timeout", None, True),
        (
            lambda: openai.APIConnectionError(request=_http_request()),
            "connection_error",
            None,
            True,
        ),
        (lambda: httpx.ReadTimeout("read timeout"), "timeout", None, True),
        (lambda: httpx.ConnectError("connection refused"), "connection_error", None, True),
        (lambda: ValueError("kaputt"), "unknown", None, False),
    ],
)
def test_normalize_error_mapping(
    adapter: ProviderAdapter,
    exc_factory: Any,
    expected_code: str,
    expected_status: Any,
    expected_retryable: bool,
) -> None:
    normalized = adapter.normalize_error(exc_factory())

    assert normalized.provider == adapter.name
    assert normalized.code == expected_code
    assert normalized.status == expected_status
    assert normalized.retryable is expected_retryable
    assert normalized.cause is not None


def test_normalize_provider_error_is_provider_agnostic() -> None:
    normalized = normalize_provider_error(_status_error(500), provider="google")
    assert normalized.provider == "google"
    assert normalized.retryable is True


# ---------------------------------------------------------------------------
# Szenario 7: Streaming — Tokens + done; Fehler als error-Chunk
# ---------------------------------------------------------------------------


def test_stream_success_yields_tokens_then_done(adapter: ProviderAdapter) -> None:
    client = _mock_client(response=iter(_stream_chunks("hal", "lo")))

    chunks = list(adapter.stream(client, _request()))

    assert [c.type for c in chunks] == ["token", "token", "done"]
    assert "".join(c.text or "" for c in chunks) == "hallo"
    assert client.chat.completions.create.call_args.kwargs["stream"] is True


def test_stream_error_yields_error_chunk(adapter: ProviderAdapter) -> None:
    client = _mock_client(side_effect=_status_error(400))

    chunks = list(adapter.stream(client, _request()))

    assert len(chunks) == 1
    assert chunks[0].type == "error"
    assert chunks[0].error is not None
    assert chunks[0].error.provider == adapter.name
    assert chunks[0].error.retryable is False


# ---------------------------------------------------------------------------
# Provider-spezifisches Payload-Shaping
# ---------------------------------------------------------------------------


def test_ollama_adapter_sets_extra_body() -> None:
    adapter = OllamaAdapter(num_ctx=8192, think=False)
    kwargs = adapter.prepare_request_kwargs(_request())

    assert kwargs["extra_body"] == {"options": {"num_ctx": 8192}, "think": False}
    assert kwargs["max_tokens"] == 256


def test_ollama_extra_body_without_num_ctx_keeps_think_only() -> None:
    assert build_ollama_extra_body(num_ctx=None, think=True) == {"think": True}
    assert build_ollama_extra_body(num_ctx=0, think=False) == {"think": False}


@pytest.mark.parametrize(
    ("model", "expected_key"),
    [
        ("gpt-5-nano", "max_completion_tokens"),
        ("gpt-5", "max_completion_tokens"),
        ("o1-preview", "max_completion_tokens"),
        ("o3", "max_completion_tokens"),
        ("o4.1", "max_completion_tokens"),
        ("gpt-4o", "max_tokens"),
        ("gpt-500", "max_tokens"),  # striktes Prefix-Matching
        ("qwen3:8b", "max_tokens"),
    ],
)
def test_openai_adapter_token_param_heuristic(model: str, expected_key: str) -> None:
    adapter = OpenAIAdapter()
    kwargs = adapter.prepare_request_kwargs(_request(model=model))

    assert expected_key in kwargs
    assert "extra_body" not in kwargs


def test_uses_max_completion_tokens_matches_client_heuristic() -> None:
    # Spiegel der testfixierten LLMClient-Semantik (Wortgrenze -, ., exakt).
    assert uses_max_completion_tokens("gpt-5") is True
    assert uses_max_completion_tokens("gpt-5-mini") is True
    assert uses_max_completion_tokens("o1.5-turbo") is True
    assert uses_max_completion_tokens("gpt-500") is False
    assert uses_max_completion_tokens("oasis-model") is False
    assert uses_max_completion_tokens("") is False


def test_gemini_adapter_plain_openai_wire_format() -> None:
    adapter = GeminiAdapter()
    kwargs = adapter.prepare_request_kwargs(_request(model="gemini-3-flash-preview"))

    assert "extra_body" not in kwargs
    assert kwargs["max_tokens"] == 256


def test_response_format_and_tools_wire_format() -> None:
    adapter = OpenAIAdapter()
    req = _request(
        response_format={"type": "json_object"},
        tools=[{"name": "quick_search", "description": "s", "parameters": {}}],
    )
    kwargs = adapter.prepare_request_kwargs(req)

    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["tools"] == [
        {
            "type": "function",
            "function": {"name": "quick_search", "description": "s", "parameters": {}},
        }
    ]


def test_wire_response_format_json_schema_branch() -> None:
    """json_schema-Branch von wire_response_format (base.py:63-64).

    Striktes JSON-Schema muss als {"type": "json_schema", "json_schema": <schema>}
    durchgereicht werden — der Laufzeit-Fallback strict -> json_object -> text
    orchestriert weiterhin der LLMClient, aber das Payload-Shaping passiert hier.
    """
    adapter = OpenAIAdapter()
    schema: dict[str, object] = {
        "name": "report",
        "schema": {"type": "object", "properties": {"x": {"type": "string"}}},
    }
    req = _request(response_format={"type": "json_schema", "json_schema": schema})
    kwargs = adapter.prepare_request_kwargs(req)

    assert kwargs["response_format"] == {"type": "json_schema", "json_schema": schema}


def test_response_format_json_schema_without_schema_rejected_at_contract() -> None:
    """type="json_schema" OHNE schema-Objekt wird am Contract abgelehnt (fail-fast).

    Sonst lehnt OpenAI zur Laufzeit mit HTTP 400 ab. Der model_validator auf
    ResponseFormat fängt den Konfigurationsfehler früh ab (Gemini-Finding).
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResponseFormat(type="json_schema", json_schema=None)


# ---------------------------------------------------------------------------
# Registry → Adapter-Aufloesung
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "expected_cls"),
    [
        ("ollama", OllamaAdapter),
        ("cloud", OllamaAdapter),
        ("ollama_cloud", OllamaAdapter),
        ("google", GeminiAdapter),
        ("openai", OpenAIAdapter),
        ("openai_compatible", OpenAIAdapter),
        ("bedrock", OpenAIAdapter),  # Issue #1282 — mantle OpenAI-Compat
        ("unknown", OpenAIAdapter),  # OpenAI-Wire-Format als Default
    ],
)
def test_get_adapter_resolution(provider: str, expected_cls: type) -> None:
    resolved = get_adapter(provider, num_ctx=4096, think=True)
    assert isinstance(resolved, expected_cls)
    assert resolved.num_ctx == 4096
    assert resolved.think is True