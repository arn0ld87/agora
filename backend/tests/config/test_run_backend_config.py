"""Config-Vertrag für `AGORA_RUN_BACKEND` (Issue #1587).

Zwei Zusagen: der Default bleibt die Datei und braucht keine Datenbank, und
`postgres` ist nur zusammen mit `AGORA_SIMULATION_BACKEND=postgres` zulässig —
`agora.runs.simulation_id` ist ein Fremdschlüssel auf `agora.simulations`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import RUN_BACKENDS, Config, validate_run_backend
from app.repositories.run_repository import RunBackendUnavailable, get_run_repository
from app.services.file_run_store import FileRunRepository

URL = 'postgresql+psycopg://u:p@host:5432/db'
BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_run_backends_are_exactly_file_and_postgres():
    assert RUN_BACKENDS == frozenset({'file', 'postgres'})


def test_default_is_file_without_environment_or_dotenv():
    """Der Default selbst, nicht der Wert dieser Testumgebung.

    Eigener Prozess, damit weder eine gesetzte ``AGORA_RUN_BACKEND`` noch
    eine lokale ``.env`` (``load_dotenv`` wird vor dem Import abgeschaltet)
    noch ein Reload von ``app.config`` den übrigen Tests hineinspielt
    (CodeRabbit-Review auf #1605).
    """
    env = {k: v for k, v in os.environ.items() if k != 'AGORA_RUN_BACKEND'}
    probe = (
        'import dotenv; dotenv.load_dotenv = lambda *a, **k: False; '
        'from app.config import Config; print(Config.RUN_BACKEND)'
    )
    result = subprocess.run(
        [sys.executable, '-c', probe],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )

    assert result.stdout.strip().splitlines()[-1] == 'file'


def test_file_needs_no_database_url():
    assert validate_run_backend('file', '', 'file') == []


def test_file_is_accepted_whatever_the_simulation_backend():
    assert validate_run_backend('file', '', 'postgres') == []


def test_unknown_value_is_rejected():
    errors = validate_run_backend('postgress', URL, 'postgres')

    assert len(errors) == 1
    assert "unknown value 'postgress'" in errors[0]


def test_postgres_with_simulation_backend_file_is_rejected():
    errors = validate_run_backend('postgres', URL, 'file')

    assert len(errors) == 1
    assert 'AGORA_SIMULATION_BACKEND=postgres' in errors[0]


def test_postgres_without_database_url_is_rejected():
    errors = validate_run_backend('postgres', '  ', 'postgres')

    assert len(errors) == 1
    assert 'DATABASE_URL' in errors[0]


def test_postgres_with_simulation_postgres_and_url_is_accepted():
    assert validate_run_backend('postgres', URL, 'postgres') == []


def test_values_are_normalised():
    assert validate_run_backend(' Postgres ', URL, ' POSTGRES ') == []


@pytest.fixture
def config_without_unrelated_errors(monkeypatch):
    monkeypatch.setattr(Config, 'DEBUG', True)
    monkeypatch.setattr(Config, 'SECRET_KEY', 'test-secret-not-a-placeholder')
    monkeypatch.setattr(Config, 'LLM_API_KEY', 'ollama')
    monkeypatch.setattr(Config, 'NEO4J_URI', 'bolt://localhost:7687')
    monkeypatch.setattr(Config, 'NEO4J_PASSWORD', 'test-password-not-a-placeholder')
    return Config


def test_config_validate_rejects_run_postgres_with_simulation_file(
    config_without_unrelated_errors, monkeypatch
):
    """Die Regel muss an `Config.validate()` hängen, nicht nur existieren."""
    monkeypatch.setattr(Config, 'DATABASE_URL', URL)
    monkeypatch.setattr(Config, 'PROJECT_BACKEND', 'postgres')
    monkeypatch.setattr(Config, 'SIMULATION_BACKEND', 'file')
    monkeypatch.setattr(Config, 'RUN_BACKEND', 'postgres')

    errors = [e for e in Config.validate() if 'AGORA_RUN_BACKEND' in e]

    assert len(errors) == 1
    assert 'AGORA_SIMULATION_BACKEND=postgres' in errors[0]


def test_config_validate_rejects_unknown_run_backend(
    config_without_unrelated_errors, monkeypatch
):
    monkeypatch.setattr(Config, 'RUN_BACKEND', 'sqlite')

    errors = [e for e in Config.validate() if 'AGORA_RUN_BACKEND' in e]

    assert len(errors) == 1
    assert "unknown value 'sqlite'" in errors[0]


def test_config_validate_accepts_the_full_postgres_chain(
    config_without_unrelated_errors, monkeypatch
):
    monkeypatch.setattr(Config, 'DATABASE_URL', URL)
    monkeypatch.setattr(Config, 'PROJECT_BACKEND', 'postgres')
    monkeypatch.setattr(Config, 'SIMULATION_BACKEND', 'postgres')
    monkeypatch.setattr(Config, 'RUN_BACKEND', 'postgres')

    assert [e for e in Config.validate() if 'AGORA_RUN_BACKEND' in e] == []


def test_factory_default_is_file_adapter(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, 'RUN_BACKEND', 'file')

    repo = get_run_repository(registry_dir=str(tmp_path))

    assert isinstance(repo, FileRunRepository)
    assert repo.registry_dir == str(tmp_path)


def test_factory_postgres_returns_adapter_without_connecting(monkeypatch):
    """Der Adapter löst die Datenbank erst beim ersten Zugriff auf."""
    from app.infrastructure.postgres.repositories import PostgresRunRepository

    monkeypatch.setattr(Config, 'RUN_BACKEND', 'postgres')

    assert isinstance(get_run_repository(), PostgresRunRepository)


def test_factory_rejects_unknown_value_instead_of_falling_back(monkeypatch):
    monkeypatch.setattr(Config, 'RUN_BACKEND', 'sqlite')

    with pytest.raises(RunBackendUnavailable):
        get_run_repository()


def test_run_backend_counts_for_schema_gate_backup_and_readiness(monkeypatch):
    """Alembic-Drift-Gate, Backup und Readiness fragen
    ``active_postgres_backends`` — der neue Schalter muss dort mitzählen."""
    from app.infrastructure.postgres.backends import active_postgres_backends

    monkeypatch.setattr(Config, 'RUN_BACKEND', 'postgres')

    assert 'RUN_BACKEND' in active_postgres_backends(Config)
