"""Workspaces und Mitglieder (ADR-0018, Issue #1616).

* ``GET /api/auth/config`` — öffentlich: Auth-Modus und, bei aktivem JWT, die
  Angaben für den Supabase-Client im Browser. Kein Geheimnis.
* ``GET /api/workspaces`` — die Workspaces des Nutzers mit seiner Rolle.
* ``POST /api/workspaces/bootstrap`` — persönlicher Workspace beim ersten
  Login, idempotent. Offene Registrierung heißt: jeder bestätigte Nutzer
  bekommt genau einen persönlichen Workspace, keinen Zugang zu anderen.
* ``GET /api/workspaces/current/members`` — Mitglieder des aktiven Workspace.
* ``PUT``/``DELETE /api/workspaces/current/members/<user_id>`` — Owner und
  Admins verwalten Mitglieder. Der letzte Owner bleibt; ein Admin vergibt
  und entzieht keine Owner-Rolle; jeder darf sich selbst entfernen.

Der aktive Workspace kommt immer aus dem Principal (``X-Agora-Workspace``,
vom Guard gegen die Mitgliedschaft geprüft), nie aus einem Pfad.
"""

from __future__ import annotations

from uuid import UUID

from flask import Blueprint, current_app, request
from pydantic import ValidationError

from ..config import Config
from ..contracts.auth_contract import AuthType
from ..contracts.workspace_contract import (
    DEFAULT_WORKSPACE_ID,
    AuthConfigResponse,
    WorkspaceBootstrapRequest,
    WorkspaceMemberUpsert,
    WorkspaceRole,
    WorkspaceSummary,
)
from ..security.principal_context import (
    current_identity,
    current_principal,
    tenant_mode_active,
)
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import json_error, json_success
from ..utils.auth import identity_only
from ..utils.logger import get_logger
from ..utils.rate_limit import build_rate_limit_key, workspace_rate_limiter

logger = get_logger('agora.workspaces')

#: Öffentlich, ohne Guard: der Browser braucht die Angaben vor dem Login.
auth_public_bp = Blueprint('auth_public', __name__)
workspaces_bp = Blueprint('workspaces', __name__)

_MANAGERS = frozenset({WorkspaceRole.OWNER, WorkspaceRole.ADMIN})
_MUTATING = frozenset({'POST', 'PUT', 'DELETE'})


def _repository():
    from ..repositories.workspace_repository import get_workspace_repository

    return get_workspace_repository()


@auth_public_bp.route('/config', methods=['GET'])
def auth_config():
    jwt_enabled = tenant_mode_active()
    response = AuthConfigResponse(
        auth_backend=Config.AUTH_BACKEND,
        jwt_enabled=jwt_enabled,
        supabase_url=(Config.SUPABASE_URL or None) if jwt_enabled else None,
        supabase_anon_key=(Config.SUPABASE_ANON_KEY or None) if jwt_enabled else None,
    )
    return json_success(response.model_dump(mode='json'))


@workspaces_bp.before_request
def _limit_mutations():
    """Rate-Limit auf Bootstrap und Mitgliederverwaltung (Plan §37)."""
    if request.method not in _MUTATING:
        return None
    result = workspace_rate_limiter.check(
        build_rate_limit_key('workspaces'),
        max_requests=current_app.config.get('AGORA_WORKSPACE_RATE_LIMIT_MAX', Config.AGORA_WORKSPACE_RATE_LIMIT_MAX),
        window_seconds=current_app.config.get(
            'AGORA_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS', Config.AGORA_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS
        ),
    )
    if result.allowed:
        return None
    response, status = json_error(
        ApiErrorCode.RATE_LIMITED,
        status=429,
        extra={'retry_after_seconds': result.retry_after_seconds},
    )
    response.headers['Retry-After'] = str(result.retry_after_seconds)
    return response, status


def _personal_slug(user_id: UUID) -> str:
    """Eindeutig je Nutzer — macht den Bootstrap ohne Sperre idempotent."""
    return f'u-{user_id.hex[:20]}'


@workspaces_bp.route('', methods=['GET'])
@identity_only
def list_workspaces():
    identity = current_identity()
    if identity is None:
        # Betreiber-Zugang (Master-Token, ``ago_``-Key, offener Modus).
        principal = current_principal()
        summaries = [
            WorkspaceSummary(
                workspace_id=DEFAULT_WORKSPACE_ID,
                name='Standard',
                slug='default',
                role=WorkspaceRole.OWNER,
            )
        ] if principal is not None else []
    else:
        repo = _repository()
        summaries = []
        for workspace in repo.list_for_user(identity.user_id):
            membership = repo.membership(workspace.workspace_id, identity.user_id)
            if membership is None:
                continue
            summaries.append(
                WorkspaceSummary(
                    workspace_id=workspace.workspace_id,
                    name=workspace.name,
                    slug=workspace.slug,
                    role=membership.role,
                )
            )
    return json_success(
        [s.model_dump(mode='json') for s in summaries], count=len(summaries)
    )


