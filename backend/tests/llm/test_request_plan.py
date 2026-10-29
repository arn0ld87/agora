"""Tests für ``app.llm.request_plan`` (Issue #1225).

Alles hier prüft das Interface direkt: ``build_request`` bekommt seine
Provider-Heuristiken über ``RequestOptions`` herein, ``execute`` bekommt seinen
Attempt als Callable. Kein ``patch()`` auf Modulnamen — was ein Test einsetzt,
setzt er als Argument ein.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from app.llm.request_plan import (
    DEFAULT_CHAT_QUIRKS,
    DEFAULT_REQUEST_OPTIONS,
    REASONING_EFFORT_QUIRK,
    TEMPERATURE_QUIRK,
    TOKEN_KEY_QUIRK,
    VISION_QUIRKS,
    Quirk,
    RequestOptions,
    RequestPlan,
    build_request,
    execute,
    execute_with_retry,
    extract_int_token_usage,
    extract_non_stream_chat_choice,
    reassemble_chat_stream,
    should_force_stream,
    strip_thinking_tags,
    thinking_extra_body,
)

MESSAGES: List[Dict[str, Any]] = [{"role": "user", "content": "hi"}]


def _options(*, omits: bool = False, key: str = "max_tokens") -> RequestOptions:
    """Options mit festen Antworten — die Seams als Testeingabe."""
    return RequestOptions(
        omits_temperature=lambda _model: omits,
        completion_token_key=lambda _model: key,
    )


# ---------------------------------------------------------------------------
# build_request
# ---------------------------------------------------------------------------


def test_build_request_keeps_temperature_when_model_accepts_it() -> None:
    plan = build_request(
        model="gpt-4o",
        messages=MESSAGES,
        temperature=0.7,
        max_tokens=4096,
        options=_options(omits=False),
    )
    assert plan.kwargs["temperature"] == 0.7


def test_build_request_omits_temperature_when_model_rejects_it() -> None:
    """#1096: der Key darf gar nicht erst im Request stehen, nicht nur leer sein."""
    plan = build_request(
        model="gpt-5-mini",
        messages=MESSAGES,
        temperature=0.7,
        max_tokens=4096,
        options=_options(omits=True),
    )
    assert "temperature" not in plan.kwargs


@pytest.mark.parametrize("key", ["max_tokens", "max_completion_tokens"])
def test_build_request_uses_the_token_key_the_options_name(key: str) -> None:
    plan = build_request(
        model="whatever",
        messages=MESSAGES,
        temperature=0.3,
        max_tokens=2048,
        options=_options(key=key),
    )
    assert plan.kwargs[key] == 2048
    other = "max_completion_tokens" if key == "max_tokens" else "max_tokens"
    assert other not in plan.kwargs


def test_build_request_omits_optional_keys_when_unset() -> None:
    """Ohne response_format, extra_body, stream oder extra bleibt der Request nackt."""
    plan = build_request(
        model="gpt-4o",
        messages=MESSAGES,
        temperature=0.7,
        max_tokens=1024,
        options=_options(),
    )
    assert set(plan.kwargs) == {"model", "messages", "temperature", "max_tokens"}


def test_build_request_omits_stream_key_when_false() -> None:
    """``stream=False`` heißt: kein ``stream`` im Request, nicht ``stream=False``."""
    plan = build_request(
        model="gpt-4o",
        messages=MESSAGES,
        temperature=0.7,
        max_tokens=1024,
        stream=False,
        options=_options(),
    )
    assert "stream" not in plan.kwargs

    streaming = build_request(
        model="gpt-4o",
        messages=MESSAGES,
        temperature=0.7,
        max_tokens=1024,
        stream=True,
        options=_options(),
    )
    assert streaming.kwargs["stream"] is True


def test_build_request_passes_through_response_format_extra_body_and_extra() -> None:
    plan = build_request(
        model="gpt-4o",
        messages=MESSAGES,
        temperature=0.7,
        max_tokens=1024,
        response_format={"type": "json_object"},
        extra_body={"think": False},
        extra={"tools": [{"name": "t"}], "tool_choice": "auto"},
        options=_options(),
    )
    assert plan.kwargs["response_format"] == {"type": "json_object"}
    assert plan.kwargs["extra_body"] == {"think": False}
    assert plan.kwargs["tools"] == [{"name": "t"}]
    assert plan.kwargs["tool_choice"] == "auto"


