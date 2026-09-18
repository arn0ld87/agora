"""PostgreSQL-Zugang (docs/plans/supabase.md §8).

`Database` aus `session.py` ist der einzige vorgesehene Weg zu einer
Verbindung. Freie `psycopg.connect()`-Aufrufe in Services sind ausdrücklich
nicht vorgesehen — sie umgehen Pool, Konfiguration und Fehlerbehandlung.
"""

from .engine import build_engine, normalize_database_url
from .session import Database, get_database, reset_database

__all__ = [
    'Database',
    'build_engine',
    'get_database',
    'normalize_database_url',
    'reset_database',
]
