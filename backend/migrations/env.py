"""Alembic-Laufzeitumgebung für Agora (docs/plans/supabase.md §8).

Die Verbindung kommt aus `DATABASE_URL`, nicht aus `alembic.ini`: eine
Zeichenkette mit Passwort gehört nicht in eine versionierte Datei. Gelesen
wird sie über denselben Adapter wie im Anwendungscode, damit Migration und
Laufzeit nicht mit zwei verschiedenen Treibern oder Schemata arbeiten.

`target_metadata` kommt aus der gemeinsamen Declarative Base. Alembic und die
Anwendung arbeiten dadurch gegen dieselbe Modelldefinition; Tabellen werden
trotzdem ausschließlich über versionierte Migrationen geändert.
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
from app.infrastructure.postgres.models import AGORA_SCHEMA, Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def _include_name(
    name: str | None,
    type_: str,
    _parent_names: dict[str, str | None],
) -> bool:
    """Reflektiert für Autogenerate ausschließlich das Agora-Fachschema."""
    return type_ != 'schema' or name == AGORA_SCHEMA


def _database_url() -> str:
    """Verbindung für Migrationen, auf das psycopg-3-Schema normalisiert.

    ``AGORA_MIGRATION_DATABASE_URL`` hat Vorrang (ADR-0018, #1615): Die
    Laufzeitrolle der App darf weder Tabellen besitzen noch RLS umgehen.
    Migrationen laufen deshalb mit der Owner-Rolle. Ohne diese Variable gilt
    ``DATABASE_URL`` wie bisher, also für Installationen mit nur einer Rolle.
    """
    raw = os.environ.get('AGORA_MIGRATION_DATABASE_URL', '') or os.environ.get('DATABASE_URL', '')
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
        include_name=_include_name,
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
        # ``FORCE ROW LEVEL SECURITY`` (#1615) gilt auch für den Tabellen-Owner.
        # Eine Migration arbeitet über alle Workspaces, also im System-Kontext
        # der Policies — für die ganze Verbindung, nicht nur eine Transaktion.
        connection.exec_driver_sql("SELECT set_config('agora.system', 'on', false)")
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=_include_name,
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
