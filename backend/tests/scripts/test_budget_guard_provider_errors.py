"""Anbieterfehler im Simulations-Subprozess: HTTP-Status und Meldung (Issue #1772).

Im Lauf ``sim_c8c6b30aa652`` standen zu 872 ``RateLimitError`` nur
``Rate limit exhausted after 3 attempts`` und der Proxy-Objektname im Log; das
Call-Event trug ``http_status=None``. Diese Tests sichern, dass der Status im
Event landet und die gekürzte, von Schlüsseln bereinigte Anbietermeldung genau
einmal je Fehlerart und Minute geloggt wird.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sim_runtime.budget_guard import (  # noqa: E402
    FAILURE_MESSAGE_MAX_CHARS,
    SubprocessBudgetGuard,
)

RATE_LIMIT_MESSAGE = (
    "Rate limit reached for gpt-6-luna on tokens per min (TPM): "
    "Limit 2000000, Used 1990000, Requested 20000"
)


class RateLimitError(Exception):
    """Gleicher Klassenname wie ``openai.RateLimitError``; traegt ``status_code``."""

    def __init__(self, message: str, status_code: int | None = 429) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = {"message": message}


class _ResponseOnlyError(Exception):
    """Status nur ueber ``response.status_code`` (z. B. httpx-basierte Fehler)."""

    class _Response:
        status_code = 503

    response = _Response()


class _FailingModel:
    model_type = "fake"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def run(self, messages, *args, **kwargs):
        raise self._exc

    async def arun(self, messages, *args, **kwargs):
        raise self._exc


class _Clock:
    def __init__(self) -> None:
        self.now = 5000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def run_ledger(tmp_path, monkeypatch):
    run_dirs = tmp_path / "runs"
    run_dirs.mkdir()
    monkeypatch.setattr(
        "app.services.llm_invocation_logger.ArtifactLocator.run_dir",
        staticmethod(lambda run_id: str(run_dirs / run_id)),
    )
    monkeypatch.setenv("AGORA_RUN_ID", "run_sim_errors")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-6-luna")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com")
    return run_dirs / "run_sim_errors"


@pytest.fixture()
def guard_records():
    """Log-Records des Guard-Loggers direkt abgreifen (App-Logger propagieren nicht)."""
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    from app.utils.logger import get_logger

    target = get_logger("agora.sim_runtime.budget_guard")
    handler = _Collect(level=logging.DEBUG)
    previous_level = target.level
    target.addHandler(handler)
    target.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        target.removeHandler(handler)
        target.setLevel(previous_level)


def _events(run_ledger: Path) -> list[dict]:
    path = run_ledger / "llm_call_events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _failure_records(records: list[logging.LogRecord]) -> list[str]:
    return [r.getMessage() for r in records if "Anbieterfehler" in r.getMessage()]


def _guard(run_ledger: Path, clock: _Clock) -> SubprocessBudgetGuard:
    guard = SubprocessBudgetGuard(str(run_ledger), "run_sim_errors")
    guard._failure_log_clock = clock
    return guard


def _call_arun(proxy, times: int) -> None:
    async def scenario() -> None:
        for _ in range(times):
            with pytest.raises(Exception):  # noqa: B017 — Fake-Fehler, Klasse egal
                await proxy.arun([])

    asyncio.run(scenario())


class TestHttpStatusInCallEvent:
    def test_rate_limit_sets_http_status_429(self, run_ledger, guard_records):
        guard = _guard(run_ledger, _Clock())
        proxy = guard.wrap_model(_FailingModel(RateLimitError(RATE_LIMIT_MESSAGE)))

        _call_arun(proxy, 1)

        events = _events(run_ledger)
        assert len(events) == 1
        assert events[0]["success"] is False
        assert events[0]["error_type"] == "RateLimitError"
        assert events[0]["http_status"] == 429

    def test_status_from_response_attribute(self, run_ledger, guard_records):
        guard = _guard(run_ledger, _Clock())
        proxy = guard.wrap_model(_FailingModel(_ResponseOnlyError("upstream")))

        _call_arun(proxy, 1)

        assert _events(run_ledger)[0]["http_status"] == 503

    def test_sync_run_path_sets_http_status(self, run_ledger, guard_records):
        guard = _guard(run_ledger, _Clock())
        proxy = guard.wrap_model(_FailingModel(RateLimitError(RATE_LIMIT_MESSAGE)))

        with pytest.raises(RateLimitError):
            proxy.run([])

        assert _events(run_ledger)[0]["http_status"] == 429

    def test_error_without_status_keeps_http_status_none_and_does_not_log(
        self, run_ledger, guard_records
    ):
        guard = _guard(run_ledger, _Clock())
        proxy = guard.wrap_model(_FailingModel(RuntimeError("socket closed")))

        _call_arun(proxy, 1)

        event = _events(run_ledger)[0]
        assert event["error_type"] == "RuntimeError"
        assert event["http_status"] is None
        assert _failure_records(guard_records) == []


class TestThrottledProviderMessageLog:
    def test_three_errors_in_one_minute_log_the_message_once(self, run_ledger, guard_records):
        guard = _guard(run_ledger, _Clock())
        proxy = guard.wrap_model(_FailingModel(RateLimitError(RATE_LIMIT_MESSAGE)))

        _call_arun(proxy, 3)

        lines = _failure_records(guard_records)
        assert len(lines) == 1
        assert "Limit 2000000, Used 1990000, Requested 20000" in lines[0]
        assert "RateLimitError" in lines[0]
        assert "HTTP 429" in lines[0]
        assert len(_events(run_ledger)) == 3  # Events bleiben vollstaendig, je Aufruf eines

    def test_next_minute_logs_again_with_suppressed_count(self, run_ledger, guard_records):
        clock = _Clock()
        guard = _guard(run_ledger, clock)
        proxy = guard.wrap_model(_FailingModel(RateLimitError(RATE_LIMIT_MESSAGE)))

        _call_arun(proxy, 3)
        clock.now += 61
        _call_arun(proxy, 1)

        lines = _failure_records(guard_records)
        assert len(lines) == 2
        assert "0 gleichartige" in lines[0]
        assert "2 gleichartige" in lines[1]

    def test_other_status_is_a_separate_error_kind(self, run_ledger, guard_records):
        guard = _guard(run_ledger, _Clock())
        rate = guard.wrap_model(_FailingModel(RateLimitError(RATE_LIMIT_MESSAGE)))
        other = guard.wrap_model(_FailingModel(RateLimitError("Daily quota", status_code=403)))

        _call_arun(rate, 2)
        _call_arun(other, 2)

        assert len(_failure_records(guard_records)) == 2

    def test_message_is_truncated(self, run_ledger, guard_records):
        guard = _guard(run_ledger, _Clock())
        proxy = guard.wrap_model(_FailingModel(RateLimitError("x" * 2000)))

        _call_arun(proxy, 1)

        (line,) = _failure_records(guard_records)
        message_part = line.split("): ", 1)[1].split(" (", 1)[0]
        assert len(message_part) <= FAILURE_MESSAGE_MAX_CHARS
        assert message_part.endswith("…")


class TestNoSecretsInLog:
    def test_keys_in_provider_message_are_redacted(self, run_ledger, guard_records):
        # Zur Laufzeit zusammengesetzt, damit der Secret-Scan den erfundenen Wert nicht meldet.
        secret = "sk-" + "abcDEF" + "1234567890xyz"
        message = (
            f"Incorrect API key provided: {secret}. "
            "Authorization: Bearer tok.en-123456 api_key=hunter2hunter2"
        )
        guard = _guard(run_ledger, _Clock())
        proxy = guard.wrap_model(_FailingModel(RateLimitError(message, status_code=401)))

        _call_arun(proxy, 1)

        (line,) = _failure_records(guard_records)
        assert "sk-abc" not in line
        assert "tok.en-123456" not in line
        assert "hunter2hunter2" not in line
        assert "[redacted]" in line

    def test_prompt_and_headers_are_not_read(self, run_ledger, guard_records):
        class _Err(RateLimitError):
            request = type("R", (), {"headers": {"Authorization": "Bearer SECRET-HEADER"}})()
            messages = [{"role": "user", "content": "GEHEIMER PROMPT"}]

        guard = _guard(run_ledger, _Clock())
        proxy = guard.wrap_model(_FailingModel(_Err(RATE_LIMIT_MESSAGE)))

        _call_arun(proxy, 1)

        (line,) = _failure_records(guard_records)
        assert "SECRET-HEADER" not in line
        assert "GEHEIMER PROMPT" not in line
