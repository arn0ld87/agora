"""Regression-Tests für Issue #1103 (CWE-319): HTTPS für credential-behaftete
LLM-Endpoints erzwingen.

``ensure_credentialed_transport_security`` ist fail-closed: http:// mit einem
api_key ist nur erlaubt, wenn der Host nachweislich lokal/privat ist.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.llm.transport_security import (
    InsecureTransportError,
    ensure_credentialed_transport_security,
)


# ---------------------------------------------------------------------------
# Policy-Matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.example.com/v1",
        "http://localhost:11434",
        "http://localhost:11434/v1",
        "http://sub.localhost:11434",
        "http://127.0.0.1:8080/v1",
        "http://192.168.1.10:11434",
        "http://10.0.0.5:11434",
        "http://172.16.0.1:11434",
        "http://100.64.0.1:11434",
        "http://100.127.255.254:11434",
        "http://[::1]:11434",
        "http://ollama:11434",  # Docker-Compose-Servicename, single-label
        "http://host.docker.internal:11434",  # Docker-Host-Gateway
    ],
)
def test_allowed_transports_with_credential_do_not_raise(base_url: str) -> None:
    ensure_credentialed_transport_security(base_url, "sk-test")


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.example.com/v1",
        "http://172.32.0.1:11434",  # knapp ausserhalb 172.16.0.0/12
        "http://100.128.0.1:11434",  # knapp ausserhalb 100.64.0.0/10
        "not a url with a key",  # kaputte/unparsebare URL
    ],
)
def test_public_http_with_credential_raises(base_url: str) -> None:
    with pytest.raises(InsecureTransportError):
        ensure_credentialed_transport_security(base_url, "sk-test")


def test_public_http_without_credential_does_not_raise() -> None:
    ensure_credentialed_transport_security("http://api.example.com/v1", None)


def test_no_base_url_does_not_raise() -> None:
    ensure_credentialed_transport_security(None, "sk-test")


def test_error_message_never_contains_the_api_key() -> None:
    with pytest.raises(InsecureTransportError) as exc_info:
        ensure_credentialed_transport_security(
            "http://api.example.com/v1", "sk-super-secret-value"
        )
    assert "sk-super-secret-value" not in str(exc_info.value)


def test_error_message_strips_userinfo_and_query() -> None:
    with pytest.raises(InsecureTransportError) as exc_info:
        ensure_credentialed_transport_security(
            "http://user:pw@api.example.com/v1?token=leak", "sk-test"
        )
    message = str(exc_info.value)
    assert "user:pw" not in message
    assert "token=leak" not in message


# ---------------------------------------------------------------------------
# Env-Override: AGORA_LLM_ALLOW_INSECURE_HTTP
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag_value", ["1", "true", "True", "YES", "on"])
def test_env_override_allows_public_http_with_credential(
    monkeypatch: pytest.MonkeyPatch, flag_value: str
) -> None:
    monkeypatch.setenv("AGORA_LLM_ALLOW_INSECURE_HTTP", flag_value)
    ensure_credentialed_transport_security("http://api.example.com/v1", "sk-test")


def test_env_override_absent_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGORA_LLM_ALLOW_INSECURE_HTTP", raising=False)
    with pytest.raises(InsecureTransportError):
        ensure_credentialed_transport_security("http://api.example.com/v1", "sk-test")


@pytest.mark.parametrize("flag_value", ["0", "false", "no", "off", ""])
def test_env_override_falsy_values_still_raise(
    monkeypatch: pytest.MonkeyPatch, flag_value: str
) -> None:
    monkeypatch.setenv("AGORA_LLM_ALLOW_INSECURE_HTTP", flag_value)
    with pytest.raises(InsecureTransportError):
        ensure_credentialed_transport_security("http://api.example.com/v1", "sk-test")


def test_env_override_logs_warning_with_sanitized_url(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    # ``setup_logger`` setzt ``propagate=False`` (app/utils/logger.py) — caplog
    # haengt am Root-Handler, muss also Propagation entlang der Logger-Kette
    # explizit erlauben (siehe tests/llm/test_init_logging.py).
    monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
    monkeypatch.setattr(
        logging.getLogger("agora.llm_transport_security"), "propagate", True
    )
    monkeypatch.setenv("AGORA_LLM_ALLOW_INSECURE_HTTP", "true")
    with caplog.at_level(logging.WARNING, logger="agora.llm_transport_security"):
        ensure_credentialed_transport_security(
            "http://user:secret-token@api.example.com/v1?token=leak", "sk-test"
        )
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "secret-token" not in message
    assert "token=leak" not in message
    # Gleichheit statt Substring-Match auf die Domain: CodeQL wertet
    # ``"<domain>" in <str>`` als unvollstaendige URL-Sanitization
    # (py/incomplete-url-substring-sanitization), und die Gleichheit prueft
    # zugleich, dass exakt die sanitisierte Form geloggt wird.
    assert warnings[0].args == ("http://api.example.com/v1",)


# ---------------------------------------------------------------------------
# LLMClient-Integration
# ---------------------------------------------------------------------------


def _patch_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.client.OpenAI", lambda **_kw: MagicMock())


class TestLLMClientEnforcesTransportSecurity:
    def test_https_with_key_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_openai(monkeypatch)
        from app.llm.client import LLMClient

        client = LLMClient(
            api_key="k",
            base_url="https://api.example.com/v1",
            model="m",
            use_active_config=False,
        )
        assert client.base_url == "https://api.example.com/v1"

    def test_http_public_host_with_key_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_openai(monkeypatch)
        monkeypatch.delenv("AGORA_LLM_ALLOW_INSECURE_HTTP", raising=False)
        from app.llm.client import LLMClient
        from app.llm.transport_security import InsecureTransportError

        with pytest.raises(InsecureTransportError):
            LLMClient(
                api_key="k",
                base_url="http://api.example.com/v1",
                model="m",
                use_active_config=False,
            )

    def test_http_localhost_with_key_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_openai(monkeypatch)
        from app.llm.client import LLMClient

        client = LLMClient(
            api_key="k",
            base_url="http://localhost:11434",
            model="m",
            use_active_config=False,
        )
        assert client.base_url == "http://localhost:11434"
