"""Erzeugt das PostgreSQL-Backup-Manifest (Issue #1583).

Hält fest, was ein Restore hinterher gegenprüfen muss: die Alembic-Revision,
auf der die Quelldatenbank *zum Zeitpunkt des Backups* tatsächlich stand, und
die Zeilenzahl je Tabelle im Schema ``agora``. Ohne dieses Manifest wäre
``restore_verify.py`` blind — es könnte nur prüfen, DASS irgendeine Datenbank
existiert, nicht ob sie den erwarteten Stand hat.

**Warum die Revision live aus der Quelldatenbank kommt, nicht aus dem Dump.**
``pg_dump -n agora`` sichert bewusst nur das Fachschema; ``alembic_version``
liegt in ``public`` (``migrations/env.py``: „In `agora` wäre es ein
Henne-Ei-Problem" — die Tabelle müsste in dem Schema liegen, das die erste
Migration erst anlegt) und ist damit nie Teil dieses Dumps. Der Vergleich, den
``restore_verify.py`` nach dem Restore zieht, ist deshalb: „stand die
Quelldatenbank beim Backup auf dem Revisionskopf, den ``backend/migrations/``
zum Zeitpunkt der Verifikation kennt" — nicht ein Blick in eine Tabelle, die
dieser Dump nie enthält.

Aufruf (aus ``backend/``, ``DATABASE_URL`` gesetzt)::

    uv run python scripts/postgres_backup_manifest.py --output /pfad/postgres-manifest.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.infrastructure.postgres.models import AGORA_SCHEMA  # noqa: E402
from app.infrastructure.postgres.session import Database  # noqa: E402


def _current_revision(database: Database) -> str:
    """Die Alembic-Revision, auf der die Quelldatenbank gerade steht.

    ``MigrationContext`` statt eines rohen ``SELECT * FROM alembic_version``:
    der Zugriffsweg bleibt so unabhängig davon, wo/wie Alembic seine
    Versionstabelle intern führt.
    """
    with database.engine.connect() as connection:
        context = MigrationContext.configure(connection)
        heads = context.get_current_heads()
    if len(heads) != 1:
        raise RuntimeError(
            f'Erwartet genau eine aktuelle Revision in der Quelldatenbank, gefunden: {heads!r}'
        )
    return heads[0]


def _row_counts(database: Database) -> dict[str, int]:
    """Zeilenzahl je Tabelle im Schema ``agora``.

    Keine hartkodierte Tabellenliste: eine künftige Tabelle zählt automatisch
    mit, ohne dass dieses Skript nachgezogen werden müsste.
    """
    counts: dict[str, int] = {}
    with database.session() as session:
        tables = (
            session.execute(
                text(
                    'SELECT table_name FROM information_schema.tables '
                    'WHERE table_schema = :schema AND table_type = :kind '
                    'ORDER BY table_name'
                ),
                {'schema': AGORA_SCHEMA, 'kind': 'BASE TABLE'},
            )
            .scalars()
            .all()
        )
        for table in tables:
            # Tabellennamen kommen aus information_schema (unser eigenes,
            # migrationsverwaltetes Schema), nicht aus Nutzereingabe.
            count = session.execute(
                text(f'SELECT COUNT(*) FROM {AGORA_SCHEMA}."{table}"')  # noqa: S608
            ).scalar_one()
            counts[table] = int(count)
    return counts


def build_manifest(database_url: str) -> dict:
    """Baut das Manifest gegen eine frische, poollose Verbindung.

    ``use_pool=False``: dieser Prozess lebt für einen Aufruf, ein Pool wäre
    nur eine Quelle offen bleibender Verbindungen.
    """
    database = Database(database_url, use_pool=False)
    try:
        return {
            'revision': _current_revision(database),
            'row_counts': _row_counts(database),
        }
    finally:
        database.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--output', type=Path, required=True, help='Zielpfad für postgres-manifest.json'
    )
    args = parser.parse_args(argv)

    database_url = os.environ.get('DATABASE_URL', '')
    if not database_url.strip():
        print('DATABASE_URL is not set', file=sys.stderr)
        return 1

    manifest = build_manifest(database_url)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    print(f'Postgres-Manifest geschrieben: {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
