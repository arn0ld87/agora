"""
Tests for opt-in structured JSON logging (AGORA_LOG_FORMAT=json).

Coverage:
- JSON mode: every line is valid JSON and contains all mandatory fields
- Text mode: output matches the legacy bracket format (not JSON)
- extra={'simulation_id': ...} is propagated into JSON output
- Exception logging includes a formatted traceback string
"""

import json
import logging
import re
import sys
from io import StringIO


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_logger_module(monkeypatch, log_format: str):
    """
    Reload utils.logger so that _LOG_FORMAT re-evaluates with the patched env.
    Returns the freshly reloaded module.
    """
    monkeypatch.setenv('AGORA_LOG_FORMAT', log_format)
    # Remove cached module so _LOG_FORMAT constant is re-read
    mod_key = 'app.utils.logger'
    if mod_key in sys.modules:
        del sys.modules[mod_key]
    import app.utils.logger as logger_mod
    return logger_mod


def _make_stream_logger(logger_mod, name: str) -> tuple[logging.Logger, StringIO]:
    """
    Build a logger that writes to an in-memory StringIO buffer.
    Returns (logger, stream).
    """
    stream = StringIO()
    use_json = logger_mod._LOG_FORMAT == 'json'
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logger_mod._make_formatter(use_json, detailed=True))

    log = logging.getLogger(name)
    log.handlers.clear()
    log.propagate = False
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    return log, stream


# ---------------------------------------------------------------------------
# JSON mode tests
# ---------------------------------------------------------------------------

class TestJSONFormatter:
    def test_valid_json_per_line(self, monkeypatch, tmp_path):
        lm = _reload_logger_module(monkeypatch, 'json')
        log, stream = _make_stream_logger(lm, 'test.json.basic')

        log.info("hello world")
        log.warning("something happened")

        lines = [line for line in stream.getvalue().splitlines() if line.strip()]
        assert len(lines) == 2, "Expected exactly two log lines"
        for line in lines:
            parsed = json.loads(line)  # raises if invalid JSON
            assert isinstance(parsed, dict)

    def test_mandatory_fields_present(self, monkeypatch):
        lm = _reload_logger_module(monkeypatch, 'json')
        log, stream = _make_stream_logger(lm, 'test.json.fields')

        log.info("checking fields")

        line = stream.getvalue().strip()
        parsed = json.loads(line)

        for field in ('timestamp', 'level', 'logger', 'message', 'module', 'function', 'line'):
            assert field in parsed, f"Mandatory field '{field}' missing from JSON output"

    def test_timestamp_is_iso8601_utc(self, monkeypatch):
        lm = _reload_logger_module(monkeypatch, 'json')
        log, stream = _make_stream_logger(lm, 'test.json.ts')

        log.info("ts check")

        parsed = json.loads(stream.getvalue().strip())
        ts = parsed['timestamp']
        # ISO-8601 UTC ends with +00:00
        assert '+00:00' in ts or ts.endswith('Z'), f"Timestamp not UTC ISO-8601: {ts}"

    def test_simulation_id_in_extra_propagated(self, monkeypatch):
        lm = _reload_logger_module(monkeypatch, 'json')
        log, stream = _make_stream_logger(lm, 'test.json.simid')

        log.info("sim start", extra={'simulation_id': 'abc-123'})

        parsed = json.loads(stream.getvalue().strip())
        assert parsed.get('simulation_id') == 'abc-123'

    def test_request_id_in_extra_propagated(self, monkeypatch):
        lm = _reload_logger_module(monkeypatch, 'json')
        log, stream = _make_stream_logger(lm, 'test.json.reqid')

        log.debug("request debug", extra={'request_id': 'deadbeef'})

        parsed = json.loads(stream.getvalue().strip())
        assert parsed.get('request_id') == 'deadbeef'

    def test_exception_contains_traceback(self, monkeypatch):
        lm = _reload_logger_module(monkeypatch, 'json')
        log, stream = _make_stream_logger(lm, 'test.json.exc')

        try:
            raise ValueError("boom")
        except ValueError:
            log.error("caught error", exc_info=True)

        parsed = json.loads(stream.getvalue().strip())
        assert 'exception' in parsed
        exc_text = parsed['exception']
        assert 'ValueError' in exc_text
        assert 'boom' in exc_text

    def test_no_simulation_id_field_when_not_provided(self, monkeypatch):
        lm = _reload_logger_module(monkeypatch, 'json')
        log, stream = _make_stream_logger(lm, 'test.json.nosimid')

        log.info("plain message")

        parsed = json.loads(stream.getvalue().strip())
        assert 'simulation_id' not in parsed

    def test_level_field_matches_record_level(self, monkeypatch):
        lm = _reload_logger_module(monkeypatch, 'json')
        log, stream = _make_stream_logger(lm, 'test.json.level')

        log.warning("a warning")

        parsed = json.loads(stream.getvalue().strip())
        assert parsed['level'] == 'WARNING'


# ---------------------------------------------------------------------------
# Text mode tests
# ---------------------------------------------------------------------------

class TestTextFormatter:
    _TEXT_PATTERN = re.compile(
        r'^\[[\d-]+ [\d:]+\] \w+ \[.+\] .+'
    )

    def test_text_mode_not_json(self, monkeypatch):
        lm = _reload_logger_module(monkeypatch, 'text')
        log, stream = _make_stream_logger(lm, 'test.text.basic')

        log.info("plain text log")

        line = stream.getvalue().strip()
        # Must NOT be parseable as JSON
        try:
            json.loads(line)
            assert False, "Text-mode log line should not be valid JSON"
        except json.JSONDecodeError:
            pass

    def test_text_mode_format(self, monkeypatch):
        lm = _reload_logger_module(monkeypatch, 'text')
        log, stream = _make_stream_logger(lm, 'test.text.format')

        log.debug("format check")

        line = stream.getvalue().strip()
        assert self._TEXT_PATTERN.match(line), (
            f"Text log line does not match expected pattern. Got: {line!r}"
        )