@workspaces_bp.route('/bootstrap', methods=['POST'])
@identity_only
def bootstrap_workspace():
    identity = current_identity()
    if identity is None:
        return json_error('only for signed-in users', status=400, code='not_applicable')
    try:
        body = WorkspaceBootstrapRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400)

    from ..infrastructure.postgres.repositories.workspace_repository import (
        WorkspaceSlugTaken,
    )

    repo = _repository()
    slug = _personal_slug(identity.user_id)
    workspace = repo.get_by_slug(slug)
    created = False
    if workspace is None:
        default_name = (identity.email or '').split('@', 1)[0] or 'Mein Workspace'
        try:
            workspace = repo.create(body.name or default_name[:80], slug)
            created = True
        except WorkspaceSlugTaken:
            # Gleichzeitiger zweiter Aufruf desselben Nutzers.
            workspace = repo.get_by_slug(slug)
    assert workspace is not None
    membership = repo.membership(workspace.workspace_id, identity.user_id)
    if membership is None:
        # Owner nur für einen Workspace ohne Mitglieder: frisch angelegt oder
        # nach einem abgebrochenen ersten Aufruf verwaist. Wer aus seinem
        # persönlichen Workspace entfernt wurde, kommt so nicht zurück.
        if repo.list_members(workspace.workspace_id):
            return json_error(
                'personal workspace unavailable', status=409, code='personal_workspace_unavailable'
            )
        membership = repo.add_member(workspace.workspace_id, identity.user_id, WorkspaceRole.OWNER)
    if created:
        logger.info('workspace bootstrap: personal workspace created')
    summary = WorkspaceSummary(
        workspace_id=workspace.workspace_id,
        name=workspace.name,
        slug=workspace.slug,
        role=membership.role,
    )
    return json_success(summary.model_dump(mode='json'), created=created)


def _require_principal():
    principal = current_principal()
    if principal is None:
        return None, json_error('workspace required', status=400, code='workspace_required')
    return principal, None


@workspaces_bp.route('/current/members', methods=['GET'])
def list_members():
    principal, error = _require_principal()
    if error:
        return error
    members = _repository().list_members(principal.workspace_id)
    return json_success([m.model_dump(mode='json') for m in members], count=len(members))


def _parse_user_id(raw: str):
    try:
        return UUID(raw), None
    except ValueError:
        return None, json_error(ApiErrorCode.INVALID_ID, status=400)


@workspaces_bp.route('/current/members/<user_id>', methods=['PUT'])
def upsert_member(user_id: str):
    principal, error = _require_principal()
    if error:
        return error
    target, error = _parse_user_id(user_id)
    if error:
        return error
    try:
        body = WorkspaceMemberUpsert.model_validate(request.get_json(silent=True) or {})
    except ValidationError:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400)
    if not principal.roles & _MANAGERS:
        return json_error('forbidden', status=403, code='role_required')

    repo = _repository()
    existing = repo.membership(principal.workspace_id, target)
    is_owner_actor = WorkspaceRole.OWNER in principal.roles
    touches_owner = body.role == WorkspaceRole.OWNER or (
        existing is not None and existing.role == WorkspaceRole.OWNER
    )
    if touches_owner and not is_owner_actor:
        return json_error('forbidden', status=403, code='owner_required')

    from ..infrastructure.postgres.repositories.workspace_repository import LastOwnerError

    try:
        membership = repo.add_member(principal.workspace_id, target, body.role, keep_owner=True)
    except LastOwnerError:
        return json_error('last owner', status=409, code='last_owner')
    return json_success(membership.model_dump(mode='json'))


@workspaces_bp.route('/current/members/<user_id>', methods=['DELETE'])
def remove_member(user_id: str):
    principal, error = _require_principal()
    if error:
        return error
    target, error = _parse_user_id(user_id)
    if error:
        return error
    is_self = principal.auth_type == AuthType.JWT and principal.user_id == target
    if not is_self and not principal.roles & _MANAGERS:
        return json_error('forbidden', status=403, code='role_required')

    repo = _repository()
    existing = repo.membership(principal.workspace_id, target)
    if existing is None:
        return json_error(ApiErrorCode.NOT_FOUND, status=404)
    if (
        existing.role == WorkspaceRole.OWNER
        and not is_self
        and WorkspaceRole.OWNER not in principal.roles
    ):
        return json_error('forbidden', status=403, code='owner_required')

    from ..infrastructure.postgres.repositories.workspace_repository import LastOwnerError

    try:
        repo.remove_member(principal.workspace_id, target, keep_owner=True)
    except LastOwnerError:
        return json_error('last owner', status=409, code='last_owner')
    return json_success({'removed': str(target)})
