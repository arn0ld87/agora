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
    def test_no_enforcer_is_silent_noop(self, monkeypatch):
        client = _make_client(enforcer=None)

        # logger.warning darf nicht aufgerufen werden — der No-Op-Pfad
        # soll still sein, weil weder ein Fehler noch eine Limitaus-
        # schoepfung vorliegt.
        logged: list[str] = []
        monkeypatch.setattr(
            "app.llm.client.logger.warning", lambda *a, **k: logged.append(a[0] % a[1:])
        )

        # Darf weder raisen noch loggen.
        client._budget_check()
        client._budget_record()

        assert logged == []


# ---------------------------------------------------------------------------
# 7. Regression Issue #764 (Codex P1): Genau EIN ``_budget_check`` pro
#    tatsaechlichem Providerrequest, auch ueber die Pfadteilung
#    ``chat_json`` -> ``chat``.
# ---------------------------------------------------------------------------


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
                "latency_ms": latency_ms,
                "success": success,
                "error_type": error_type,
                "http_status": http_status,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        )


def _wire_invocation_recorder(client: LLMClient) -> _InvocationRecorder:
    recorder = _InvocationRecorder()
    object.__setattr__(client, "_log_invocation_event", recorder)
    return recorder


def _make_ollama_client_with_enforcer(enforcer: object) -> LLMClient:
    client = _make_client(enforcer)
    object.__setattr__(client, "_is_ollama", lambda: True)
    return client


