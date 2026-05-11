"""
Regression cover for OpenAI 400: ``Unsupported parameter: 'max_tokens' is not
supported with this model. Use 'max_completion_tokens' instead.``

GPT-5 / o1 / o3 / o4 müssen den OpenAI-Aufruf mit ``max_completion_tokens=N``
statt ``max_tokens=N`` bekommen. Alle anderen Modelle (gpt-4o, gpt-3.5,
qwen2.5:32b, gemini-*) bleiben bei ``max_tokens=N``.

Mock-only — kein Netzwerk.
"""

from __future__ import annotations

import pytest

from app.utils.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Pure-Heuristik-Unit-Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    [
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "GPT-5-Pro",            # case-insensitiv
        "  gpt-5-thinking  ",   # getrimmt
        "o1",
        "o1-preview",
        "o3",
        "o3-mini",
        "o4-mini-2025-01-01",
    ],
)
def test_models_that_require_max_completion_tokens(model: str) -> None:
    assert LLMClient._uses_max_completion_tokens(model) is True


@pytest.mark.parametrize(
    "model",
    [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
        "qwen2.5:32b",
        "qwen3-coder-next:cloud",
        "deepseek-v4-flash:cloud",
        "gemini-3-flash-preview",
        "llama3.1:70b",
        # Strikt-Prefix-Matching: hypothetische Namen, die "gpt-5" nur als
        # Substring-Anfang ohne Trennzeichen enthalten, sind KEIN GPT-5.
        "gpt-500",
        "gpt-50",
        "o10-experimental",
        "o42-mini",
        "",          # leerer Modellname → Fallback auf max_tokens
        "   ",
    ],
)
def test_models_that_keep_max_tokens(model: str) -> None:
    assert LLMClient._uses_max_completion_tokens(model) is False


def test_completion_token_kwargs_override_model() -> None:
    """Vision-Pfad: explizites `model` überschreibt self.model."""
    obj = LLMClient.__new__(LLMClient)
    obj.model = "qwen2.5:32b"
    assert obj._completion_token_kwargs(1024, model="gpt-5-vision") == {
        "max_completion_tokens": 1024
    }
    # Umgekehrt: self.model GPT-5, override auf gpt-4o → max_tokens.
    obj.model = "gpt-5-mini"
    assert obj._completion_token_kwargs(2048, model="gpt-4o") == {
        "max_tokens": 2048
    }


def test_completion_token_kwargs_gpt5() -> None:
    """Instance-Methode liefert das passende Wire-Key-Dict pro self.model."""
    obj = LLMClient.__new__(LLMClient)
    obj.model = "gpt-5-mini"
    assert obj._completion_token_kwargs(4096) == {"max_completion_tokens": 4096}


def test_completion_token_kwargs_legacy() -> None:
    obj = LLMClient.__new__(LLMClient)
    obj.model = "gpt-4o"
    assert obj._completion_token_kwargs(2048) == {"max_tokens": 2048}


# ---------------------------------------------------------------------------
# Integration: chat() ruft OpenAI-SDK mit dem richtigen Schlüssel
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


class _FakeCompletions:
    def __init__(self) -> None:
        self.captured_kwargs: dict | None = None

    def create(self, **kwargs):
        self.captured_kwargs = kwargs
        return _FakeResponse()


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAI:
    def __init__(self) -> None:
        self.chat = _FakeChat()


@pytest.fixture()
def fake_client(monkeypatch):
    """LLMClient ohne echten OpenAI-Init, mit fake-Client an .client."""
    obj = LLMClient.__new__(LLMClient)
    obj._max_retries = 0          # kein Retry-Wrap nötig
    obj._retry_initial_delay = 0.0
    obj._retry_max_delay = 0.0
    obj._num_ctx = 8192
    obj._think = False
    obj.api_key = "test"
    # Non-Ollama base_url → kein force-stream-Pfad.
    obj.base_url = "https://api.openai.com/v1"
    obj.client = _FakeOpenAI()
    # Deaktiviere Streaming-Force-Pfad explizit (für alle Tests in diesem Modul).
    monkeypatch.setenv("LLM_FORCE_STREAM", "false")
    # E2E-Stub muss aus sein.
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
    return obj


def test_chat_sends_max_completion_tokens_for_gpt5(fake_client) -> None:
    fake_client.model = "gpt-5-mini"
    fake_client.chat(
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=4096,
    )
    captured = fake_client.client.chat.completions.captured_kwargs
    assert captured is not None
    assert captured.get("max_completion_tokens") == 4096
    assert "max_tokens" not in captured


def test_chat_sends_max_tokens_for_gpt4o(fake_client) -> None:
    fake_client.model = "gpt-4o"
    fake_client.chat(
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=2048,
    )
    captured = fake_client.client.chat.completions.captured_kwargs
    assert captured is not None
    assert captured.get("max_tokens") == 2048
    assert "max_completion_tokens" not in captured


def test_chat_sends_max_completion_tokens_for_o1_preview(fake_client) -> None:
    fake_client.model = "o1-preview"
    fake_client.chat(
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=8192,
    )
    captured = fake_client.client.chat.completions.captured_kwargs
    assert captured is not None
    assert captured.get("max_completion_tokens") == 8192
    assert "max_tokens" not in captured


def test_describe_image_picks_key_from_vision_model_not_self_model(fake_client) -> None:
    """describe_image kann ein anderes Modell als self.model nutzen — die
    Token-Key-Heuristik muss sich am tatsächlich versendeten Modell orientieren.
    """
    fake_client.model = "qwen2.5:32b"  # self.model -> max_tokens
    fake_client.describe_image(
        image_b64="aGVsbG8=",
        prompt="describe",
        model="gpt-5-vision",          # override -> max_completion_tokens
        max_tokens=1024,
    )
    captured = fake_client.client.chat.completions.captured_kwargs
    assert captured is not None
    assert captured.get("max_completion_tokens") == 1024
    assert "max_tokens" not in captured
