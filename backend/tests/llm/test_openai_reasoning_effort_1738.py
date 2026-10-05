"""``reasoning_effort`` der Route erreicht OpenAI-Reasoning-Modelle (#1738).

Bug: Die Route traegt ``reasoning_effort`` (Default ``"none"``), der Wert
wurde aber nie an den Provider gesendet. OpenAI-Reasoning-Modelle
(``gpt-6.1-sol``) haben serverseitig einen Default ungleich ``none`` und
sperren dann Function-Tools auf ``/v1/chat/completions`` mit 400 "Function
tools with reasoning_effort are not supported ... set reasoning_effort to
'none'". Die Section-ReAct des Reports scheiterte dadurch in jeder Section.

Szenarien:
    (a) Tool-Call gegen openai + gpt-6.1-sol, Route "none" -> ``"none"`` im Request.
    (b) Gleicher Fall auf dem ``chat()``-/``chat_json()``-Pfad; ``force_no_thinking``
        erzwingt ``"none"`` auch bei Route "high".
    (c) Ollama, openai-kompatibler Fremd-Endpoint und gpt-4.1 senden den
        Parameter NICHT.
    (d) Quirk: 400 "Unsupported value 'none' for reasoning_effort" -> genau
        ein Retry ohne Parameter; der Tools-400 loest keinen Retry aus.
"""

from __future__ import annotations

import pytest

from app.llm.providers.openai import is_reasoning_effort_400, reasoning_effort_kwargs
from app.utils.llm_client import LLMClient


class _FakeBadRequest(Exception):
    """Ersatz fuer openai.BadRequestError mit strukturiertem ``.body``."""

    def __init__(self, message: str, *, body: dict | None = None) -> None:
        super().__init__(message)
        self.body = body


_UNSUPPORTED_NONE_MSG = (
    "Unsupported value: 'none' is not supported with the 'o3' model. "
    "Supported values are: 'low', 'medium', and 'high'."
)


def _unsupported_none_400() -> _FakeBadRequest:
    return _FakeBadRequest(
        "Error code: 400 - {'error': {'message': \""
        + _UNSUPPORTED_NONE_MSG
        + "\", 'type': 'invalid_request_error', 'param': 'reasoning_effort', "
        "'code': 'unsupported_value'}}",
        body={
            "message": _UNSUPPORTED_NONE_MSG,
            "type": "invalid_request_error",
            "param": "reasoning_effort",
            "code": "unsupported_value",
        },
    )


_TOOLS_MSG = (
    "Function tools with reasoning_effort are not supported for gpt-6.1-sol "
    "in /v1/chat/completions. Please use /v1/responses instead, or set "
    "reasoning_effort to 'none'."
)


def _tools_400() -> _FakeBadRequest:
    return _FakeBadRequest(
        "Error code: 400 - {'error': {'message': \""
        + _TOOLS_MSG
        + "\", 'type': 'invalid_request_error', 'param': 'reasoning_effort', "
        "'code': 'unsupported_parameter'}}",
        body={
            "message": _TOOLS_MSG,
            "type": "invalid_request_error",
            "param": "reasoning_effort",
            "code": "unsupported_parameter",
        },
    )


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls = None


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.finish_reason = "stop"
        self.message = _FakeMessage(content)


class _FakeUsage:
    prompt_tokens = 1
    completion_tokens = 1
    total_tokens = 2


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


class _Completions:
    """Protokolliert kwargs; wirft optional die ersten Fehler der Reihe nach."""

    def __init__(
        self, errors: list[Exception] | None = None, content: str = '{"a": 1}'
    ) -> None:
        self.calls: list[dict] = []
        self._errors = list(errors or [])
        self._content = content

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self._errors:
            raise self._errors.pop(0)
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, completions) -> None:
        self.completions = completions


class _FakeOpenAI:
    def __init__(self, completions) -> None:
        self.chat = _FakeChat(completions)


_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Wetter abfragen",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


