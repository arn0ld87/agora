"""Guard mit ``AGORA_AUTH_BACKEND`` und Supabase-JWT (ADR-0018, Issue #1613).

Geprüft am echten Blueprint-Guard mit einer Mini-App. Die Mitgliedschaften
kommen aus einem Fake-Repository; gegen PostgreSQL läuft derselbe Pfad in
``tests/integration/test_hybrid_auth_postgres.py``.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import jwt
import pytest
from flask import Blueprint, Flask, jsonify

from app.config import Config
from app.contracts.auth_contract import AuthType, Principal
from app.contracts.workspace_contract import (
    DEFAULT_WORKSPACE_ID,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from app.security import principal_context
from app.security.principal_context import (
    bind_scope,
    current_principal,
    split_bound_scope,
)
from app.utils import auth as auth_module
from app.utils import signed_ticket
from app.utils.auth import allow_ticket_auth, install_blueprint_guard

ISSUER = 'https://supabase.example.test/auth/v1'
SECRET = 'j' * 40
MASTER = 'master-token-for-tests'
USER = uuid.UUID('11111111-2222-4333-8444-555555555555')
WS_A = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000001')
WS_B = uuid.UUID('bbbbbbbb-0000-4000-8000-000000000002')
NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)


class FakeWorkspaces:
    def __init__(self, memberships: dict[uuid.UUID, WorkspaceRole] | None = None):
        self.memberships = memberships or {}

    def membership(self, workspace_id, user_id):
        role = self.memberships.get(workspace_id)
        if user_id != USER or role is None:
            return None
        return WorkspaceMembership(workspace_id=workspace_id, user_id=user_id, role=role, created_at=NOW)

    def list_for_user(self, user_id):
        if user_id != USER:
            return []
        return [
            Workspace(workspace_id=ws, name='W', slug=f'w-{ws.hex[:6]}', created_at=NOW, updated_at=NOW)
            for ws in self.memberships
        ]


def _token(**overrides: Any) -> str:
    now = int(time.time())
    claims = {'sub': str(USER), 'iss': ISSUER, 'aud': 'authenticated', 'iat': now, 'exp': now + 600}
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm='HS256')


def _principal_json():
    principal = current_principal()
    assert principal is not None
    return jsonify(principal.model_dump(mode='json'))


@pytest.fixture
def make_client(monkeypatch):
    """Mini-App mit dem echten Guard; ``mode``/``jwt``/``master`` steuern die Lage."""

    def build(
        *,
        mode: str = 'hybrid',
        jwt_on: bool = False,
        master: str | None = MASTER,
        workspaces: FakeWorkspaces | None = None,
    ):
        monkeypatch.setattr(Config, 'AUTH_BACKEND', mode)
        monkeypatch.setattr(Config, 'SUPABASE_JWT_ISSUER', ISSUER if jwt_on else '')
        monkeypatch.setattr(Config, 'SUPABASE_JWT_SECRET', SECRET if jwt_on else '')
        monkeypatch.setattr(Config, 'SUPABASE_JWKS_URL', '')
        if master is None:
            monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
        else:
            monkeypatch.setenv('AGORA_AUTH_TOKEN', master)
        repo = workspaces or FakeWorkspaces({WS_A: WorkspaceRole.MEMBER})
        monkeypatch.setattr(
            'app.repositories.workspace_repository.get_workspace_repository', lambda: repo
        )
        monkeypatch.setattr(auth_module, '_check_api_key', lambda token: token == 'ago_' + 'k' * 40)
        principal_context.reset_jwt_verifier()
        signed_ticket._reset_seen_for_tests()

        bp = Blueprint(f'probe_{uuid.uuid4().hex}', __name__)

        @bp.route('/whoami')
        def whoami():
            return _principal_json()

        @bp.route('/stream/<sid>')
        @allow_ticket_auth(lambda sid: f'sse:{sid}')
        def stream(sid):
            return _principal_json()

        install_blueprint_guard(bp)
        app = Flask(__name__)
        app.config['SECRET_KEY'] = 'ticket-secret-for-tests'
        app.register_blueprint(bp, url_prefix='/api')
        return app.test_client()

    yield build
    principal_context.reset_jwt_verifier()


def _bearer(token: str, workspace: uuid.UUID | None = None) -> dict[str, str]:
    headers = {'Authorization': f'Bearer {token}'}
    if workspace is not None:
        headers['X-Agora-Workspace'] = str(workspace)
    return headers


# -- hybrid ohne JWT-Konfiguration = legacy ---------------------------------------


def test_hybrid_without_jwt_config_behaves_like_legacy(make_client):
    client = make_client(mode='hybrid', jwt_on=False)

    ok = client.get('/api/whoami', headers={'X-Agora-Token': MASTER})
    assert ok.status_code == 200
    assert ok.get_json()['auth_type'] == 'master_token'
    assert ok.get_json()['workspace_id'] == str(DEFAULT_WORKSPACE_ID)
    assert ok.get_json()['roles'] == ['owner']
    # Ein JWT zählt hier nicht — es ist nur ein falscher Token.
    assert client.get('/api/whoami', headers=_bearer(_token())).status_code == 401


def test_open_mode_only_without_token_and_without_jwt(make_client):
    client = make_client(mode='hybrid', jwt_on=False, master=None)
    assert client.get('/api/whoami').get_json()['auth_type'] == 'anonymous'

    client = make_client(mode='hybrid', jwt_on=True, master=None)
    assert client.get('/api/whoami').status_code == 401


def test_api_key_is_a_default_workspace_owner(make_client):
    client = make_client(mode='hybrid', jwt_on=True)

    body = client.get('/api/whoami', headers={'X-Agora-Token': 'ago_' + 'k' * 40}).get_json()

    assert (body['auth_type'], body['workspace_id'], body['roles']) == (
        'api_key', str(DEFAULT_WORKSPACE_ID), ['owner'],
    )


# -- JWT ---------------------------------------------------------------------------


def test_valid_jwt_with_single_membership(make_client):
    client = make_client(jwt_on=True)

    body = client.get('/api/whoami', headers=_bearer(_token())).get_json()

    assert body == {
        'auth_type': 'jwt',
        'user_id': str(USER),
        'workspace_id': str(WS_A),
        'roles': ['member'],
        'scopes': [],
    }


def test_workspace_header_selects_among_memberships(make_client):
    client = make_client(
        jwt_on=True,
        workspaces=FakeWorkspaces({WS_A: WorkspaceRole.MEMBER, WS_B: WorkspaceRole.ADMIN}),
    )

    missing = client.get('/api/whoami', headers=_bearer(_token()))
    assert (missing.status_code, missing.get_json()['code']) == (400, 'workspace_header_required')

    chosen = client.get('/api/whoami', headers=_bearer(_token(), WS_B)).get_json()
    assert (chosen['workspace_id'], chosen['roles']) == (str(WS_B), ['admin'])


def test_foreign_workspace_header_is_forbidden(make_client):
    client = make_client(jwt_on=True)

    response = client.get('/api/whoami', headers=_bearer(_token(), WS_B))

    assert (response.status_code, response.get_json()['code']) == (403, 'workspace_forbidden')


def test_malformed_workspace_header_is_a_bad_request(make_client):
    client = make_client(jwt_on=True)

    response = client.get(
        '/api/whoami', headers={**_bearer(_token()), 'X-Agora-Workspace': 'kein-uuid'}
    )

    assert (response.status_code, response.get_json()['code']) == (400, 'invalid_workspace_header')


def test_user_without_membership_is_told_so(make_client):
    client = make_client(jwt_on=True, workspaces=FakeWorkspaces({}))

    response = client.get('/api/whoami', headers=_bearer(_token()))

    assert (response.status_code, response.get_json()['code']) == (403, 'workspace_membership_required')


@pytest.mark.parametrize(
    'bad',
    [
        {'exp': int(time.time()) - 3600},
        {'iss': 'https://evil.example.test/auth/v1'},
        {'aud': 'anon'},
    ],
)
def test_invalid_jwt_is_rejected_and_never_compared_as_master_token(make_client, bad):
    client = make_client(jwt_on=True)

    response = client.get('/api/whoami', headers=_bearer(_token(**bad)))

    assert (response.status_code, response.get_json()['code']) == (401, 'invalid_token')


def test_rejected_jwt_is_not_logged(make_client):
    """Eigener Handler am ``agora.auth``-Logger: der Projekt-Logger
    propagiert nicht und schreibt auf einen früh gebundenen Stream."""
    records: list[str] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = Collect(level=logging.DEBUG)
    logger = logging.getLogger('agora.auth')
    logger.addHandler(handler)
    try:
        client = make_client(jwt_on=True)
        token = _token(exp=int(time.time()) - 3600)
        client.get('/api/whoami', headers=_bearer(token))
    finally:
        logger.removeHandler(handler)
    logged = '\n'.join(records)

    assert 'JWT rejected (expired)' in logged
    assert token not in logged
    assert token.split('.')[1] not in logged


def test_master_token_still_works_in_hybrid_with_jwt(make_client):
    client = make_client(jwt_on=True)

    body = client.get('/api/whoami', headers={'X-Agora-Token': MASTER}).get_json()

    assert body['auth_type'] == 'master_token'


# -- supabase ---------------------------------------------------------------------


def test_supabase_mode_rejects_the_master_token(make_client):
    client = make_client(mode='supabase', jwt_on=True)

    assert client.get('/api/whoami', headers={'X-Agora-Token': MASTER}).status_code == 401
    assert client.get('/api/whoami').status_code == 401
    assert client.get('/api/whoami', headers=_bearer(_token())).status_code == 200
    assert client.get('/api/whoami', headers={'X-Agora-Token': 'ago_' + 'k' * 40}).status_code == 200


# -- Tickets ----------------------------------------------------------------------


def _ticket(scope: str, principal: Principal | None) -> str:
    signed = bind_scope(scope, principal) if principal is not None else scope
    return signed_ticket.issue('ticket-secret-for-tests', signed, ttl_seconds=60)


def test_bound_ticket_carries_the_issuing_principal(make_client):
    client = make_client(jwt_on=True)
    issuer = Principal(
        auth_type=AuthType.JWT, user_id=USER, workspace_id=WS_A, roles=frozenset({WorkspaceRole.MEMBER})
    )

    body = client.get(f'/api/stream/sim1?ticket={_ticket("sse:sim1", issuer)}').get_json()

    assert (body['auth_type'], body['user_id'], body['workspace_id']) == ('jwt', str(USER), str(WS_A))


def test_unbound_ticket_only_without_jwt(make_client):
    legacy = make_client(jwt_on=False)
    assert legacy.get(f'/api/stream/sim1?ticket={_ticket("sse:sim1", None)}').status_code == 200

    hybrid = make_client(jwt_on=True)
    assert hybrid.get(f'/api/stream/sim1?ticket={_ticket("sse:sim1", None)}').status_code == 401


def test_ticket_for_another_resource_is_rejected(make_client):
    client = make_client(jwt_on=True)
    issuer = principal_context.legacy_principal(AuthType.MASTER_TOKEN)

    assert client.get(f'/api/stream/sim2?ticket={_ticket("sse:sim1", issuer)}').status_code == 401


def test_rewritten_binding_breaks_the_signature(make_client):
    client = make_client(jwt_on=True)
    issuer = Principal(
        auth_type=AuthType.JWT, user_id=USER, workspace_id=WS_A, roles=frozenset({WorkspaceRole.VIEWER})
    )
    ticket = _ticket('sse:sim1', issuer)
    forged = ticket.replace(str(WS_A), str(WS_B)).replace('viewer', 'owner')

    assert client.get(f'/api/stream/sim1?ticket={forged}').status_code == 401


def test_scope_binding_roundtrip_and_garbage():
    principal = Principal(
        auth_type=AuthType.JWT,
        user_id=USER,
        workspace_id=WS_B,
        roles=frozenset({WorkspaceRole.ADMIN}),
    )

    assert split_bound_scope(bind_scope('sse:x', principal)) == ('sse:x', principal)
    assert split_bound_scope('sse:x') == ('sse:x', None)
    assert split_bound_scope('sse:x@kaputt') == ('sse:x@kaputt', None)
    assert '.' not in bind_scope('sse:x', principal)


def test_clients_cannot_send_a_binding():
    from app.api.auth import _scope_is_allowed

    assert _scope_is_allowed('sse:abc')
    assert not _scope_is_allowed('sse:abc@jwt~x~y~owner')


# -- Betreiber-Blueprints und Scopes -------------------------------------------


@pytest.fixture
def scoped_client(make_client, monkeypatch):
    """Mini-App mit einem Betreiber-Blueprint und Scope-Endpunkten."""
    from app.utils.scopes import require_scope

    def build(**kwargs):
        client = make_client(**kwargs)
        app = client.application
        operator = Blueprint(f'op_{uuid.uuid4().hex}', __name__)

        @operator.route('/settings')
        def settings():
            return jsonify({'ok': True})

        data = Blueprint(f'data_{uuid.uuid4().hex}', __name__)

        @data.route('/read')
        @require_scope('report:read')
        def read():
            return jsonify({'ok': True})

        @data.route('/write', methods=['POST'])
        @require_scope('report:write')
        def write():
            return jsonify({'ok': True})

        install_blueprint_guard(operator, tenant_access=False)
        install_blueprint_guard(data)
        app.register_blueprint(operator, url_prefix='/op')
        app.register_blueprint(data, url_prefix='/data')
        return app.test_client()

    return build


def test_operator_blueprints_are_closed_to_jwt_users(scoped_client):
    client = scoped_client(jwt_on=True, workspaces=FakeWorkspaces({WS_A: WorkspaceRole.OWNER}))

    denied = client.get('/op/settings', headers=_bearer(_token()))
    assert (denied.status_code, denied.get_json()['code']) == (403, 'operator_only')
    assert client.get('/op/settings', headers={'X-Agora-Token': MASTER}).status_code == 200


@pytest.mark.parametrize(
    ('role', 'read', 'write'),
    [
        (WorkspaceRole.OWNER, 200, 200),
        (WorkspaceRole.ADMIN, 200, 200),
        (WorkspaceRole.MEMBER, 200, 200),
        (WorkspaceRole.VIEWER, 200, 403),
    ],
)
def test_scopes_follow_the_workspace_role(scoped_client, role, read, write):
    client = scoped_client(jwt_on=True, workspaces=FakeWorkspaces({WS_A: role}))

    assert client.get('/data/read', headers=_bearer(_token())).status_code == read
    response = client.post('/data/write', headers=_bearer(_token()))
    assert response.status_code == write
    if write == 403:
        assert response.get_json()['code'] == 'scope_missing'


def test_master_token_passes_scope_checks(scoped_client):
    """Der Master-Token trägt Admin-Scopes, auch ohne API-Key-Header."""
    client = scoped_client(jwt_on=False)

    assert client.get('/data/read', headers={'X-Agora-Token': MASTER}).status_code == 200
