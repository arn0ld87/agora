"""Regression cover for #1572: gpt-6-Familie fehlte in der max_completion_tokens-/
temperature-Heuristik.

Ohne diese Heuristik-Erweiterung erzeugte jeder ``chat()``-Aufruf gegen
``gpt-6-luna`` vier HTTP-Requests statt eines: 400 ``max_tokens not
supported`` -> Key-Swap -> 400 ``temperature ... only the default (1)`` ->
Temperature-Drop -> 400 max_tokens -> Key-Swap -> Erfolg. Die Quirk-Netze in
``execute``/``chat()`` reparierten das jedes Mal live statt proaktiv im
ersten Request korrekt zu shapen.

Zwei Ebenen:
    (1) ``LLMClient.chat()``-Integration — genau EIN ``create()``-Call.
    (2) ``build_request()`` direkt — dieselbe Behauptung ohne HTTP-Mocking.
"""

from __future__ import annotations

from app.llm.request_plan import build_request
from app.utils.llm_client import LLMClient


# ---------------------------------------------------------------------------
# (1) LLMClient.chat() — genau ein Request, korrekt geshaped
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


def _fake_client() -> LLMClient:
    obj = LLMClient.__new__(LLMClient)
    obj._max_retries = 0
    obj._retry_initial_delay = 0.0
    obj._retry_max_delay = 0.0
    obj._num_ctx = 8192
    obj._think = False
    obj.api_key = "test"
    obj.base_url = "https://api.openai.com/v1"
    obj.model = "gpt-6-luna"
    return obj


def test_chat_shapes_gpt6_luna_correctly_on_first_attempt(monkeypatch) -> None:
    """gpt-6-luna braucht genau EINEN create()-Call, kein Quirk-Retry-Netz."""
    monkeypatch.setenv("LLM_FORCE_STREAM", "false")
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

    fake_client = _fake_client()
    completions = _StableCompletions()
    fake_client.client = _FakeOpenAI(completions)

    fake_client.chat(messages=[{"role": "user", "content": "hi"}], temperature=0.7)

    assert len(completions.calls) == 1, "gpt-6-luna darf keinen Quirk-Retry brauchen"
    call = completions.calls[0]
    assert "max_completion_tokens" in call
    assert "max_tokens" not in call
    assert "temperature" not in call


# ---------------------------------------------------------------------------
# (2) build_request() direkt — dieselbe Behauptung ohne HTTP-Mocking
# ---------------------------------------------------------------------------


def test_build_request_shapes_gpt6_luna_without_mocking() -> None:
    plan = build_request(
        model="gpt-6-luna",
        temperature=0.3,
        max_tokens=100,
        messages=[],
    )
    assert plan.kwargs["max_completion_tokens"] == 100
    assert "max_tokens" not in plan.kwargs
    assert "temperature" not in plan.kwargs
