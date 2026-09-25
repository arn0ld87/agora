"""Workspace-API, offene Registrierung und Mitgliederverwaltung (ADR-0018, #1616).

Echte Mitgliedschaften in PostgreSQL, echter Guard, signierte Supabase-JWTs:

* ``GET /api/auth/config`` gibt die Browser-Angaben nur bei aktivem JWT aus.
* ``POST /api/workspaces/bootstrap`` legt genau einen persönlichen Workspace
  an, idempotent, ohne Zugang zu fremden.
* Owner und Admins verwalten Mitglieder; der letzte Owner bleibt, ein Admin
  vergibt und entzieht keine Owner-Rolle, jeder darf sich selbst entfernen.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Iterator

import jwt
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from flask import Flask

from app.api.workspaces import auth_public_bp, workspaces_bp
from app.config import WORKSPACE_SCOPED_BACKENDS, Config
from app.contracts.workspace_contract import DEFAULT_WORKSPACE_ID, WorkspaceRole
from app.infrastructure.postgres import session as session_module
from app.infrastructure.postgres.repositories.workspace_repository import (
    PostgresWorkspaceRepository,
)
from app.infrastructure.postgres.session import Database
from app.security import principal_context
from app.utils.auth import install_blueprint_guard
from app.utils.rate_limit import workspace_rate_limiter

pytestmark = pytest.mark.integration

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / 'migrations'
ISSUER = 'https://supabase.example.test/auth/v1'
SECRET = 'q' * 40
MASTER = 'master-token-for-tests'
ALICE = uuid.UUID('a11ce000-0000-4000-8000-000000000011')
BOB = uuid.UUID('b0b00000-0000-4000-8000-000000000012')
CAROL = uuid.UUID('ca401000-0000-4000-8000-000000000013')


@pytest.fixture
def database(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = AlembicConfig(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    command.upgrade(config, 'head')
    db = Database(postgres_database_url)
    monkeypatch.setattr(session_module, '_database', db)
    monkeypatch.setattr(Config, 'DATABASE_URL', postgres_database_url)
    try:
        yield db
    finally:
        db.dispose()


def _app() -> Flask:
    install_blueprint_guard(workspaces_bp)
    app = Flask(__name__)
    app.register_blueprint(workspaces_bp, url_prefix='/api/workspaces')
    app.register_blueprint(auth_public_bp, url_prefix='/api/auth')
    return app


@pytest.fixture
def client(database, monkeypatch):
    monkeypatch.setattr(Config, 'AUTH_BACKEND', 'hybrid')
    monkeypatch.setattr(Config, 'SUPABASE_JWT_ISSUER', ISSUER)
    monkeypatch.setattr(Config, 'SUPABASE_JWT_SECRET', SECRET)
    monkeypatch.setattr(Config, 'SUPABASE_JWKS_URL', '')
    monkeypatch.setattr(Config, 'SUPABASE_URL', 'https://supabase.example.test')
    monkeypatch.setattr(Config, 'SUPABASE_ANON_KEY', 'public-anon-key')
    for _, attr in WORKSPACE_SCOPED_BACKENDS:
        monkeypatch.setattr(Config, attr, 'postgres')
    monkeypatch.delenv('AGORA_ALLOW_ANONYMOUS', raising=False)
    monkeypatch.delenv('AGORA_CORS_ALLOW_ALL', raising=False)
    monkeypatch.setenv('AGORA_AUTH_TOKEN', MASTER)
    principal_context.reset_jwt_verifier()
    workspace_rate_limiter.reset_for_tests()
    yield _app().test_client()
    workspace_rate_limiter.reset_for_tests()
    principal_context.reset_jwt_verifier()


def _headers(user: uuid.UUID, workspace: uuid.UUID | None = None, email: str | None = None) -> dict:
    now = int(time.time())
    claims = {'sub': str(user), 'iss': ISSUER, 'aud': 'authenticated', 'iat': now, 'exp': now + 600}
    if email:
        claims['email'] = email
    headers = {'Authorization': f"Bearer {jwt.encode(claims, SECRET, algorithm='HS256')}"}
    if workspace is not None:
        headers['X-Agora-Workspace'] = str(workspace)
    return headers


def _bootstrap(client, user: uuid.UUID, **kwargs) -> dict:
    response = client.post('/api/workspaces/bootstrap', headers=_headers(user, **kwargs), json={})
    assert response.status_code == 200, response.get_json()
    return response.get_json()


# -- Auth-Konfiguration ------------------------------------------------------------


def test_auth_config_exposes_the_browser_settings_only_with_jwt(client, monkeypatch):
    body = client.get('/api/auth/config').get_json()['data']
    assert body == {
        'auth_backend': 'hybrid',
        'jwt_enabled': True,
        'supabase_url': 'https://supabase.example.test',
        'supabase_anon_key': 'public-anon-key',
    }

    monkeypatch.setattr(Config, 'AUTH_BACKEND', 'legacy')
    body = client.get('/api/auth/config').get_json()['data']
    assert body['jwt_enabled'] is False
    assert body['supabase_url'] is None and body['supabase_anon_key'] is None


def test_cors_allow_all_keeps_jwt_off(client, monkeypatch):
    monkeypatch.setenv('AGORA_CORS_ALLOW_ALL', 'true')

    assert client.get('/api/auth/config').get_json()['data']['jwt_enabled'] is False
    response = client.get('/api/workspaces', headers=_headers(ALICE))
    assert response.status_code == 401


# -- Bootstrap ---------------------------------------------------------------------


def test_bootstrap_creates_one_personal_workspace_and_is_idempotent(client):
    first = _bootstrap(client, ALICE, email='alice@example.test')
    second = _bootstrap(client, ALICE, email='alice@example.test')

    assert first['created'] is True and second['created'] is False
    assert first['data'] == second['data']
    assert first['data']['role'] == 'owner'
    assert first['data']['name'] == 'alice'
    listed = client.get('/api/workspaces', headers=_headers(ALICE)).get_json()
    assert listed['count'] == 1
    assert listed['data'][0]['workspace_id'] == first['data']['workspace_id']


def test_bootstrap_never_grants_access_to_another_workspace(client):
    alice = _bootstrap(client, ALICE)['data']
    bob = _bootstrap(client, BOB)['data']

    assert alice['workspace_id'] != bob['workspace_id']
    listed = client.get('/api/workspaces', headers=_headers(BOB)).get_json()['data']
    assert [w['workspace_id'] for w in listed] == [bob['workspace_id']]
    foreign = client.get(
        '/api/workspaces/current/members',
        headers=_headers(BOB, uuid.UUID(alice['workspace_id'])),
    )
    assert (foreign.status_code, foreign.get_json()['code']) == (403, 'workspace_forbidden')


def test_bootstrap_rejects_unknown_fields(client):
    response = client.post(
        '/api/workspaces/bootstrap', headers=_headers(ALICE), json={'workspace_id': str(DEFAULT_WORKSPACE_ID)}
    )

    assert response.status_code == 400
    assert client.get('/api/workspaces', headers=_headers(ALICE)).get_json()['count'] == 0


def test_new_user_without_workspace_gets_an_empty_list(client):
    body = client.get('/api/workspaces', headers=_headers(CAROL)).get_json()

    assert (body['data'], body['count']) == ([], 0)


def test_operator_sees_the_default_workspace_and_cannot_bootstrap(client):
    master = {'X-Agora-Token': MASTER}

    listed = client.get('/api/workspaces', headers=master).get_json()['data']
    assert listed == [
        {'workspace_id': str(DEFAULT_WORKSPACE_ID), 'name': 'Standard', 'slug': 'default', 'role': 'owner'}
    ]
    response = client.post('/api/workspaces/bootstrap', headers=master, json={})
    assert (response.status_code, response.get_json()['code']) == (400, 'not_applicable')


def test_requests_without_credentials_are_rejected(client):
    assert client.get('/api/workspaces').status_code == 401
    assert client.post('/api/workspaces/bootstrap', json={}).status_code == 401


# -- Mitglieder --------------------------------------------------------------------


@pytest.fixture
def team(client, database):
    """Alice ist Owner, Bob Admin, Carol Member in Alices Workspace."""
    ws = uuid.UUID(_bootstrap(client, ALICE)['data']['workspace_id'])
    repo = PostgresWorkspaceRepository(database=database)
    repo.add_member(ws, BOB, WorkspaceRole.ADMIN)
    repo.add_member(ws, CAROL, WorkspaceRole.MEMBER)
    return ws


def _put(client, actor, ws, target, role):
    return client.put(
        f'/api/workspaces/current/members/{target}', headers=_headers(actor, ws), json={'role': role}
    )


def _delete(client, actor, ws, target):
    return client.delete(f'/api/workspaces/current/members/{target}', headers=_headers(actor, ws))


def test_members_are_listed_for_every_member(client, team):
    body = client.get('/api/workspaces/current/members', headers=_headers(CAROL, team)).get_json()

    roles = {m['user_id']: m['role'] for m in body['data']}
    assert roles == {str(ALICE): 'owner', str(BOB): 'admin', str(CAROL): 'member'}


def test_member_cannot_manage_members(client, team):
    response = _put(client, CAROL, team, BOB, 'viewer')

    assert (response.status_code, response.get_json()['code']) == (403, 'role_required')
    response = _delete(client, CAROL, team, BOB)
    assert (response.status_code, response.get_json()['code']) == (403, 'role_required')


def test_admin_manages_members_but_not_owners(client, team):
    assert _put(client, BOB, team, CAROL, 'viewer').status_code == 200

    grant = _put(client, BOB, team, CAROL, 'owner')
    demote = _put(client, BOB, team, ALICE, 'member')
    remove = _delete(client, BOB, team, ALICE)

    for response in (grant, demote, remove):
        assert (response.status_code, response.get_json()['code']) == (403, 'owner_required')


def test_last_owner_stays(client, team):
    demote = _put(client, ALICE, team, ALICE, 'admin')
    leave = _delete(client, ALICE, team, ALICE)

    for response in (demote, leave):
        assert (response.status_code, response.get_json()['code']) == (409, 'last_owner')

    assert _put(client, ALICE, team, BOB, 'owner').status_code == 200
    assert _put(client, ALICE, team, ALICE, 'admin').status_code == 200


def test_member_may_leave_and_loses_access(client, team):
    assert _delete(client, CAROL, team, CAROL).status_code == 200

    response = client.get('/api/workspaces/current/members', headers=_headers(CAROL, team))
    assert (response.status_code, response.get_json()['code']) == (403, 'workspace_forbidden')


def test_bootstrap_does_not_restore_a_removed_owner(client, team):
    assert _put(client, ALICE, team, BOB, 'owner').status_code == 200
    assert _delete(client, BOB, team, ALICE).status_code == 200

    response = client.post('/api/workspaces/bootstrap', headers=_headers(ALICE), json={})

    assert (response.status_code, response.get_json()['code']) == (409, 'personal_workspace_unavailable')
    denied = client.get('/api/workspaces/current/members', headers=_headers(ALICE, team))
    assert (denied.status_code, denied.get_json()['code']) == (403, 'workspace_forbidden')


def test_bootstrap_adopts_an_orphaned_personal_workspace(client, database):
    """Erster Aufruf brach nach dem Anlegen ab: der zweite macht den Nutzer zum Owner."""
    from app.api.workspaces import _personal_slug

    repo = PostgresWorkspaceRepository(database=database)
    orphan = repo.create('Alice', _personal_slug(ALICE))

    body = _bootstrap(client, ALICE)

    assert body['data']['workspace_id'] == str(orphan.workspace_id)
    assert body['data']['role'] == 'owner'


def test_invalid_member_input_is_rejected(client, team):
    bad_id = client.put(
        '/api/workspaces/current/members/not-a-uuid', headers=_headers(ALICE, team), json={'role': 'member'}
    )
    bad_role = _put(client, ALICE, team, CAROL, 'superuser')
    missing = _delete(client, ALICE, team, uuid.uuid4())

    assert bad_id.status_code == 400
    assert bad_role.status_code == 400
    assert missing.status_code == 404


def test_mutations_are_rate_limited(client, team):
    client.application.config['AGORA_WORKSPACE_RATE_LIMIT_MAX'] = 2
    workspace_rate_limiter.reset_for_tests()

    statuses = [_put(client, ALICE, team, CAROL, 'member').status_code for _ in range(3)]

    assert statuses == [200, 200, 429]
    # Lesen bleibt unbegrenzt.
    assert client.get('/api/workspaces', headers=_headers(ALICE)).status_code == 200
