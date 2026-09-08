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

Issue #1478 (Codex P1, Runde 3): der Guard sass danach immer noch auf der
falschen Ebene — ein einzelner ``_budget_check()`` deckte die gesamte
logische Operation ab statt jeden physischen Providerrequest. Ein transienter
Retry oder eine Quirk-Korrektur erzeugte dadurch nur EINEN Budget-Check trotz
mehrerer physischer Requests, und erfolgreiche native Tool-Calls trugen keine
Usage-Daten ins Ledger (``_log_invocation_event`` bekam nie prompt_tokens/
completion_tokens). ``TestBudgetGuardToolCallsRetry``,
``TestBudgetGuardToolCallsQuirk`` und ``TestToolCallsLedgerBooking`` decken
das ab.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

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


class _InvocationRecorder:
    """Zeichnet Aufrufe von ``_log_invocation_event`` auf (Kopie aus
    ``test_budget_guard_vision.py`` — je Testmodul sein eigenes Test-Double,
    kein Cross-Import zwischen Testdateien)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        *,
        stage: str,
        latency_ms: float,
        success: bool,
        error_type: object = None,
        http_status: object = None,
        remote_request_id: object = None,
        prompt_tokens: object = None,
        completion_tokens: object = None,
    ) -> None:
        self.calls.append(
            {
                "stage": stage,
                "success": success,
                "error_type": error_type,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        )


def _wire_invocation_recorder(client: LLMClient) -> _InvocationRecorder:
    recorder = _InvocationRecorder()
    object.__setattr__(client, "_log_invocation_event", recorder)
    return recorder


def _wire_provider(client: LLMClient, create_fn, *, is_ollama: bool = False) -> None:
    object.__setattr__(client, "_is_ollama", lambda: is_ollama)
    object.__setattr__(client, "_is_minimax", lambda: False)
    object.__setattr__(client, "_detect_provider", lambda: "ollama")
    object.__setattr__(
        client,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_fn))),
    )


def _tools_payload() -> list[dict]:
    return [{"type": "function", "function": {"name": "noop", "parameters": {}}}]


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


class TestBudgetGuardToolCallsRetry:
    """Issue #1478 (Codex P1, Runde 3): der Guard-Lebenszyklus laeuft pro
    physischem Providerattempt, nicht einmal um die gesamte logische
    Operation — ein transienter Retry muss deshalb ZWEI Budget-Checks/Records
    und ZWEI Invocation-Events erzeugen (analog zu
    ``TestBudgetGuardVisionRetry`` im Vision-Pfad)."""

    def test_transient_retry_produces_two_budget_checks_and_events(
        self, monkeypatch
    ) -> None:
        from openai import APIConnectionError

        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        # Genau EIN Neuversuch nach dem ersten transienten Fehlschlag.
        object.__setattr__(client, "_max_retries", 1)
        monkeypatch.setattr(
            LLMClient, "_publish_model_active", lambda self, *a, **k: None
        )
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        recorder = _wire_invocation_recorder(client)

        fake_message = SimpleNamespace(content="ok", tool_calls=None)
        fake_choice = SimpleNamespace(finish_reason="stop", message=fake_message)
        fake_response = SimpleNamespace(
            choices=[fake_choice],
            usage=SimpleNamespace(prompt_tokens=30, completion_tokens=5),
        )

        attempts = {"count": 0}

        def _flaky_create(**kwargs: object) -> object:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise APIConnectionError(request=MagicMock())
            return fake_response

        _wire_provider(client, _flaky_create, is_ollama=False)

        result = client.chat_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=_tools_payload(),
        )

        assert result["content"] == "ok"
        assert attempts["count"] == 2
        # Vor dem Fix: EIN Check/Record fuer beide physischen Requests
        # zusammen. Nach dem Fix: einer pro Attempt.
        assert enforcer.check_calls == 2
        assert enforcer.record_calls == 2
        assert len(recorder.calls) == 2
        assert recorder.calls[0]["success"] is False
        assert recorder.calls[1]["success"] is True
        assert recorder.calls[1]["prompt_tokens"] == 30
        assert recorder.calls[1]["completion_tokens"] == 5


class TestBudgetGuardToolCallsQuirk:
    """Issue #1478 (Codex P1, Runde 3): auch eine Quirk-Korrektur
    (``TOKEN_KEY_QUIRK``/``TEMPERATURE_QUIRK``) setzt einen zweiten
    physischen Request ab — anders als der Vision-Pfad kennt der Tool-Pfad
    beide Quirks (temperature-Quirk aus #1096), deshalb ein eigener Test."""

    def test_token_key_quirk_produces_two_budget_checks_and_events(
        self, monkeypatch
    ) -> None:
        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        monkeypatch.setattr(
            LLMClient, "_publish_model_active", lambda self, *a, **k: None
        )
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        recorder = _wire_invocation_recorder(client)

        fake_message = SimpleNamespace(content="ok", tool_calls=None)
        fake_choice = SimpleNamespace(finish_reason="stop", message=fake_message)
        fake_response = SimpleNamespace(
            choices=[fake_choice],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3),
        )

        attempts = {"count": 0}

        def _create_with_token_key_400(**kwargs: object) -> object:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise Exception(
                    "Error code: 400 - 'max_tokens' is not supported with "
                    "this model. Use 'max_completion_tokens' instead."
                )
            return fake_response

        _wire_provider(client, _create_with_token_key_400, is_ollama=False)

        result = client.chat_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=_tools_payload(),
        )

        assert result["content"] == "ok"
        assert attempts["count"] == 2
        assert enforcer.check_calls == 2
        assert enforcer.record_calls == 2
        assert len(recorder.calls) == 2
        assert recorder.calls[0]["success"] is False
        assert recorder.calls[1]["success"] is True


