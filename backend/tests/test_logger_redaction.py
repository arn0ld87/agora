"""
Tests für die Secret-Redaction in app.utils.logger.

Deckt die typischen Leak-Vektoren ab, die uns vor P2 trafen:
  - Werkzeug-Access-Line mit ?token=/?ticket= im Query-String
  - Authorization: Bearer <jwt>-Header in Debug-Logs
  - X-Agora-Token-Header in stringifizierten Mappings
  - JSON-Bodies mit "password"/"api_key"
  - Env-Stil ``LLM_API_KEY=...`` aus Subprozess-Logs

Negativtests stellen sicher, dass harmlose Strings nicht angefasst werden.
"""

from __future__ import annotations

import logging
from io import StringIO

import pytest

from app.utils.logger import (
    REDACTED,
    RedactionFilter,
    _scrub,
    install_redaction_filter,
)


@pytest.fixture
def buffered_logger() -> tuple[logging.Logger, StringIO]:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))

    log = logging.getLogger(f"agora.test.redaction.{id(stream)}")
    log.handlers.clear()
    log.filters.clear()
    log.propagate = False
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    install_redaction_filter(log)
    return log, stream


class TestScrubHelper:
    @pytest.mark.parametrize(
        "raw, must_not_contain",
        [
            (
                "GET /api/simulation/abc/stream?ticket=eyJhbGciOiJIUzI1NiJ9.payload.sig",
                "eyJhbGciOiJIUzI1NiJ9.payload.sig",
            ),
            (
                "Authorization: Bearer s3cret-bearer-token-1234",
                "s3cret-bearer-token-1234",
            ),
            (
                "X-Agora-Token: super-secret-value",
                "super-secret-value",
            ),
            (
                'Request body: {"password": "hunter2", "user": "alex"}',
                "hunter2",
            ),
            (
                'payload={"api_key": "sk-live-abcdef123456"}',  # gitleaks:allow
                "sk-live-abcdef123456",  # gitleaks:allow
            ),
            (
                "env: LLM_API_KEY=ollama-cloud-very-secret",
                "ollama-cloud-very-secret",
            ),
            (
                "GET /api/foo?token=bar123&other=ok",
                "bar123",
            ),
        ],
    )
    def test_scrubs_known_secret_shapes(self, raw: str, must_not_contain: str) -> None:
        scrubbed = _scrub(raw)
        assert must_not_contain not in scrubbed, scrubbed
        assert REDACTED in scrubbed

    @pytest.mark.parametrize(
        "raw",
        [
            "Simulation abc-123 finished round 5",
            "Neo4jStorage initialized (connected to bolt://localhost:7687)",
            "request_id=deadbeef path=/api/status",
            # Schlüsselwort enthalten, aber kein Wert -> nichts zu maskieren
            "no token provided",
        ],
    )
    def test_leaves_neutral_messages_untouched(self, raw: str) -> None:
        assert _scrub(raw) == raw


class TestRedactionFilter:
    def test_filter_scrubs_format_args(self, buffered_logger):
        log, stream = buffered_logger
        log.info("auth header: %s", "Bearer abc-def-ghi-jkl")
        line = stream.getvalue().strip()
        assert "abc-def-ghi-jkl" not in line
        assert REDACTED in line

    def test_filter_scrubs_query_token_in_path(self, buffered_logger):
        log, stream = buffered_logger
        log.info("Request: GET /api/simulation/x/stream?ticket=raw-ticket-xyz HTTP/1.1")
        line = stream.getvalue().strip()
        assert "raw-ticket-xyz" not in line
        assert REDACTED in line

    def test_filter_scrubs_json_password(self, buffered_logger):
        log, stream = buffered_logger
        log.debug('body=%s', '{"password": "topsecret", "user": "alex"}')
        line = stream.getvalue().strip()
        assert "topsecret" not in line
        assert REDACTED in line

    def test_filter_idempotent_install(self):
        log = logging.getLogger("agora.test.redaction.idempotent")
        log.handlers.clear()
        log.filters.clear()
        install_redaction_filter(log)
        install_redaction_filter(log)
        redaction_filters = [f for f in log.filters if isinstance(f, RedactionFilter)]
        assert len(redaction_filters) == 1

    def test_filter_propagates_to_handlers(self):
        log = logging.getLogger("agora.test.redaction.handlers")
        log.handlers.clear()
        log.filters.clear()
        log.propagate = False
        log.setLevel(logging.DEBUG)
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        install_redaction_filter(log)

        log.warning("Authorization: Bearer leaked-token-9999")
        assert "leaked-token-9999" not in stream.getvalue()
        assert REDACTED in stream.getvalue()

    def test_filter_does_not_break_on_non_string_args(self, buffered_logger):
        log, stream = buffered_logger
        log.info("count=%d ok=%s", 42, True)
        line = stream.getvalue().strip()
        assert line.endswith("count=42 ok=True")
