"""Tools-Pfad wendet den ``temperature``-Quirk aus #1096 an (#1228).

``tool_calls._chat_with_tools`` setzte ``temperature`` bedingungslos in den
Request — der Quirk aus #1096 (GPT-5-/o1/o3/o4-Reasoning-Familie akzeptiert
ausschliesslich den Default-Wert (1), sonst 400 ``unsupported_value``) war
auf diesem Pfad nie nachgezogen: weder Shaping ueber ``omits_temperature``
beim Requestbau noch ein Retry-Netz in der execute-Quirkliste. Ein natives
Tool-Calling gegen gpt-5-mini/o3 lief damit garantiert in einen 400 ohne
zweiten Versuch, waehrend ``chat()`` beides hat.

Vier Szenarien:
    (a) Tools-Request gegen gpt-5-mini enthaelt kein ``temperature``.
    (b) Tools-Request gegen gpt-4o behaelt ``temperature``.
    (c) Unbekanntes Reasoning-Modell (noch nicht in der Heuristik): gemockter
        unsupported_value/temperature-400 loest im Tools-Pfad einen Retry
        ohne ``temperature`` aus — Netz, Paritaet mit ``chat()``.
    (d) Gegenprobe: ein 400 ohne temperature-Bezug propagiert sofort.
"""

from __future__ import annotations

import pytest

from app.utils.llm_client import LLMClient


class _FakeBadRequestWithBody(Exception):
    """Ersatz fuer openai.BadRequestError mit strukturiertem ``.body``.

    Gleiche Struktur wie in ``test_temperature_quirk.py``: das OpenAI-SDK
    entpackt den Fehlerbody bereits auf ``{"message", "type", "param",
    "code"}``.
    """

    def __init__(self, message: str, *, body: dict | None = None) -> None:
        super().__init__(message)
        self.body = body


def _make_temperature_400(temperature_value: str) -> _FakeBadRequestWithBody:
    return _FakeBadRequestWithBody(
        "Error code: 400 - {'error': {'message': \"Unsupported value: "
        f"'temperature' does not support {temperature_value} with this model. "
        "Only the default (1) value is supported.\", 'type': "
        "'invalid_request_error', 'param': 'temperature', 'code': "
        "'unsupported_value'}}",
        body={
            "message": "Unsupported value: 'temperature' does not support "
            f"{temperature_value} with this model. Only the default (1) "
            "value is supported.",
            "type": "invalid_request_error",
            "param": "temperature",
            "code": "unsupported_value",
        },
    )


# ---------------------------------------------------------------------------
# Fakes fuer den nicht-streamenden Tools-Pfad
# ---------------------------------------------------------------------------


class _FakeMessage:
    content = ""

    tool_calls = None


class _FakeChoice:
    finish_reason = "stop"
    message = _FakeMessage()


class _FakeResponse:
    choices = [_FakeChoice()]


class _StableCompletions:
    """Gibt immer 200 zurueck — fuer reine Shaping-Assertions."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        return _FakeResponse()


class _FlakyCompletions:
    """Wirft beim ersten Call einen 400-Temperature-Error; danach 200."""

    def __init__(self, first_error: Exception) -> None:
        self.calls: list[dict] = []
        self._first_error = first_error

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        if len(self.calls) == 1:
            raise self._first_error
        return _FakeResponse()


class _AlwaysFailCompletions:
    """Wirft immer denselben Fehler — fuer Gegenproben ohne Retry."""

    def __init__(self, error: Exception) -> None:
        self.calls: list[dict] = []
        self._error = error

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        raise self._error


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
def fake_client(monkeypatch):
    obj = LLMClient.__new__(LLMClient)
    obj._max_retries = 0
    obj._retry_initial_delay = 0.0
    obj._retry_max_delay = 0.0
    obj._num_ctx = 8192
    obj._think = False
    obj.api_key = "test"
    obj.base_url = "https://api.openai.com/v1"  # detect_provider -> "openai"
    obj.model = "gpt-4o"
    monkeypatch.setenv("LLM_FORCE_STREAM", "false")
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    return obj


# ---------------------------------------------------------------------------
# (a)/(b) Request-Shaping auf dem Tools-Pfad
# ---------------------------------------------------------------------------


def test_chat_with_tools_omits_temperature_for_gpt5_family(fake_client) -> None:
    """(a) gpt-5-mini: temperature darf gar nicht erst in die Kwargs landen."""
    fake_client.model = "gpt-5-mini"
    completions = _StableCompletions()
    fake_client.client = _FakeOpenAI(completions)

    result = fake_client.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=_TOOLS,
        temperature=0.5,
    )

    assert len(completions.calls) == 1
    assert "temperature" not in completions.calls[0]
    # Der Rest des Requests bleibt unveraendert: Tools kommen durch.
    assert completions.calls[0]["tools"] == _TOOLS
    assert result["finish_reason"] == "stop"


def test_chat_with_tools_keeps_temperature_for_gpt4o(fake_client) -> None:
    """(b) gpt-4o: temperature bleibt unveraendert erhalten."""
    completions = _StableCompletions()
    fake_client.client = _FakeOpenAI(completions)

    fake_client.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=_TOOLS,
        temperature=0.5,
    )

    assert len(completions.calls) == 1
    assert completions.calls[0].get("temperature") == 0.5


# ---------------------------------------------------------------------------
# (c)/(d) Retry-Netz in der execute-Quirkliste (Paritaet mit chat())
# ---------------------------------------------------------------------------


def test_chat_with_tools_retries_without_temperature_on_400(fake_client) -> None:
    """(c) Unbekanntes Reasoning-Modell (noch nicht in omits_temperature())
    sendet temperature, bekommt den unsupported_value-400 und retried
    einmalig ohne ``temperature`` — kein dritter Versuch.
    """
    fake_client.model = "gpt-6-preview"  # (noch) nicht in omits_temperature()
    completions = _FlakyCompletions(_make_temperature_400("0.5"))
    fake_client.client = _FakeOpenAI(completions)

    fake_client.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=_TOOLS,
        temperature=0.5,
    )

    assert len(completions.calls) == 2, "must retry exactly once"
    assert completions.calls[0].get("temperature") == 0.5
    assert "temperature" not in completions.calls[1]


def test_chat_with_tools_does_not_retry_on_unrelated_400(fake_client) -> None:
    """(d) Gegenprobe: ein 400, der nichts mit temperature zu tun hat,
    propagiert sofort — kein Verschleiern echter Validation-Fehler."""
    completions = _AlwaysFailCompletions(_FakeBadRequestWithBody("Invalid API key"))
    fake_client.client = _FakeOpenAI(completions)

    with pytest.raises(_FakeBadRequestWithBody):
        fake_client.chat_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=_TOOLS,
            temperature=0.5,
        )
    assert len(completions.calls) == 1, "must NOT retry unrelated 400"
