"""PostgreSQL-Backup-, Restore- und Verifikations-Roundtrip (Issue #1583).

Der eigentliche Fresh-Host-Drill (echter Host, echter Docker-Daemon, echtes
Backup) bleibt #766/S13. Was hier läuft, ist der Kern des Nachweises: ein
``pg_dump -n agora`` einer echten Datenbank, ein ``pg_restore`` in eine
zweite, und ``restore_verify.py`` gegen das dabei erzeugte
``postgres-manifest.json`` — inklusive der drei Arten, wie das rot werden
muss, damit der grüne Fall etwas wert ist: eine fehlende Zeile, ein Projekt
ohne Verzeichnis, eine falsche Revision.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Iterator
from unittest import mock

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import Config
from app.contracts import Project
from app.infrastructure.postgres import reset_database
from app.infrastructure.postgres import pg_cli
from app.infrastructure.postgres.repositories.project_repository import (
    PostgresProjectRepository,
)
from app.infrastructure.postgres.session import Database
from scripts.postgres_backup_manifest import build_manifest
from scripts.restore_verify import run_verification

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'

# Vom Auftrag vorgegeben: Version 16, beide Binaries unter /usr/bin.
_PG_DUMP = shutil.which('pg_dump')
_PG_RESTORE = shutil.which('pg_restore')


def _require_pg_binaries() -> None:
    """CI soll failen, nicht skippen — derselbe Mechanismus wie
    ``postgres_database_url`` in ``conftest.py`` (``_skip_or_fail``)."""
    from tests.integration.conftest import _skip_or_fail

    if _PG_DUMP is None or _PG_RESTORE is None:
        _skip_or_fail('pg_dump/pg_restore nicht in PATH gefunden.')


@pytest.fixture
def target_database_url(postgres_database_url: str) -> Iterator[str]:
    """Eine zweite, leere disposable Datenbank — das Restore-Ziel.

    ``postgres_database_url`` liefert nur eine. Der Roundtrip braucht zwei:
    eine echte Quelle mit Migrationen und Daten, ein leeres Ziel, das der
    Restore erst füllt.
    """
    admin_url = os.environ['AGORA_TEST_POSTGRES_URL']
    database_name = f'agora_itest_target_{uuid.uuid4().hex}'
    parsed_url = make_url(admin_url)
    test_url = parsed_url.set(database=database_name)
    admin_engine = create_engine(parsed_url, isolation_level='AUTOCOMMIT')

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    try:
        yield test_url.render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    'SELECT pg_terminate_backend(pid) '
                    'FROM pg_stat_activity '
                    'WHERE datname = :database_name '
                    'AND pid <> pg_backend_pid()'
                ),
                {'database_name': database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin_engine.dispose()


@pytest.fixture
def source_db(postgres_database_url: str) -> Iterator[Database]:
    """Quelldatenbank auf Alembic-Head, mit einem Beispielprojekt."""
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    os.environ['DATABASE_URL'] = postgres_database_url
    try:
        command.upgrade(config, 'head')
    finally:
        del os.environ['DATABASE_URL']

    database = Database(postgres_database_url, use_pool=False)
    try:
        yield database
    finally:
        database.dispose()


def _run_pg_cli(tool: str, database_url: str, dump_path: Path) -> None:
    """Derselbe Weg wie ``restore-drill.sh``: ``pg_cli`` startet das Werkzeug
    selbst, das Passwort geht nur über ``PGPASSWORD`` an den Kindprozess."""
    with mock.patch.dict(os.environ, {'DATABASE_URL': database_url}):
        assert pg_cli.main([tool, '--file', str(dump_path)]) == 0


def _dump(source_url: str, dump_path: Path) -> None:
    _run_pg_cli('dump', source_url, dump_path)


def _restore(target_url: str, dump_path: Path) -> None:
    _run_pg_cli('restore', target_url, dump_path)


def _stamp(target_url: str, revision: str, monkeypatch) -> None:
    """Was ``restore-drill.sh`` nach ``pg_restore`` tut: ``alembic_version``
    liegt in ``public`` und ist nicht im Dump, also wird die Revision aus dem
    Manifest nachgestempelt."""
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    monkeypatch.setenv('DATABASE_URL', target_url)
    command.stamp(config, revision)


def _write_project_directory(root: Path, project_id: str) -> None:
    directory = root / 'projects' / project_id / 'files'
    directory.mkdir(parents=True)
    (directory / 'quelle.pdf').write_text('Inhalt', encoding='utf-8')


class TestRoundtrip:
    """Der grüne Fall: Backup, Restore, Verifikation — alles stimmt."""

    def test_a_faithful_restore_passes_verification(
        self, tmp_path, source_db, target_database_url, monkeypatch
    ) -> None:
        _require_pg_binaries()
        project = Project(
            project_id='proj_1583backupok',
            name='Backup-Roundtrip',
            created_at='2026-01-01T00:00:00',
            updated_at='2026-01-01T00:00:00',
        )
        PostgresProjectRepository(database=source_db).add_existing(project)

        uploads = tmp_path / 'uploads'
        _write_project_directory(uploads, project.project_id)

        manifest = build_manifest(str(source_db._url))  # noqa: SLF001 - Testzugriff auf den Adapter
        manifest_path = tmp_path / 'postgres-manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

        dump_path = tmp_path / 'postgres.dump'
        _dump(str(source_db._url), dump_path)  # noqa: SLF001
        _restore(target_database_url, dump_path)
        _stamp(target_database_url, manifest['revision'], monkeypatch)

        monkeypatch.setattr(Config, 'DATABASE_URL', target_database_url)
        monkeypatch.setattr(Config, 'PROJECT_BACKEND', 'postgres')
        reset_database()
        try:
            report = run_verification(
                uploads,
                uploads,
                postgres_manifest=manifest_path,
                migrations_dir=MIGRATIONS_DIR,
            )
        finally:
            reset_database()

        postgres_checks = {c.name: c for c in report.checks if c.section == 'PostgreSQL'}
        assert postgres_checks, 'kein PostgreSQL-Abschnitt geprüft — Backend nicht erkannt?'
        for name, check in postgres_checks.items():
            assert check.ok and not check.skipped, f'{name}: {check.detail}'


class TestRoundtripCatchesDrift:
    """Der eigentliche Nachweis: die drei Arten, wie das rot werden muss."""

    def _prepare(
        self, tmp_path, source_db, target_database_url, monkeypatch, stamp=True
    ) -> tuple[Path, dict]:
        project = Project(
            project_id='proj_1583backupbad',
            name='Backup-Roundtrip',
            created_at='2026-01-01T00:00:00',
            updated_at='2026-01-01T00:00:00',
        )
        PostgresProjectRepository(database=source_db).add_existing(project)

        uploads = tmp_path / 'uploads'
        _write_project_directory(uploads, project.project_id)

        manifest = build_manifest(str(source_db._url))  # noqa: SLF001

        dump_path = tmp_path / 'postgres.dump'
        _dump(str(source_db._url), dump_path)  # noqa: SLF001
        _restore(target_database_url, dump_path)
        if stamp:
            _stamp(target_database_url, manifest['revision'], monkeypatch)

        return uploads, manifest

    def test_a_project_without_its_directory_fails_verification(
        self, tmp_path, source_db, target_database_url, monkeypatch
    ) -> None:
        _require_pg_binaries()
        uploads, manifest = self._prepare(tmp_path, source_db, target_database_url, monkeypatch)
        # Das Projektverzeichnis fehlt — als hätte ein Restore die Metadaten,
        # aber nicht die Artefakte zurückgespielt.
        shutil.rmtree(uploads / 'projects' / 'proj_1583backupbad')

        manifest_path = tmp_path / 'postgres-manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

        monkeypatch.setattr(Config, 'DATABASE_URL', target_database_url)
        reset_database()
        try:
            report = run_verification(
                uploads,
                uploads,
                postgres_manifest=manifest_path,
                migrations_dir=MIGRATIONS_DIR,
                require_postgres=True,
            )
        finally:
            reset_database()

        check = next(
            c
            for c in report.checks
            if c.name == 'agora.projects referenziert vorhandene Projektverzeichnisse'
        )
        assert not check.ok
        assert 'proj_1583backupbad' in check.detail

    def test_a_missing_row_fails_the_row_count_check(
        self, tmp_path, source_db, target_database_url, monkeypatch
    ) -> None:
        _require_pg_binaries()
        uploads, manifest = self._prepare(tmp_path, source_db, target_database_url, monkeypatch)

        manifest_path = tmp_path / 'postgres-manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

        # Eine Zeile verschwindet nach dem Restore — als hätte ein
        # gleichzeitiger Schreibvorgang sie verloren.
        target_db = Database(target_database_url, use_pool=False)
        try:
            with target_db.session() as session:
                session.execute(text('DELETE FROM agora.projects'))
        finally:
            target_db.dispose()

        monkeypatch.setattr(Config, 'DATABASE_URL', target_database_url)
        reset_database()
        try:
            report = run_verification(
                uploads,
                uploads,
                postgres_manifest=manifest_path,
                migrations_dir=MIGRATIONS_DIR,
                require_postgres=True,
            )
        finally:
            reset_database()

        check = next(
            c
            for c in report.checks
            if c.name == 'Zeilenzahl je Tabelle stimmt mit Manifest ueberein'
        )
        assert not check.ok
        assert 'projects' in check.detail

    def test_a_wrong_revision_in_the_manifest_fails_the_alembic_head_check(
        self, tmp_path, source_db, target_database_url, monkeypatch
    ) -> None:
        _require_pg_binaries()
        uploads, manifest = self._prepare(tmp_path, source_db, target_database_url, monkeypatch)
        manifest['revision'] = 'deadbeef0000'

        manifest_path = tmp_path / 'postgres-manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

        monkeypatch.setattr(Config, 'DATABASE_URL', target_database_url)
        reset_database()
        try:
            report = run_verification(
                uploads,
                uploads,
                postgres_manifest=manifest_path,
                migrations_dir=MIGRATIONS_DIR,
                require_postgres=True,
            )
        finally:
            reset_database()

        check = next(
            c
            for c in report.checks
            if c.name == 'Alembic-Head stimmt mit Backup-Manifest ueberein'
        )
        assert not check.ok
        assert 'deadbeef0000' in check.detail

    def test_a_restore_without_stamped_revision_fails_the_alembic_head_check(
        self, tmp_path, source_db, target_database_url, monkeypatch
    ) -> None:
        """``pg_dump -n agora`` enthält ``public.alembic_version`` nicht. Ohne
        Nachstempeln startete die App wegen des Start-Gates (#1582) nicht —
        die Verifikation muss das vorher melden."""
        _require_pg_binaries()
        uploads, manifest = self._prepare(
            tmp_path, source_db, target_database_url, monkeypatch, stamp=False
        )

        manifest_path = tmp_path / 'postgres-manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

        monkeypatch.setattr(Config, 'DATABASE_URL', target_database_url)
        reset_database()
        try:
            report = run_verification(
                uploads,
                uploads,
                postgres_manifest=manifest_path,
                migrations_dir=MIGRATIONS_DIR,
                require_postgres=True,
            )
        finally:
            reset_database()

        check = next(
            c
            for c in report.checks
            if c.name == 'Alembic-Head stimmt mit Backup-Manifest ueberein'
        )
        assert not check.ok
        assert 'Datenbank=keine' in check.detail
