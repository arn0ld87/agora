"""``active_postgres_backends`` zählt jeden ``*_BACKEND``-Schalter (#1576)."""

from __future__ import annotations

from types import SimpleNamespace

from app.config import Config
from app.infrastructure.postgres.backends import (
    active_postgres_backends,
    any_postgres_backend,
)


def test_legacy_defaults_report_no_postgres_backend(monkeypatch):
    monkeypatch.setattr(Config, 'METADATA_BACKEND', 'legacy')
    monkeypatch.setattr(Config, 'LLM_PROFILE_BACKEND', 'sqlite')
    monkeypatch.setattr(Config, 'PROJECT_BACKEND', 'file')
    for name in dir(Config):
        if name.endswith('_BACKEND') and getattr(Config, name) == 'postgres':
            monkeypatch.setattr(Config, name, 'file')

    assert active_postgres_backends(Config) == ()
    assert any_postgres_backend(Config) is False


def test_every_backend_switch_on_postgres_is_listed_sorted():
    config = SimpleNamespace(
        PROJECT_BACKEND='postgres',
        LLM_PROFILE_BACKEND=' Postgres ',
        METADATA_BACKEND='legacy',
        EVENT_BUS_BACKEND='redis',
        SIMULATION_BACKEND='postgres',
    )

    assert active_postgres_backends(config) == (
        'LLM_PROFILE_BACKEND',
        'PROJECT_BACKEND',
        'SIMULATION_BACKEND',
    )
    assert any_postgres_backend(config) is True


def test_private_and_non_string_attributes_are_ignored():
    config = SimpleNamespace(_HIDDEN_BACKEND='postgres', COUNT_BACKEND=3)

    assert active_postgres_backends(config) == ()
