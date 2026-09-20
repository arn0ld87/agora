"""Tests for the Claude-CLI provider bridge.

All `subprocess.run` calls are mocked — no real `claude` binary is ever
invoked, even if it happens to be installed on the test machine.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.llm.errors import LlmProviderError
from app.llm.providers import claude_cli as claude_cli_mod
from app.llm.providers.claude_cli import (
    ClaudeCliClient,
    claude_cli_fallback_models,
    interpret_claude_cli_result,
    is_claude_cli_available,
)


# ---------------------------------------------------------------------------
# is_claude_cli_available()
# ---------------------------------------------------------------------------


def test_is_claude_cli_available_true_when_which_finds_binary(monkeypatch):
    monkeypatch.setattr(claude_cli_mod.shutil, "which", lambda _binary: "/usr/local/bin/claude")
    assert is_claude_cli_available() is True


def test_is_claude_cli_available_false_when_which_finds_nothing(monkeypatch):
    monkeypatch.setattr(claude_cli_mod.shutil, "which", lambda _binary: None)
    assert is_claude_cli_available() is False


# ---------------------------------------------------------------------------
# claude_cli_fallback_models()
# ---------------------------------------------------------------------------


def test_fallback_models_sentinel_first_then_documented_aliases():
    models = claude_cli_fallback_models()
    assert models[0] == claude_cli_mod.CLAUDE_CLI_DEFAULT_MODEL_ID
    assert "sonnet" in models
    assert "opus" in models
    assert "fable" in models


# ---------------------------------------------------------------------------
# interpret_claude_cli_result() — JSON-first, exit-code-fallback
# ---------------------------------------------------------------------------


def _json_result(**overrides: Any) -> str:
    payload = {"type": "result", "is_error": False, "result": "hallo"}
    payload.update(overrides)
    return json.dumps(payload)


def test_interpret_success_returns_result_field():
    text = interpret_claude_cli_result(0, _json_result(result="antwort"), "")
    assert text == "antwort"


def test_interpret_is_error_true_raises_with_result_message():
    payload = _json_result(is_error=True, result="Not logged in · Please run /login")
    with pytest.raises(claude_cli_mod.ClaudeCliUnavailableError, match="Not logged in"):
        interpret_claude_cli_result(1, payload, "")


def test_interpret_json_without_result_field_raises():
    payload = json.dumps({"type": "result", "is_error": False})
    with pytest.raises(claude_cli_mod.ClaudeCliUnavailableError, match="result"):
        interpret_claude_cli_result(0, payload, "")


def test_interpret_falls_back_to_stderr_when_stdout_not_json():
    with pytest.raises(claude_cli_mod.ClaudeCliUnavailableError, match="boom"):
        interpret_claude_cli_result(1, "kein json", "boom")


def test_interpret_empty_output_raises():
    with pytest.raises(claude_cli_mod.ClaudeCliUnavailableError):
        interpret_claude_cli_result(0, "", "")


def test_interpret_prefers_json_result_even_on_nonzero_exit():
    """Ein 401 kommt als sauberes JSON auf stdout UND exit=1 — beides gilt,
    aber die JSON-Fehlermeldung ist informativer als der Exit-Code allein."""
    payload = _json_result(is_error=True, result="api_error_status=401")
    with pytest.raises(claude_cli_mod.ClaudeCliUnavailableError, match="401"):
        interpret_claude_cli_result(1, payload, "irrelevanter stderr text")


# ---------------------------------------------------------------------------
# ClaudeCliClient().chat.completions.create(...)
# ---------------------------------------------------------------------------


def _mock_available(monkeypatch) -> None:
    monkeypatch.setattr(claude_cli_mod.shutil, "which", lambda _binary: "/usr/local/bin/claude")


def test_create_success_returns_openai_shaped_message(monkeypatch):
    _mock_available(monkeypatch)
    run_result = MagicMock(returncode=0, stdout=_json_result(result="antwort text"), stderr="")
    mock_run = MagicMock(return_value=run_result)
    monkeypatch.setattr(claude_cli_mod.subprocess, "run", mock_run)

    client = ClaudeCliClient(oauth_token="tok_abc")
    completion = client.chat.completions.create(
        model="sonnet",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert completion.choices[0].message.content == "antwort text"
    mock_run.assert_called_once()


def test_create_without_oauth_token_raises_invalid_credentials_without_subprocess(monkeypatch):
    _mock_available(monkeypatch)
    mock_run = MagicMock()
    monkeypatch.setattr(claude_cli_mod.subprocess, "run", mock_run)

    client = ClaudeCliClient(oauth_token=None)
    with pytest.raises(LlmProviderError, match="CLAUDE_CODE_OAUTH_TOKEN"):
        client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])

    mock_run.assert_not_called()


def test_create_timeout_raises_llm_provider_error_with_timeout_message(monkeypatch):
    _mock_available(monkeypatch)

    def _raise_timeout(*_args: Any, **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd=["claude"], timeout=180)

    monkeypatch.setattr(claude_cli_mod.subprocess, "run", _raise_timeout)

    client = ClaudeCliClient(oauth_token="tok_abc")
    with pytest.raises(LlmProviderError, match="Timeout"):
        client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])


def test_create_is_error_raises_with_cli_message(monkeypatch):
    _mock_available(monkeypatch)
    payload = _json_result(is_error=True, result="Not logged in · Please run /login")
    monkeypatch.setattr(
        claude_cli_mod.subprocess,
        "run",
        MagicMock(return_value=MagicMock(returncode=1, stdout=payload, stderr="")),
    )

    client = ClaudeCliClient(oauth_token="tok_abc")
    with pytest.raises(LlmProviderError, match="Not logged in"):
        client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])


def test_create_binary_missing_raises_without_calling_subprocess(monkeypatch):
    monkeypatch.setattr(claude_cli_mod.shutil, "which", lambda _binary: None)
    mock_run = MagicMock()
    monkeypatch.setattr(claude_cli_mod.subprocess, "run", mock_run)

    client = ClaudeCliClient(oauth_token="tok_abc")
    with pytest.raises(LlmProviderError):
        client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])

    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Subprozess-Aufruf-Details — Isolation (Sicherheit + Kosten)
# ---------------------------------------------------------------------------


def test_subprocess_invocation_isolates_cwd_home_and_sets_token(monkeypatch, tmp_path):
    _mock_available(monkeypatch)
    run_result = MagicMock(returncode=0, stdout=_json_result(result="ok"), stderr="")
    mock_run = MagicMock(return_value=run_result)
    monkeypatch.setattr(claude_cli_mod.subprocess, "run", mock_run)

    project_cwd = str(tmp_path)
    client = ClaudeCliClient(oauth_token="tok_secret")
    client.chat.completions.create(model="sonnet", messages=[{"role": "user", "content": "hi"}])

    _args, kwargs = mock_run.call_args
    cmd = _args[0]
    assert "--tools" in cmd
    tools_idx = cmd.index("--tools")
    assert cmd[tools_idx + 1] == ""
    assert "--permission-prompts" in cmd and "none" in cmd
    assert "--output-format" in cmd and "json" in cmd
    assert "--model" in cmd and "sonnet" in cmd

    assert kwargs["cwd"] != project_cwd
    assert kwargs["cwd"] is not None

    env = kwargs["env"]
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "tok_secret"
    # Isoliertes HOME: nicht das reale $HOME des Testprozesses.
    import os as _os

    assert env["HOME"] != _os.environ.get("HOME")
    assert kwargs["cwd"] not in (None, "")


def test_sentinel_model_omits_model_flag(monkeypatch):
    _mock_available(monkeypatch)
    run_result = MagicMock(returncode=0, stdout=_json_result(result="ok"), stderr="")
    mock_run = MagicMock(return_value=run_result)
    monkeypatch.setattr(claude_cli_mod.subprocess, "run", mock_run)

    client = ClaudeCliClient(oauth_token="tok_abc")
    client.chat.completions.create(
        model=claude_cli_mod.CLAUDE_CLI_DEFAULT_MODEL_ID,
        messages=[{"role": "user", "content": "hi"}],
    )

    cmd = mock_run.call_args[0][0]
    assert "--model" not in cmd


def test_subprocess_timeout_default_is_180_and_overridable_via_env(monkeypatch):
    _mock_available(monkeypatch)
    run_result = MagicMock(returncode=0, stdout=_json_result(result="ok"), stderr="")
    mock_run = MagicMock(return_value=run_result)
    monkeypatch.setattr(claude_cli_mod.subprocess, "run", mock_run)
    monkeypatch.delenv(claude_cli_mod.CLAUDE_CLI_TIMEOUT_ENV, raising=False)

    client = ClaudeCliClient(oauth_token="tok_abc")
    client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])
    _args, kwargs = mock_run.call_args
    assert kwargs["timeout"] == pytest.approx(180.0)

    monkeypatch.setenv(claude_cli_mod.CLAUDE_CLI_TIMEOUT_ENV, "45")
    mock_run.reset_mock()
    client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])
    _args, kwargs = mock_run.call_args
    assert kwargs["timeout"] == pytest.approx(45.0)


# ---------------------------------------------------------------------------
# Tool-Call-Uebersetzung — wiederverwendet aus codex_cli, hier nur der
# Shim-spezifische Teil (build_shim_message)
# ---------------------------------------------------------------------------


def test_build_shim_message_translates_tool_call_blocks():
    text = (
        'Klar, einen Moment.\n<tool_call>\n{"name": "search", "parameters": {"q": "x"}}\n'
        "</tool_call>"
    )
    message = claude_cli_mod.build_shim_message(text)
    assert message.tool_calls is not None
    assert message.tool_calls[0].function.name == "search"
    assert "search" not in message.content or "<tool_call>" not in message.content


def test_build_shim_message_without_tool_calls_is_plain_prose():
    message = claude_cli_mod.build_shim_message("nur prosa, kein werkzeug")
    assert message.tool_calls is None
    assert message.content == "nur prosa, kein werkzeug"
