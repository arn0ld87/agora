"""Das Start-Gate begrenzt den Verbindungsaufbau (Codex-Review auf #1599)."""

from __future__ import annotations

import pytest

from app.infrastructure.postgres import schema_gate


class _StopAfterEngine(Exception):
    pass


def _capture_connect_args(monkeypatch) -> dict:
    captured: dict = {}

    def fake_create_engine(url, **kwargs):
        captured.update(kwargs.get('connect_args', {}))
        raise _StopAfterEngine

    monkeypatch.setattr(schema_gate, 'create_engine', fake_create_engine)
    with pytest.raises(_StopAfterEngine):
        schema_gate.verify_schema_at_head('postgresql+psycopg://u:p@host:5432/db')
    return captured


def test_default_connect_timeout_is_short(monkeypatch):
    monkeypatch.delenv('AGORA_SCHEMA_GATE_CONNECT_TIMEOUT', raising=False)

    assert _capture_connect_args(monkeypatch) == {'connect_timeout': 10}


def test_connect_timeout_is_configurable(monkeypatch):
    monkeypatch.setenv('AGORA_SCHEMA_GATE_CONNECT_TIMEOUT', '3')

    assert _capture_connect_args(monkeypatch) == {'connect_timeout': 3}


@pytest.mark.parametrize('raw', ['0', '-5', 'zehn'])
def test_invalid_values_fall_back_to_default(monkeypatch, raw):
    monkeypatch.setenv('AGORA_SCHEMA_GATE_CONNECT_TIMEOUT', raw)

    assert _capture_connect_args(monkeypatch) == {'connect_timeout': 10}
