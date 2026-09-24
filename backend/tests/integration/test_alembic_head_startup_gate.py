"""Startabbruch bei Alembic-Drift gegen eine echte Datenbank (#1582).

Zwei Ebenen: das Gate-Modul direkt (``verify_schema_at_head``) gegen eine
tatsächlich hochgezogene PostgreSQL-Instanz, und ``create_app`` mit
``AGORA_PROJECT_BACKEND=postgres`` — die Stelle, an der der Betreiber den
Fehler tatsächlich zu sehen bekäme.

``create_app`` braucht kein Neo4j/Redis: ``Neo4jStorage()`` fängt seinen
eigenen Verbindungsfehler ab und setzt ``None`` (siehe ``app/__init__.py``),
Redis wird an dieser Stelle im Boot-Pfad noch nicht angefasst. Das Muster für
einen durchlaufenden ``create_app()``-Aufruf ohne echte Infrastruktur folgt
``tests/test_app_startup_reconciliation.py::_prepare_startup_env``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

from app.infrastructure.postgres.schema_gate import SchemaDriftError, verify_schema_at_head
from app.services.run_registry import RunRegistry

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'


def _bare_alembic_config() -> AlembicConfig:
    """Nur für ``ScriptDirectory``-Lookups — liest keine Datenbank, führt
    ``env.py`` nicht aus, braucht deshalb kein ``DATABASE_URL``."""
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    return config


def _alembic_config(database_url: str, monkeypatch) -> AlembicConfig:
    """``env.py`` liest ``DATABASE_URL`` aus der Umgebung, nicht aus der Config
    (siehe ``migrations/env.py::_database_url``) — dieselbe Notwendigkeit wie
    in ``tests/integration/test_postgres_project_migration.py::migrated_db``.
    """
    monkeypatch.setenv('DATABASE_URL', database_url)
    return _bare_alembic_config()


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(_bare_alembic_config())


def _head_revision() -> str:
    heads = _script_directory().get_heads()
    assert len(heads) == 1, f'Test setzt genau einen Head voraus, gefunden: {heads}'
    return heads[0]


def _previous_revision(head: str) -> str:
    """Die Revision unmittelbar vor ``head`` — für den ``upgrade(..., f'{head}-1')``-Zustand.

    ``ScriptDirectory.get_revision`` versteht keine relative Syntax wie
    ``<head>-1`` (das ist ein ``alembic upgrade``-Ausdruck, kein Lookup-Key) —
    der direkte Weg ist ``down_revision`` des Head-Scripts.
    """
    resolved = _script_directory().get_revision(head)
    assert resolved is not None
    assert isinstance(resolved.down_revision, str), (
        f'Test setzt eine lineare Migrationslinie voraus, gefunden: {resolved.down_revision}'
    )
    return resolved.down_revision


class TestVerifySchemaAtHeadAgainstRealDatabase:
    def test_previous_revision_raises_with_both_revisions_named(
        self, postgres_database_url: str, monkeypatch
    ) -> None:
        config = _alembic_config(postgres_database_url, monkeypatch)
        head = _head_revision()
        previous = _previous_revision(head)
        command.upgrade(config, f'{head}-1')

        with pytest.raises(SchemaDriftError) as excinfo:
            verify_schema_at_head(postgres_database_url, MIGRATIONS_DIR)

        message = str(excinfo.value)
        assert head in message
        assert previous in message
        assert 'alembic upgrade head' in message

    def test_empty_database_raises_no_revision_found(
        self, postgres_database_url: str
    ) -> None:
        with pytest.raises(SchemaDriftError) as excinfo:
            verify_schema_at_head(postgres_database_url, MIGRATIONS_DIR)

        message = str(excinfo.value)
        assert 'Keine Alembic-Revision' in message
        assert 'alembic upgrade head' in message
        assert head_is_named_in(message)

    def test_head_revision_passes(self, postgres_database_url: str, monkeypatch) -> None:
        config = _alembic_config(postgres_database_url, monkeypatch)
        command.upgrade(config, 'head')

        verify_schema_at_head(postgres_database_url, MIGRATIONS_DIR)  # darf nicht werfen

    def test_unknown_newer_revision_does_not_advise_upgrade(
        self, postgres_database_url: str, monkeypatch
    ) -> None:
        """Rückweg auf älteren Code: die DB trägt eine Revision, die der Code
        nicht kennt. ``upgrade head`` wäre dann der falsche Rat."""
        from sqlalchemy import create_engine, text

        config = _alembic_config(postgres_database_url, monkeypatch)
        command.upgrade(config, 'head')
        engine = create_engine(postgres_database_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE alembic_version SET version_num = 'ffffffffffff'")
                )
        finally:
            engine.dispose()

        with pytest.raises(SchemaDriftError) as excinfo:
            verify_schema_at_head(postgres_database_url, MIGRATIONS_DIR)

        message = str(excinfo.value)
        assert 'neuer als der Code' in message
        assert 'ffffffffffff' in message
        assert 'upgrade head' not in message

    def test_no_url_or_password_leaks_into_the_message(
        self, postgres_database_url: str
    ) -> None:
        with pytest.raises(SchemaDriftError) as excinfo:
            verify_schema_at_head(postgres_database_url, MIGRATIONS_DIR)

        message = str(excinfo.value)
        assert postgres_database_url not in message
        # grobe Heuristik: kein `://` (Schema-Trenner einer URL) in der Meldung
        assert '://' not in message


def head_is_named_in(message: str) -> bool:
    return _head_revision() in message


@pytest.fixture
def _reset_run_registry(tmp_path, monkeypatch) -> Iterator[None]:
    monkeypatch.setattr(RunRegistry, 'REGISTRY_DIR', str(tmp_path / 'run_registry'))
    RunRegistry._instance = None
    yield
    RunRegistry._instance = None


def _prepare_startup_env(monkeypatch) -> None:
    """Bringt ``create_app()`` bis zum Gate durch, ohne echte Neo4j/Redis-Infra.

    Analog ``tests/test_app_startup_reconciliation.py::_prepare_startup_env``.
    """
    monkeypatch.setenv('FLASK_DEBUG', 'false')
    monkeypatch.setenv('AGORA_ALLOW_ANONYMOUS', 'true')
    monkeypatch.delenv('AGORA_CORS_ALLOW_ALL', raising=False)

    from app.config import Config as _Config

    monkeypatch.setattr(_Config, 'DEBUG', False)
    monkeypatch.setattr(_Config, 'SECRET_KEY', 'test-secret-key-not-a-placeholder')
    monkeypatch.setattr(_Config, 'NEO4J_PASSWORD', 'test-neo4j-password')

    monkeypatch.setattr(
        'app.storage.embedding_service.validate_embedding_configuration',
        lambda skip_probe=False: 768,
    )


class TestCreateAppAbortsOnSchemaDrift:
    def test_create_app_raises_when_project_backend_is_behind_head(
        self, postgres_database_url: str, monkeypatch, _reset_run_registry
    ) -> None:
        config = _alembic_config(postgres_database_url, monkeypatch)
        head = _head_revision()
        command.upgrade(config, f'{head}-1')

        _prepare_startup_env(monkeypatch)
        from app.config import Config as _Config

        monkeypatch.setattr(_Config, 'PROJECT_BACKEND', 'postgres')
        monkeypatch.setattr(_Config, 'DATABASE_URL', postgres_database_url)

        from app import create_app

        with pytest.raises(SchemaDriftError) as excinfo:
            create_app()

        assert head in str(excinfo.value)

    def test_create_app_starts_when_project_backend_is_at_head(
        self, postgres_database_url: str, monkeypatch, _reset_run_registry
    ) -> None:
        config = _alembic_config(postgres_database_url, monkeypatch)
        command.upgrade(config, 'head')

        _prepare_startup_env(monkeypatch)
        from app.config import Config as _Config

        monkeypatch.setattr(_Config, 'PROJECT_BACKEND', 'postgres')
        monkeypatch.setattr(_Config, 'DATABASE_URL', postgres_database_url)

        from app import create_app

        app = create_app()

        assert app is not None
