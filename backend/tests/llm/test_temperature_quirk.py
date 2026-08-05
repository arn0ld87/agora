"""GPT-5-/o-Reasoning-Familie akzeptiert nur den Default-``temperature``-Wert (#1096).

Jeder Run gegen diese Modelle brach bisher mit 400 ``unsupported_value`` /
``param=temperature`` ab, weil ``LLMClient`` feste ``temperature``-Werte
sendet (chat 0.7, describe_image 0.3, chat_json 0.3). Zweiter Defekt:
``chat_json()`` deutete diesen 400er faelschlich als fehlenden
Strict-Schema-Support und fiel grundlos auf ``json_object`` zurueck.

Vier Szenarien:
    (a) Request-Shaping fuer gpt-5.6-luna enthaelt kein ``temperature``.
    (b) Request-Shaping fuer gpt-4o behaelt ``temperature``.
    (c) Ein gemockter unsupported_value/temperature-400 loest in ``chat()``
        einen Retry ohne ``temperature`` aus (Netz fuer unbekannte
        Reasoning-Modelle, die die Heuristik noch nicht kennt).
    (d) Derselbe gemockte 400 in ``chat_json()`` loest NICHT den
        json_object-Fallback aus — response_format bleibt json_schema.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.llm.providers.openai import is_temperature_400, omits_temperature
from app.utils.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Heuristik-Unit-Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    [
        "gpt-5",
        "gpt-5-nano",
        "gpt-5.6-luna",
        "o1-preview",
        "o3",
        "o4.1",
    ],
)
def test_omits_temperature_matches_reasoning_family(model: str) -> None:
    assert omits_temperature(model) is True


@pytest.mark.parametrize(
    "model",
    [
        "gpt-4o",
        "gpt-500",  # striktes Prefix-Matching — kein Match auf "gpt-5"
        "qwen3:8b",
        "",
    ],
)
def test_omits_temperature_ignores_unrelated_models(model: str) -> None:
    assert omits_temperature(model) is False


class _FakeBadRequestWithBody(Exception):
    """Ersatz fuer openai.BadRequestError mit strukturiertem ``.body`` (SDK-Shape).

    Das OpenAI-SDK entpackt den Fehlerbody bereits auf
    ``{"message", "type", "param", "code"}`` (siehe
    ``openai._client.OpenAI._make_status_error``) — kein ``{"error": {...}}``-
    Wrapper mehr auf Exception-Ebene.
    """

    def __init__(self, message: str, *, body: dict | None = None) -> None:
        super().__init__(message)
        self.body = body


def test_is_temperature_400_matches_structured_body() -> None:
    exc = _FakeBadRequestWithBody(
        "Error code: 400 - {'error': {'message': \"Unsupported value: "
        "'temperature' does not support 0.7 with this model. Only the "
        "default (1) value is supported.\", 'type': 'invalid_request_error', "
        "'param': 'temperature', 'code': 'unsupported_value'}}",
        body={
            "message": "Unsupported value: 'temperature' does not support 0.7 "
            "with this model. Only the default (1) value is supported.",
            "type": "invalid_request_error",
            "param": "temperature",
            "code": "unsupported_value",
        },
    )
    assert is_temperature_400(exc) is True


@pytest.mark.parametrize(
    "message",
    [
        "Unsupported value: 'temperature' does not support 0.7 with this "
        "model. Only the default (1) value is supported.",
        "BadRequest: temperature is not supported with this model",
    ],
)
def test_is_temperature_400_matches_known_wordings_without_body(message: str) -> None:
    exc = _FakeBadRequestWithBody(message, body=None)
    assert is_temperature_400(exc) is True


@pytest.mark.parametrize(
    "message",
    [
        "Connection reset by peer",
        "Rate limit exceeded (429)",
        "Invalid API key",
        "'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.",
        "",
    ],
)
def test_is_temperature_400_ignores_unrelated_errors(message: str) -> None:
    exc = _FakeBadRequestWithBody(message, body=None)
    assert is_temperature_400(exc) is False


# ---------------------------------------------------------------------------
# Integration: Request-Shaping + Retry ueber LLMClient
# ---------------------------------------------------------------------------


class _FakeUsage:
    completion_tokens = 42


class _FakeMessage:
    content = '{"ok": true}'


class _FakeChoice:
    finish_reason = "stop"
    message = _FakeMessage()


class _FakeResponse:
    choices = [_FakeChoice()]
    usage = _FakeUsage()


class _FlakyCompletions:
    """Wirft beim ersten Call einen 400-Temperature-Error; beim zweiten 200."""

    def __init__(self, fail_first_with: str) -> None:
        self.calls: list[dict] = []
        self._fail_first_with = fail_first_with

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        if len(self.calls) == 1:
            raise _FakeBadRequestWithBody(
                self._fail_first_with,
                body={
                    "message": self._fail_first_with,
                    "param": "temperature",
                    "code": "unsupported_value",
                },
            )
        return _FakeResponse()


class _StableCompletions:
    """Gibt immer 200 zurueck — fuer reine Shaping-Assertions."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        return _FakeResponse()


class _FakeChat:
    def __init__(self, completions) -> None:
        self.completions = completions


class _FakeOpenAI:
    def __init__(self, completions) -> None:
        self.chat = _FakeChat(completions)


