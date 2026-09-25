"""Auth-Contract (Pydantic v2) — Issue #1612, docs/plans/supabase.md PR 5.

``Principal`` ist der künftige Träger für "wer handelt gerade, in welchem
Workspace, mit welchen Rollen" — noch ohne einen Consumer, der ihn befüllt.
Er ist ``frozen``: ein Principal wird für eine Request konstruiert und danach
nicht mehr verändert, dieselbe Erwartung wie bei ``PostCreatedEvent``.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from .workspace_contract import WorkspaceRole


class AuthType(str, Enum):
    """Woher ein Principal seine Identität bezieht."""

    JWT = 'jwt'
    API_KEY = 'api_key'
    MASTER_TOKEN = 'master_token'  # noqa: S105 - Enum-Wertname, kein Secret
    ANONYMOUS = 'anonymous'


class Principal(BaseModel):
    """Wer handelt, in welchem Workspace, mit welchen Rollen/Scopes.

    ``auth_type=jwt`` verlangt ``user_id`` — ein JWT identifiziert immer einen
    Nutzer, die übrigen ``AuthType``-Werte (API-Key, Master-Token, anonym)
    können ohne Nutzerbezug auftreten.
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    auth_type: AuthType
    user_id: Optional[UUID] = None
    workspace_id: UUID
    roles: frozenset[WorkspaceRole]
    scopes: frozenset[str] = frozenset()

    @model_validator(mode='after')
    def _jwt_requires_user_id(self) -> 'Principal':
        if self.auth_type == AuthType.JWT and self.user_id is None:
            raise ValueError('auth_type=jwt requires user_id')
        return self


__all__ = ['AuthType', 'Principal']
