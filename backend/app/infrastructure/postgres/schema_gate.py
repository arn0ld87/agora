"""Start-Gate gegen Alembic-Drift (Issue #1582, docs/plans/supabase.md §8).

Steht irgendeine Ablage auf ``postgres`` (siehe ``backends.py``), muss die
Revision in der Datenbank dem Head aus ``backend/migrations/`` entsprechen —
sonst arbeitet der Prozess gegen ein Schema, das nicht zum Code passt, ohne
dass das an irgendeiner Stelle auffällt (siehe
``docs/runbooks/llm-profile-postgres-umstellung.md``). Diese Funktion macht
daraus einen Startabbruch statt eines stillen Laufs gegen ein unvollständiges
Schema.

Baut absichtlich eine eigene, kurzlebige Verbindung (``NullPool``) statt den
Anwendungs-Pool aus ``session.py`` zu benutzen: der Check läuft, bevor
irgendein anderer Teil der Anwendung eine Verbindung braucht, und soll dessen
Lebenszyklus nicht vorwegnehmen.
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import NullPool

from .engine import normalize_database_url


#: ``backend/migrations`` — dieselbe Linie, die ``alembic upgrade head`` anwendet.
MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / 'migrations'


#: Verbindungs-Timeout (Sekunden) für das Start-Gate. Ohne ihn wartet
#: psycopg bei einem stumm verworfenen Verbindungsaufbau rund 130 s — länger
#: als die ``start-period`` des Container-Healthchecks (Codex-Review auf
#: #1599). Überschreibbar per ``AGORA_SCHEMA_GATE_CONNECT_TIMEOUT``.
DEFAULT_CONNECT_TIMEOUT = 10


def _connect_timeout() -> int:
    raw = os.environ.get('AGORA_SCHEMA_GATE_CONNECT_TIMEOUT', '').strip()
    if not raw:
        return DEFAULT_CONNECT_TIMEOUT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CONNECT_TIMEOUT
    return value if value > 0 else DEFAULT_CONNECT_TIMEOUT


class SchemaDriftError(RuntimeError):
    """Die Datenbank steht nicht auf dem Alembic-Head aus ``migrations/``."""


def _script_directory(migrations_dir: Path) -> ScriptDirectory:
    """Lädt die Migrationslinie, ohne eine Verbindung aufzubauen."""
    config = AlembicConfig(str(migrations_dir / 'alembic.ini'))
    config.set_main_option('script_location', str(migrations_dir))
    return ScriptDirectory.from_config(config)


def _expected_head(migrations_dir: Path) -> str:
    """Der einzige gültige Head. Mehrere Heads sind selbst schon ein Fehler."""
    heads = _script_directory(migrations_dir).get_heads()
    if len(heads) != 1:
        raise SchemaDriftError(
            f"Uneindeutige Migrationslinie: {len(heads)} Alembic-Heads in "
            f"{migrations_dir} statt einem. `alembic merge` fehlt vermutlich."
        )
    return heads[0]


def _current_heads(database: str | Engine) -> tuple[str, ...]:
    """Die in der Datenbank vermerkten Revisionen, ohne den Anwendungs-Pool."""
    if isinstance(database, Engine):
        with database.connect() as connection:
            return MigrationContext.configure(connection).get_current_heads()

    normalized = normalize_database_url(database)
    engine = create_engine(
        normalized,
        poolclass=NullPool,
        future=True,
        connect_args={'connect_timeout': _connect_timeout()},
    )
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_heads()
    finally:
        engine.dispose()


def verify_schema_at_head(
    database: str | Engine, migrations_dir: Path | str = MIGRATIONS_DIR
) -> None:
    """Wirft ``SchemaDriftError``, wenn die DB nicht auf dem Alembic-Head steht.

    ``database`` ist entweder eine ``DATABASE_URL`` (Normalfall — der Aufruf
    aus ``create_app`` hat keine eigene Engine) oder eine bereits gebaute
    ``Engine`` (Tests, die eine gemeinsame Verbindung wiederverwenden wollen).
    Keine URL und kein Passwort landet in der Fehlermeldung — nur Revisionen.
    """
    migrations_path = Path(migrations_dir)
    expected = _expected_head(migrations_path)
    current = _current_heads(database)

    if not current:
        raise SchemaDriftError(
            "Keine Alembic-Revision in der Datenbank gefunden — "
            "`alembic upgrade head` fehlt. Erwartete Revision (Head): "
            f"{expected}."
        )

    if len(current) == 1 and current[0] == expected:
        return

    aktuelle = ', '.join(sorted(current))
    known = {rev.revision for rev in _script_directory(migrations_path).walk_revisions()}
    if any(revision not in known for revision in current):
        # Die Datenbank kennt eine Revision, die dieser Code nicht hat — etwa
        # nach einem Rückweg auf einen älteren Code-Stand. ``upgrade head``
        # wäre hier der falsche Rat.
        raise SchemaDriftError(
            "Datenbankschema ist neuer als der Code — die Revision ist in "
            f"{migrations_path} unbekannt. Aktuelle Revision: {aktuelle}, "
            f"erwartete Revision (Head): {expected}. Code-Stand prüfen oder "
            f"`alembic downgrade {expected}` mit dem neueren Code-Stand ausführen."
        )
    raise SchemaDriftError(
        "Datenbankschema liegt hinter dem Code zurück — "
        "`alembic upgrade head` fehlt. Aktuelle Revision: "
        f"{aktuelle}, erwartete Revision (Head): {expected}."
    )
