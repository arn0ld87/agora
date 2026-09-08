"""Regressionstest Slice B4b: Budget-Guard und Ledger decken den Vision-Pfad ab.

Vor dem Fix rief ``describe_image`` (bzw. sein interner ``_create_vision``-
Provider-Call) weder ``_budget_check()`` noch ``_log_invocation_event``/
``_budget_record()`` auf — Vision-Aufrufe waren fuer Budget-Guard und Ledger
vollstaendig unsichtbar, unabhaengig vom Ausgang des Calls.

Issue #1478 (Codex P1): der Guard sass ausserdem auf der falschen Ebene — er
umschloss die gesamte ``execute()``-Operation statt jeden physischen
Provider-Request. Ein wiederholter Versuch (transient retry,
``TOKEN_KEY_QUIRK``) erzeugte dadurch nur EINEN Budget-Check/Event/Record,
obwohl mehrere physische Requests abgesetzt wurden — ``max_llm_calls=1``
erlaubte damit mehrere abgerechnete Requests und das Ledger zaehlte zu
niedrig. ``TestBudgetGuardVisionRetry`` deckt das mit einem echten Retry ab.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.llm.client import LLMClient
from app.services.run_budget import BudgetExceededError


class _RecordingEnforcer:
    """Test-Double, der jeden Hook-Aufruf protokolliert."""

    def __init__(self, *, check_raises: BaseException | None = None) -> None:
        self.check_calls = 0
        self.record_calls = 0
        self.check_raises = check_raises

    def check_before_call(self) -> None:
        self.check_calls += 1
        if self.check_raises is not None:
            raise self.check_raises

    def record_after_call(self) -> None:
        self.record_calls += 1


def _make_client(enforcer: object) -> LLMClient:
    """LLMClient ohne ``__init__`` mit bereits injiziertem Enforcer-Cache."""
    obj = LLMClient.__new__(LLMClient)
    obj.model = "vision-model"
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
    """Zeichnet Aufrufe von ``_log_invocation_event`` auf."""

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


def _wire_provider(client: LLMClient, create_fn) -> None:
    object.__setattr__(client, "_is_ollama", lambda: False)
    object.__setattr__(client, "_is_minimax", lambda: False)
    object.__setattr__(
        client,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_fn))),
    )


class TestBudgetGuardVisionBlocks:
    def test_exhausted_budget_blocks_describe_image_before_provider_call(
        self, monkeypatch
    ) -> None:
        exc = BudgetExceededError("calls", 11, 10)
        enforcer = _RecordingEnforcer(check_raises=exc)
        client = _make_client(enforcer)
        recorder = _wire_invocation_recorder(client)

        def _boom_create(**kwargs: object) -> None:
            raise AssertionError(
                "Provider-Call darf bei erschoepftem Budget nicht stattfinden"
            )

        _wire_provider(client, _boom_create)

        with pytest.raises(BudgetExceededError) as info:
            client.describe_image(image_b64="Zm9v", prompt="Was zeigt das Bild?")

        assert info.value is exc
        assert enforcer.check_calls == 1
        # Blockiert VOR dem Call -> kein Event, kein Record (analog zu
        # ``_provider_attempt`` im Textpfad).
        assert recorder.calls == []
        assert enforcer.record_calls == 0


class TestVisionLedgerBooking:
    """Slice B4b: erfolgreiche und fehlgeschlagene Vision-Calls landen im Ledger."""

    def test_successful_vision_call_is_logged_and_budget_recorded(
        self, monkeypatch
    ) -> None:
        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        recorder = _wire_invocation_recorder(client)

        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Eine Katze."))],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=8),
        )
        _wire_provider(client, lambda **kwargs: response)

        result = client.describe_image(image_b64="Zm9v", prompt="Was zeigt das Bild?")

        assert result == "Eine Katze."
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["stage"] == "vision"
        assert recorder.calls[0]["success"] is True
        assert recorder.calls[0]["prompt_tokens"] == 120
        assert recorder.calls[0]["completion_tokens"] == 8

    def test_failed_vision_call_logs_failure_event_and_records_budget(
        self, monkeypatch
    ) -> None:
        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        recorder = _wire_invocation_recorder(client)

        def _boom(**kwargs: object) -> None:
            raise RuntimeError("provider 503")

        _wire_provider(client, _boom)

        with pytest.raises(RuntimeError, match="provider 503"):
            client.describe_image(image_b64="Zm9v", prompt="Was zeigt das Bild?")

        # Fehlgeschlagener Vision-Call zaehlt trotzdem als Providerattempt —
        # Event + Record duerfen nicht ausbleiben, sonst unterlaeuft der Call
        # das weiche Budget-Limit.
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["stage"] == "vision"
        assert recorder.calls[0]["success"] is False
        assert recorder.calls[0]["error_type"] == "RuntimeError"


class TestBudgetGuardVisionRetry:
    """Issue #1478 (Codex P1): der Guard-Lebenszyklus laeuft pro physischem
    Providerattempt, nicht einmal um die gesamte Operation — ein Retry muss
    deshalb ZWEI Budget-Checks/Records und ZWEI Invocation-Events erzeugen."""

    def test_transient_retry_produces_two_budget_checks_and_events(
        self, monkeypatch
    ) -> None:
        from openai import APIConnectionError

        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        # max_retries=1 statt 0 (Default in _make_client) — genau EIN
        # Neuversuch nach dem ersten transienten Fehlschlag.
        object.__setattr__(client, "_max_retries", 1)
        recorder = _wire_invocation_recorder(client)

        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Ein Hund."))],
            usage=SimpleNamespace(prompt_tokens=50, completion_tokens=4),
        )

        attempts = {"count": 0}

        def _flaky_create(**kwargs: object) -> object:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise APIConnectionError(request=MagicMock())
            return response

        _wire_provider(client, _flaky_create)

        result = client.describe_image(image_b64="Zm9v", prompt="Was zeigt das Bild?")

        assert result == "Ein Hund."
        assert attempts["count"] == 2
        # Vor dem Fix: EIN Check/Record fuer beide physischen Requests
        # zusammen. Nach dem Fix: einer pro Attempt.
        assert enforcer.check_calls == 2
        assert enforcer.record_calls == 2
        assert len(recorder.calls) == 2
        assert recorder.calls[0]["success"] is False
        assert recorder.calls[0]["stage"] == "vision"
        assert recorder.calls[1]["success"] is True
        assert recorder.calls[1]["stage"] == "vision"
