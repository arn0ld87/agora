"""Backup-Manifest für das Schema ``agora`` (Issue #1583).

Hält fest, was ein Restore hinterher gegenprüfen muss: die Alembic-Revision,
auf der die Quelldatenbank beim Backup stand, und die Zeilenzahl je Tabelle
im Schema ``agora``. ``restore_verify.py`` prüft nach dem Restore dagegen.

**Dieselbe Sicht wie der Dump.** ``collect_manifest`` nimmt eine Verbindung
entgegen, statt selbst eine aufzubauen: ``pg_cli dump`` exportiert in einer
``REPEATABLE READ``-Transaktion einen Snapshot, lässt ``pg_dump --snapshot``
darauf laufen und erhebt das Manifest in derselben Transaktion. Ein
Schreibvorgang zwischen Dump und Zählung kann so keinen Unterschied erzeugen
(Codex-Review auf #1602).

``alembic_version`` liegt in ``public`` (``migrations/env.py``) und ist nicht
Teil von ``pg_dump -n agora``; die Revision kommt deshalb ins Manifest und
wird beim Restore nachgestempelt (``pg_cli restore``).
"""

from __future__ import annotations

from typing import Any

from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, text

from .models import AGORA_SCHEMA
from .session import Database


def _current_revision(connection: Connection) -> str:
    heads = MigrationContext.configure(connection).get_current_heads()
    if len(heads) != 1:
        raise RuntimeError(
            f'Erwartet genau eine aktuelle Revision in der Quelldatenbank, gefunden: {heads!r}'
        )
    return heads[0]


def _row_counts(connection: Connection) -> dict[str, int]:
    """Zeilenzahl je Tabelle in ``agora`` — ohne hartkodierte Tabellenliste."""
    tables = (
        connection.execute(
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
    counts: dict[str, int] = {}
    for table in tables:
        # Tabellennamen kommen aus information_schema des eigenen,
        # migrationsverwalteten Schemas, nicht aus Nutzereingabe.
        count = connection.execute(
            text(f'SELECT COUNT(*) FROM {AGORA_SCHEMA}."{table}"')  # noqa: S608
        ).scalar_one()
        counts[table] = int(count)
    return counts


def collect_manifest(connection: Connection) -> dict[str, Any]:
    """Revision und Zeilenzahlen über eine bestehende Verbindung."""
    return {
        'revision': _current_revision(connection),
        'row_counts': _row_counts(connection),
    }


def build_manifest(database_url: str) -> dict[str, Any]:
    """Manifest über eine eigene, poollose Verbindung (ohne Snapshot)."""
    database = Database(database_url, use_pool=False)
    try:
        with database.engine.connect() as connection:
            return collect_manifest(connection)
    finally:
        database.dispose()
