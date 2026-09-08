"""Regressionstest Slice B4a: Budget-Guard deckt den Tool-Call-Pfad ab.

Vor dem Fix rief ``_chat_with_tools`` (``LLMClient.chat_with_tools``)
``_budget_check()`` nirgends auf — ein erschoepftes Hard-Limit wurde
ignoriert und der Provider trotzdem angefragt. Dieser Test stellt sicher,
dass ein erschoepftes Budget dieselbe ``BudgetExceededError`` wirft wie der
Textpfad (``chat``/``chat_json``) und dass dabei KEIN Providercall
stattfindet.

Issue #1478 (Codex P1): ``_budget_check()`` reserviert einen In-Flight-Slot
VOR dem Providercall, aber weder der Erfolgs- noch der Exception-Pfad riefen
danach ``_budget_record()`` auf — die Reservierung blieb bis zum Ablauf der
900s-TTL bestehen UND zaehlte parallel im Ledger, der Call also doppelt. Die
beiden Tests unten decken die Freigabe auf beiden Ausgaengen ab.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm.client import LLMClient
from app.services.run_budget import BudgetExceededError


class _BlockingEnforcer:
    """Enforcer, der jeden Call sofort mit ``BudgetExceededError`` blockt."""

    def __init__(self, exc: BudgetExceededError) -> None:
        self.check_calls = 0
        self._exc = exc

    def check_before_call(self) -> None:
        self.check_calls += 1
        raise self._exc

    def record_after_call(self) -> None:  # pragma: no cover — darf nie laufen
        raise AssertionError(
            "record_after_call darf nicht laufen, wenn check_before_call blockt"
        )


class _RecordingEnforcer:
    """Enforcer, der jeden Call durchlaesst und Check/Record-Aufrufe zaehlt."""

    def __init__(self) -> None:
        self.check_calls = 0
        self.record_calls = 0

    def check_before_call(self) -> None:
        self.check_calls += 1

    def record_after_call(self) -> None:
        self.record_calls += 1


def _make_client(enforcer: object) -> LLMClient:
    """LLMClient ohne ``__init__`` mit bereits injiziertem Enforcer-Cache."""
    obj = LLMClient.__new__(LLMClient)
    obj.model = "test-model"
    obj.base_url = "http://localhost:11434/v1"
    obj.api_key = "test-key"
    obj._max_retries = 0
    obj._retry_initial_delay = 0.0
    obj._retry_max_delay = 0.0
    obj._num_ctx = 8192
    obj._think = False
    object.__setattr__(obj, "_budget_enforcer_cache", enforcer)
    return obj


class TestBudgetGuardToolCalls:
    def test_exhausted_budget_blocks_chat_with_tools_before_provider_call(
        self, monkeypatch
    ) -> None:
        exc = BudgetExceededError("calls", 11, 10)
        enforcer = _BlockingEnforcer(exc)
        client = _make_client(enforcer)

        monkeypatch.setattr(
            LLMClient, "_publish_model_active", lambda self, *a, **k: None
        )
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        # Provider deterministisch auf "ollama" zwingen, damit der echte
        # Tool-Call-Pfad genommen wird (kein unknown-Fallback auf chat()).
        object.__setattr__(client, "_is_ollama", lambda: True)
        object.__setattr__(client, "_is_minimax", lambda: False)
        object.__setattr__(client, "_detect_provider", lambda: "ollama")

        def _boom_create(**kwargs: object) -> None:
            raise AssertionError(
                "Provider-Call darf bei erschoepftem Budget nicht stattfinden"
            )

        object.__setattr__(
            client,
            "client",
            SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(create=_boom_create)
                )
            ),
        )

        with pytest.raises(BudgetExceededError) as info:
            client.chat_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                tools=[
                    {
                        "type": "function",
                        "function": {"name": "noop", "parameters": {}},
                    }
                ],
            )

        assert info.value is exc
        assert enforcer.check_calls == 1

    def test_successful_tool_call_releases_budget_reservation(
        self, monkeypatch
    ) -> None:
        """Issue #1478 (Codex P1): Erfolgreicher Call muss die Reservierung
        aus ``check_before_call()`` per ``record_after_call()`` freigeben —
        sonst zaehlt der Call doppelt (In-Flight-Reservierung + Ledger)."""
        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)

        monkeypatch.setattr(
            LLMClient, "_publish_model_active", lambda self, *a, **k: None
        )
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        object.__setattr__(client, "_is_ollama", lambda: False)
        object.__setattr__(client, "_is_minimax", lambda: False)
        object.__setattr__(client, "_detect_provider", lambda: "ollama")

        fake_message = SimpleNamespace(content="hi", tool_calls=None)
        fake_choice = SimpleNamespace(finish_reason="stop", message=fake_message)
        fake_response = SimpleNamespace(choices=[fake_choice])

        object.__setattr__(
            client,
            "client",
            SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(
                        create=lambda **kwargs: fake_response
                    )
                )
            ),
        )

        client.chat_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[
                {"type": "function", "function": {"name": "noop", "parameters": {}}}
            ],
        )

        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1

    def test_failed_tool_call_releases_budget_reservation(
        self, monkeypatch
    ) -> None:
        """Issue #1478 (Codex P1): Ein fehlgeschlagener Providerattempt muss
        dieselbe Reservierung ebenso freigeben — sonst haengt sie bis zur
        900s-TTL, statt den naechsten Call sofort wieder freizugeben."""
        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)

        monkeypatch.setattr(
            LLMClient, "_publish_model_active", lambda self, *a, **k: None
        )
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        object.__setattr__(client, "_is_ollama", lambda: False)
        object.__setattr__(client, "_is_minimax", lambda: False)
        object.__setattr__(client, "_detect_provider", lambda: "ollama")

        def _boom_create(**kwargs: object) -> None:
            raise RuntimeError("provider unavailable")

        object.__setattr__(
            client,
            "client",
            SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=_boom_create))
            ),
        )

        with pytest.raises(RuntimeError):
            client.chat_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                tools=[
                    {"type": "function", "function": {"name": "noop", "parameters": {}}}
                ],
            )

        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
