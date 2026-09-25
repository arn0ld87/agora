"""RLS-Testmatrix aus Plan §18 (ADR-0018, Issue #1615).

Zwei Nutzer, zwei Workspaces. Geprüft wird die **Datenbank**, nicht die
Adapter: die Abfragen laufen roh gegen die Tabellen, damit ein fehlender
Filter in einem Adapter hier nicht verdeckt wird. Superuser umgehen RLS immer;
jede Abfrage läuft deshalb unter einer eingeschränkten Rolle (``SET ROLE``).
"""

from __future__ import annotations

import secrets
import uuid
from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from flask import Flask
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.contracts.auth_contract import AuthType, Principal
from app.contracts.workspace_contract import DEFAULT_WORKSPACE_ID, WorkspaceRole
from app.infrastructure.postgres.rls_gate import (
    RlsRoleError,
    rls_role_violations,
    verify_rls_role,
)
from app.infrastructure.postgres.session import Database
from app.security.principal_context import set_principal

pytestmark = pytest.mark.integration

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / 'migrations'
BEFORE_RLS = '14d60476b8ce'
WS_A = uuid.UUID('aaaaaaaa-0000-4000-8000-00000000000a')
WS_B = uuid.UUID('bbbbbbbb-0000-4000-8000-00000000000b')
ALICE = uuid.UUID('a11ce000-0000-4000-8000-000000000001')
BOB = uuid.UUID('b0b00000-0000-4000-8000-000000000002')


def _alembic() -> AlembicConfig:
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    return config


