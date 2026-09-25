"""Realtime-Publication und RLS für ``authenticated`` (ADR-0018, Issue #1618).

* Ohne Publication ``supabase_realtime`` (reines PostgreSQL, CI) ist die
  Migration ein No-op.
* Mit Publication stehen genau die vier Listen-Tabellen darin, nur für
  ``INSERT`` und ``UPDATE`` (``DELETE`` prüft Realtime nicht gegen RLS).
* Die Rolle ``authenticated``, unter der Realtime je Abonnent die Sichtbarkeit
  prüft, sieht keinen fremden Workspace (Matrix aus #1615). Schema ``auth``
  und ``auth.uid()`` werden dafür wie im Supabase-Image nachgebildet.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / 'migrations'
BEFORE_REALTIME = 'e746a558dce5'
TABLES = {'projects', 'simulations', 'runs', 'reports'}
WS_A = uuid.UUID('aaaaaaaa-0000-4000-8000-00000000000a')
WS_B = uuid.UUID('bbbbbbbb-0000-4000-8000-00000000000b')
ALICE = uuid.UUID('a11ce000-0000-4000-8000-000000000001')
BOB = uuid.UUID('b0b00000-0000-4000-8000-000000000002')

#: Wie im Supabase-Image: ``sub`` aus den Claims, die Realtime und PostgREST
#: je Anfrage setzen.
_AUTH_UID = """
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$
"""


def _alembic() -> AlembicConfig:
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    return config


def _published(url: str) -> dict[str, tuple[bool, bool, bool, bool]]:
    with create_engine(url).connect() as c:
        tables = {
            r.tablename
            for r in c.execute(
                text(
                    "SELECT tablename FROM pg_publication_tables "
                    "WHERE pubname = 'supabase_realtime' AND schemaname = 'agora'"
                )
            )
        }
        flags = c.execute(
            text(
                'SELECT pubinsert, pubupdate, pubdelete, pubtruncate FROM pg_publication '
                "WHERE pubname = 'supabase_realtime'"
            )
        ).one()
    return {t: tuple(flags) for t in tables}


@pytest.fixture
def db_url(postgres_database_url: str, monkeypatch) -> str:
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    return postgres_database_url


def test_migration_is_a_noop_without_publication(db_url):
    command.upgrade(_alembic(), 'head')

    with create_engine(db_url).connect() as c:
        count = c.execute(
            text("SELECT count(*) FROM pg_publication WHERE pubname = 'supabase_realtime'")
        ).scalar_one()
    assert count == 0
    command.downgrade(_alembic(), BEFORE_REALTIME)
    command.upgrade(_alembic(), 'head')
    command.check(_alembic())


def test_migration_publishes_the_list_tables_for_insert_and_update_only(db_url):
    command.upgrade(_alembic(), BEFORE_REALTIME)
    with create_engine(db_url, isolation_level='AUTOCOMMIT').connect() as c:
        # Wie im Supabase-Image: leer, alle Operationen.
        c.execute(text('CREATE PUBLICATION supabase_realtime'))

    command.upgrade(_alembic(), 'head')

    published = _published(db_url)
    assert set(published) == TABLES
    assert set(published.values()) == {(True, True, False, False)}


def test_migration_is_idempotent_for_an_already_published_table(db_url):
    command.upgrade(_alembic(), BEFORE_REALTIME)
    with create_engine(db_url, isolation_level='AUTOCOMMIT').connect() as c:
        c.execute(text('CREATE PUBLICATION supabase_realtime FOR TABLE agora.projects'))

    command.upgrade(_alembic(), 'head')

    assert set(_published(db_url)) == TABLES


def test_downgrade_removes_the_tables_and_restores_all_operations(db_url):
    command.upgrade(_alembic(), BEFORE_REALTIME)
    with create_engine(db_url, isolation_level='AUTOCOMMIT').connect() as c:
        c.execute(text('CREATE PUBLICATION supabase_realtime'))
    command.upgrade(_alembic(), 'head')

    command.downgrade(_alembic(), BEFORE_REALTIME)

    with create_engine(db_url).connect() as c:
        tables = c.execute(
            text("SELECT count(*) FROM pg_publication_tables WHERE pubname = 'supabase_realtime'")
        ).scalar_one()
        flags = c.execute(
            text(
                'SELECT pubinsert, pubupdate, pubdelete, pubtruncate FROM pg_publication '
                "WHERE pubname = 'supabase_realtime'"
            )
        ).one()
    assert tables == 0
    assert tuple(flags) == (True, True, True, True)


# -- RLS für authenticated (Realtime-Sicht) -------------------------------------------


@pytest.fixture
def supabase_like(db_url: str) -> Iterator[str]:
    """Schema ``auth``, ``auth.uid()`` und Rolle ``authenticated`` vor den
    Migrationen, damit #1615 die Lese-Policies anlegt; zwei Workspaces mit je
    einem Bestand in allen vier Tabellen."""
    admin = create_engine(db_url, isolation_level='AUTOCOMMIT')
    with admin.connect() as c:
        created_role = not c.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')")
        ).scalar_one()
        if created_role:
            c.execute(text('CREATE ROLE authenticated NOLOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS'))
        c.execute(text('CREATE SCHEMA auth'))
        c.execute(text(_AUTH_UID))
        c.execute(text('GRANT USAGE ON SCHEMA auth TO authenticated'))
        c.execute(text('CREATE PUBLICATION supabase_realtime'))
    command.upgrade(_alembic(), 'head')
    with admin.connect() as c:
        c.execute(text("SELECT set_config('agora.system', 'on', false)"))
        for ws, slug, user in ((WS_A, 'alice', ALICE), (WS_B, 'bob', BOB)):
            p = {'w': str(ws), 'u': str(user), 's': slug}
            c.execute(text('INSERT INTO agora.workspaces (id, name, slug) VALUES (:w, :s, :s)'), p)
            c.execute(
                text("INSERT INTO agora.workspace_members (workspace_id, user_id, role) VALUES (:w, :u, 'owner')"),
                p,
            )
            c.execute(
                text(
                    'INSERT INTO agora.projects (id, name, status, created_at, updated_at, payload, workspace_id) '
                    "VALUES ('proj_' || :s, 'P', 'created', 'x', 'x', '{}', :w)"
                ),
                p,
            )
            c.execute(
                text(
                    'INSERT INTO agora.simulations '
                    '(id, project_id, graph_id, status, created_at, updated_at, payload, workspace_id) '
                    "VALUES ('sim_' || :s, 'proj_' || :s, 'g', 'created', 'x', 'x', '{}', :w)"
                ),
                p,
            )
            c.execute(
                text(
                    'INSERT INTO agora.runs (id, updated_at, payload, workspace_id) '
                    "VALUES ('run_' || :s, '2026-09-26T00:00:00', '{}', :w)"
                ),
                p,
            )
            c.execute(
                text(
                    'INSERT INTO agora.reports (id, report_id, status, payload, workspace_id) '
                    "VALUES ('report_' || :s, 'report_' || :s, 'completed', '{}', :w)"
                ),
                p,
            )
    try:
        yield db_url
    finally:
        with admin.connect() as c:
            # Rechte und Policies in dieser Datenbank lösen; die Datenbank
            # selbst entfernt das conftest.
            c.execute(text('DROP OWNED BY authenticated'))
            if created_role:
                try:
                    c.execute(text('DROP ROLE authenticated'))
                except DBAPIError:
                    # Rechte in einer anderen Testdatenbank: Rolle bleibt.
                    pass
        admin.dispose()


def _visible_as(url: str, user: uuid.UUID | None) -> dict[str, set[str]]:
    """Was Realtime für einen Abonnenten prüft: ``SET ROLE authenticated``
    und dessen Claims, ohne Agora-Kontext."""
    claims = json.dumps({'sub': str(user), 'role': 'authenticated'}) if user else ''
    seen: dict[str, set[str]] = {}
    with create_engine(url).connect() as c:
        c.execute(text('SET ROLE authenticated'))
        c.execute(text("SELECT set_config('request.jwt.claims', :c, false)"), {'c': claims})
        for table in sorted(TABLES):
            seen[table] = {r[0] for r in c.execute(text(f'SELECT id FROM agora.{table}'))}
    return seen


def test_authenticated_sees_only_its_own_workspace(supabase_like):
    assert _visible_as(supabase_like, ALICE) == {
        'projects': {'proj_alice'},
        'simulations': {'sim_alice'},
        'runs': {'run_alice'},
        'reports': {'report_alice'},
    }
    assert _visible_as(supabase_like, BOB) == {
        'projects': {'proj_bob'},
        'simulations': {'sim_bob'},
        'runs': {'run_bob'},
        'reports': {'report_bob'},
    }


def test_authenticated_without_claims_sees_nothing(supabase_like):
    assert _visible_as(supabase_like, None) == {t: set() for t in TABLES}


def test_authenticated_cannot_write(supabase_like):
    with create_engine(supabase_like).connect() as c:
        c.execute(text('SET ROLE authenticated'))
        c.execute(
            text("SELECT set_config('request.jwt.claims', :c, false)"),
            {'c': json.dumps({'sub': str(ALICE)})},
        )
        with pytest.raises(DBAPIError):
            c.execute(text("UPDATE agora.projects SET name = 'x' WHERE id = 'proj_alice'"))
