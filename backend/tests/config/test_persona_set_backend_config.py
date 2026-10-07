"""Config-Vertrag für `AGORA_PERSONA_SET_BACKEND` (Issue #1807).

Zwei Zusagen: der Default bleibt die Datei und braucht keine Datenbank, und
`postgres` verlangt nur `DATABASE_URL`. `agora.persona_sets` hat keinen
Fremdschlüssel auf eine andere Metadaten-Tabelle, deshalb gibt es — anders als
bei Simulationen, Runs und Reports — keine Abhängigkeit von einem zweiten
Schalter.
"""

from __future__ import annotations

import pytest

from app.config import PERSONA_SET_BACKENDS, Config, validate_persona_set_backend
from app.infrastructure.postgres.backends import active_postgres_backends

URL = 'postgresql+psycopg://u:p@host:5432/db'


def test_persona_set_backends_are_exactly_file_and_postgres():
    assert PERSONA_SET_BACKENDS == frozenset({'file', 'postgres'})


def test_default_is_file_without_database_url():
    assert Config.PERSONA_SET_BACKEND == 'file'
    assert validate_persona_set_backend('file', '') == []


def test_unknown_value_is_rejected():
    errors = validate_persona_set_backend('postgress', URL)

    assert len(errors) == 1
    assert "unknown value 'postgress'" in errors[0]


def test_postgres_without_database_url_is_rejected():
    errors = validate_persona_set_backend('postgres', '  ')

    assert len(errors) == 1
    assert 'DATABASE_URL' in errors[0]


def test_postgres_with_url_is_accepted_without_other_backends():
    assert validate_persona_set_backend('postgres', URL) == []


def test_value_is_normalized():
    assert validate_persona_set_backend(' Postgres ', URL) == []


@pytest.fixture
def config_without_unrelated_errors(monkeypatch):
    monkeypatch.setattr(Config, 'DEBUG', True)
    monkeypatch.setattr(Config, 'SECRET_KEY', 'test-secret-not-a-placeholder')
    monkeypatch.setattr(Config, 'LLM_API_KEY', 'ollama')
    monkeypatch.setattr(Config, 'NEO4J_URI', 'bolt://localhost:7687')
    monkeypatch.setattr(Config, 'NEO4J_PASSWORD', 'test-password-not-a-placeholder')
    return Config


def test_config_validate_rejects_postgres_without_database_url(
    config_without_unrelated_errors, monkeypatch
):
    """Die Regel muss an `Config.validate()` hängen, nicht nur existieren."""
    monkeypatch.setattr(Config, 'DATABASE_URL', '')
    monkeypatch.setattr(Config, 'PERSONA_SET_BACKEND', 'postgres')

    errors = [e for e in Config.validate() if 'AGORA_PERSONA_SET_BACKEND' in e]

    assert len(errors) == 1
    assert 'DATABASE_URL' in errors[0]


def test_config_validate_accepts_persona_sets_on_postgres_alone(
    config_without_unrelated_errors, monkeypatch
):
    monkeypatch.setattr(Config, 'DATABASE_URL', URL)
    monkeypatch.setattr(Config, 'PERSONA_SET_BACKEND', 'postgres')

    assert [e for e in Config.validate() if 'AGORA_PERSONA_SET_BACKEND' in e] == []


def test_config_validate_rejects_unknown_value(config_without_unrelated_errors, monkeypatch):
    monkeypatch.setattr(Config, 'PERSONA_SET_BACKEND', 'sqlite')

    errors = [e for e in Config.validate() if 'AGORA_PERSONA_SET_BACKEND' in e]

    assert len(errors) == 1
    assert "unknown value 'sqlite'" in errors[0]


def test_the_backend_counts_for_the_postgres_start_gates(monkeypatch):
    """Readiness, Schema-Gate und Backup erkennen `*_BACKEND`-Attribute von selbst."""
    monkeypatch.setattr(Config, 'PERSONA_SET_BACKEND', 'postgres')

    assert 'PERSONA_SET_BACKEND' in active_postgres_backends(Config)

    monkeypatch.setattr(Config, 'PERSONA_SET_BACKEND', 'file')

    assert 'PERSONA_SET_BACKEND' not in active_postgres_backends(Config)