@pytest.fixture()
def make_client(monkeypatch):
    monkeypatch.setenv("LLM_FORCE_STREAM", "false")
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

    def _make(
        *,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-6.1-sol",
        effort: str = "none",
        completions: _Completions | None = None,
    ) -> tuple[LLMClient, _Completions]:
        comps = completions or _Completions()
        obj = LLMClient.__new__(LLMClient)
        obj._max_retries = 0
        obj._retry_initial_delay = 0.0
        obj._retry_max_delay = 0.0
        obj._num_ctx = 8192
        obj._think = effort != "none"
        obj.reasoning_effort = effort
        obj.api_key = "test"
        obj.base_url = base_url
        obj.model = model
        obj.client = _FakeOpenAI(comps)
        return obj, comps

    return _make


def _chat_with_tools(client: LLMClient) -> None:
    client.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}], tools=_TOOLS
    )


# ---------------------------------------------------------------------------
# (a) Tools-Pfad
# ---------------------------------------------------------------------------


def test_tools_path_sends_reasoning_effort_none_for_gpt_61_sol(make_client) -> None:
    client, comps = make_client()

    _chat_with_tools(client)

    assert len(comps.calls) == 1
    assert comps.calls[0]["reasoning_effort"] == "none"
    assert comps.calls[0]["tools"] == _TOOLS


def test_tools_path_forwards_route_effort(make_client) -> None:
    client, comps = make_client(effort="low")

    _chat_with_tools(client)

    assert comps.calls[0]["reasoning_effort"] == "low"


# ---------------------------------------------------------------------------
# (b) chat()-/chat_json()-Pfad
# ---------------------------------------------------------------------------


def test_chat_path_sends_reasoning_effort_none(make_client) -> None:
    client, comps = make_client()

    client.chat(messages=[{"role": "user", "content": "hi"}])

    assert comps.calls[0]["reasoning_effort"] == "none"


def test_chat_path_force_no_thinking_overrides_route_effort(make_client) -> None:
    client, comps = make_client(effort="high")

    client.chat(
        messages=[{"role": "user", "content": "hi"}], force_no_thinking=True
    )

    assert comps.calls[0]["reasoning_effort"] == "none"


def test_chat_json_path_sends_reasoning_effort(make_client) -> None:
    client, comps = make_client(effort="medium")
    client.chat_json(messages=[{"role": "user", "content": "hi"}])

    assert comps.calls[0]["reasoning_effort"] == "medium"


# ---------------------------------------------------------------------------
# (c) Kein Parameter fuer andere Provider / Nicht-Reasoning-Modelle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("base_url", "model"),
    [
        ("http://localhost:11434", "gpt-6.1-sol"),  # Ollama
        ("https://openrouter.ai.attacker.test/v1", "gpt-6.1-sol"),  # kein OpenRouter
        ("https://llm-proxy.example.test/v1", "gpt-6.1-sol"),  # openai-kompatibel
        ("https://api.openai.com/v1", "gpt-4.1"),  # Nicht-Reasoning
        ("https://api.openai.com/v1", "gpt-4o"),
    ],
)
def test_no_reasoning_effort_for_other_providers_and_models(
    make_client, base_url: str, model: str
) -> None:
    client, comps = make_client(base_url=base_url, model=model, effort="none")

    client.chat(messages=[{"role": "user", "content": "hi"}])
    _chat_with_tools(client)

    assert comps.calls, "mindestens ein Request erwartet"
    for call in comps.calls:
        assert "reasoning_effort" not in call


def test_tools_path_unknown_provider_short_circuit_sends_no_effort(make_client) -> None:
    """Unknown-Provider: Tools-Pfad faellt auf chat() ohne Tools zurueck,
    ohne ``reasoning_effort``."""
    client, comps = make_client(
        base_url="https://llm-proxy.example.test/v1", model="gpt-6.1-sol"
    )

    _chat_with_tools(client)

    assert comps.calls
    assert all("reasoning_effort" not in c for c in comps.calls)