class TestChatJsonSingleBudgetCheckPerProvider:
    """Issue #764 (Codex P1): jeder physische Providerrequest erhaelt
    genau einen ``_budget_check`` und genau ein ``_log_invocation_event``."""

    def test_chat_json_delegates_to_chat_with_exactly_one_check(self, monkeypatch):
        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        # Ollama-Flag NICHT gesetzt -> OpenAI-kompatibler Pfad ueber chat().
        object.__setattr__(client, "_is_ollama", lambda: False)

        def _fake_ollama(*args, **kwargs):
            raise AssertionError("ollama path must not be entered")

        object.__setattr__(client, "_ollama_chat_with_schema", _fake_ollama)

        # chat() stubben, damit kein echter OpenAI-Client noetig ist. Der
        # Stub bildet den echten chat()-Budget-Pfad nach: jeder Provider-
        # aufruf erzeugt genau einen check + ein event + ein record.
        def _fake_chat(messages, temperature=0.7, max_tokens=4096, response_format=None,
                       context="chat", force_no_thinking=False, require_complete=False,
                       enforce_token_floor=True):
            client._budget_check()
            client._log_invocation_event(stage=context, latency_ms=10.0, success=True)
            client._budget_record()
            return '{}'

        object.__setattr__(client, "chat", _fake_chat)

        client.chat_json(messages=[{"role": "user", "content": "ping"}])

        # Genau ein Check + ein Record + ein Event — chat() uebernimmt
        # beides fuer den OpenAI-Pfad, chat_json() macht keinen Pre-Check.
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is True

    def test_e2e_stub_path_has_exactly_one_check_and_one_record(self, monkeypatch):
        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")

        result = client.chat_json(messages=[{"role": "user", "content": "hi"}])

        assert isinstance(result, dict)
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is True

    def test_native_ollama_success_has_exactly_one_check_event_record(self, monkeypatch):
        from pydantic import BaseModel

        class _Schema(BaseModel):
            ok: bool

        enforcer = _RecordingEnforcer()
        client = _make_ollama_client_with_enforcer(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        def _fake_ollama(messages, schema, temperature, max_tokens, force_no_thinking=False):
            return '{"ok": true}', {"prompt_eval_count": 4, "eval_count": 2}

        object.__setattr__(client, "_ollama_chat_with_schema", _fake_ollama)

        parsed = client.chat_json(messages=[{"role": "user", "content": "x"}], schema=_Schema)

        assert parsed["ok"] is True
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is True
        assert recorder.calls[0]["prompt_tokens"] == 4
        assert recorder.calls[0]["completion_tokens"] == 2

    def test_strict_schema_fallback_makes_two_requests_each_checked(self, monkeypatch):
        """Zwei reale Requests (Ollama + OpenAI-Fallback) → zwei Checks."""
        from pydantic import BaseModel

        class _Schema(BaseModel):
            ok: bool

        enforcer = _RecordingEnforcer()
        client = _make_ollama_client_with_enforcer(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        def _fake_ollama(messages, schema, temperature, max_tokens, force_no_thinking=False):
            raise RuntimeError("network down")

        object.__setattr__(client, "_ollama_chat_with_schema", _fake_ollama)

        # Erster ``chat()``-Call schlaegt fehl (strict json_schema unsupported),
        # zweiter ``chat()``-Call liefert das json_object-Fallback-Ergebnis.
        chat_calls = {"n": 0}

        def _fake_chat(messages, temperature=0.7, max_tokens=4096, response_format=None,
                       context="chat", force_no_thinking=False, require_complete=False,
                       enforce_token_floor=True):
            chat_calls["n"] += 1
            client._budget_check()
            if chat_calls["n"] == 1:
                # Erstversuch: Provider lehnt strict json_schema ab.
                client._log_invocation_event(
                    stage=context, latency_ms=10.0, success=False,
                    error_type="RuntimeError",
                )
                client._budget_record()
                raise RuntimeError("strict json_schema not supported here")
            client._log_invocation_event(stage=context, latency_ms=10.0, success=True)
            client._budget_record()
            return '{"ok": true}'

        object.__setattr__(client, "chat", _fake_chat)

        parsed = client.chat_json(messages=[{"role": "user", "content": "x"}], schema=_Schema)

        assert parsed["ok"] is True
        # Native Ollama (1) + Chat-Fallback-Versuch (1) + Chat-JSON-Object (1) = 3 Checks
        # Records: native Ollama fail (1) + erster Chat fail (1) + zweiter Chat OK (1) = 3
        # Events: native Ollama fail + erster Chat fail + zweiter Chat OK = 3
        assert enforcer.check_calls == 3
        assert enforcer.record_calls == 3
        assert len(recorder.calls) == 3
        # Erster Event muss der fehlgeschlagene native Ollama-Versuch sein.
        assert recorder.calls[0]["success"] is False
        assert recorder.calls[0]["error_type"] == "RuntimeError"
        # Letzter Event ist der erfolgreiche OpenAI-Fallback.
        assert recorder.calls[-1]["success"] is True


# ---------------------------------------------------------------------------
# 8. Regression Issue #764 (Codex P2): fehlgeschlagene Providerrequests
#    zaehlen als ein Call (usage_ledger + Budget), Parsing-Fehler NICHT.
# ---------------------------------------------------------------------------


class TestFailedRequestsCountAsProviderAttempts:
    def test_native_ollama_transport_fail_with_openai_success_records_two_events(self, monkeypatch):
        """Native Ollama schlaegt fehl → OpenAI-Fallback gelingt → 2 Events,
        erstes success=False, zweites success=True. Call-Budget steigt um 2."""
        from pydantic import BaseModel

        class _Schema(BaseModel):
            ok: bool

        enforcer = _RecordingEnforcer()
        client = _make_ollama_client_with_enforcer(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        def _fake_ollama(messages, schema, temperature, max_tokens, force_no_thinking=False):
            raise RuntimeError("provider 500")

        object.__setattr__(client, "_ollama_chat_with_schema", _fake_ollama)

        # Fake-Chat() bildet den echten chat()-Budget-Pfad nach: jeder
        # Provideraufruf erzeugt genau einen check + ein event + ein record.
        def _fake_chat(messages, temperature=0.7, max_tokens=4096, response_format=None,
                       context="chat", force_no_thinking=False, require_complete=False,
                       enforce_token_floor=True):
            client._budget_check()
            client._log_invocation_event(stage=context, latency_ms=10.0, success=True)
            client._budget_record()
            return '{"ok": true}'

        object.__setattr__(client, "chat", _fake_chat)

        parsed = client.chat_json(messages=[{"role": "user", "content": "x"}], schema=_Schema)

        assert parsed["ok"] is True
        # 1 Check (native Ollama) + 1 Check (OpenAI via chat) = 2
        assert enforcer.check_calls == 2
        # 1 Record (native Ollama fail) + 1 Record (OpenAI success) = 2
        assert enforcer.record_calls == 2
        assert len(recorder.calls) == 2
        assert recorder.calls[0]["success"] is False
        assert recorder.calls[0]["error_type"] == "RuntimeError"
        assert recorder.calls[1]["success"] is True

    def test_native_ollama_failure_without_fallback_counts_one_attempt(self, monkeypatch):
        """Native Ollama fail + Provider NICHT Ollama → OpenAI-Pfad geht durch,
        aber wir testen den Pfad, wo OpenAI selbst fehlschlaegt: 1 Event."""
        from pydantic import BaseModel

        class _Schema(BaseModel):
            ok: bool

        enforcer = _RecordingEnforcer()
        client = _make_ollama_client_with_enforcer(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        def _fake_ollama(messages, schema, temperature, max_tokens, force_no_thinking=False):
            raise RuntimeError("native fail")

        object.__setattr__(client, "_ollama_chat_with_schema", _fake_ollama)

        def _fake_chat(messages, temperature=0.7, max_tokens=4096, response_format=None,
                       context="chat", force_no_thinking=False, require_complete=False,
                       enforce_token_floor=True):
            client._budget_check()
            client._log_invocation_event(stage=context, latency_ms=10.0, success=False, error_type="RuntimeError")
            client._budget_record()
            raise RuntimeError("openai fail too")

        object.__setattr__(client, "chat", _fake_chat)

        with pytest.raises(RuntimeError, match="openai fail too"):
            client.chat_json(messages=[{"role": "user", "content": "x"}], schema=_Schema)

        # Native Ollama (1 check + 1 record + 1 event) + OpenAI (1 check + 1 record + 1 event) = 2/2/2
        assert enforcer.check_calls == 2
        assert enforcer.record_calls == 2
        assert len(recorder.calls) == 2
        assert all(call["success"] is False for call in recorder.calls)

    def test_native_ollama_truncation_reraises_without_fallback(self, monkeypatch):
        """LLMOutputTruncatedError: kein Fallback (gleiches Cap, kein
        zweiter Call), aber ein failed Event + record."""
        from pydantic import BaseModel
        from app.llm.client import LLMOutputTruncatedError

        class _Schema(BaseModel):
            ok: bool

        enforcer = _RecordingEnforcer()
        client = _make_ollama_client_with_enforcer(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        chat_called = {"n": 0}

        def _fake_chat(*args, **kwargs):
            chat_called["n"] += 1
            raise AssertionError("chat() must not be called for truncation")

        object.__setattr__(client, "chat", _fake_chat)

        def _fake_ollama(messages, schema, temperature, max_tokens, force_no_thinking=False):
            raise LLMOutputTruncatedError("truncated at cap")

        object.__setattr__(client, "_ollama_chat_with_schema", _fake_ollama)

        with pytest.raises(LLMOutputTruncatedError):
            client.chat_json(messages=[{"role": "user", "content": "x"}], schema=_Schema)

        assert chat_called["n"] == 0  # kein Fallback
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is False
        assert recorder.calls[0]["error_type"] == "LLMOutputTruncatedError"

    def test_json_parse_error_after_successful_response_counts_one_attempt(self, monkeypatch):
        """Provider liefert, aber JSON ist kaputt → 1 Event, kein zusaetzliches
        failed Event."""
        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        object.__setattr__(client, "_is_ollama", lambda: False)

        def _fake_chat(messages, temperature=0.7, max_tokens=4096, response_format=None,
                       context="chat", force_no_thinking=False, require_complete=False,
                       enforce_token_floor=True):
            client._budget_check()
            client._log_invocation_event(stage=context, latency_ms=10.0, success=True)
            client._budget_record()
            return "this is not json"

        object.__setattr__(client, "chat", _fake_chat)

        with pytest.raises(ValueError, match="Invalid JSON"):
            client.chat_json(messages=[{"role": "user", "content": "x"}])

        # 1 Check (chat) + 1 Record (chat) + 1 Event (success=True) — der Parse-Fehler
        # ist ein LOKALES Problem nach erfolgreicher Providerantwort und erzeugt
        # kein zusaetzliches Providerevent.
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is True

    def test_pydantic_validation_error_counts_one_attempt(self, monkeypatch):
        """Provider liefert valides JSON, aber Pydantic-Schema schlaegt fehl →
        1 Event."""
        from pydantic import BaseModel, ValidationError

        class _Schema(BaseModel):
            ok: bool

        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        object.__setattr__(client, "_is_ollama", lambda: False)

        def _fake_chat(messages, temperature=0.7, max_tokens=4096, response_format=None,
                       context="chat", force_no_thinking=False, require_complete=False,
                       enforce_token_floor=True):
            client._budget_check()
            client._log_invocation_event(stage=context, latency_ms=10.0, success=True)
            client._budget_record()
            return '{"not_ok": true}'

        object.__setattr__(client, "chat", _fake_chat)

        with pytest.raises(ValidationError):
            client.chat_json(
                messages=[{"role": "user", "content": "x"}], schema=_Schema
            )

        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1

    def test_hard_limit_blocks_fallback_after_failed_first_request(self, monkeypatch):
        """Bei ``max_llm_calls=1`` und fehlgeschlagenem ersten Request darf der
        zweite Fallback-Request NICHT stattfinden — der Enforcer blockt ihn."""
        from pydantic import BaseModel
        from app.services.run_budget import BudgetExceededError

        class _Schema(BaseModel):
            ok: bool

        # Pre-set-Check raises immer (simuliert max_llm_calls=1 erreicht).
        # Wir simulieren das Verhalten, indem der Enforcer ab dem zweiten
        # Aufruf BudgetExceededError wirft.
        call_count = {"n": 0}

        class _HardLimitEnforcer:
            def check_before_call(self) -> None:
                call_count["n"] += 1
                if call_count["n"] > 1:
                    raise BudgetExceededError("calls", 2, 1)

            def record_after_call(self) -> None:
                pass

        enforcer = _HardLimitEnforcer()
        client = _make_ollama_client_with_enforcer(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        def _fake_ollama(messages, schema, temperature, max_tokens, force_no_thinking=False):
            raise RuntimeError("native fail")

        object.__setattr__(client, "_ollama_chat_with_schema", _fake_ollama)

        chat_called = {"n": 0}

        def _fake_chat(messages, temperature=0.7, max_tokens=4096, response_format=None,
                       context="chat", force_no_thinking=False, require_complete=False,
                       enforce_token_floor=True):
            # Reihenfolge wie im echten chat(): Budget-Check VOR jedem
            # anderen Schritt. Wenn der Enforcer blockt, wird der Stub-
            # Body nie erreicht.
            client._budget_check()
            chat_called["n"] += 1
            return '{"ok": true}'

        object.__setattr__(client, "chat", _fake_chat)

        with pytest.raises(BudgetExceededError):
            client.chat_json(messages=[{"role": "user", "content": "x"}], schema=_Schema)

        # Native Ollama (Check #1 OK) → schlaegt fehl → record → OpenAI-Fallback
        # versucht Check #2 → BLOCKIERT durch Hard-Limit. Der Chat-Call wird
        # nie ausgefuehrt, weil der Hard-Limit bereits in ``check_before_call``
        # raiset (bevor der eigentliche Provider-Call startet).
        assert chat_called["n"] == 0
        assert call_count["n"] == 2  # beide Checks versucht, der zweite blockt
        # Events: 1 fuer native Ollama fail.
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is False


class TestChatExceptionPathRecordsBudget:
    """Issue #764 (Codex P2): ``chat()``-Exception-Pfad muss den fehlgeschlagenen
    Call in den weichen Budget-Limits zaehlen (``_budget_record`` aufrufen)."""

    def test_chat_failure_records_budget_and_logs_event(self, monkeypatch):
        from app.llm.client import LLMClient

        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        monkeypatch.setattr(LLMClient, "_publish_model_active", lambda self, *a, **k: None)

        # ``self.client.chat.completions.create`` stubben, der mit Exception antwortet.
        class _BoomClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        raise RuntimeError("provider 503")

        object.__setattr__(client, "client", _BoomClient)
        # Force den OpenAI-kompatiblen Pfad (kein Ollama).
        object.__setattr__(client, "_is_ollama", lambda: False)
        # Streaming-Pfad umgehen — wir wollen den nicht-streaming-Zweig.
        monkeypatch.setattr(
            "app.llm.client.os.environ.get", lambda k, default=None: "false" if k == "LLM_FORCE_STREAM" else default
        )

        with pytest.raises(RuntimeError, match="provider 503"):
            client.chat(messages=[{"role": "user", "content": "x"}])

        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1  # <-- der Fix: record auch im Failure-Pfad
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is False
        assert recorder.calls[0]["error_type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# 8b. Regression Issue #764 (Review-Restpunkt): HTTP-200-Antwort ohne
#     verarbeitbare ``choices`` muss EIN Failure-Event + EIN Budget-Record
#     erzeugen, KEIN zusaetzlicher Providerrequest, KEIN doppeltes Event.
# ---------------------------------------------------------------------------


class TestMalformedResponseLocalFailure:
    """Nach erfolgreichem ``create()`` kann die lokale Verarbeitung der
    Antwort fehlschlagen (leeres ``choices``, ``message`` ohne ``content``
    o.ae.). Der ``_provider_attempt`` hat den HTTP-Attempt bereits als
    Success geloggt — die Telemetrie fuer die anschliessende lokale
    Verarbeitung muss aber konsistent bleiben.
    """

    def test_http_200_without_choices_records_one_failure_event_and_one_record(
        self, monkeypatch
    ):
        from types import SimpleNamespace

        from app.llm.client import LLMClient

        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        monkeypatch.setattr(
            LLMClient, "_publish_model_active", lambda self, *a, **k: None
        )
        # Force den OpenAI-kompatiblen Pfad (kein Ollama).
        object.__setattr__(client, "_is_ollama", lambda: False)
        # Streaming-Pfad umgehen — wir wollen den nicht-streaming-Zweig.
        monkeypatch.setattr(
            "app.llm.client.os.environ.get",
            lambda k, default=None: "false" if k == "LLM_FORCE_STREAM" else default,
        )

        # HTTP 200-Antwort, aber ohne verarbeitbare ``choices``-Liste.
        malformed = SimpleNamespace(choices=[])

        create_calls = {"n": 0}

        def _create(**kwargs):
            create_calls["n"] += 1
            return malformed

        TestRetryAndFallbackTracking._install_create(client, _create)

        with pytest.raises(IndexError):
            client.chat(messages=[{"role": "user", "content": "x"}])

        # Genau ein Providerrequest — kein Retry nach lokalem Fehler.
        assert create_calls["n"] == 1
        # Genau ein Budgetcheck (im ``_provider_attempt`` VOR ``create()``).
        assert enforcer.check_calls == 1
        # Genau ein Budgetrecord nach lokalem Fehler (der Fix).
        assert enforcer.record_calls == 1
        # Genau ein Failure-Event, success=False — KEIN Success-Event daneben.
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is False
        assert recorder.calls[0]["error_type"] == "IndexError"

    def test_malformed_response_keeps_reported_usage_in_failure_event(
        self, monkeypatch
    ):
        """Codex P2: abgerechnete Tokens duerfen beim lokalen Fehler nicht verloren gehen.

        ``run_usage_ledger._Bucket.add`` leitet Verbrauch und Kosten allein aus
        den Event-Feldern ab. Traegt das Failure-Event keine Tokenzahlen, ist
        der Call zwar gezaehlt, sein Verbrauch aber unbekannt — harte Token-
        und Kostenlimits lassen dann zu viele Folgecalls durch.
        """
        from types import SimpleNamespace

        from app.llm.client import LLMClient

        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        monkeypatch.setattr(
            LLMClient, "_publish_model_active", lambda self, *a, **k: None
        )
        object.__setattr__(client, "_is_ollama", lambda: False)
        monkeypatch.setattr(
            "app.llm.client.os.environ.get",
            lambda k, default=None: "false" if k == "LLM_FORCE_STREAM" else default,
        )

        # Leeres ``choices``, aber der Provider hat abgerechnet.
        malformed = SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(prompt_tokens=1200, completion_tokens=340),
        )
        TestRetryAndFallbackTracking._install_create(client, lambda **kw: malformed)

        with pytest.raises(IndexError):
            client.chat(messages=[{"role": "user", "content": "x"}])

        assert len(recorder.calls) == 1
        event = recorder.calls[0]
        assert event["success"] is False
        assert event["prompt_tokens"] == 1200
        assert event["completion_tokens"] == 340

    def test_non_numeric_usage_does_not_leak_into_failure_event(self, monkeypatch):
        """Nicht-numerische Providerwerte bleiben None statt als Tokenzahl zu zaehlen."""
        from types import SimpleNamespace

        from app.llm.client import LLMClient

        enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        recorder = _wire_invocation_recorder(client)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        monkeypatch.setattr(
            LLMClient, "_publish_model_active", lambda self, *a, **k: None
        )
        object.__setattr__(client, "_is_ollama", lambda: False)
        monkeypatch.setattr(
            "app.llm.client.os.environ.get",
            lambda k, default=None: "false" if k == "LLM_FORCE_STREAM" else default,
        )

        malformed = SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(prompt_tokens="n/a", completion_tokens=None),
        )
        TestRetryAndFallbackTracking._install_create(client, lambda **kw: malformed)

        with pytest.raises(IndexError):
            client.chat(messages=[{"role": "user", "content": "x"}])

        event = recorder.calls[0]
        assert event["prompt_tokens"] is None
        assert event["completion_tokens"] is None


# ---------------------------------------------------------------------------
# 9. Retry- und Fallback-Tracking (Issue #764, letzter Review-Punkt):
#    Jeder tatsaechliche Providerrequest (Initial, Retry, Token-Key-Fallback,
#    Streaming) erhaelt GENAU EINE ``_budget_check`` / ``_log_invocation_event``
#    / ``_budget_record``-Triplet.
# ---------------------------------------------------------------------------


class TestRetryAndFallbackTracking:
    """Issue #764 (letzter Review-Punkt): jede echte HTTP-Anfrage beim Provider
    wird als EIN Providerattempt gezaehlt — unabhaengig davon, ob sie aus
    dem ersten Call, einem Retry oder dem Token-Key-Fallback stammt."""

    @staticmethod
    def _make_transient_503() -> Exception:
        """APIStatusError mit 503 -> retry faehig (transient)."""
        import httpx
        from openai import APIStatusError

        req = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
        resp = httpx.Response(503, request=req)
        return APIStatusError("upstream 503", response=resp, body=None)

    @staticmethod
    def _make_token_key_400() -> Exception:
        """APIStatusError mit 400 + max_tokens-Hinweis -> Token-Key-Fallback."""
        import httpx
        from openai import APIStatusError

        req = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
        resp = httpx.Response(400, request=req)
        return APIStatusError(
            "'max_tokens' is not supported with this model. "
            "Use 'max_completion_tokens' instead.",
            response=resp,
            body=None,
        )

    @staticmethod
    def _make_response(content: str = "ok", prompt_tokens: int = 10, completion_tokens: int = 5):
        from types import SimpleNamespace

        usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason="stop",
                )
            ],
            usage=usage,
        )

    def _setup_client(self, *, max_retries: int = 0, is_ollama: bool = False, enforcer=None):
        if enforcer is None:
            enforcer = _RecordingEnforcer()
        client = _make_client(enforcer)
        client._max_retries = max_retries
        object.__setattr__(client, "_is_ollama", lambda: is_ollama)
        return client, enforcer

    @staticmethod
    def _install_create(client: LLMClient, create_fn):
        """Hängt ``create_fn`` als ``self.client.chat.completions.create`` ein."""
        from types import SimpleNamespace

        object.__setattr__(
            client,
            "client",
            SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=create_fn))
            ),
        )

    # -- 1. erster Request schlaegt fehl, zweiter Retry erfolgreich ----------
    def test_first_attempt_fails_retry_succeeds_two_provider_attempts(self, monkeypatch):
        """Szenario 1: transient-503 beim ersten Versuch, OK beim zweiten.
        Erwartung: 2 Checks, 2 Events, 2 Records."""
        monkeypatch.setattr("time.sleep", lambda _s: None)  # Retry-Backoff neutralisieren
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        monkeypatch.setattr(
            "app.llm.client.os.environ.get",
            lambda k, default=None: "false" if k == "LLM_FORCE_STREAM" else default,
        )

        enforcer = _RecordingEnforcer()
        client, _ = self._setup_client(max_retries=1, is_ollama=False, enforcer=enforcer)
        recorder = _wire_invocation_recorder(client)

        attempts = {"n": 0}
        success_response = self._make_response("retry wins")

        def _create(**kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise self._make_transient_503()
            return success_response

        self._install_create(client, _create)

        result = client.chat(messages=[{"role": "user", "content": "x"}])

        assert result == "retry wins"
        assert attempts["n"] == 2  # zwei echte Providerrequests
        assert enforcer.check_calls == 2
        assert enforcer.record_calls == 2
        assert len(recorder.calls) == 2
        assert recorder.calls[0]["success"] is False
        assert recorder.calls[0]["error_type"] == "APIStatusError"
        assert recorder.calls[1]["success"] is True
        assert recorder.calls[1]["prompt_tokens"] == 10
        assert recorder.calls[1]["completion_tokens"] == 5

    # -- 2. mehrere Retries schlagen alle fehl ------------------------------
    def test_multiple_retries_each_count_as_separate_attempt(self, monkeypatch):
        """Szenario 2: alle Retries werfen transient-503.
        Erwartung: 1 Event pro tatsaechlichem Request."""
        monkeypatch.setattr("time.sleep", lambda _s: None)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        monkeypatch.setattr(
            "app.llm.client.os.environ.get",
            lambda k, default=None: "false" if k == "LLM_FORCE_STREAM" else default,
        )

        enforcer = _RecordingEnforcer()
        client, _ = self._setup_client(max_retries=2, is_ollama=False, enforcer=enforcer)
        recorder = _wire_invocation_recorder(client)

        attempts = {"n": 0}

        def _create(**kwargs):
            attempts["n"] += 1
            raise self._make_transient_503()

        self._install_create(client, _create)

        with pytest.raises(Exception, match="upstream 503"):
            client.chat(messages=[{"role": "user", "content": "x"}])

        # max_retries=2 -> 3 Versuche (initial + 2 Retries).
        assert attempts["n"] == 3
        assert enforcer.check_calls == 3
        assert enforcer.record_calls == 3
        assert len(recorder.calls) == 3
        assert all(call["success"] is False for call in recorder.calls)
        assert all(call["error_type"] == "APIStatusError" for call in recorder.calls)

    # -- 3. HTTP-400 Token-Key, 2. Request erfolgreich -----------------------
    def test_http_400_token_key_fallback_two_provider_attempts(self, monkeypatch):
        """Szenario 3: 400 wegen max_tokens/max_completion_tokens-Inkompatibilitaet,
        Fallback gelingt. Erwartung: 2 Checks, 2 Events, 2 Records.
        Zusaetzlich: erst Call hat max_tokens, zweiter max_completion_tokens."""
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        monkeypatch.setattr(
            "app.llm.client.os.environ.get",
            lambda k, default=None: "false" if k == "LLM_FORCE_STREAM" else default,
        )

        enforcer = _RecordingEnforcer()
        client, _ = self._setup_client(max_retries=0, is_ollama=False, enforcer=enforcer)
        recorder = _wire_invocation_recorder(client)

        attempts = {"n": 0}
        attempts_kwargs: list[dict[str, object]] = []
        success_response = self._make_response("fallback wins")

        def _create(**kwargs):
            attempts["n"] += 1
            attempts_kwargs.append(dict(kwargs))
            if attempts["n"] == 1:
                raise self._make_token_key_400()
            return success_response

        self._install_create(client, _create)

        result = client.chat(messages=[{"role": "user", "content": "x"}])

        assert result == "fallback wins"
        assert attempts["n"] == 2
        # Erst Call verwendet max_tokens, Fallback verwendet max_completion_tokens.
        assert "max_tokens" in attempts_kwargs[0]
        assert "max_completion_tokens" not in attempts_kwargs[0]
        assert "max_completion_tokens" in attempts_kwargs[1]
        assert "max_tokens" not in attempts_kwargs[1]
        assert enforcer.check_calls == 2
        assert enforcer.record_calls == 2
        assert len(recorder.calls) == 2
        assert recorder.calls[0]["success"] is False
        assert recorder.calls[0]["http_status"] == 400
        assert recorder.calls[1]["success"] is True

    # -- 4. hartes Limit mitten in einer Retry-Serie -------------------------
    def test_hard_limit_during_retry_blocks_further_provider_requests(self, monkeypatch):
        """Szenario 4: nach dem ersten fehlgeschlagenen Versuch wirft der
        Enforcer BudgetExceededError. Es darf KEIN weiterer Providerrequest
        stattfinden."""
        monkeypatch.setattr("time.sleep", lambda _s: None)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        monkeypatch.setattr(
            "app.llm.client.os.environ.get",
            lambda k, default=None: "false" if k == "LLM_FORCE_STREAM" else default,
        )

        check_count = {"n": 0}

        class _HardLimitEnforcer:
            def check_before_call(self) -> None:
                check_count["n"] += 1
                if check_count["n"] > 1:
                    raise BudgetExceededError("calls", 2, 1)

            def record_after_call(self) -> None:
                pass

        enforcer = _HardLimitEnforcer()
        client, _ = self._setup_client(
            max_retries=3, is_ollama=False, enforcer=enforcer
        )
        recorder = _wire_invocation_recorder(client)

        create_calls = {"n": 0}

        def _create(**kwargs):
            create_calls["n"] += 1
            raise self._make_transient_503()

        self._install_create(client, _create)

        with pytest.raises(BudgetExceededError):
            client.chat(messages=[{"role": "user", "content": "x"}])

        # Genau EIN realer Providerrequest — der zweite Check blockt VOR create().
        assert create_calls["n"] == 1
        # Beide Checks wurden versucht: 1. OK, 2. blockt mit BudgetExceededError.
        assert check_count["n"] == 2
        # Genau ein failed Event + ein Record (vom ersten, tatsaechlich
        # ausgefuehrten Versuch).
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is False

    # -- 5. normaler erfolgreicher Request -----------------------------------
    def test_normal_success_counts_exactly_one_provider_attempt(self, monkeypatch):
        """Szenario 5: einfacher Erfolg ohne Retries/Fallback.
        Erwartung: genau 1 Check, 1 Event, 1 Record."""
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        monkeypatch.setattr(
            "app.llm.client.os.environ.get",
            lambda k, default=None: "false" if k == "LLM_FORCE_STREAM" else default,
        )

        enforcer = _RecordingEnforcer()
        client, _ = self._setup_client(max_retries=0, is_ollama=False, enforcer=enforcer)
        recorder = _wire_invocation_recorder(client)

        success_response = self._make_response("plain ok")

        def _create(**kwargs):
            return success_response

        self._install_create(client, _create)

        result = client.chat(messages=[{"role": "user", "content": "x"}])

        assert result == "plain ok"
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is True
        assert recorder.calls[0]["prompt_tokens"] == 10
        assert recorder.calls[0]["completion_tokens"] == 5

    # -- 6. Streaming-Erfolg -------------------------------------------------
    def test_streaming_success_counts_exactly_one_provider_attempt(self, monkeypatch):
        """Szenario 6: Streaming wird vollstaendig durchlaufen, Usage kommt
        aus dem letzten Chunk. Erwartung: genau ein Providerattempt."""
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        # LLM_FORCE_STREAM per Default "true" fuer Ollama-Pfad.
        monkeypatch.setattr(
            "app.llm.client.os.environ.get",
            lambda k, default=None: "true" if k == "LLM_FORCE_STREAM" else default,
        )

        enforcer = _RecordingEnforcer()
        client, _ = self._setup_client(max_retries=0, is_ollama=True, enforcer=enforcer)
        recorder = _wire_invocation_recorder(client)

        from types import SimpleNamespace

        def _stream_iter():
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="hello "),
                        finish_reason=None,
                    )
                ],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="world"),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=2),
            )

        def _create(**kwargs):
            assert kwargs.get("stream") is True
            return _stream_iter()

        self._install_create(client, _create)

        result = client.chat(messages=[{"role": "user", "content": "x"}])

        assert result == "hello world"
        assert enforcer.check_calls == 1
        assert enforcer.record_calls == 1
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["success"] is True
        assert recorder.calls[0]["prompt_tokens"] == 2
        assert recorder.calls[0]["completion_tokens"] == 2
