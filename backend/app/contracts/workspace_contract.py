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

from pydantic import BaseModel, ConfigDict

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


__all__ = ['DEFAULT_WORKSPACE_ID', 'Workspace', 'WorkspaceMembership', 'WorkspaceRole']
