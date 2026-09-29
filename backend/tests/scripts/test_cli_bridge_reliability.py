"""Regressionstests zu Issue #1713 Slice S3 — CLI-Bruecke mit Retry und
Concurrency-Limit.

Hintergrund: ``codex exec``/``claude -p`` laufen als ein Subprozess pro
Anfrage (~8-40s). Ohne Grenze startet eine Simulationsrunde mit z. B. 30
aktiven Agenten ebenso viele Subprozesse gleichzeitig — CPU-Kontention macht
jeden einzelnen Aufruf langsamer und laesst ihn eher in den Timeout laufen,
der dann wie ein echter Konfigurationsfehler behandelt wird. Zwei Haerten:

1. Ein Retry mit festem Backoff bei einem transienten Fehlschlag
   (``CodexCliUnavailableError``/``ClaudeCliUnavailableError`` aus Timeout
   oder Startfehler) — Default ein Retry, konfigurierbar ueber
   ``AGORA_CLI_RETRY_ATTEMPTS``/``AGORA_CLI_RETRY_BACKOFF_SECONDS``.
2. Eine prozessweite ``asyncio.Semaphore`` (``AGORA_CLI_MAX_CONCURRENCY``,
   Default 4) begrenzt gleichzeitige Subprozesse.

``BudgetExceededError`` (harter Laufzustand aus der Budget-Proxy-Schicht,
``scripts/sim_runtime/budget_guard.py``) darf NIE retried werden — die
Retry-Schleife faengt bewusst nur die CLI-eigene Unavailable-Exception, kein
breites ``except Exception``.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from app.services.run_budget import BudgetExceededError  # noqa: E402


def _reset_semaphore(monkeypatch: pytest.MonkeyPatch, module) -> None:
    """Erzwingt eine frische ``asyncio.Semaphore`` beim naechsten Aufruf,
    damit ein zuvor in einem anderen Test gesetzter Concurrency-Wert nicht
    nachwirkt (Semaphore wird lazy beim ersten Aufruf erzeugt und gecacht)."""
    monkeypatch.setattr(module, "_cli_semaphore", None)


class TestCodexCliRetry:
    @pytest.fixture()
    def module(self):
        from sim_runtime import codex_cli_model

        return codex_cli_model

    @pytest.fixture()
    def model(self, module):
        return module.CodexCliModel(model_type="gpt-5.6-luna")

    def test_recovers_after_one_transient_failure(self, module, model, monkeypatch):
        monkeypatch.setenv(module.CLI_RETRY_BACKOFF_SECONDS_ENV, "0")
        _reset_semaphore(monkeypatch, module)
        calls = {"n": 0}

        async def _flaky(_self, _prompt):
            calls["n"] += 1
            if calls["n"] == 1:
                raise module.CodexCliUnavailableError("codex exec Timeout nach 180s")
            return "ok"

        monkeypatch.setattr(module.CodexCliModel, "_ainvoke_once", _flaky)

        result = asyncio.run(model._ainvoke("prompt"))

        assert result == "ok"
        assert calls["n"] == 2, "Default ist genau ein Retry"

    def test_gives_up_after_exhausting_retries(self, module, model, monkeypatch):
        monkeypatch.setenv(module.CLI_RETRY_BACKOFF_SECONDS_ENV, "0")
        _reset_semaphore(monkeypatch, module)
        calls = {"n": 0}

        async def _always_fails(_self, _prompt):
            calls["n"] += 1
            raise module.CodexCliUnavailableError("codex exec Timeout nach 180s")

        monkeypatch.setattr(module.CodexCliModel, "_ainvoke_once", _always_fails)

        with pytest.raises(module.CodexCliUnavailableError):
            asyncio.run(model._ainvoke("prompt"))

        assert calls["n"] == 2, "Erstversuch + genau ein Retry, danach harter Fehler"

    def test_retry_attempts_env_zero_disables_retry(self, module, model, monkeypatch):
        monkeypatch.setenv(module.CLI_RETRY_ATTEMPTS_ENV, "0")
        _reset_semaphore(monkeypatch, module)
        calls = {"n": 0}

        async def _always_fails(_self, _prompt):
            calls["n"] += 1
            raise module.CodexCliUnavailableError("kaputt")

        monkeypatch.setattr(module.CodexCliModel, "_ainvoke_once", _always_fails)

        with pytest.raises(module.CodexCliUnavailableError):
            asyncio.run(model._ainvoke("prompt"))

        assert calls["n"] == 1

    def test_budget_exceeded_error_is_not_retried(self, module, model, monkeypatch):
        """Harter Laufzustand — die Retry-Schleife faengt nur
        ``CodexCliUnavailableError``, kein breites ``except Exception``."""
        _reset_semaphore(monkeypatch, module)
        calls = {"n": 0}

        async def _budget_exceeded(_self, _prompt):
            calls["n"] += 1
            raise BudgetExceededError("calls", 10, 10)

        monkeypatch.setattr(module.CodexCliModel, "_ainvoke_once", _budget_exceeded)

        with pytest.raises(BudgetExceededError):
            asyncio.run(model._ainvoke("prompt"))

        assert calls["n"] == 1, "BudgetExceededError darf nie retried werden"

    def test_semaphore_limits_concurrent_subprocesses(self, module, model, monkeypatch):
        monkeypatch.setenv(module.CLI_MAX_CONCURRENCY_ENV, "2")
        _reset_semaphore(monkeypatch, module)
        state = {"active": 0, "max_active": 0}

        async def _tracked(_self, _prompt):
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            await asyncio.sleep(0.05)
            state["active"] -= 1
            return "ok"

        monkeypatch.setattr(module.CodexCliModel, "_ainvoke_once", _tracked)

        async def _drive():
            return await asyncio.gather(*(model._ainvoke("prompt") for _ in range(6)))

        results = asyncio.run(_drive())

        assert results == ["ok"] * 6
        assert state["max_active"] <= 2, "Semaphore muss Concurrency auf 2 begrenzen"
        assert state["max_active"] >= 2, (
            "Test muss echte Nebenlaeufigkeit erzeugen, sonst beweist er nichts"
        )


class TestClaudeCliRetry:
    @pytest.fixture()
    def module(self):
        from sim_runtime import claude_cli_model

        return claude_cli_model

    @pytest.fixture()
    def model(self, module):
        return module.ClaudeCliModel(model_type="claude-cli-default")

    def test_recovers_after_one_transient_failure(self, module, model, monkeypatch):
        monkeypatch.setenv(module.CLI_RETRY_BACKOFF_SECONDS_ENV, "0")
        _reset_semaphore(monkeypatch, module)
        calls = {"n": 0}

        async def _flaky(_self, _prompt):
            calls["n"] += 1
            if calls["n"] == 1:
                raise module.ClaudeCliUnavailableError("claude -p Timeout nach 180s")
            return "ok"

        monkeypatch.setattr(module.ClaudeCliModel, "_ainvoke_once", _flaky)

        result = asyncio.run(model._ainvoke("prompt"))

        assert result == "ok"
        assert calls["n"] == 2

    def test_gives_up_after_exhausting_retries(self, module, model, monkeypatch):
        monkeypatch.setenv(module.CLI_RETRY_BACKOFF_SECONDS_ENV, "0")
        _reset_semaphore(monkeypatch, module)
        calls = {"n": 0}

        async def _always_fails(_self, _prompt):
            calls["n"] += 1
            raise module.ClaudeCliUnavailableError("claude -p Timeout nach 180s")

        monkeypatch.setattr(module.ClaudeCliModel, "_ainvoke_once", _always_fails)

        with pytest.raises(module.ClaudeCliUnavailableError):
            asyncio.run(model._ainvoke("prompt"))

        assert calls["n"] == 2

    def test_budget_exceeded_error_is_not_retried(self, module, model, monkeypatch):
        _reset_semaphore(monkeypatch, module)
        calls = {"n": 0}

        async def _budget_exceeded(_self, _prompt):
            calls["n"] += 1
            raise BudgetExceededError("tokens", 100, 100)

        monkeypatch.setattr(module.ClaudeCliModel, "_ainvoke_once", _budget_exceeded)

        with pytest.raises(BudgetExceededError):
            asyncio.run(model._ainvoke("prompt"))

        assert calls["n"] == 1

    def test_semaphore_limits_concurrent_subprocesses(self, module, model, monkeypatch):
        monkeypatch.setenv(module.CLI_MAX_CONCURRENCY_ENV, "2")
        _reset_semaphore(monkeypatch, module)
        state = {"active": 0, "max_active": 0}

        async def _tracked(_self, _prompt):
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            await asyncio.sleep(0.05)
            state["active"] -= 1
            return "ok"

        monkeypatch.setattr(module.ClaudeCliModel, "_ainvoke_once", _tracked)

        async def _drive():
            return await asyncio.gather(*(model._ainvoke("prompt") for _ in range(6)))

        results = asyncio.run(_drive())

        assert results == ["ok"] * 6
        assert state["max_active"] <= 2
        assert state["max_active"] >= 2
