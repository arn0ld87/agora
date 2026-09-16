"""Alembic-Laufzeitumgebung für Agora (docs/plans/supabase.md §8).

Die Verbindung kommt aus `DATABASE_URL`, nicht aus `alembic.ini`: eine
Zeichenkette mit Passwort gehört nicht in eine versionierte Datei. Gelesen
wird sie über denselben Adapter wie im Anwendungscode, damit Migration und
Laufzeit nicht mit zwei verschiedenen Treibern oder Schemata arbeiten.

`target_metadata` ist noch `None`. Agora hat in dieser Phase keine
ORM-Modelle — das Datenmodell entsteht in Phase 3 (§9). Bis dahin sind
Migrationen von Hand geschrieben, und `--autogenerate` würde jede vorhandene
Tabelle als zu löschen vorschlagen.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# `backend/` auf den Pfad, damit `app.*` importierbar ist. `prepend_sys_path`
# in alembic.ini deckt den Normalfall ab; dieser Block hält auch den Aufruf
# aus einem anderen Arbeitsverzeichnis am Leben.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.infrastructure.postgres import normalize_database_url  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Kein ORM-Metadata bis Phase 3 (§9). Siehe Modul-Docstring.
target_metadata = None

# Fachschema. `public` bleibt möglichst leer, damit Fachtabellen nicht in
# einem direkt über PostgREST exponierten Schema landen (§9).
AGORA_SCHEMA = 'agora'


def _database_url() -> str:
    """`DATABASE_URL` aus der Umgebung, auf das psycopg-3-Schema normalisiert."""
    raw = os.environ.get('DATABASE_URL', '')
    if not raw.strip():
        raise RuntimeError(
            'DATABASE_URL is not set — alembic needs it to reach the database '
            '(e.g. postgresql+psycopg://user:password@host:5432/dbname)'
        )
    return normalize_database_url(raw)


def run_migrations_offline() -> None:
    """`--sql`-Modus: erzeugt SQL, ohne sich zu verbinden."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        include_schemas=True,
        version_table_schema=None,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Normalfall: verbindet und wendet die Migrationen an."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration['sqlalchemy.url'] = _database_url()

    connectable = engine_from_config(
        configuration,
        prefix='sqlalchemy.',
        # NullPool: der Alembic-Prozess lebt für einen Lauf. Ein Pool wäre
        # hier nur eine Quelle offen bleibender Verbindungen.
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            # `alembic_version` bleibt in `public`. In `agora` wäre es ein
            # Henne-Ei-Problem: die Tabelle müsste in dem Schema liegen, das
            # die erste Migration erst anlegt.
            version_table_schema=None,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
