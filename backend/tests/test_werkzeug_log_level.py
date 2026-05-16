"""Werkzeug-Access-Log-Level wird per AGORA_WERKZEUG_LOG_LEVEL gesteuert.

Why: werkzeug INFO-Logs (jeder GET /api/runs Poll) verdecken Pipeline-Stage-
Events im Container-Log. Default WARNING, per Env-Flag wieder aufdrehbar.
"""

from __future__ import annotations

import logging

import pytest

from app import configure_werkzeug_log_level


@pytest.fixture(autouse=True)
def _reset_werkzeug_logger():
    werkzeug = logging.getLogger("werkzeug")
    werkzeug.setLevel(logging.NOTSET)
    yield
    werkzeug.setLevel(logging.NOTSET)


def test_default_level_is_warning(monkeypatch):
    monkeypatch.delenv("AGORA_WERKZEUG_LOG_LEVEL", raising=False)
    assert configure_werkzeug_log_level() == logging.WARNING
    assert logging.getLogger("werkzeug").level == logging.WARNING


def test_override_to_info(monkeypatch):
    monkeypatch.setenv("AGORA_WERKZEUG_LOG_LEVEL", "INFO")
    assert configure_werkzeug_log_level() == logging.INFO
    assert logging.getLogger("werkzeug").level == logging.INFO


def test_override_to_debug_lowercase(monkeypatch):
    monkeypatch.setenv("AGORA_WERKZEUG_LOG_LEVEL", "debug")
    assert configure_werkzeug_log_level() == logging.DEBUG
    assert logging.getLogger("werkzeug").level == logging.DEBUG


def test_invalid_level_falls_back_to_warning(monkeypatch):
    monkeypatch.setenv("AGORA_WERKZEUG_LOG_LEVEL", "BOGUS_LEVEL")
    assert configure_werkzeug_log_level() == logging.WARNING
    assert logging.getLogger("werkzeug").level == logging.WARNING
