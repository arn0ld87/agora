"""Slice 1b: 400-Fallback-Retry für max_tokens ↔ max_completion_tokens.

Die Heuristik in ``_uses_max_completion_tokens`` deckt die heutigen GPT-5/
o-Modelle ab, aber ein neuer Proxy oder ein neues Modell kann den Trigger
verschieben. Wenn das Backend einen 400 mit Wortlaut „'max_tokens' is not
supported … use 'max_completion_tokens'" (oder umgekehrt) bekommt, muss
``LLMClient.chat()`` **einmalig** mit getauschtem Schlüssel retryen — kein
Endlos-Retry, kein 4xx-Loop.

Streaming + Non-Streaming + describe_image sind alle abgedeckt.
"""

from __future__ import annotations

import pytest

from app.utils.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Heuristik-Unit-Tests
# ---------------------------------------------------------------------------


class _FakeOpenAIBadRequest(Exception):
    """Ersatz für openai.BadRequestError, falls openai im Test nicht installiert ist.

    Die Heuristik in ``_is_token_key_400`` greift auf den Wortlaut, nicht
    auf den Typ — daher reicht eine Exception mit der richtigen Message.
    """


@pytest.mark.parametrize(
    "message",
    [
        "Error code: 400 - Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.",
        "Unsupported parameter: 'max_completion_tokens' is not supported with this model. Use 'max_tokens' instead.",
        "BadRequest: max_tokens is not supported, use max_completion_tokens",
        "max_completion_tokens is not supported with this provider, use max_tokens",
    ],
)
def test_is_token_key_400_matches_known_wordings(message: str) -> None:
    exc = _FakeOpenAIBadRequest(message)
    assert LLMClient._is_token_key_400(exc) is True


@pytest.mark.parametrize(
    "message",
    [
        "Connection reset by peer",
        "Rate limit exceeded (429)",
        "Invalid API key",
        "max_tokens parameter is required",  # generic validation, kein 400-Routing-Hint
        "",
    ],
)
def test_is_token_key_400_ignores_unrelated_errors(message: str) -> None:
    exc = _FakeOpenAIBadRequest(message)
    assert LLMClient._is_token_key_400(exc) is False


def test_swap_token_kwargs_max_tokens_to_completion() -> None:
    swapped = LLMClient._swap_token_kwargs({"model": "x", "max_tokens": 4096})
    assert swapped == {"model": "x", "max_completion_tokens": 4096}


def test_swap_token_kwargs_completion_to_max_tokens() -> None:
    swapped = LLMClient._swap_token_kwargs({"model": "x", "max_completion_tokens": 2048})
    assert swapped == {"model": "x", "max_tokens": 2048}


def test_swap_token_kwargs_no_key_returns_none() -> None:
    assert LLMClient._swap_token_kwargs({"model": "x", "messages": []}) is None


# ---------------------------------------------------------------------------
# Integration: chat() retried einmalig mit getauschtem Key
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
    """Wirft beim ersten Call einen 400-Token-Key-Error; beim zweiten gibt sie 200 zurück."""

    def __init__(self, fail_first_with: str) -> None:
        self.calls: list[dict] = []
        self._fail_first_with = fail_first_with

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        if len(self.calls) == 1:
            raise _FakeOpenAIBadRequest(self._fail_first_with)
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
    obj.model = "gpt-4o"  # Heuristik sagt max_tokens
    monkeypatch.setenv("LLM_FORCE_STREAM", "false")
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    return obj


def test_chat_retries_with_swapped_key_on_400(fake_client) -> None:
    """gpt-4o sendet max_tokens. Wenn der Proxy 400 wirft mit 'use max_completion_tokens',
    soll der zweite Versuch max_completion_tokens enthalten — kein dritter Versuch.
    """
    completions = _FlakyCompletions(
        fail_first_with=(
            "Error code: 400 - Unsupported parameter: 'max_tokens' is not "
            "supported with this model. Use 'max_completion_tokens' instead."
        )
    )
    fake_client.client = _FakeOpenAI(completions)

    fake_client.chat(messages=[{"role": "user", "content": "hi"}], max_tokens=4096)

    assert len(completions.calls) == 2, "must retry exactly once"
    # 1. Versuch: Heuristik → max_tokens
    assert completions.calls[0].get("max_tokens") == 4096
    assert "max_completion_tokens" not in completions.calls[0]
    # 2. Versuch: getauscht
    assert completions.calls[1].get("max_completion_tokens") == 4096
    assert "max_tokens" not in completions.calls[1]


