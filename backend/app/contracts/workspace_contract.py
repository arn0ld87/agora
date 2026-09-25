"""Workspace-Contract (Pydantic v2) — Issue #1612, docs/plans/supabase.md PR 5.

Beschreibt einen Workspace und die Mitgliedschaft eines Nutzers darin, wie sie
in ``agora.workspaces``/``agora.workspace_members`` liegen
(``app/infrastructure/postgres/models/workspace.py``). Dieser Vertrag bildet
nur die Struktur ab — **umgeschaltet ist damit nichts**: kein Consumer liest
oder schreibt bisher über ihn.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

#: Feste UUID des Default-Workspace. Die Alembic-Revision ``5c2913c7ba4f``
#: legt ihn an; Legacy-Principals (Master-Token, ``ago_``-Keys) und der
#: Bestand vor ADR-0018 gehören zu ihm. Die Migration trägt denselben Wert als
#: Literal, weil Migrationen keinen App-Code importieren.
DEFAULT_WORKSPACE_ID = UUID('00000000-0000-0000-0000-000000000001')


class WorkspaceRole(str, Enum):
    """Rolle einer Mitgliedschaft. Werte identisch zum Check-Constraint
    ``ck_workspace_members_role_valid``."""

    OWNER = 'owner'
    ADMIN = 'admin'
    MEMBER = 'member'
    VIEWER = 'viewer'


class Workspace(BaseModel):
    """Metadaten eines Workspace."""

    model_config = ConfigDict(extra='forbid')

    workspace_id: UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class WorkspaceMembership(BaseModel):
    """Mitgliedschaft eines Nutzers in genau einem Workspace mit einer Rolle."""

    model_config = ConfigDict(extra='forbid')

    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole
    created_at: datetime


class WorkspaceSummary(BaseModel):
    """Ein Workspace aus Sicht eines Nutzers: mit seiner Rolle darin
    (``GET /api/workspaces``, #1616)."""

    model_config = ConfigDict(extra='forbid')

    workspace_id: UUID
    name: str
    slug: str
    role: WorkspaceRole


class WorkspaceBootstrapRequest(BaseModel):
    """``POST /api/workspaces/bootstrap``: optionaler Anzeigename."""

    model_config = ConfigDict(extra='forbid')

    name: str | None = Field(default=None, min_length=1, max_length=80)


class WorkspaceMemberUpsert(BaseModel):
    """``PUT /api/workspaces/current/members/<user_id>``."""

    model_config = ConfigDict(extra='forbid')

    role: WorkspaceRole


class AuthConfigResponse(BaseModel):
    """``GET /api/auth/config`` — öffentlich, ohne Geheimnisse (#1616).

    ``supabase_anon_key`` ist der öffentliche Anon-Key; er ist für den Browser
    bestimmt und gewährt allein keinen Zugriff auf Agora-Daten.
    """

    model_config = ConfigDict(extra='forbid')

    auth_backend: str
    jwt_enabled: bool
    supabase_url: str | None = None
    supabase_anon_key: str | None = None


__all__ = [
    'DEFAULT_WORKSPACE_ID',
    'AuthConfigResponse',
    'Workspace',
    'WorkspaceBootstrapRequest',
    'WorkspaceMemberUpsert',
    'WorkspaceMembership',
    'WorkspaceRole',
    'WorkspaceSummary',
]