def test_helper_unit_cases() -> None:
    assert reasoning_effort_kwargs(
        provider="openai", model="gpt-6.1-sol", effort="high"
    ) == {"reasoning_effort": "high"}
    assert reasoning_effort_kwargs(
        provider="openai", model="gpt-6.1-sol", effort="high", force_no_thinking=True
    ) == {"reasoning_effort": "none"}
    assert reasoning_effort_kwargs(
        provider="openai", model="gpt-6.1-sol", effort=None
    ) == {"reasoning_effort": "none"}
    assert reasoning_effort_kwargs(provider="ollama", model="gpt-6.1-sol", effort="none") == {}
    assert reasoning_effort_kwargs(provider="unknown", model="gpt-6.1-sol", effort="none") == {}
    assert reasoning_effort_kwargs(provider="openai", model="gpt-4.1", effort="none") == {}


# ---------------------------------------------------------------------------
# (d) Quirk
# ---------------------------------------------------------------------------


def test_quirk_retries_once_without_reasoning_effort_on_tools_path(make_client) -> None:
    client, comps = make_client(
        model="o3", completions=_Completions([_unsupported_none_400()])
    )

    _chat_with_tools(client)

    assert len(comps.calls) == 2, "genau ein Retry"
    assert comps.calls[0]["reasoning_effort"] == "none"
    assert "reasoning_effort" not in comps.calls[1]


def test_quirk_retries_once_without_reasoning_effort_on_chat_path(make_client) -> None:
    client, comps = make_client(
        model="o3", completions=_Completions([_unsupported_none_400()])
    )

    client.chat(messages=[{"role": "user", "content": "hi"}])

    assert len(comps.calls) == 2
    assert comps.calls[0]["reasoning_effort"] == "none"
    assert "reasoning_effort" not in comps.calls[1]


def test_tools_400_does_not_trigger_retry(make_client) -> None:
    """Der Tools-400 entsteht gerade OHNE ``reasoning_effort=none`` — ein
    Retry ohne Parameter wuerde ihn reproduzieren statt beheben."""
    client, comps = make_client(completions=_Completions([_tools_400()]))

    with pytest.raises(_FakeBadRequest):
        _chat_with_tools(client)

    assert len(comps.calls) == 1


def test_detector_is_narrow() -> None:
    assert is_reasoning_effort_400(_unsupported_none_400())
    assert not is_reasoning_effort_400(_tools_400())
    assert not is_reasoning_effort_400(_FakeBadRequest("Invalid API key"))
    assert not is_reasoning_effort_400(
        _FakeBadRequest("Unsupported value: 'temperature' does not support 0.7")
    )


# ---------------------------------------------------------------------------
# (g) OpenRouter: reasoning_effort fuer jedes Modell
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("effort", "expected"),
    [("none", "none"), ("high", "high")],
)
def test_openrouter_sends_reasoning_effort_for_any_model(
    make_client, effort: str, expected: str
) -> None:
    """OpenRouter bildet ``reasoning_effort`` auf das Zielmodell ab. Ohne den
    Parameter denkt z. B. DeepSeek V4.1 Flash bei jedem Aufruf."""
    client, comps = make_client(
        base_url="https://openrouter.ai/api/v1",
        model="deepseek/deepseek-v4.1-flash",
        effort=effort,
    )

    client.chat(messages=[{"role": "user", "content": "hi"}])

    assert comps.calls[0]["reasoning_effort"] == expected


def test_openrouter_force_no_thinking_overrides_route_effort(make_client) -> None:
    client, comps = make_client(
        base_url="https://openrouter.ai/api/v1",
        model="deepseek/deepseek-v4.1-flash",
        effort="high",
    )

    client.chat(messages=[{"role": "user", "content": "hi"}], force_no_thinking=True)

    assert comps.calls[0]["reasoning_effort"] == "none"
