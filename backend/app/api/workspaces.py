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

from functools import wraps
from uuid import UUID

from flask import Blueprint, current_app, request
from werkzeug.exceptions import BadRequest
from pydantic import ValidationError

from ..config import Config
from ..contracts.auth_contract import AuthType
from ..contracts.workspace_contract import (
    DEFAULT_WORKSPACE_ID,
    AuthConfigResponse,
    WorkspaceBootstrapRequest,
    WorkspaceMemberRemoval,
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
from ..repositories.workspace_repository import WorkspaceBackendUnavailable
from ..utils.rate_limit import build_rate_limit_key, workspace_rate_limiter

logger = get_logger('agora.workspaces')

#: Öffentlich, ohne Guard: der Browser braucht die Angaben vor dem Login.
auth_public_bp = Blueprint('auth_public', __name__)
workspaces_bp = Blueprint('workspaces', __name__)

_MANAGERS = frozenset({WorkspaceRole.OWNER, WorkspaceRole.ADMIN})


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


@workspaces_bp.errorhandler(WorkspaceBackendUnavailable)
def _backend_unavailable(_exc):
    # Einmandantig ohne DATABASE_URL gibt es nur den virtuellen
    # Default-Workspace; Mitglieder und Bootstrap brauchen PostgreSQL.
    return json_error('workspaces require DATABASE_URL', status=503, code='workspaces_unavailable')


def _json_object() -> dict | None:
    """Body als JSON-Objekt; leerer Body zählt als ``{}``, alles andere
    (kaputtes JSON, Liste, Zahl) als ``None``."""
    if not request.get_data(cache=True):
        return {}
    try:
        body = request.get_json(force=True)
    except BadRequest:
        return None
    return body if isinstance(body, dict) else None


def _rate_limit_key() -> str:
    """Nach der Anmeldung: je Nutzer, sonst je Client-Adresse (Betreiber)."""
    identity = current_identity()
    principal = current_principal()
    user_id = identity.user_id if identity is not None else (principal.user_id if principal else None)
    if user_id is not None:
        return f'workspaces:user:{user_id}'
    return build_rate_limit_key('workspaces')


def _rate_limited(view):
    """Rate-Limit auf Bootstrap und Mitgliederverwaltung (Plan §37).

    Als Decorator an der View, nicht als ``before_request``: so läuft es erst
    nach dem Guard. Anfragen ohne gültige Anmeldung verbrauchen den Topf
    eines Nutzers nicht.
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        result = workspace_rate_limiter.check(
            _rate_limit_key(),
            max_requests=current_app.config.get(
                'AGORA_WORKSPACE_RATE_LIMIT_MAX', Config.AGORA_WORKSPACE_RATE_LIMIT_MAX
            ),
            window_seconds=current_app.config.get(
                'AGORA_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS', Config.AGORA_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS
            ),
        )
        if not result.allowed:
            response, status = json_error(
                ApiErrorCode.RATE_LIMITED,
                status=429,
                extra={'retry_after_seconds': result.retry_after_seconds},
            )
            response.headers['Retry-After'] = str(result.retry_after_seconds)
            return response, status
        return view(*args, **kwargs)

    return wrapper


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
@_rate_limited
def bootstrap_workspace():
    identity = current_identity()
    if identity is None:
        return json_error('only for signed-in users', status=400, code='not_applicable')
    raw = _json_object()
    if raw is None:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400)
    try:
        body = WorkspaceBootstrapRequest.model_validate(raw)
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
@_rate_limited
def upsert_member(user_id: str):
    principal, error = _require_principal()
    if error:
        return error
    target, error = _parse_user_id(user_id)
    if error:
        return error
    raw = _json_object()
    if raw is None:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400)
    try:
        body = WorkspaceMemberUpsert.model_validate(raw)
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

    from ..infrastructure.postgres.repositories.workspace_repository import (
        LastOwnerError,
        UserDirectoryUnavailable,
    )

    if existing is None:
        # Keine Phantom-Mitgliedschaft: ``user_id`` hat keinen Fremdschlüssel
        # auf ``auth.users`` (reines PostgreSQL in der CI), die Prüfung liegt
        # hier. Ohne ``auth``-Schema ist sie nicht möglich.
        try:
            known = repo.user_exists(target)
        except UserDirectoryUnavailable:
            logger.warning('workspace members: auth.users not readable for the runtime role')
            return json_error('user directory unavailable', status=503, code='user_directory_unavailable')
        if known is False:
            return json_error(ApiErrorCode.NOT_FOUND, status=404)

    try:
        membership = repo.add_member(principal.workspace_id, target, body.role, keep_owner=True)
    except LastOwnerError:
        return json_error('last owner', status=409, code='last_owner')
    return json_success(membership.model_dump(mode='json'))


@workspaces_bp.route('/current/members/<user_id>', methods=['DELETE'])
@_rate_limited
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
    return json_success(WorkspaceMemberRemoval(user_id=target).model_dump(mode='json'))