def test_build_request_defaults_bind_to_the_real_heuristics() -> None:
    """Ohne Options greifen die echten Provider-Heuristiken, nicht Platzhalter."""
    reasoning = build_request(
        model="gpt-5-mini",
        messages=MESSAGES,
        temperature=0.7,
        max_tokens=1024,
        options=DEFAULT_REQUEST_OPTIONS,
    )
    assert "temperature" not in reasoning.kwargs
    assert reasoning.kwargs["max_completion_tokens"] == 1024

    classic = build_request(
        model="gpt-4o",
        messages=MESSAGES,
        temperature=0.7,
        max_tokens=1024,
    )
    assert classic.kwargs["temperature"] == 0.7
    assert classic.kwargs["max_tokens"] == 1024


# ---------------------------------------------------------------------------
# thinking_extra_body
# ---------------------------------------------------------------------------


def test_thinking_extra_body_ollama_carries_num_ctx_and_think() -> None:
    assert thinking_extra_body(ollama=True, minimax=False, num_ctx=8192, think=True) == {
        "options": {"num_ctx": 8192},
        "think": True,
    }


def test_thinking_extra_body_ollama_without_num_ctx_leaves_server_default() -> None:
    """Ohne num_ctx darf kein ``options``-Block entstehen — sonst überschreibt
    ein leerer Block still den Serverdefault."""
    assert thinking_extra_body(ollama=True, minimax=False, num_ctx=None, think=False) == {
        "think": False
    }


@pytest.mark.parametrize(("think", "expected"), [(True, "adaptive"), (False, "disabled")])
def test_thinking_extra_body_minimax_uses_its_own_field(think: bool, expected: str) -> None:
    assert thinking_extra_body(ollama=False, minimax=True, think=think) == {
        "thinking": {"type": expected}
    }


def test_thinking_extra_body_returns_none_for_other_providers() -> None:
    assert thinking_extra_body(ollama=False, minimax=False, num_ctx=8192, think=True) is None


def test_thinking_extra_body_prefers_ollama_when_both_flags_set() -> None:
    body = thinking_extra_body(ollama=True, minimax=True, num_ctx=4096, think=False)
    assert body is not None
    assert "think" in body and "thinking" not in body


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


class _Recorder:
    """Attempt-Callable, das jeden Request mitschreibt und nach Skript scheitert.

    *failures* ist die Liste der Exceptions für die ersten Versuche; ist sie
    aufgebraucht, liefert der Attempt ``"ok"``.
    """

    def __init__(self, failures: Optional[List[Exception]] = None) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._failures = list(failures or [])

    def __call__(self, kwargs: Dict[str, Any]) -> str:
        self.calls.append(dict(kwargs))
        if self._failures:
            raise self._failures.pop(0)
        return "ok"


class _Boom(Exception):
    """Fehler, den kein Quirk erkennt."""


def _plan(**overrides: Any) -> RequestPlan:
    kwargs: Dict[str, Any] = {"model": "gpt-4o", "max_tokens": 4096, "temperature": 0.7}
    kwargs.update(overrides)
    return RequestPlan(kwargs=kwargs)


def _token_key_400() -> Exception:
    return _Boom(
        "Error code: 400 - Unsupported parameter: 'max_tokens' is not supported "
        "with this model. Use 'max_completion_tokens' instead."
    )


def _temperature_400() -> Exception:
    return _Boom(
        "Unsupported value: 'temperature' does not support 0.7 with this model. "
        "Only the default (1) value is supported."
    )


def test_execute_without_quirks_runs_the_attempt_once() -> None:
    attempt = _Recorder()
    assert execute(_plan(), attempt) == "ok"
    assert len(attempt.calls) == 1


def test_execute_passes_the_plan_kwargs_through_unchanged() -> None:
    attempt = _Recorder()
    execute(_plan(messages=MESSAGES), attempt, quirks=(TOKEN_KEY_QUIRK,))
    assert attempt.calls[0]["messages"] == MESSAGES


