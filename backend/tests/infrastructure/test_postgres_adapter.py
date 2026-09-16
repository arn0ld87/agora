"""Verträge des PostgreSQL-Adapters (docs/plans/supabase.md §8).

Keiner dieser Tests baut eine Verbindung auf. Das ist der Punkt: der Adapter
darf beim Import und beim Konstruieren nichts tun, sonst kostet er auch in
einer Installation etwas, die ihn nie benutzt.
"""

from __future__ import annotations

import pytest

from app.config import Config
from app.infrastructure.postgres import (
    Database,
    build_engine,
    get_database,
    normalize_database_url,
    reset_database,
)

VALID_URL = 'postgresql+psycopg://user:pw@supavisor:5432/postgres'


@pytest.fixture(autouse=True)
def _clean_process_adapter():
    """Der Prozess-Singleton darf nicht zwischen Tests überleben."""
    reset_database()
    yield
    reset_database()


# ---------------------------------------------------------------------------
# normalize_database_url
# ---------------------------------------------------------------------------


def test_psycopg3_url_passes_through():
    assert normalize_database_url(VALID_URL) == VALID_URL


def test_surrounding_whitespace_is_stripped():
    assert normalize_database_url(f'  {VALID_URL}  ') == VALID_URL


@pytest.mark.parametrize('legacy_prefix', ['postgresql://', 'postgres://'])
def test_legacy_scheme_is_rewritten_to_psycopg3(legacy_prefix):
    """`postgresql://` wählt in SQLAlchemy psycopg2, das hier nicht existiert.

    Der Anwendungspfad lehnt das in `Config.validate()` ab. Alembic und
    Wartungsskripte lesen `DATABASE_URL` aber direkt aus der Umgebung und
    kämen sonst mit einem Treiber-Import-Fehler heraus, der nach einem
    fehlenden Paket aussieht.
    """
    result = normalize_database_url(f'{legacy_prefix}user:pw@supavisor:5432/postgres')

    assert result == VALID_URL


@pytest.mark.parametrize('empty', ['', '   ', None])
def test_empty_url_raises(empty):
    with pytest.raises(ValueError, match='DATABASE_URL is empty'):
        normalize_database_url(empty)


def test_foreign_scheme_raises():
    """Eine MySQL-URL ist kein Tippfehler, den man reparieren sollte."""
    with pytest.raises(ValueError, match='must start with'):
        normalize_database_url('mysql+pymysql://user:pw@host:3306/db')


def test_error_message_does_not_leak_credentials():
    """Die URL trägt ein Passwort — es darf nicht in der Exception landen."""
    with pytest.raises(ValueError) as excinfo:
        normalize_database_url('mysql+pymysql://user:sehr-geheim@host:3306/db')

    assert 'sehr-geheim' not in str(excinfo.value)


# ---------------------------------------------------------------------------
# build_engine
# ---------------------------------------------------------------------------


def test_build_engine_does_not_connect():
    """Eine Engine ist eine Konfiguration, keine Verbindung.

    Der Host `supavisor` existiert im Test nicht; dass das hier nicht stört,
    ist genau die Zusicherung.
    """
    engine = build_engine(VALID_URL)

    assert engine.dialect.name == 'postgresql'
    assert engine.dialect.driver == 'psycopg'
    engine.dispose()


def test_build_engine_without_pool_uses_nullpool():
    from sqlalchemy.pool import NullPool

    engine = build_engine(VALID_URL, use_pool=False)

    assert isinstance(engine.pool, NullPool)
    engine.dispose()


def test_build_engine_rewrites_legacy_scheme():
    engine = build_engine('postgresql://user:pw@supavisor:5432/postgres')

    assert engine.dialect.driver == 'psycopg'
    engine.dispose()


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def test_database_constructor_does_not_build_engine():
    """Ein ungenutzter Adapter hält keine Ressourcen."""
    database = Database(VALID_URL)

    assert database._engine is None


def test_database_engine_is_built_once():
    database = Database(VALID_URL)

    first = database.engine
    second = database.engine

    assert first is second
    database.dispose()


def test_dispose_allows_rebuild():
    database = Database(VALID_URL)
    first = database.engine

    database.dispose()
    second = database.engine

    assert first is not second
    database.dispose()


# ---------------------------------------------------------------------------
# get_database
# ---------------------------------------------------------------------------


def test_get_database_without_url_raises(monkeypatch):
    """Kein Default-Fallback: wer hierher kommt, will die Datenbank benutzen."""
    monkeypatch.setattr(Config, 'DATABASE_URL', '')

    with pytest.raises(RuntimeError, match='DATABASE_URL is not configured'):
        get_database()


def test_get_database_returns_process_singleton(monkeypatch):
    monkeypatch.setattr(Config, 'DATABASE_URL', VALID_URL)

    assert get_database() is get_database()


def test_reset_database_clears_the_singleton(monkeypatch):
    monkeypatch.setattr(Config, 'DATABASE_URL', VALID_URL)
    first = get_database()

    reset_database()

    assert get_database() is not first
