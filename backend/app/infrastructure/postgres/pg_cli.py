"""Verbindungsparameter für ``pg_dump``/``pg_restore`` aus ``DATABASE_URL`` (#1583).

``pg_dump``/``pg_restore`` verstehen weder ``postgresql+psycopg://`` noch ein
Passwort auf der Kommandozeile. Diese Datei zerlegt ``DATABASE_URL`` einmalig
in die Teile, die die beiden CLI-Tools über ``--host``/``--port``/
``--username``/``--dbname`` erwarten, und liefert das Passwort getrennt zur
Übergabe über die Umgebungsvariable ``PGPASSWORD`` — nie als Argument, nie
geloggt.

Aufruf aus der Shell (siehe ``scripts/restore-drill.sh``)::

    uv run python -m app.infrastructure.postgres.pg_cli status
    uv run python -m app.infrastructure.postgres.pg_cli dump --file postgres.dump --manifest postgres-manifest.json
    uv run python -m app.infrastructure.postgres.pg_cli restore --file postgres.dump --manifest postgres-manifest.json

``DATABASE_URL`` kommt aus ``Config`` — also aus der Umgebung oder der
``.env`` des Repositorys, genau wie für die Anwendung selbst (Codex-Review
auf #1602: eine nur in ``.env`` hinterlegte URL erreichte die Shell nie).
Das Passwort verlässt diesen Prozess ausschließlich über die Umgebung des
Kindprozesses — nie über ``stdout``, nie als Argument.

``dump`` exportiert in einer ``REPEATABLE READ``-Transaktion einen Snapshot,
lässt ``pg_dump --snapshot`` darauf laufen und erhebt das Manifest in
derselben Transaktion — Dump und Manifest beschreiben denselben Stand.
``restore`` spielt das Archiv zurück und stempelt danach die Revision aus
dem Manifest nach (``alembic_version`` liegt in ``public`` und ist nicht im
Dump).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url

from ...utils.logger import get_logger

logger = get_logger('agora.postgres.pg_cli')


@dataclass(frozen=True)
class PgConnectionParams:
    """Aus ``DATABASE_URL`` zerlegte Verbindungsdaten für ``pg_dump``/``pg_restore``."""

    host: str
    port: int
    user: str
    dbname: str
    password: str

    def cli_args(self) -> list[str]:
        """``host``/``port``/``user``/``dbname`` als Flags — niemals das Passwort."""
        return [
            f'--host={self.host}',
            f'--port={self.port}',
            f'--username={self.user}',
            f'--dbname={self.dbname}',
        ]

    def environ(self) -> dict[str, str]:
        """``PGPASSWORD`` für den Subprozess. Leer, wenn kein Passwort gesetzt ist.

        Das ist der einzige vorgesehene Weg, das Passwort an ``pg_dump``/
        ``pg_restore`` zu übergeben, ohne es in ``argv`` oder einem
        Prozess-Log sichtbar zu machen.
        """
        return {'PGPASSWORD': self.password} if self.password else {}


def parse_connection_params(database_url: str) -> PgConnectionParams:
    """Zerlegt eine SQLAlchemy-URL (jedes Treiber-Suffix) in ihre Bestandteile.

    ``make_url`` interessiert sich nicht für das Treiber-Suffix — anders als
    ``normalize_database_url`` muss hier nichts auf ``postgresql+psycopg://``
    korrigiert werden, es werden nur die Bestandteile ausgelesen.
    """
    url = make_url(database_url)
    return PgConnectionParams(
        host=url.host or 'localhost',
        port=url.port or 5432,
        user=url.username or '',
        dbname=url.database or '',
        password=url.password or '',
    )


#: Exit-Code von ``status``, wenn ein Backend auf ``postgres`` steht, aber
#: ``DATABASE_URL`` fehlt.
EXIT_MISSING_URL = 3


def build_command(
    tool: str, params: PgConnectionParams, dump_file: str, snapshot: str | None = None
) -> list[str]:
    """Die Befehlszeile für ``pg_dump``/``pg_restore`` — ohne Passwort."""
    # ``--enable-row-security``: Ohne diese Option setzen beide Werkzeuge
    # ``row_security = off`` und brechen ab, sobald eine Policy greift. Mit
    # ``FORCE ROW LEVEL SECURITY`` (#1615) gilt das auch für den Owner. Den
    # System-Kontext der Policies setzt ``_child_env`` über ``PGOPTIONS``.
    if tool == 'dump':
        command = [
            'pg_dump', *params.cli_args(), '-n', 'agora', '-Fc', '--enable-row-security',
            '-f', dump_file,
        ]
        if snapshot:
            command.append(f'--snapshot={snapshot}')
        return command
    if tool == 'restore':
        return [
            'pg_restore', *params.cli_args(), '--clean', '--if-exists',
            '--enable-row-security', dump_file,
        ]
    raise ValueError(f'unbekanntes Werkzeug: {tool}')


#: System-Kontext der RLS-Policies für ``pg_dump``/``pg_restore`` (#1615).
RLS_SYSTEM_OPTION = '-c agora.system=on'


def _child_env(params: PgConnectionParams) -> dict[str, str]:
    env = {**os.environ, **params.environ()}
    existing = env.get('PGOPTIONS', '').strip()
    env['PGOPTIONS'] = f'{existing} {RLS_SYSTEM_OPTION}'.strip()
    # DATABASE_URL trägt das Passwort ebenfalls; der Kindprozess braucht sie nicht.
    env.pop('DATABASE_URL', None)
    return env


def _database_url() -> str:
    """Owner-Verbindung, wenn getrennt konfiguriert (#1615), sonst ``DATABASE_URL``.

    Die Laufzeitrolle darf keine Tabelle besitzen. ``pg_restore --clean``
    muss Tabellen löschen und neu anlegen und braucht deshalb die Rolle, mit
    der auch die Migrationen laufen.
    """
    from app.config import Config

    migration_url = os.environ.get('AGORA_MIGRATION_DATABASE_URL', '').strip()
    return migration_url or (Config.DATABASE_URL or '').strip()


def _status() -> int:
    """Aktive Backends auf ``stdout``; Exit 3, wenn dann die URL fehlt."""
    from app.config import Config

    from .backends import active_postgres_backends

    active = active_postgres_backends(Config)
    sys.stdout.write(' '.join(active) + '\n')
    if active and not _database_url():
        return EXIT_MISSING_URL
    return 0


def _dump(url: str, params: PgConnectionParams, dump_file: str, manifest_file: str) -> int:
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    from .backup_manifest import collect_manifest
    from .engine import normalize_database_url

    engine = create_engine(normalize_database_url(url), poolclass=NullPool)
    try:
        with engine.connect() as connection:
            connection = connection.execution_options(isolation_level='REPEATABLE READ')
            snapshot = connection.execute(text('SELECT pg_export_snapshot()')).scalar_one()
            completed = subprocess.run(
                build_command('dump', params, dump_file, snapshot=snapshot),
                env=_child_env(params),
                check=False,
            )
            if completed.returncode != 0:
                return completed.returncode
            manifest = collect_manifest(connection)
            connection.rollback()
    finally:
        engine.dispose()

    with open(manifest_file, 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write('\n')
    logger.info('pg_dump und Manifest aus einem Snapshot geschrieben: %s', dump_file)
    return 0


def _restore(url: str, params: PgConnectionParams, dump_file: str, manifest_file: str) -> int:
    with open(manifest_file, encoding='utf-8') as handle:
        revision = json.load(handle)['revision']

    completed = subprocess.run(
        build_command('restore', params, dump_file), env=_child_env(params), check=False
    )
    if completed.returncode != 0:
        return completed.returncode

    from alembic import command
    from alembic.config import Config as AlembicConfig

    migrations_dir = Path(__file__).resolve().parents[3] / 'migrations'
    config = AlembicConfig(str(migrations_dir / 'alembic.ini'))
    config.set_main_option('script_location', str(migrations_dir))
    # migrations/env.py liest die Owner-URL aus der Umgebung dieses Prozesses —
    # nur für den Stempel gesetzt, danach wie vorher.
    previous = os.environ.get('AGORA_MIGRATION_DATABASE_URL')
    os.environ['AGORA_MIGRATION_DATABASE_URL'] = url
    try:
        command.stamp(config, revision)
    finally:
        if previous is None:
            os.environ.pop('AGORA_MIGRATION_DATABASE_URL', None)
        else:
            os.environ['AGORA_MIGRATION_DATABASE_URL'] = previous
    logger.info('Restore abgeschlossen, Alembic-Revision %s gestempelt', revision)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI-Einstieg für ``restore-drill.sh``."""
    parser = argparse.ArgumentParser(description='pg_dump/pg_restore für das Schema agora')
    parser.add_argument('tool', choices=('status', 'dump', 'restore'))
    parser.add_argument('--file', help='Pfad des Custom-Format-Archivs')
    parser.add_argument('--manifest', help='Pfad von postgres-manifest.json')
    args = parser.parse_args(argv)

    if args.tool == 'status':
        return _status()
    if not args.file or not args.manifest:
        parser.error('dump/restore brauchen --file und --manifest')

    url = _database_url()
    if not url:
        logger.error('DATABASE_URL is not set')
        return 1
    try:
        params = parse_connection_params(url)
    except Exception as exc:  # noqa: BLE001 - Fehlermeldung ohne Rohwert der URL
        logger.error('DATABASE_URL konnte nicht zerlegt werden: %s', type(exc).__name__)
        return 1

    if args.tool == 'dump':
        return _dump(url, params, args.file, args.manifest)
    return _restore(url, params, args.file, args.manifest)


if __name__ == '__main__':
    raise SystemExit(main())