def test_execute_retries_once_with_the_rewritten_request() -> None:
    attempt = _Recorder(failures=[_token_key_400()])
    assert execute(_plan(), attempt, quirks=(TOKEN_KEY_QUIRK,)) == "ok"
    assert len(attempt.calls) == 2
    assert attempt.calls[0]["max_tokens"] == 4096
    assert attempt.calls[1]["max_completion_tokens"] == 4096
    assert "max_tokens" not in attempt.calls[1]


def test_execute_propagates_errors_no_quirk_recognises() -> None:
    attempt = _Recorder(failures=[_Boom("Invalid API key")])
    with pytest.raises(_Boom):
        execute(_plan(), attempt, quirks=(TOKEN_KEY_QUIRK, TEMPERATURE_QUIRK))
    assert len(attempt.calls) == 1, "ein unbekannter Fehler darf keinen Retry auslösen"


def test_execute_propagates_when_the_rewrite_has_nothing_to_change() -> None:
    """Matchender Quirk ohne anwendbare Korrektur retried nicht."""
    attempt = _Recorder(failures=[_temperature_400()])
    with pytest.raises(_Boom):
        execute(
            RequestPlan(kwargs={"model": "gpt-4o", "max_tokens": 1}),  # kein temperature
            attempt,
            quirks=(TEMPERATURE_QUIRK,),
        )
    assert len(attempt.calls) == 1


def test_execute_does_not_loop_when_the_same_error_repeats() -> None:
    attempt = _Recorder(failures=[_token_key_400(), _token_key_400()])
    with pytest.raises(_Boom):
        execute(_plan(), attempt, quirks=(TOKEN_KEY_QUIRK,))
    assert len(attempt.calls) == 2, "genau ein Neuversuch je Quirk, kein dritter"


def test_execute_lets_the_outer_quirk_take_over_after_the_inner_one_gave_up() -> None:
    """Der äußere Quirk setzt auf dem ORIGINALrequest auf.

    Erst scheitert der Token-Key-Retry, dann greift der Temperature-Quirk — und
    zwar auf den kwargs, die er selbst gesehen hat: mit dem ursprünglichen
    ``max_tokens``, nicht mit der Korrektur des inneren Quirks.
    """
    attempt = _Recorder(failures=[_token_key_400(), _temperature_400()])
    assert execute(_plan(), attempt, quirks=(TOKEN_KEY_QUIRK, TEMPERATURE_QUIRK)) == "ok"
    assert len(attempt.calls) == 3
    assert attempt.calls[0]["max_tokens"] == 4096
    assert attempt.calls[1]["max_completion_tokens"] == 4096  # innerer Quirk
    # Dritter Versuch: temperature weg, Token-Key wieder wie im Original.
    assert "temperature" not in attempt.calls[2]
    assert attempt.calls[2]["max_tokens"] == 4096


def test_execute_offers_the_inner_quirk_again_inside_the_outer_retry() -> None:
    """Nach der äußeren Korrektur steht der innere Quirk erneut zur Verfügung."""
    attempt = _Recorder(failures=[_temperature_400(), _token_key_400()])
    assert execute(_plan(), attempt, quirks=(TOKEN_KEY_QUIRK, TEMPERATURE_QUIRK)) == "ok"
    assert len(attempt.calls) == 3
    assert attempt.calls[1] == {  # äußere Korrektur, Token-Key noch original
        "model": "gpt-4o",
        "max_tokens": 4096,
    }
    assert attempt.calls[2]["max_completion_tokens"] == 4096
    assert "temperature" not in attempt.calls[2]


def test_execute_applies_quirks_in_the_given_order() -> None:
    """``quirks[0]`` sieht den Fehler zuerst — auch wenn ein späterer auch passt."""
    seen: List[str] = []

    def _tag(name: str) -> Quirk:
        def _rewrite(kwargs: Dict[str, Any]) -> Dict[str, Any]:
            seen.append(name)
            return {**kwargs, "touched_by": name}

        return Quirk(name=name, remedy=name, matches=lambda _exc: True, rewrite=_rewrite)

    attempt = _Recorder(failures=[_Boom("anything")])
    execute(_plan(), attempt, quirks=(_tag("inner"), _tag("outer")))
    assert seen == ["inner"], "der äußere Quirk kommt erst dran, wenn der innere aufgibt"
    assert attempt.calls[1]["touched_by"] == "inner"