@pytest.fixture
def setup(postgres_database_url: str, monkeypatch) -> Iterator[dict]:
    """Schema auf Head, zwei Workspaces mit je einem Bestand, eine
    eingeschränkte Rolle (NOLOGIN für ``SET ROLE``, LOGIN für das Start-Gate)."""
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    command.upgrade(_alembic(), 'head')
    role = f'agora_rls_{uuid.uuid4().hex[:10]}'
    login_role = f'{role}_login'
    # Je Lauf erzeugt, nie im Quelltext; Hex ist als SQL-Literal unbedenklich.
    login_secret = secrets.token_hex(16)
    admin = create_engine(postgres_database_url, isolation_level='AUTOCOMMIT')
    with admin.connect() as c:
        c.execute(text("SELECT set_config('agora.system', 'on', false)"))
        c.execute(text(f'CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS'))
        c.execute(text(f"CREATE ROLE {login_role} LOGIN PASSWORD '{login_secret}' NOSUPERUSER NOBYPASSRLS"))
        for r in (role, login_role):
            c.execute(text(f'GRANT USAGE ON SCHEMA agora TO {r}'))
            c.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA agora TO {r}'))
            c.execute(text(f'GRANT SELECT ON public.alembic_version TO {r}'))
        for ws, slug in ((WS_A, 'alice'), (WS_B, 'bob')):
            c.execute(
                text("INSERT INTO agora.workspaces (id, name, slug) VALUES (:id, :slug, :slug)"),
                {'id': str(ws), 'slug': slug},
            )
        for ws, user in ((WS_A, ALICE), (WS_B, BOB)):
            c.execute(
                text("INSERT INTO agora.workspace_members (workspace_id, user_id, role) VALUES (:w, :u, 'owner')"),
                {'w': str(ws), 'u': str(user)},
            )
        for ws, suffix in ((WS_A, 'a'), (WS_B, 'b')):
            c.execute(
                text(
                    "INSERT INTO agora.projects (id, name, status, created_at, updated_at, payload, workspace_id) "
                    "VALUES (:id, 'P', 'created', 'x', 'x', '{}', :w)"
                ),
                {'id': f'proj_{suffix * 12}', 'w': str(ws)},
            )
            c.execute(
                text(
                    "INSERT INTO agora.simulations (id, project_id, graph_id, status, created_at, updated_at, payload, workspace_id) "
                    "VALUES (:id, :p, 'g', 'created', 'x', 'x', '{}', :w)"
                ),
                {'id': f'sim_{suffix * 12}', 'p': f'proj_{suffix * 12}', 'w': str(ws)},
            )

    database = Database(postgres_database_url)

    @event.listens_for(database.engine, 'connect')
    def _restricted(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET ROLE {role}')
        cursor.close()

    try:
        yield {
            'db': database,
            'role': role,
            'login_url': make_url(postgres_database_url)
            .set(username=login_role, password=login_secret)
            .render_as_string(hide_password=False),
            'admin_url': postgres_database_url,
            'login_secret': login_secret,
        }
    finally:
        database.dispose()
        with admin.connect() as c:
            for r in (role, login_role):
                c.execute(text(f'DROP OWNED BY {r}'))
                c.execute(text(f'DROP ROLE {r}'))
        admin.dispose()


def _as(workspace_id: uuid.UUID, user: uuid.UUID | None = ALICE, auth_type: AuthType = AuthType.JWT):
    ctx = Flask(__name__).test_request_context('/')
    ctx.push()
    set_principal(
        Principal(
            auth_type=auth_type,
            user_id=user,
            workspace_id=workspace_id,
            roles=frozenset({WorkspaceRole.OWNER}),
        )
    )
    return ctx


def _ids(db: Database, table: str) -> set[str]:
    queries = {
        'projects': 'SELECT id FROM agora.projects',
        'simulations': 'SELECT id FROM agora.simulations',
        'workspaces': 'SELECT id::text FROM agora.workspaces',
        'workspace_members': 'SELECT user_id::text FROM agora.workspace_members',
    }
    with db.session() as s:
        return set(s.scalars(text(queries[table])))


# -- §18: Lesen und Ändern ---------------------------------------------------------


def test_each_user_reads_only_their_workspace(setup):
    db = setup['db']
    ctx = _as(WS_A)
    try:
        assert _ids(db, 'projects') == {'proj_aaaaaaaaaaaa'}
        assert _ids(db, 'simulations') == {'sim_aaaaaaaaaaaa'}
        assert _ids(db, 'workspaces') == {str(WS_A)}
        assert _ids(db, 'workspace_members') == {str(ALICE)}
    finally:
        ctx.pop()
    ctx = _as(WS_B, BOB)
    try:
        assert _ids(db, 'projects') == {'proj_bbbbbbbbbbbb'}
    finally:
        ctx.pop()


def test_a_can_change_a_but_not_b(setup):
    db = setup['db']
    ctx = _as(WS_A)
    try:
        with db.session() as s:
            own = s.execute(text("UPDATE agora.projects SET name = 'neu' WHERE id = 'proj_aaaaaaaaaaaa'")).rowcount
            foreign = s.execute(text("UPDATE agora.projects SET name = 'neu' WHERE id = 'proj_bbbbbbbbbbbb'")).rowcount
            gone = s.execute(text("DELETE FROM agora.simulations WHERE id = 'sim_bbbbbbbbbbbb'")).rowcount
        assert (own, foreign, gone) == (1, 0, 0)
    finally:
        ctx.pop()


def test_manipulated_id_leaks_nothing(setup):
    db = setup['db']
    ctx = _as(WS_A)
    try:
        with db.session() as s:
            row = s.execute(text("SELECT id FROM agora.projects WHERE id = 'proj_bbbbbbbbbbbb'")).first()
        assert row is None
    finally:
        ctx.pop()


def test_api_key_principal_sees_only_the_default_workspace(setup):
    ctx = _as(DEFAULT_WORKSPACE_ID, user=None, auth_type=AuthType.API_KEY)
    try:
        assert _ids(setup['db'], 'projects') == set()
    finally:
        ctx.pop()


def test_writing_into_a_foreign_workspace_is_rejected_by_policy(setup):
    db = setup['db']
    ctx = _as(WS_A)
    try:
        with pytest.raises(DBAPIError, match='row-level security'), db.session() as s:
            s.execute(
                text(
                    "INSERT INTO agora.projects (id, name, status, created_at, updated_at, payload, workspace_id) "
                    "VALUES ('proj_einbruch0001', 'x', 'created', 'x', 'x', '{}', :w)"
                ),
                {'w': str(WS_B)},
            )
    finally:
        ctx.pop()


def test_reports_can_only_reference_own_simulations(setup):
    db = setup['db']
    ctx = _as(WS_A)
    try:
        with pytest.raises(IntegrityError), db.session() as s:
            s.execute(
                text(
                    "INSERT INTO agora.reports (id, report_id, simulation_id, status, payload, workspace_id) "
                    "VALUES ('report_fremd00001', 'report_fremd00001', 'sim_bbbbbbbbbbbb', 'completed', '{}', :w)"
                ),
                {'w': str(WS_A)},
            )
    finally:
        ctx.pop()


# -- System-Kontext und fehlender Kontext ----------------------------------------------


def test_system_context_sees_all_workspaces(setup):
    """Außerhalb eines Requests (Hintergrundarbeit) läuft die Session im
    System-Kontext."""
    assert _ids(setup['db'], 'projects') == {'proj_aaaaaaaaaaaa', 'proj_bbbbbbbbbbbb'}


def test_without_any_context_nothing_is_visible(setup):
    """Eine Verbindung, die ``Database.session()`` umgeht, setzt keinen
    Kontext — dann ist nichts sichtbar (fail-closed)."""
    with setup['db'].engine.connect() as connection:
        rows = connection.execute(text('SELECT id FROM agora.projects')).all()
    assert rows == []


def test_policies_are_forced_on_every_scoped_table(setup):
    with create_engine(setup['admin_url']).connect() as c:
        rows = c.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relnamespace = 'agora'::regnamespace AND relkind = 'r' "
                "AND relname IN ('projects','simulations','runs','reports','workspaces','workspace_members')"
            )
        ).all()
    assert {r.relname for r in rows if r.relrowsecurity and r.relforcerowsecurity} == {
        'projects', 'simulations', 'runs', 'reports', 'workspaces', 'workspace_members'
    }


def test_the_migration_can_be_taken_back(setup):
    command.downgrade(_alembic(), BEFORE_RLS)
    with create_engine(setup['admin_url']).connect() as c:
        forced = c.execute(
            text(
                "SELECT count(*) FROM pg_class WHERE relnamespace = 'agora'::regnamespace "
                "AND relrowsecurity"
            )
        ).scalar_one()
    assert forced == 0
    command.upgrade(_alembic(), 'head')
    command.check(_alembic())


# -- Start-Gate --------------------------------------------------------------------


def test_start_gate_rejects_a_bypassing_role_in_tenant_mode(setup):
    admin_violations = rls_role_violations(setup['admin_url'])
    assert 'superuser' in admin_violations or 'owner of agora tables' in admin_violations
    with pytest.raises(RlsRoleError) as excinfo:
        verify_rls_role(setup['admin_url'], tenant_mode=True)
    admin_password = make_url(setup['admin_url']).password
    if admin_password:
        assert str(admin_password) not in str(excinfo.value)
    assert setup['login_secret'] not in str(excinfo.value)
    # Einmandantig nur ein Hinweis.
    assert verify_rls_role(setup['admin_url'], tenant_mode=False) == admin_violations


def test_start_gate_accepts_a_restricted_role(setup):
    assert rls_role_violations(setup['login_url']) == []
    assert verify_rls_role(setup['login_url'], tenant_mode=True) == []
