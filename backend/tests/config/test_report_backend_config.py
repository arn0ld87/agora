"""Config-Vertrag für `AGORA_REPORT_BACKEND` (Issue #1588).

Zwei Zusagen: der Default bleibt die Datei und braucht keine Datenbank, und
`postgres` ist nur zusammen mit `AGORA_SIMULATION_BACKEND=postgres` zulässig —
`agora.reports.simulation_id` ist ein Fremdschlüssel auf `agora.simulations`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import REPORT_BACKENDS, Config, validate_report_backend
from app.repositories.report_repository import ReportBackendUnavailable, get_report_repository
from app.services.file_report_store import FileReportRepository

URL = 'postgresql+psycopg://u:p@host:5432/db'
BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_report_backends_are_exactly_file_and_postgres():
    assert REPORT_BACKENDS == frozenset({'file', 'postgres'})


def test_default_is_file_without_environment_or_dotenv():
    """Der Default selbst, nicht der Wert dieser Testumgebung: eigener Prozess
    ohne ``AGORA_REPORT_BACKEND`` und ohne ``load_dotenv`` (CodeRabbit-Review
    auf #1607, dasselbe Muster wie für ``AGORA_RUN_BACKEND``)."""
    env = {k: v for k, v in os.environ.items() if k != 'AGORA_REPORT_BACKEND'}
    probe = (
        'import dotenv; dotenv.load_dotenv = lambda *a, **k: False; '
        'from app.config import Config; print(Config.REPORT_BACKEND)'
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
    assert validate_report_backend('file', '', 'file') == []


def test_file_is_accepted_whatever_the_simulation_backend():
    assert validate_report_backend('file', '', 'postgres') == []


def test_unknown_value_is_rejected():
    errors = validate_report_backend('postgress', URL, 'postgres')

    assert len(errors) == 1
    assert "unknown value 'postgress'" in errors[0]


def test_postgres_with_simulation_backend_file_is_rejected():
    errors = validate_report_backend('postgres', URL, 'file')

    assert len(errors) == 1
    assert 'AGORA_SIMULATION_BACKEND=postgres' in errors[0]


def test_postgres_without_database_url_is_rejected():
    errors = validate_report_backend('postgres', '  ', 'postgres')

    assert len(errors) == 1
    assert 'DATABASE_URL' in errors[0]


def test_postgres_with_simulation_postgres_and_url_is_accepted():
    assert validate_report_backend('postgres', URL, 'postgres') == []


def test_values_are_normalised():
    assert validate_report_backend(' Postgres ', URL, ' POSTGRES ') == []


@pytest.fixture
def config_without_unrelated_errors(monkeypatch):
    monkeypatch.setattr(Config, 'DEBUG', True)
    monkeypatch.setattr(Config, 'SECRET_KEY', 'test-secret-not-a-placeholder')
    monkeypatch.setattr(Config, 'LLM_API_KEY', 'ollama')
    monkeypatch.setattr(Config, 'NEO4J_URI', 'bolt://localhost:7687')
    monkeypatch.setattr(Config, 'NEO4J_PASSWORD', 'test-password-not-a-placeholder')
    return Config


def test_config_validate_rejects_report_postgres_with_simulation_file(
    config_without_unrelated_errors, monkeypatch
):
    """Die Regel muss an `Config.validate()` hängen, nicht nur existieren."""
    monkeypatch.setattr(Config, 'DATABASE_URL', URL)
    monkeypatch.setattr(Config, 'PROJECT_BACKEND', 'postgres')
    monkeypatch.setattr(Config, 'SIMULATION_BACKEND', 'file')
    monkeypatch.setattr(Config, 'REPORT_BACKEND', 'postgres')

    errors = [e for e in Config.validate() if 'AGORA_REPORT_BACKEND' in e]

    assert len(errors) == 1
    assert 'AGORA_SIMULATION_BACKEND=postgres' in errors[0]


def test_config_validate_rejects_unknown_report_backend(
    config_without_unrelated_errors, monkeypatch
):
    monkeypatch.setattr(Config, 'REPORT_BACKEND', 'sqlite')

    errors = [e for e in Config.validate() if 'AGORA_REPORT_BACKEND' in e]

    assert len(errors) == 1
    assert "unknown value 'sqlite'" in errors[0]


def test_config_validate_accepts_the_full_postgres_chain(
    config_without_unrelated_errors, monkeypatch
):
    monkeypatch.setattr(Config, 'DATABASE_URL', URL)
    monkeypatch.setattr(Config, 'PROJECT_BACKEND', 'postgres')
    monkeypatch.setattr(Config, 'SIMULATION_BACKEND', 'postgres')
    monkeypatch.setattr(Config, 'REPORT_BACKEND', 'postgres')

    assert [e for e in Config.validate() if 'AGORA_REPORT_BACKEND' in e] == []


def test_factory_default_is_file_adapter(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, 'REPORT_BACKEND', 'file')

    repo = get_report_repository(reports_dir=str(tmp_path))

    assert isinstance(repo, FileReportRepository)
    assert repo.reports_dir == str(tmp_path)


def test_factory_postgres_returns_adapter_without_connecting(monkeypatch):
    """Der Adapter löst die Datenbank erst beim ersten Zugriff auf."""
    from app.infrastructure.postgres.repositories import PostgresReportRepository

    monkeypatch.setattr(Config, 'REPORT_BACKEND', 'postgres')

    assert isinstance(get_report_repository(), PostgresReportRepository)


def test_factory_rejects_unknown_value_instead_of_falling_back(monkeypatch):
    monkeypatch.setattr(Config, 'REPORT_BACKEND', 'sqlite')

    with pytest.raises(ReportBackendUnavailable):
        get_report_repository()


def test_report_backend_counts_for_schema_gate_backup_and_readiness(monkeypatch):
    """Alembic-Drift-Gate, Backup und Readiness fragen
    ``active_postgres_backends`` — der neue Schalter muss dort mitzählen."""
    from app.infrastructure.postgres.backends import active_postgres_backends

    monkeypatch.setattr(Config, 'REPORT_BACKEND', 'postgres')

    assert 'REPORT_BACKEND' in active_postgres_backends(Config)