class TestToolCallsLedgerBooking:
    """Issue #1478 (Codex P1, Runde 3): erfolgreiche native Tool-Calls
    landen mit ihren Tokens im Usage-Ledger statt als "token-unknown"."""

    def test_non_streaming_usage_reaches_ledger(self, monkeypatch) -> None:
        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        monkeypatch.setattr(
            LLMClient, "_publish_model_active", lambda self, *a, **k: None
        )
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        recorder = _wire_invocation_recorder(client)

        fake_message = SimpleNamespace(content="ok", tool_calls=None)
        fake_choice = SimpleNamespace(finish_reason="stop", message=fake_message)
        fake_response = SimpleNamespace(
            choices=[fake_choice],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=8),
        )

        _wire_provider(client, lambda **kwargs: fake_response, is_ollama=False)

        client.chat_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=_tools_payload(),
        )

        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is True
        assert recorder.calls[0]["prompt_tokens"] == 120
        assert recorder.calls[0]["completion_tokens"] == 8

    def test_streaming_usage_reaches_ledger(self, monkeypatch) -> None:
        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        monkeypatch.setattr(
            LLMClient, "_publish_model_active", lambda self, *a, **k: None
        )
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        monkeypatch.setenv("LLM_FORCE_STREAM", "true")
        recorder = _wire_invocation_recorder(client)

        content_chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason=None,
                    delta=SimpleNamespace(content="hi", tool_calls=None),
                )
            ],
            usage=None,
        )
        final_chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    delta=SimpleNamespace(content=None, tool_calls=None),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=50, completion_tokens=4),
        )

        _wire_provider(
            client,
            lambda **kwargs: iter([content_chunk, final_chunk]),
            is_ollama=True,
        )

        result = client.chat_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=_tools_payload(),
        )

        assert result["content"] == "hi"
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is True
        assert recorder.calls[0]["prompt_tokens"] == 50
        assert recorder.calls[0]["completion_tokens"] == 4
