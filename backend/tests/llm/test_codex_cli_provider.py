"""Tests for the Codex-CLI provider bridge (Issue #1405).

All `subprocess.run` calls are mocked — no real `codex` binary is ever
invoked, even if it happens to be installed on the test machine.
"""
from __future__ import annotations

import subprocess
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from app.llm.errors import LlmProviderError
from app.llm.providers import codex_cli as codex_cli_mod
from app.llm.providers.codex_cli import (
    CodexCliClient,
    _flatten_messages,
    is_codex_cli_available,
)


# ---------------------------------------------------------------------------
# is_codex_cli_available()
# ---------------------------------------------------------------------------


def test_is_codex_cli_available_true_when_which_finds_binary(monkeypatch):
    monkeypatch.setattr(codex_cli_mod.shutil, "which", lambda _binary: "/usr/local/bin/codex")
    assert is_codex_cli_available() is True


def test_is_codex_cli_available_false_when_which_finds_nothing(monkeypatch):
    monkeypatch.setattr(codex_cli_mod.shutil, "which", lambda _binary: None)
    assert is_codex_cli_available() is False


# ---------------------------------------------------------------------------
# CodexCliClient().chat.completions.create(...)
# ---------------------------------------------------------------------------


def _mock_available(monkeypatch) -> None:
    monkeypatch.setattr(codex_cli_mod.shutil, "which", lambda _binary: "/usr/local/bin/codex")


def test_create_success_returns_openai_shaped_message(monkeypatch):
    _mock_available(monkeypatch)
    run_result = MagicMock(returncode=0, stdout="antwort text", stderr="")
    mock_run = MagicMock(return_value=run_result)
    monkeypatch.setattr(codex_cli_mod.subprocess, "run", mock_run)

    client = CodexCliClient()
    completion = client.chat.completions.create(
        model="gpt-5-codex",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert completion.choices[0].message.content == "antwort text"
    mock_run.assert_called_once()


def test_create_timeout_raises_llm_provider_error_with_timeout_message(monkeypatch):
    _mock_available(monkeypatch)

    def _raise_timeout(*_args: Any, **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd=["codex"], timeout=180)

    monkeypatch.setattr(codex_cli_mod.subprocess, "run", _raise_timeout)

    client = CodexCliClient()
    with pytest.raises(LlmProviderError, match="Timeout"):
        client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])


def test_create_nonzero_returncode_raises_with_stderr_excerpt(monkeypatch):
    _mock_available(monkeypatch)
    run_result = MagicMock(returncode=1, stdout="", stderr="auth error")
    monkeypatch.setattr(codex_cli_mod.subprocess, "run", MagicMock(return_value=run_result))

    client = CodexCliClient()
    with pytest.raises(LlmProviderError, match="auth error"):
        client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])


def test_create_empty_stdout_raises_leere_ausgabe(monkeypatch):
    _mock_available(monkeypatch)
    run_result = MagicMock(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(codex_cli_mod.subprocess, "run", MagicMock(return_value=run_result))

    client = CodexCliClient()
    with pytest.raises(LlmProviderError, match="leere Ausgabe"):
        client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])


def test_create_binary_missing_raises_without_calling_subprocess(monkeypatch):
    monkeypatch.setattr(codex_cli_mod.shutil, "which", lambda _binary: None)
    mock_run = MagicMock()
    monkeypatch.setattr(codex_cli_mod.subprocess, "run", mock_run)

    client = CodexCliClient()
    with pytest.raises(LlmProviderError):
        client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])

    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# _flatten_messages()
# ---------------------------------------------------------------------------


def test_flatten_messages_keeps_role_markers_and_order():
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": "Du bist hilfreich."},
        {"role": "user", "content": "Was ist 2+2?"},
    ]
    prompt = _flatten_messages(messages)

    system_idx = prompt.index("[SYSTEM]")
    user_idx = prompt.index("[USER]")
    assert system_idx < user_idx
    assert "Du bist hilfreich." in prompt
    assert "Was ist 2+2?" in prompt


# ---------------------------------------------------------------------------
# Subprozess-Aufruf-Details
# ---------------------------------------------------------------------------


def test_subprocess_invocation_uses_isolated_cwd_and_sandbox_flags(monkeypatch, tmp_path):
    _mock_available(monkeypatch)
    run_result = MagicMock(returncode=0, stdout="ok", stderr="")
    mock_run = MagicMock(return_value=run_result)
    monkeypatch.setattr(codex_cli_mod.subprocess, "run", mock_run)

    project_cwd = str(tmp_path)
    client = CodexCliClient()
    client.chat.completions.create(model="gpt-5-codex", messages=[{"role": "user", "content": "hi"}])

    _args, kwargs = mock_run.call_args
    cmd = _args[0]
    assert "--sandbox" in cmd and "read-only" in cmd
    assert "--skip-git-repo-check" in cmd
    assert kwargs["timeout"] == pytest.approx(180.0)
    assert kwargs["cwd"] != project_cwd
    assert kwargs["cwd"] is not None


def test_subprocess_timeout_default_is_180_and_overridable_via_env(monkeypatch):
    _mock_available(monkeypatch)
    run_result = MagicMock(returncode=0, stdout="ok", stderr="")
    mock_run = MagicMock(return_value=run_result)
    monkeypatch.setattr(codex_cli_mod.subprocess, "run", mock_run)
    monkeypatch.delenv(codex_cli_mod.CODEX_CLI_TIMEOUT_ENV, raising=False)

    client = CodexCliClient()
    client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])
    _args, kwargs = mock_run.call_args
    assert kwargs["timeout"] == pytest.approx(180.0)

    monkeypatch.setenv(codex_cli_mod.CODEX_CLI_TIMEOUT_ENV, "45")
    mock_run.reset_mock()
    client.chat.completions.create(model=None, messages=[{"role": "user", "content": "hi"}])
    _args, kwargs = mock_run.call_args
    assert kwargs["timeout"] == pytest.approx(45.0)