def test_chat_retries_in_other_direction_too(fake_client) -> None:
    """gpt-5-mini sendet max_completion_tokens. Wenn ein älterer Proxy 400 wirft mit
    'use max_tokens', muss der Fallback in die andere Richtung greifen.
    """
    fake_client.model = "gpt-5-mini"
    completions = _FlakyCompletions(
        fail_first_with=(
            "Unsupported parameter: 'max_completion_tokens' is not supported "
            "with this model. Use 'max_tokens' instead."
        )
    )
    fake_client.client = _FakeOpenAI(completions)

    fake_client.chat(messages=[{"role": "user", "content": "hi"}], max_tokens=2048)

    assert len(completions.calls) == 2
    assert completions.calls[0].get("max_completion_tokens") == 2048
    assert "max_tokens" not in completions.calls[0]
    assert completions.calls[1].get("max_tokens") == 2048
    assert "max_completion_tokens" not in completions.calls[1]


def test_chat_does_not_retry_on_unrelated_400(fake_client) -> None:
    """Ein 400, der nichts mit Token-Limit zu tun hat, propagiert sofort —
    kein Endlos-Retry, kein Verschleiern echter Validation-Fehler."""

    class _AlwaysFail:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise _FakeOpenAIBadRequest("Invalid API key")

    completions = _AlwaysFail()
    fake_client.client = _FakeOpenAI(completions)

    with pytest.raises(_FakeOpenAIBadRequest):
        fake_client.chat(messages=[{"role": "user", "content": "hi"}], max_tokens=1024)
    assert completions.calls == 1, "must NOT retry unrelated 400"


def test_chat_streaming_path_also_falls_back(monkeypatch) -> None:
    """Force-Stream (Ollama) muss denselben Fallback nutzen — Streaming-Pfad
    war historisch der häufigere, weil Ollama Cloud non-stream stalled.
    """
    obj = LLMClient.__new__(LLMClient)
    obj._max_retries = 0
    obj._retry_initial_delay = 0.0
    obj._retry_max_delay = 0.0
    obj._num_ctx = 8192
    obj._think = False
    obj.api_key = "test"
    obj.base_url = "http://localhost:11434/v1"  # Ollama → force_stream
    obj.model = "qwen2.5:32b"
    monkeypatch.setenv("LLM_FORCE_STREAM", "true")
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

    # Streaming-Response simulieren: eine einzige fake-chunk-Folge.
    class _Chunk:
        def __init__(self, content=None, finish=None):
            self.choices = [
                type("Choice", (), {
                    "delta": type("Delta", (), {"content": content})(),
                    "finish_reason": finish,
                })()
            ]
            self.usage = None

    def fake_iter():
        yield _Chunk(content="ok", finish=None)
        yield _Chunk(content=None, finish="stop")

    class _StreamingFlaky:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def create(self, **kwargs):
            self.calls.append(dict(kwargs))
            if len(self.calls) == 1:
                raise _FakeOpenAIBadRequest(
                    "'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead."
                )
            return fake_iter()

    completions = _StreamingFlaky()
    obj.client = _FakeOpenAI(completions)

    obj.chat(messages=[{"role": "user", "content": "hi"}], max_tokens=4096)

    assert len(completions.calls) == 2
    assert completions.calls[0].get("max_tokens") == 4096
    assert completions.calls[1].get("max_completion_tokens") == 4096


def test_describe_image_falls_back_too(fake_client) -> None:
    """Vision-Pfad muss denselben Fallback haben — sonst läuft ein neues
    Vision-Modell beim nächsten Mal wieder auf 400 auf.
    """
    completions = _FlakyCompletions(
        fail_first_with=(
            "Unsupported parameter: 'max_tokens' is not supported. Use 'max_completion_tokens' instead."
        )
    )
    fake_client.client = _FakeOpenAI(completions)
    fake_client.describe_image(image_b64="aGVsbG8=", prompt="describe", max_tokens=1024)

    assert len(completions.calls) == 2
    assert completions.calls[0].get("max_tokens") == 1024
    assert completions.calls[1].get("max_completion_tokens") == 1024
