"""Welche Metadaten-Ablagen stehen auf PostgreSQL? (#1576)

Readiness (#1581), Start-Gate bei Alembic-Drift (#1582) und Backup (#1583)
fragen dieselbe Sache: steht irgendein ``AGORA_*_BACKEND`` auf ``postgres``?
Die Antwort kommt aus einer Stelle, damit ein neuer Schalter (etwa
``SIMULATION_BACKEND``) automatisch mitzählt, ohne dass drei Aufrufer
nachgezogen werden müssen.

Die Funktion liest nur Attribute. Sie baut nie eine Verbindung auf — genau
das ist die Zusage für den Legacy-Default.
"""

from __future__ import annotations

from typing import Any

POSTGRES_BACKEND_VALUE = 'postgres'


def active_postgres_backends(config: Any) -> tuple[str, ...]:
    """Namen aller ``*_BACKEND``-Attribute von ``config`` mit Wert ``postgres``.

    ``config`` ist die ``Config``-Klasse oder ein Objekt mit denselben
    Attributen. Das Ergebnis ist sortiert und leer, solange alles auf dem
    Legacy-Default steht.
    """
    names: list[str] = []
    for name in dir(config):
        if name.startswith('_') or not name.endswith('_BACKEND'):
            continue
        value = getattr(config, name, None)
        if isinstance(value, str) and value.strip().lower() == POSTGRES_BACKEND_VALUE:
            names.append(name)
    return tuple(sorted(names))


def any_postgres_backend(config: Any) -> bool:
    """``True``, sobald mindestens eine Ablage auf PostgreSQL steht."""
    return bool(active_postgres_backends(config))