def test_execute_does_not_mutate_the_plan() -> None:
    plan = _plan()
    before = dict(plan.kwargs)
    attempt = _Recorder(failures=[_token_key_400()])
    execute(plan, attempt, quirks=(TOKEN_KEY_QUIRK,))
    assert plan.kwargs == before


# ---------------------------------------------------------------------------
# execute_with_retry + response helpers (Slice #6 Deep Module)
# ---------------------------------------------------------------------------


def test_default_quirk_tuples_preserve_chat_and_vision_policies() -> None:
    assert DEFAULT_CHAT_QUIRKS == (
        TOKEN_KEY_QUIRK,
        TEMPERATURE_QUIRK,
        REASONING_EFFORT_QUIRK,
    )
    assert VISION_QUIRKS == (TOKEN_KEY_QUIRK,)


def test_execute_with_retry_delegates_to_retry_runner_and_applies_quirks() -> None:
    seen_retry_kwargs: Dict[str, Any] = {}

    def _fake_retry_runner(fn: Any, **kwargs: Any) -> Any:
        seen_retry_kwargs.update(kwargs)
        return fn()

    attempt = _Recorder(failures=[_token_key_400()])
    result = execute_with_retry(
        _plan(),
        provider_attempt=attempt,
        retry_runner=_fake_retry_runner,
        max_retries=5,
        initial_delay=0.5,
        max_delay=15.0,
        quirks=VISION_QUIRKS,
        label="vision",
    )
    assert result == "ok"
    assert len(attempt.calls) == 2
    assert attempt.calls[1]["max_completion_tokens"] == 4096
    assert seen_retry_kwargs == {
        "max_retries": 5,
        "initial_delay": 0.5,
        "max_delay": 15.0,
    }


@pytest.mark.parametrize(
    ("is_ollama", "env_value", "expected"),
    [
        (False, None, False),
        (False, "1", False),
        (True, None, True),
        (True, "1", True),
        (True, "true", True),
        (True, "yes", True),
        (True, "0", False),
        (True, "false", False),
    ],
)
def test_should_force_stream_respects_ollama_and_env_override(
    is_ollama: bool, env_value: Optional[str], expected: bool
) -> None:
    assert should_force_stream(is_ollama=is_ollama, env_value=env_value) is expected


def test_strip_thinking_tags_removes_think_blocks_and_trims() -> None:
    raw = "<think>\ninternal reasoning\n</think>\n  Final answer.  "
    assert strip_thinking_tags(raw) == "Final answer."


def test_extract_int_token_usage_filters_booleans_and_mocks() -> None:
    assert extract_int_token_usage(None) == (None, None)
    valid = SimpleNamespace(prompt_tokens=120, completion_tokens=45)
    assert extract_int_token_usage(valid) == (120, 45)
    bool_usage = SimpleNamespace(prompt_tokens=True, completion_tokens=False)
    assert extract_int_token_usage(bool_usage) == (None, None)
    mock_usage = MagicMock()
    assert extract_int_token_usage(mock_usage) == (None, None)


def test_reassemble_chat_stream_concatenates_chunks_and_extracts_usage() -> None:
    expected_usage = SimpleNamespace(prompt_tokens=10, completion_tokens=2)
    chunks = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="Hello "),
                    finish_reason=None,
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="world!"),
                    finish_reason="stop",
                )
            ],
            usage=expected_usage,
        ),
    ]
    content, finish, comp_tok, usage = reassemble_chat_stream(chunks)
    assert content == "Hello world!"
    assert finish == "stop"
    assert comp_tok == 2
    assert usage is expected_usage
    assert extract_int_token_usage(usage) == (10, 2)


def test_extract_non_stream_chat_choice_returns_content_finish_and_usage() -> None:
    expected_usage = SimpleNamespace(prompt_tokens=33, completion_tokens=64)
    resp = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Direct reply"),
                finish_reason="length",
            )
        ],
        usage=expected_usage,
    )
    content, finish, comp_tok, usage = extract_non_stream_chat_choice(resp)
    assert content == "Direct reply"
    assert finish == "length"
    assert comp_tok == 64
    assert usage is expected_usage
    assert extract_int_token_usage(usage) == (33, 64)
