"""Nicht-transienter Provider-400 bricht die Section-Generierung früh ab (#1738).

Vorher wiederholte der Report-Lauf denselben deterministischen 400er für alle
Sections (``generate_section_react warf eine Exception: BadRequestError(...)``)
und setzte jedes Mal Fallback-Content mit dem pauschalen Hinweis „ungültiger
API-Key, Rate-Limit, Modell nicht verfügbar".

Nachher:
    * Nach dem ersten 400 (kein 408/429/5xx, kein Timeout, kein Prompt-spezifischer
      400 wie Context-Length) setzen die restlichen Sections keinen LLM-Call mehr
      ab, bleiben aber sichtbare Fallbacks (``is_fallback_content`` → failed →
      Bericht ``INCOMPLETE``).
    * Der Fallback-Text nennt Fehlerklasse und gekürzte Providermeldung ohne Secrets.
    * ``BudgetExceededError`` wird weiter hart durchgereicht.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.report_agent import workflow as workflow_mod
from app.services.report_agent.output_contract import is_fallback_content
from app.services.report_agent.run_degradation import RunEventLog, events_for
from app.services.report_agent.workflow import _safe_generate_section_react
from app.services.run_budget import BudgetExceededError


class BadRequestError(Exception):
    """Ersatz für ``openai.BadRequestError`` (status_code + strukturierter body)."""

    status_code = 400

    def __init__(self, message: str, *, body: dict | None = None) -> None:
        super().__init__(message)
        self.body = body


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"Error code: {status_code}")
        self.status_code = status_code


_TOOLS_400 = (
    "Function tools with reasoning_effort are not supported for gpt-6.1-sol in "
    "/v1/chat/completions. Please use /v1/responses instead, or set "
    "reasoning_effort to 'none'."
)


def _tools_400(message: str = _TOOLS_400) -> BadRequestError:
    return BadRequestError(
        f"Error code: 400 - {message}",
        body={
            "message": message,
            "type": "invalid_request_error",
            "param": "reasoning_effort",
            "code": "unsupported_parameter",
        },
    )


def _section(title: str = "Stakeholder-Analyse") -> Any:
    return SimpleNamespace(title=title, content="", metadata=None)


def _run(agent: Any, index: int) -> str:
    return _safe_generate_section_react(
        agent,
        _section(),
        MagicMock(),
        [],
        None,
        index,
        "report_1738",
    )


class _Calls:
    def __init__(self, errors: list[BaseException]) -> None:
        self.count = 0
        self._errors = errors

    def __call__(self, *_a: Any, **_kw: Any) -> str:
        self.count += 1
        if self._errors:
            raise self._errors.pop(0)
        return "## Echte Section\n\nMit Inhalt."


def test_400_short_circuits_remaining_sections_without_llm_call(monkeypatch) -> None:
    fake = _Calls([_tools_400()])
    monkeypatch.setattr(workflow_mod, "generate_section_react", fake)
    agent = MagicMock()

    results = [_run(agent, i) for i in range(1, 8)]

    assert fake.count == 1, "nach dem ersten 400 darf kein weiterer LLM-Call folgen"
    # Keine Degradation verschwindet: alle 7 bleiben sichtbare Fallbacks.
    assert all(is_fallback_content(r) for r in results)
    assert "section_index=1" in results[0]
    assert "section_index=7" in results[6]
    # Erste Section nennt Klasse + Providermeldung, Folgesections den Grund.
    assert "BadRequestError" in results[0]
    assert "Function tools with reasoning_effort" in results[0]
    assert "BadRequestError" in results[3]
    assert "übersprungen" in results[3]
    assert "kein weiterer LLM-Aufruf" in results[3]
    # Der pauschale Key-/Rate-Limit-Hinweis passt nicht zu einem 400.
    assert "ungültiger API-Key" not in results[0]
    assert "ungültiger API-Key" not in results[3]


def test_fallback_text_truncates_and_redacts_secrets(monkeypatch) -> None:
    long_tail = "x" * 600
    secret_message = (
        "Incorrect API key provided: sk-proj-abcdef1234567890. "
        "Authorization: Bearer sk-live-ZZZZ1234 api_key=hunter2hunter2 "
        + long_tail
    )
    monkeypatch.setattr(
        workflow_mod,
        "generate_section_react",
        _Calls([BadRequestError(secret_message, body=None)]),
    )

    result = _run(MagicMock(), 1)

    assert "sk-proj-abcdef1234567890" not in result
    assert "sk-live-ZZZZ1234" not in result
    assert "hunter2hunter2" not in result
    assert "[redacted]" in result
    assert long_tail not in result
    assert is_fallback_content(result)


@pytest.mark.parametrize(
    "error",
    [
        _StatusError(408),
        _StatusError(429),
        _StatusError(500),
        _StatusError(503),
        TimeoutError("timed out"),
        RuntimeError("boom"),
    ],
)
def test_transient_or_other_errors_do_not_short_circuit(monkeypatch, error) -> None:
    fake = _Calls([error])
    monkeypatch.setattr(workflow_mod, "generate_section_react", fake)
    agent = MagicMock()

    first = _run(agent, 1)
    second = _run(agent, 2)

    assert is_fallback_content(first)
    assert fake.count == 2, "transiente Fehler lassen die nächste Section weiterlaufen"
    assert second == "## Echte Section\n\nMit Inhalt."
    assert events_for(agent).persistent_provider_error is None


@pytest.mark.parametrize(
    "body",
    [
        {"message": "x", "code": "context_length_exceeded"},
        {"message": "This model's maximum context length is 128000 tokens."},
        {"message": "Blocked by content policy", "code": "content_policy_violation"},
    ],
)
def test_prompt_specific_400_does_not_short_circuit(monkeypatch, body) -> None:
    fake = _Calls([BadRequestError(f"Error code: 400 - {body['message']}", body=body)])
    monkeypatch.setattr(workflow_mod, "generate_section_react", fake)
    agent = MagicMock()

    _run(agent, 1)
    second = _run(agent, 2)

    assert fake.count == 2
    assert second == "## Echte Section\n\nMit Inhalt."


def test_budget_exceeded_is_still_reraised_and_sets_no_flag(monkeypatch) -> None:
    monkeypatch.setattr(
        workflow_mod,
        "generate_section_react",
        _Calls([BudgetExceededError("calls", observed=2, threshold=2)]),
    )
    agent = MagicMock()

    with pytest.raises(BudgetExceededError):
        _run(agent, 1)

    assert events_for(agent).persistent_provider_error is None


def test_event_log_starts_without_persistent_error() -> None:
    assert RunEventLog().persistent_provider_error is None
