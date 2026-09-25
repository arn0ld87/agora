"""Principal eines Requests (ADR-0018, Issue #1613).

Der Guard in :mod:`app.utils.auth` legt für jeden authentifizierten Request
genau einen :class:`~app.contracts.auth_contract.Principal` ab. Alles danach
— Repositories (#1614), RLS-Session (#1615), Workspace-Endpunkte (#1616) —
liest ihn über :func:`current_principal` und nie aus Request-Headern.

Workspace-Wahl für Supabase-Nutzer (§15): Der Header ``X-Agora-Workspace``
nennt den Workspace; er gilt nur, wenn die Mitgliedschaft in
``agora.workspace_members`` steht. Ohne Header gilt die einzige
Mitgliedschaft, bei mehreren ist der Header Pflicht.

Legacy-Zugänge (Master-Token, ``ago_``-Keys, offener Modus) arbeiten im
Default-Workspace mit Rolle ``owner`` — genau der Bestand, den die Migration
dorthin zurückschreibt.
"""

from __future__ import annotations

import threading
from typing import Optional
from uuid import UUID

from flask import g

from ..contracts.auth_contract import AuthType, Principal
from ..contracts.workspace_contract import DEFAULT_WORKSPACE_ID, WorkspaceRole
from .supabase_jwt import SupabaseJwtClaims, SupabaseJwtSettings, SupabaseJwtVerifier

WORKSPACE_HEADER = 'X-Agora-Workspace'
_G_ATTR = 'agora_principal'

#: Trenner der Ticket-Bindung. Weder ``.`` (Ticket-Format) noch ``@``
#: (Grenze zwischen Scope und Bindung) kommen in den Teilen vor.
_BINDING_SEPARATOR = '@'
_BINDING_FIELD_SEPARATOR = '~'


class WorkspaceSelectionError(Exception):
    """Der Workspace eines Supabase-Nutzers lässt sich nicht bestimmen."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def set_principal(principal: Principal) -> None:
    setattr(g, _G_ATTR, principal)


def current_principal() -> Optional[Principal]:
    """Principal des laufenden Requests oder ``None`` außerhalb davon."""
    return g.get(_G_ATTR)


def legacy_principal(auth_type: AuthType) -> Principal:
    """Principal für Master-Token, ``ago_``-Key und offenen Modus."""
    return Principal(
        auth_type=auth_type,
        workspace_id=DEFAULT_WORKSPACE_ID,
        roles=frozenset({WorkspaceRole.OWNER}),
    )


def resolve_jwt_principal(
    claims: SupabaseJwtClaims, header_value: Optional[str], repository
) -> Principal:
    """Principal eines Supabase-Nutzers, geprüft gegen die Mitgliedschaft.

    ``repository`` ist ein ``WorkspaceRepository``. Fehler tragen nur einen
    Code; welche Workspaces es gibt, verrät keine Antwort.
    """
    raw = (header_value or '').strip()
    if raw:
        try:
            workspace_id = UUID(raw)
        except ValueError as exc:
            raise WorkspaceSelectionError('invalid_workspace_header', 400) from exc
        membership = repository.membership(workspace_id, claims.user_id)
        if membership is None:
            # 403 statt 404: auch „existiert nicht“ darf nichts verraten.
            raise WorkspaceSelectionError('workspace_forbidden', 403)
    else:
        workspaces = repository.list_for_user(claims.user_id)
        if not workspaces:
            raise WorkspaceSelectionError('workspace_membership_required', 403)
        if len(workspaces) > 1:
            raise WorkspaceSelectionError('workspace_header_required', 400)
        workspace_id = workspaces[0].workspace_id
        membership = repository.membership(workspace_id, claims.user_id)
        if membership is None:  # zwischen beiden Abfragen entfernt
            raise WorkspaceSelectionError('workspace_membership_required', 403)
    return Principal(
        auth_type=AuthType.JWT,
        user_id=claims.user_id,
        workspace_id=workspace_id,
        roles=frozenset({membership.role}),
    )


#: Scopes je Workspace-Rolle für ``require_scope`` (ADR-0018). Dieselbe
#: Hierarchie wie bei API-Keys: ``admin`` deckt alles, ``write`` auch
#: ``*:control`` und ``*:read``, ``read`` nur ``*:read``. Das betrifft nur
#: Daten des eigenen Workspace — prozessweite Einstellungen sind für
#: JWT-Nutzer gesperrt (``install_blueprint_guard(..., tenant_access=False)``).
ROLE_SCOPES: dict[WorkspaceRole, tuple[str, ...]] = {
    WorkspaceRole.OWNER: ('admin',),
    WorkspaceRole.ADMIN: ('admin',),
    WorkspaceRole.MEMBER: ('write',),
    WorkspaceRole.VIEWER: ('read',),
}


def scopes_for_roles(roles: frozenset[WorkspaceRole]) -> list[str]:
    return sorted({scope for role in roles for scope in ROLE_SCOPES[role]})


# -- Ticket-Bindung ----------------------------------------------------------


def bind_scope(scope: str, principal: Principal) -> str:
    """Hängt den Principal an einen Ticket-Scope; die Signatur deckt beides."""
    parts = (
        principal.auth_type.value,
        str(principal.workspace_id),
        str(principal.user_id) if principal.user_id else '-',
        ','.join(sorted(role.value for role in principal.roles)),
    )
    return f'{scope}{_BINDING_SEPARATOR}{_BINDING_FIELD_SEPARATOR.join(parts)}'


def split_bound_scope(scope: str) -> tuple[str, Optional[Principal]]:
    """``(Basis-Scope, Principal)``; ohne Bindung ist der Principal ``None``.

    Eine unlesbare Bindung ergibt ``(scope, None)`` mit dem **ganzen** Text
    als Basis — der Vergleich mit dem erwarteten Scope schlägt dann fehl.
    """
    if _BINDING_SEPARATOR not in scope:
        return scope, None
    base, binding = scope.split(_BINDING_SEPARATOR, 1)
    fields = binding.split(_BINDING_FIELD_SEPARATOR)
    if len(fields) != 4:
        return scope, None
    auth_type, workspace, user, roles = fields
    try:
        principal = Principal(
            auth_type=AuthType(auth_type),
            workspace_id=UUID(workspace),
            user_id=None if user == '-' else UUID(user),
            roles=frozenset(WorkspaceRole(r) for r in roles.split(',') if r),
        )
    except ValueError:
        return scope, None
    return base, principal


# -- Verifier ----------------------------------------------------------------

_verifier_lock = threading.Lock()
_verifier: Optional[SupabaseJwtVerifier] = None


def get_jwt_verifier(settings: SupabaseJwtSettings) -> SupabaseJwtVerifier:
    """Ein Verifier pro Prozess und Einstellung; der JWKS-Cache lebt darin."""
    global _verifier
    with _verifier_lock:
        if _verifier is None or _verifier.settings != settings:
            _verifier = SupabaseJwtVerifier(settings)
        return _verifier


def reset_jwt_verifier() -> None:
    """Für Tests und nach einem Fork."""
    global _verifier
    with _verifier_lock:
        _verifier = None