@pytest.fixture()
def fake_client(monkeypatch):
    obj = LLMClient.__new__(LLMClient)
    obj._max_retries = 0
    obj._retry_initial_delay = 0.0
    obj._retry_max_delay = 0.0
    obj._num_ctx = 8192
    obj._think = False
    obj.api_key = "test"
    obj.base_url = "https://api.openai.com/v1"
    obj.model = "gpt-4o"
    monkeypatch.setenv("LLM_FORCE_STREAM", "false")
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    return obj


def test_chat_omits_temperature_for_gpt5_family(fake_client) -> None:
    """(a) gpt-5.6-luna: temperature darf gar nicht erst in den Kwargs landen."""
    fake_client.model = "gpt-5.6-luna"
    completions = _StableCompletions()
    fake_client.client = _FakeOpenAI(completions)

    fake_client.chat(messages=[{"role": "user", "content": "hi"}], temperature=0.7)

    assert len(completions.calls) == 1
    assert "temperature" not in completions.calls[0]


def test_chat_keeps_temperature_for_gpt4o(fake_client) -> None:
    """(b) gpt-4o: temperature bleibt unveraendert erhalten."""
    completions = _StableCompletions()
    fake_client.client = _FakeOpenAI(completions)

    fake_client.chat(messages=[{"role": "user", "content": "hi"}], temperature=0.7)

    assert len(completions.calls) == 1
    assert completions.calls[0].get("temperature") == 0.7


def test_describe_image_omits_temperature_for_gpt5_family(fake_client) -> None:
    fake_client.model = "gpt-5.6-luna"
    completions = _StableCompletions()
    fake_client.client = _FakeOpenAI(completions)

    fake_client.describe_image(image_b64="aGVsbG8=", prompt="describe")

    assert len(completions.calls) == 1
    assert "temperature" not in completions.calls[0]


def test_describe_image_keeps_temperature_for_gpt4o(fake_client) -> None:
    completions = _StableCompletions()
    fake_client.client = _FakeOpenAI(completions)

    fake_client.describe_image(image_b64="aGVsbG8=", prompt="describe")

    assert len(completions.calls) == 1
    assert completions.calls[0].get("temperature") == 0.3


def test_chat_retries_without_temperature_on_400(fake_client) -> None:
    """(c) Unbekanntes Reasoning-Modell (noch nicht in der Heuristik) sendet
    temperature, bekommt den unsupported_value-400 und retried einmalig ohne
    ``temperature`` — kein dritter Versuch, keine Endlosschleife.
    """
    fake_client.model = "gpt-6-preview"  # (noch) nicht in omits_temperature()
    completions = _FlakyCompletions(
        fail_first_with=(
            "Unsupported value: 'temperature' does not support 0.7 with "
            "this model. Only the default (1) value is supported."
        )
    )
    fake_client.client = _FakeOpenAI(completions)

    fake_client.chat(messages=[{"role": "user", "content": "hi"}], temperature=0.7)

    assert len(completions.calls) == 2, "must retry exactly once"
    assert completions.calls[0].get("temperature") == 0.7
    assert "temperature" not in completions.calls[1]


def test_chat_does_not_retry_on_unrelated_400(fake_client) -> None:
    """Gegenprobe: ein 400, der nichts mit temperature zu tun hat, propagiert
    sofort — kein Endlos-Retry, kein Verschleiern echter Validation-Fehler."""

    class _AlwaysFail:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise _FakeBadRequestWithBody("Invalid API key", body=None)

    completions = _AlwaysFail()
    fake_client.client = _FakeOpenAI(completions)

    with pytest.raises(_FakeBadRequestWithBody):
        fake_client.chat(messages=[{"role": "user", "content": "hi"}], temperature=0.7)
    assert completions.calls == 1, "must NOT retry unrelated 400"


# ---------------------------------------------------------------------------
# Integration: chat_json() faellt bei temperature-400 NICHT auf json_object zurueck
# ---------------------------------------------------------------------------


class PersonaSchema(BaseModel):
    ok: bool


def test_chat_json_does_not_fall_back_to_json_object_on_temperature_400(fake_client) -> None:
    """(d) Derselbe gemockte temperature-400 darf in chat_json() NICHT den
    strict->json_object-Fallback ausloesen. Der zweite (erfolgreiche)
    Providerattempt muss weiterhin im json_schema-Modus laufen, nicht
    json_object.
    """
    fake_client.model = "gpt-6-preview"
    completions = _FlakyCompletions(
        fail_first_with=(
            "Unsupported value: 'temperature' does not support 0.3 with "
            "this model. Only the default (1) value is supported."
        )
    )
    fake_client.client = _FakeOpenAI(completions)

    result = fake_client.chat_json(
        [{"role": "user", "content": "hi"}],
        temperature=0.3,
        schema=PersonaSchema,
    )

    assert result == {"ok": True}
    assert len(completions.calls) == 2, "must retry exactly once, not degrade to a 3rd call"
    # 1. Versuch: temperature gesetzt, strict json_schema angefragt.
    assert completions.calls[0].get("temperature") == 0.3
    assert completions.calls[0]["response_format"]["type"] == "json_schema"
    # 2. Versuch: temperature entfernt, WEITERHIN json_schema (kein json_object-Fallback).
    assert "temperature" not in completions.calls[1]
    assert completions.calls[1]["response_format"]["type"] == "json_schema"
