"""Guard mit Supabase-JWT gegen echte Mitgliedschaften (ADR-0018, Issue #1613).

Derselbe Pfad wie in ``tests/security/test_hybrid_auth_guard.py``, aber die
Workspace-Wahl läuft über ``PostgresWorkspaceRepository`` gegen PostgreSQL:
ein Nutzer sieht nur seine Workspaces, der Header kann das nicht umgehen.
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
from flask import Blueprint, Flask, jsonify

from app.config import Config, WORKSPACE_SCOPED_BACKENDS
from app.contracts.workspace_contract import WorkspaceRole
from app.infrastructure.postgres import session as session_module
from app.infrastructure.postgres.repositories.workspace_repository import (
    PostgresWorkspaceRepository,
)
from app.infrastructure.postgres.session import Database
from app.security import principal_context
from app.security.principal_context import current_principal
from app.utils.auth import install_blueprint_guard

pytestmark = pytest.mark.integration

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / 'migrations'
ISSUER = 'https://supabase.example.test/auth/v1'
SECRET = 'p' * 40
ALICE = uuid.UUID('a11ce000-0000-4000-8000-000000000001')
BOB = uuid.UUID('b0b00000-0000-4000-8000-000000000002')


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


@pytest.fixture
def client(database, monkeypatch):
    monkeypatch.setattr(Config, 'AUTH_BACKEND', 'hybrid')
    monkeypatch.setattr(Config, 'SUPABASE_JWT_ISSUER', ISSUER)
    monkeypatch.setattr(Config, 'SUPABASE_JWT_SECRET', SECRET)
    monkeypatch.setattr(Config, 'SUPABASE_JWKS_URL', '')
    for _, attr in WORKSPACE_SCOPED_BACKENDS:
        monkeypatch.setattr(Config, attr, 'postgres')
    monkeypatch.setenv('AGORA_AUTH_TOKEN', 'master-token-for-tests')
    principal_context.reset_jwt_verifier()

    bp = Blueprint(f'probe_{uuid.uuid4().hex}', __name__)

    @bp.route('/whoami')
    def whoami():
        principal = current_principal()
        assert principal is not None
        return jsonify(principal.model_dump(mode='json'))

    install_blueprint_guard(bp)
    app = Flask(__name__)
    app.register_blueprint(bp, url_prefix='/api')
    yield app.test_client()
    principal_context.reset_jwt_verifier()


def _headers(user: uuid.UUID, workspace: uuid.UUID | None = None) -> dict[str, str]:
    now = int(time.time())
    token = jwt.encode(
        {'sub': str(user), 'iss': ISSUER, 'aud': 'authenticated', 'iat': now, 'exp': now + 600},
        SECRET,
        algorithm='HS256',
    )
    headers = {'Authorization': f'Bearer {token}'}
    if workspace is not None:
        headers['X-Agora-Workspace'] = str(workspace)
    return headers


def test_each_user_lands_in_their_own_workspace(database, client):
    repo = PostgresWorkspaceRepository(database=database)
    ws_a = repo.create('Alice', 'alice')
    ws_b = repo.create('Bob', 'bob')
    repo.add_member(ws_a.workspace_id, ALICE, WorkspaceRole.OWNER)
    repo.add_member(ws_b.workspace_id, BOB, WorkspaceRole.VIEWER)

    alice = client.get('/api/whoami', headers=_headers(ALICE)).get_json()
    bob = client.get('/api/whoami', headers=_headers(BOB)).get_json()

    assert (alice['workspace_id'], alice['roles']) == (str(ws_a.workspace_id), ['owner'])
    assert (bob['workspace_id'], bob['roles']) == (str(ws_b.workspace_id), ['viewer'])


def test_header_cannot_reach_a_foreign_workspace(database, client):
    repo = PostgresWorkspaceRepository(database=database)
    ws_a = repo.create('Alice', 'alice')
    ws_b = repo.create('Bob', 'bob')
    repo.add_member(ws_a.workspace_id, ALICE, WorkspaceRole.OWNER)
    repo.add_member(ws_b.workspace_id, BOB, WorkspaceRole.OWNER)

    response = client.get('/api/whoami', headers=_headers(ALICE, ws_b.workspace_id))

    assert (response.status_code, response.get_json()['code']) == (403, 'workspace_forbidden')


def test_removed_membership_takes_effect_on_the_next_request(database, client):
    repo = PostgresWorkspaceRepository(database=database)
    ws = repo.create('Team', 'team')
    repo.add_member(ws.workspace_id, ALICE, WorkspaceRole.MEMBER)
    assert client.get('/api/whoami', headers=_headers(ALICE)).status_code == 200

    repo.remove_member(ws.workspace_id, ALICE)

    response = client.get('/api/whoami', headers=_headers(ALICE))
    assert (response.status_code, response.get_json()['code']) == (403, 'workspace_membership_required')


def test_master_token_lands_in_the_default_workspace(client):
    body = client.get('/api/whoami', headers={'X-Agora-Token': 'master-token-for-tests'}).get_json()

    assert body['workspace_id'] == '00000000-0000-0000-0000-000000000001'
