"""Verbindungsparameter für ``pg_dump``/``pg_restore`` aus ``DATABASE_URL`` (#1583).

``pg_dump``/``pg_restore`` verstehen weder ``postgresql+psycopg://`` noch ein
Passwort auf der Kommandozeile. Diese Datei zerlegt ``DATABASE_URL`` einmalig
in die Teile, die die beiden CLI-Tools über ``--host``/``--port``/
``--username``/``--dbname`` erwarten, und liefert das Passwort getrennt zur
Übergabe über die Umgebungsvariable ``PGPASSWORD`` — nie als Argument, nie
geloggt.

Aufruf aus der Shell (siehe ``scripts/restore-drill.sh``)::

    uv run python -m app.infrastructure.postgres.pg_cli

liest ``DATABASE_URL`` aus der Umgebung (bewusst nicht aus ``argv`` — sonst
stünde das Passwort in jeder Prozessliste) und schreibt fünf Zeilen auf
``stdout``: ``host``, ``port``, ``user``, ``dbname``, ``password``. Der
Aufrufer liest sie in Variablen ein und darf sie an keiner Stelle selbst
loggen oder als Kommandozeilenargument weiterreichen.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from sqlalchemy.engine import make_url


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


def main() -> int:
    """CLI-Einstieg für ``restore-drill.sh``: fünf Zeilen auf ``stdout``."""
    raw = os.environ.get('DATABASE_URL', '')
    if not raw.strip():
        print('DATABASE_URL is not set', file=sys.stderr)
        return 1
    try:
        params = parse_connection_params(raw)
    except Exception as exc:  # noqa: BLE001 - Fehlermeldung ohne Rohwert der URL
        print(f'DATABASE_URL konnte nicht zerlegt werden: {type(exc).__name__}', file=sys.stderr)
        return 1
    for value in (params.host, params.port, params.user, params.dbname, params.password):
        print(value)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
