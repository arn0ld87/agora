"""Regression zu Issue #1229 — Vision-Pfad behandelt MiniMax-thinking nicht.

``describe_image`` will laut Kommentar „never want reasoning noise in vision
output". Bei Ollama erreicht es das über ``think=False``; gegen MiniMax
(api.minimax.io) fehlte das ``thinking``-Feld komplett. MiniMax-M3 ist
vision-fähig (``image_url``-Content-Parts im OpenAI-kompatiblen Pfad) und
schaltet Reasoning **an**, wenn ``thinking`` fehlt — der Vision-Pfad lieferte
also genau das Rauschen, das er vermeiden will.

Mock-only — kein Netzwerk.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.utils.llm_client import LLMClient

_MINIMAX_URL = "https://api.minimax.io/v1"


class _FakeUsage:
    completion_tokens = 42


class _FakeMessage:
    content = "a plain description"


class _FakeChoice:
    message = _FakeMessage()


class _FakeResponse:
    choices = [_FakeChoice()]
    usage = _FakeUsage()


class _StableCompletions:
    """Gibt immer 200 zurueck und protokolliert die Request-Kwargs."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs: Any):
        self.calls.append(dict(kwargs))
        return _FakeResponse()


class _FakeChat:
    def __init__(self, completions) -> None:
        self.completions = completions


class _FakeOpenAI:
    def __init__(self, completions) -> None:
        self.chat = _FakeChat(completions)


def _fake_client(base_url: str, model: str) -> LLMClient:
    obj = LLMClient.__new__(LLMClient)
    obj._max_retries = 0
    obj._retry_initial_delay = 0.0
    obj._retry_max_delay = 0.0
    obj._num_ctx = 8192
    obj._think = False
    obj.api_key = "test-key"
    obj.base_url = base_url
    obj.model = model
    return obj


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kein VISION_MODEL_NAME-Override, kein Stream-/E2E-Modus."""
    monkeypatch.delenv("VISION_MODEL_NAME", raising=False)
    monkeypatch.setenv("LLM_FORCE_STREAM", "false")
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)


def test_describe_image_sends_disabled_thinking_to_minimax() -> None:
    """Vision-Call gegen api.minimax.io traegt {"thinking": {"type": "disabled"}}."""
    client = _fake_client(_MINIMAX_URL, "MiniMax-M3")
    completions = _StableCompletions()
    client.client = _FakeOpenAI(completions)

    content = client.describe_image(image_b64="aGVsbG8=", prompt="describe")

    assert content == "a plain description"
    assert len(completions.calls) == 1
    assert completions.calls[0].get("extra_body") == {
        "thinking": {"type": "disabled"}
    }


def test_describe_image_stays_extra_body_free_on_openai() -> None:
    """Nicht-MiniMax/Nicht-Ollama bleibt ohne extra_body — kein Over-Firing."""
    client = _fake_client("https://api.openai.com/v1", "gpt-4o")
    completions = _StableCompletions()
    client.client = _FakeOpenAI(completions)

    client.describe_image(image_b64="aGVsbG8=", prompt="describe")

    assert len(completions.calls) == 1
    assert "extra_body" not in completions.calls[0]


def test_describe_image_keeps_ollama_think_flag_false() -> None:
    """Ollama-Zweig unveraendert: think=False plus num_ctx-Boden."""
    client = _fake_client("http://localhost:11434/v1", "llava:13b")
    completions = _StableCompletions()
    client.client = _FakeOpenAI(completions)

    client.describe_image(image_b64="aGVsbG8=", prompt="describe")

    assert len(completions.calls) == 1
    extra_body = completions.calls[0].get("extra_body")
    assert extra_body is not None
    assert extra_body["think"] is False
