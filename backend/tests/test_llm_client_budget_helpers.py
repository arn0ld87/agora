"""Tests fuer die Budget-Helper in LLMClient (Issue #764 Review).

Sicherstellen, dass interne Fehler der Budget-Enforcer den LLM-Aufruf
nicht blockieren, ``BudgetExceededError`` aber weiterhin propagiert.
Auch die Pfadabdeckung (Stub / nativer Ollama-Schema-Pfad) wird verifiziert.
"""
from __future__ import annotations

import pytest

from app.llm.client import LLMClient
from app.services.run_budget import BudgetExceededError


# ---------------------------------------------------------------------------
# Hilfsklassen
# ---------------------------------------------------------------------------


class _RecordingEnforcer:
    """Test-Double, der jeden Hook-Aufruf protokolliert."""

    def __init__(
        self,
        *,
        check_raises: BaseException | None = None,
        record_raises: BaseException | None = None,
    ) -> None:
        self.check_calls = 0
        self.record_calls = 0
        self.check_raises = check_raises
        self.record_raises = record_raises

    def check_before_call(self) -> None:
        self.check_calls += 1
        if self.check_raises is not None:
            raise self.check_raises

    def record_after_call(self) -> None:
        self.record_calls += 1
        if self.record_raises is not None:
            raise self.record_raises


def _make_client(enforcer: object | None) -> LLMClient:
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
    # Privater Cache wird per object.__setattr__ gesetzt — der Helper
    # liest ihn per ``getattr(..., '_budget_enforcer_cache', 'unset')``.
    object.__setattr__(obj, "_budget_enforcer_cache", enforcer)
    return obj


# ---------------------------------------------------------------------------
# 1. Hard-Limit: BudgetExceededError propagiert
# ---------------------------------------------------------------------------


class TestBudgetCheckHardLimit:
    def test_hard_limit_raises_budget_exceeded(self):
        exc = BudgetExceededError("calls", 11, 10)
        enforcer = _RecordingEnforcer(check_raises=exc)
        client = _make_client(enforcer)

        with pytest.raises(BudgetExceededError) as info:
            client._budget_check()

        assert info.value is exc
        assert enforcer.check_calls == 1


# ---------------------------------------------------------------------------
# 2. interner Fehler in ``check_before_call`` wird geloggt, blockiert nicht
# ---------------------------------------------------------------------------


class TestBudgetCheckInternalErrorSwallowed:
    def test_arbitrary_exception_does_not_propagate(self, monkeypatch):
        logged: list[str] = []
        monkeypatch.setattr(
            "app.llm.client.logger.warning", lambda *a, **k: logged.append(a[0] % a[1:])
        )
        enforcer = _RecordingEnforcer(check_raises=RuntimeError("ledger broken"))
        client = _make_client(enforcer)

        # Darf nicht durchschlagen — der LLM-Call soll weiterlaufen.
        client._budget_check()

        assert enforcer.check_calls == 1
        assert any("check_before_call failed" in m for m in logged)
        assert any("ledger broken" in m for m in logged)

    def test_io_error_does_not_propagate(self, monkeypatch):
        logged: list[str] = []
        monkeypatch.setattr(
            "app.llm.client.logger.warning", lambda *a, **k: logged.append(a[0] % a[1:])
        )
        enforcer = _RecordingEnforcer(check_raises=OSError("/tmp full"))
        client = _make_client(enforcer)

        client._budget_check()

        assert any("check_before_call failed" in m for m in logged)
        assert any("/tmp full" in m for m in logged)


# ---------------------------------------------------------------------------
# 3. interner Fehler in ``record_after_call`` wird geloggt, blockiert nicht
# ---------------------------------------------------------------------------


class TestBudgetRecordInternalErrorSwallowed:
    def test_arbitrary_exception_does_not_propagate(self, monkeypatch):
        logged: list[str] = []
        monkeypatch.setattr(
            "app.llm.client.logger.warning", lambda *a, **k: logged.append(a[0] % a[1:])
        )
        enforcer = _RecordingEnforcer(
            record_raises=ValueError("ledger schema mismatch")
        )
        client = _make_client(enforcer)

        client._budget_record()

        assert enforcer.record_calls == 1
        assert any("record_after_call failed" in m for m in logged)
        assert any("ledger schema mismatch" in m for m in logged)

    def test_os_error_does_not_propagate(self, monkeypatch):
        logged: list[str] = []
        monkeypatch.setattr(
            "app.llm.client.logger.warning", lambda *a, **k: logged.append(a[0] % a[1:])
        )
        enforcer = _RecordingEnforcer(record_raises=OSError("disk gone"))
        client = _make_client(enforcer)

        client._budget_record()

        assert any("record_after_call failed" in m for m in logged)
        assert any("disk gone" in m for m in logged)


# ---------------------------------------------------------------------------
# 4. Pfadabdeckung — ``chat_json`` Stub-Pfad
# ---------------------------------------------------------------------------


class TestChatJsonStubPath:
    def test_stub_path_uses_budget_helpers(self, monkeypatch):
        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)

        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")

        # Stub liefert ohne schema=None ein leeres JSON-Objekt.
        result = client.chat_json(
            messages=[{"role": "user", "content": "hi"}],
        )

        assert isinstance(result, dict)
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1


# ---------------------------------------------------------------------------
# 5. Pfadabdeckung — nativer Ollama-Schema-Pfad
# ---------------------------------------------------------------------------


class TestNativeOllamaSchemaPath:
    """Prufen, dass der native Ollama-Pfad ``_budget_record`` ruft."""

    def test_native_ollama_path_records_usage(self, monkeypatch):
        from pydantic import BaseModel

        class _Schema(BaseModel):
            ok: bool

        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)

        # Provider-Detection auf Ollama zwingen.
        object.__setattr__(
            client,
            "_is_ollama",
            lambda: True,
        )

        # ``_ollama_chat_with_schema`` gibt (response_str, usage_dict) zurueck.
        def _fake_ollama(
            messages, schema, temperature, max_tokens, force_no_thinking=False
        ):
            return '{"ok": true}', {"prompt_eval_count": 12, "eval_count": 7}

        object.__setattr__(client, "_ollama_chat_with_schema", _fake_ollama)

        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        parsed = client.chat_json(
            messages=[{"role": "user", "content": "ping"}],
            schema=_Schema,
        )

        assert parsed["ok"] is True
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1


# ---------------------------------------------------------------------------
# 6. ``_budget_enforcer`` ohne Run-ID ist No-Op
# ---------------------------------------------------------------------------


class TestBudgetEnforcerAbsent:
    def test_no_enforcer_is_silent_noop(self):
        client = _make_client(enforcer=None)

        # Darf weder raisen noch loggen.
        client._budget_check()
        client._budget_record()
