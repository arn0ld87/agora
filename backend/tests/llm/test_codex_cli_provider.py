"""Tests for the Codex-CLI provider bridge (Issue #1405).

All `subprocess.run` calls are mocked — no real `codex` binary is ever
invoked, even if it happens to be installed on the test machine.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from app.llm.errors import LlmProviderError
from app.llm.providers import codex_cli as codex_cli_mod
from app.llm.providers.codex_cli import (
    CodexCliClient,
    _flatten_messages,
    discover_codex_cli_models,
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


# ---------------------------------------------------------------------------
# discover_codex_cli_models() — Modellkatalog statt Sentinel-Einzelmodell
# ---------------------------------------------------------------------------

_CATALOG_JSON = json.dumps(
    {
        "models": [
            {"slug": "gpt-reserve", "visibility": "hide"},
            {"slug": "gpt-5.6-sol", "visibility": "list"},
            {"slug": "gpt-5.6-terra", "visibility": "list"},
            {"slug": "gpt-5.5", "visibility": "list"},
            {"slug": "codex-auto-review", "visibility": "hide"},
        ]
    }
)


def test_discover_models_returns_only_listed_slugs_in_catalog_order(monkeypatch):
    _mock_available(monkeypatch)
    run_result = MagicMock(returncode=0, stdout=_CATALOG_JSON, stderr="")
    mock_run = MagicMock(return_value=run_result)
    monkeypatch.setattr(codex_cli_mod.subprocess, "run", mock_run)

    assert discover_codex_cli_models() == ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.5")

    cmd = mock_run.call_args[0][0]
    assert cmd[1:] == ["debug", "models"]


def test_discover_models_skips_hidden_and_malformed_entries(monkeypatch):
    _mock_available(monkeypatch)
    payload = json.dumps(
        {
            "models": [
                "nicht-mal-ein-objekt",
                {"visibility": "list"},
                {"slug": "", "visibility": "list"},
                {"slug": "gpt-5.4", "visibility": "list"},
                {"slug": "gpt-5.4", "visibility": "list"},
            ]
        }
    )
    monkeypatch.setattr(
        codex_cli_mod.subprocess,
        "run",
        MagicMock(return_value=MagicMock(returncode=0, stdout=payload, stderr="")),
    )

    assert discover_codex_cli_models() == ("gpt-5.4",)


@pytest.mark.parametrize(
    "run_result",
    [
        MagicMock(returncode=1, stdout="", stderr="boom"),
        MagicMock(returncode=0, stdout="kein json", stderr=""),
        MagicMock(returncode=0, stdout='["liste statt objekt"]', stderr=""),
        MagicMock(returncode=0, stdout='{"models": "kein array"}', stderr=""),
    ],
)
def test_discover_models_returns_empty_on_any_failure(monkeypatch, run_result):
    """Discovery ist Komfort — sie darf eine funktionierende Verbindung nie kippen."""
    _mock_available(monkeypatch)
    monkeypatch.setattr(codex_cli_mod.subprocess, "run", MagicMock(return_value=run_result))

    assert discover_codex_cli_models() == ()


def test_discover_models_returns_empty_on_timeout_without_raising(monkeypatch):
    _mock_available(monkeypatch)
    monkeypatch.setattr(
        codex_cli_mod.subprocess,
        "run",
        MagicMock(side_effect=subprocess.TimeoutExpired(cmd="codex", timeout=30)),
    )

    assert discover_codex_cli_models() == ()


def test_discover_models_does_not_spawn_subprocess_when_binary_missing(monkeypatch):
    monkeypatch.setattr(codex_cli_mod.shutil, "which", lambda _binary: None)
    mock_run = MagicMock()
    monkeypatch.setattr(codex_cli_mod.subprocess, "run", mock_run)

    assert discover_codex_cli_models() == ()
    mock_run.assert_not_called()


def test_discover_models_runs_in_isolated_cwd(monkeypatch):
    """Wie jeder codex-Aufruf: nie im CWD des Backend-Prozesses (= dieses Repo)."""
    _mock_available(monkeypatch)
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout=_CATALOG_JSON, stderr=""))
    monkeypatch.setattr(codex_cli_mod.subprocess, "run", mock_run)

    discover_codex_cli_models()

    cwd = mock_run.call_args.kwargs["cwd"]
    assert cwd is not None
    assert "agora-codex-catalog-" in cwd


# --------------------------------------------------------------------------- #
# Credential-Mount-Trennung
# --------------------------------------------------------------------------- #

class TestCodexCliReadiness:
    """Binary, Credential-Verzeichnis und Login sind drei verschiedene Dinge.

    Bis 0.9.5 mountete der Standard-Compose `~/.codex` des Hosts read/write in
    den Container; "Provider verfuegbar" hiess allein "Binary im PATH". Nach der
    Trennung liegt das Credential-Verzeichnis hinter einem eigenen
    Compose-Override, und die Probe muss den Unterschied benennen koennen.
    """

    def test_home_follows_codex_home_env(self, monkeypatch, tmp_path):
        from app.llm.providers.codex_cli import CODEX_HOME_ENV, codex_cli_home

        monkeypatch.setenv(CODEX_HOME_ENV, str(tmp_path / "agora-codex"))
        assert codex_cli_home() == tmp_path / "agora-codex"

    def test_home_falls_back_to_user_home(self, monkeypatch, tmp_path):
        from app.llm.providers.codex_cli import CODEX_HOME_ENV, codex_cli_home

        monkeypatch.delenv(CODEX_HOME_ENV, raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        assert codex_cli_home() == tmp_path / ".codex"

    def test_missing_directory(self, tmp_path):
        from app.llm.providers.codex_cli import codex_cli_credential_state

        assert codex_cli_credential_state(tmp_path / "nope") == "missing"

    def test_empty_directory_means_no_login(self, tmp_path):
        from app.llm.providers.codex_cli import codex_cli_credential_state

        empty = tmp_path / "codex"
        empty.mkdir()
        assert codex_cli_credential_state(empty) == "empty"

    def test_populated_directory_counts_as_login(self, tmp_path):
        """Bewusst kein Test auf einen konkreten Dateinamen der CLI.

        Deren internes Anmeldeformat ist nicht Teil unseres Vertrags; ein
        hartkodierter Dateiname wuerde beim naechsten CLI-Update still zu einem
        Falsch-Negativ.
        """
        from app.llm.providers.codex_cli import codex_cli_credential_state

        home = tmp_path / "codex"
        home.mkdir()
        (home / "some-session-file").write_text("{}")
        assert codex_cli_credential_state(home) == "ok"

    def test_unreadable_directory_is_reported_distinctly(self, tmp_path):
        """Docker legt ein fehlendes Host-Verzeichnis als root an — uid=1000
        kommt dann nicht hinein. Das ist der haeufigste Praxisfall und darf
        nicht als "nicht angemeldet" verschleiert werden."""
        import os

        from app.llm.providers.codex_cli import codex_cli_credential_state

        if os.geteuid() == 0:
            pytest.skip("als root ist jedes Verzeichnis lesbar")

        home = tmp_path / "codex"
        home.mkdir()
        (home / "session").write_text("{}")
        home.chmod(0o000)
        try:
            assert codex_cli_credential_state(home) == "unreadable"
        finally:
            home.chmod(0o700)

    def test_readiness_requires_both_binary_and_login(self, monkeypatch, tmp_path):
        from app.llm.providers import codex_cli

        monkeypatch.setattr(codex_cli, "is_codex_cli_available", lambda: True)
        monkeypatch.setattr(codex_cli, "codex_cli_home", lambda: tmp_path)

        monkeypatch.setattr(
            codex_cli, "codex_cli_credential_state", lambda home=None: "empty"
        )
        assert codex_cli.codex_cli_readiness().ready is False

        monkeypatch.setattr(
            codex_cli, "codex_cli_credential_state", lambda home=None: "ok"
        )
        readiness = codex_cli.codex_cli_readiness()
        assert readiness.ready is True
        assert readiness.status_message is None
