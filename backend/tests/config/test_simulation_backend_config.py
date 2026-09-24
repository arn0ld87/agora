"""Config-Vertrag für `AGORA_SIMULATION_BACKEND` (Issue #1585).

Zwei Zusagen: der Default bleibt die Datei und braucht keine Datenbank, und
`postgres` ist nur zusammen mit `AGORA_PROJECT_BACKEND=postgres` zulässig —
`agora.simulations.project_id` ist ein Fremdschlüssel auf `agora.projects`,
und bei Projekten in der Datei zeigte er ins Leere.
"""

from __future__ import annotations

import pytest

from app.config import SIMULATION_BACKENDS, Config, validate_simulation_backend
from app.repositories.simulation_repository import (
    SimulationBackendUnavailable,
    get_simulation_repository,
)
from app.services.file_simulation_store import FileSimulationRepository

URL = 'postgresql+psycopg://u:p@host:5432/db'


def test_simulation_backends_are_exactly_file_and_postgres():
    assert SIMULATION_BACKENDS == frozenset({'file', 'postgres'})


def test_default_is_file_without_database_url():
    assert validate_simulation_backend('file', '', 'file') == []


def test_unknown_value_is_rejected():
    errors = validate_simulation_backend('postgress', URL, 'postgres')

    assert len(errors) == 1
    assert "unknown value 'postgress'" in errors[0]


def test_postgres_with_project_backend_file_is_rejected():
    errors = validate_simulation_backend('postgres', URL, 'file')

    assert len(errors) == 1
    assert 'AGORA_PROJECT_BACKEND=postgres' in errors[0]


def test_postgres_without_database_url_is_rejected():
    errors = validate_simulation_backend('postgres', '  ', 'postgres')

    assert len(errors) == 1
    assert 'DATABASE_URL' in errors[0]


def test_postgres_with_project_postgres_and_url_is_accepted():
    assert validate_simulation_backend('postgres', URL, 'postgres') == []


@pytest.fixture
def config_without_unrelated_errors(monkeypatch):
    monkeypatch.setattr(Config, 'DEBUG', True)
    monkeypatch.setattr(Config, 'SECRET_KEY', 'test-secret-not-a-placeholder')
    monkeypatch.setattr(Config, 'LLM_API_KEY', 'ollama')
    monkeypatch.setattr(Config, 'NEO4J_URI', 'bolt://localhost:7687')
    monkeypatch.setattr(Config, 'NEO4J_PASSWORD', 'test-password-not-a-placeholder')
    return Config


def test_config_validate_rejects_simulation_postgres_with_project_file(
    config_without_unrelated_errors, monkeypatch
):
    """Die Regel muss an `Config.validate()` hängen, nicht nur existieren."""
    monkeypatch.setattr(Config, 'DATABASE_URL', URL)
    monkeypatch.setattr(Config, 'PROJECT_BACKEND', 'file')
    monkeypatch.setattr(Config, 'SIMULATION_BACKEND', 'postgres')

    errors = [e for e in Config.validate() if 'AGORA_SIMULATION_BACKEND' in e]

    assert len(errors) == 1
    assert 'AGORA_PROJECT_BACKEND=postgres' in errors[0]


def test_config_validate_accepts_simulation_and_project_on_postgres(
    config_without_unrelated_errors, monkeypatch
):
    monkeypatch.setattr(Config, 'DATABASE_URL', URL)
    monkeypatch.setattr(Config, 'PROJECT_BACKEND', 'postgres')
    monkeypatch.setattr(Config, 'SIMULATION_BACKEND', 'postgres')

    assert [e for e in Config.validate() if 'AGORA_SIMULATION_BACKEND' in e] == []


def test_factory_default_is_file_adapter(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, 'SIMULATION_BACKEND', 'file')

    assert isinstance(
        get_simulation_repository(simulations_dir=str(tmp_path)),
        FileSimulationRepository,
    )


def test_factory_postgres_returns_adapter_without_connecting(monkeypatch):
    """Der Adapter löst die Datenbank erst beim ersten Zugriff auf."""
    from app.infrastructure.postgres.repositories import PostgresSimulationRepository

    monkeypatch.setattr(Config, 'SIMULATION_BACKEND', 'postgres')

    assert isinstance(get_simulation_repository(), PostgresSimulationRepository)


def test_factory_rejects_unknown_value_instead_of_falling_back(monkeypatch):
    monkeypatch.setattr(Config, 'SIMULATION_BACKEND', 'sqlite')

    with pytest.raises(SimulationBackendUnavailable):
        get_simulation_repository()
