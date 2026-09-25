"""Vertragstests fuer Workspace/Auth (Issue #1612)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.contracts.auth_contract import AuthType, Principal
from app.contracts.workspace_contract import Workspace, WorkspaceMembership, WorkspaceRole

WORKSPACE_ID = UUID('00000000-0000-0000-0000-000000000001')
USER_ID = UUID('11111111-1111-1111-1111-111111111111')


def test_workspace_role_values() -> None:
    assert {role.value for role in WorkspaceRole} == {
        'owner',
        'admin',
        'member',
        'viewer',
    }


def test_workspace_roundtrip() -> None:
    now = datetime.now(timezone.utc)
    workspace = Workspace(
        workspace_id=WORKSPACE_ID,
        name='Standard',
        slug='default',
        created_at=now,
        updated_at=now,
    )

    dumped = workspace.model_dump()
    restored = Workspace.model_validate(dumped)

    assert restored == workspace


def test_workspace_membership_roundtrip() -> None:
    now = datetime.now(timezone.utc)
    membership = WorkspaceMembership(
        workspace_id=WORKSPACE_ID,
        user_id=USER_ID,
        role=WorkspaceRole.OWNER,
        created_at=now,
    )

    assert WorkspaceMembership.model_validate(membership.model_dump()) == membership


def test_workspace_forbids_extra_fields() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        Workspace(
            workspace_id=WORKSPACE_ID,
            name='Standard',
            slug='default',
            created_at=now,
            updated_at=now,
            extra_field='nicht erlaubt',
        )


def test_principal_jwt_requires_user_id() -> None:
    with pytest.raises(ValidationError):
        Principal(
            auth_type=AuthType.JWT,
            user_id=None,
            workspace_id=WORKSPACE_ID,
            roles=frozenset({WorkspaceRole.MEMBER}),
        )


def test_principal_jwt_with_user_id_is_valid() -> None:
    principal = Principal(
        auth_type=AuthType.JWT,
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
        roles=frozenset({WorkspaceRole.MEMBER}),
    )
    assert principal.user_id == USER_ID


@pytest.mark.parametrize(
    'auth_type', [AuthType.API_KEY, AuthType.MASTER_TOKEN, AuthType.ANONYMOUS]
)
def test_principal_non_jwt_allows_missing_user_id(auth_type: AuthType) -> None:
    principal = Principal(
        auth_type=auth_type,
        user_id=None,
        workspace_id=WORKSPACE_ID,
        roles=frozenset(),
    )
    assert principal.user_id is None


def test_principal_is_frozen() -> None:
    principal = Principal(
        auth_type=AuthType.ANONYMOUS,
        workspace_id=WORKSPACE_ID,
        roles=frozenset(),
    )
    with pytest.raises(ValidationError):
        principal.workspace_id = UUID('22222222-2222-2222-2222-222222222222')


def test_principal_default_scopes_are_empty() -> None:
    principal = Principal(
        auth_type=AuthType.ANONYMOUS,
        workspace_id=WORKSPACE_ID,
        roles=frozenset(),
    )
    assert principal.scopes == frozenset()
