"""Regressionstest Slice B4a: Budget-Guard deckt den Tool-Call-Pfad ab.

Vor dem Fix rief ``_chat_with_tools`` (``LLMClient.chat_with_tools``)
``_budget_check()`` nirgends auf — ein erschoepftes Hard-Limit wurde
ignoriert und der Provider trotzdem angefragt. Dieser Test stellt sicher,
dass ein erschoepftes Budget dieselbe ``BudgetExceededError`` wirft wie der
Textpfad (``chat``/``chat_json``) und dass dabei KEIN Providercall
stattfindet.
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
