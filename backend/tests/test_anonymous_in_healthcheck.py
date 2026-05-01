"""
Auth-Mode-in-Healthcheck-Regression (Slice 12, F5 of repo review, bonus case).

The repo review asked: when ``AGORA_ALLOW_ANONYMOUS=true`` is set, the
operator must be able to see that *somewhere* — not just buried in the boot
log. Slice 12 wires ``backend.auth_mode`` into ``/api/status`` for exactly
this reason.

This file pins the four documented values (``token``, ``anonymous``,
``open``, ``misconfigured``) so a future refactor cannot silently demote
``anonymous`` back into invisibility.
"""

from __future__ import annotations

import pytest

from app.api.status import _get_auth_mode, _get_backend_status


@pytest.fixture(autouse=True)
def _clear_auth_env(monkeypatch):
    """Each test starts from a clean auth-env so leakage between tests
    cannot mask a regression."""
    for key in ("AGORA_AUTH_TOKEN", "AGORA_ALLOW_ANONYMOUS", "FLASK_DEBUG"):
        monkeypatch.delenv(key, raising=False)


def test_auth_mode_token(monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "abc123")
    assert _get_auth_mode() == "token"


def test_auth_mode_anonymous(monkeypatch):
    monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", "true")
    assert _get_auth_mode() == "anonymous"


def test_auth_mode_anonymous_takes_precedence_over_debug(monkeypatch):
    """Explicit anonymous opt-in dominates the debug-fallback label."""
    monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", "true")
    monkeypatch.setenv("FLASK_DEBUG", "true")
    assert _get_auth_mode() == "anonymous"


def test_auth_mode_token_takes_precedence_over_anonymous(monkeypatch):
    """Token-set wins regardless of any opt-out flag."""
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "abc123")
    monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", "true")
    assert _get_auth_mode() == "token"


def test_auth_mode_open_in_debug(monkeypatch):
    """Local dev with no token and no opt-out reports ``open`` — visible
    but unalarming."""
    monkeypatch.setenv("FLASK_DEBUG", "true")
    assert _get_auth_mode() == "open"


def test_auth_mode_misconfigured_when_nothing_set():
    """No token, no anonymous-opt-out, no debug — this should not happen in
    a properly validated setup, so we expose ``misconfigured`` so it
    surfaces in /api/status."""
    assert _get_auth_mode() == "misconfigured"


def test_backend_status_payload_contains_auth_mode(monkeypatch):
    """``/api/status.backend`` includes the auth_mode field."""
    monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", "true")

    payload = _get_backend_status()

    assert payload["ok"] is True
    assert payload["auth_mode"] == "anonymous"
    assert "version" in payload
