"""Workspace provider keys must stay isolated from users and operator state."""

from __future__ import annotations

from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from flask import Flask

from app.api import workspaces as workspace_api
from app.contracts.auth_contract import AuthType, Principal
from app.contracts.workspace_contract import WorkspaceRole
from app.services.workspace_provider_credentials_store import WorkspaceProviderCredentialsStore


ALICE_WORKSPACE = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
BOB_WORKSPACE = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
ALICE = UUID("a11ce000-0000-4000-8000-000000000011")


@pytest.fixture
def key_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("AGORA_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    return tmp_path


def _principal(workspace_id=ALICE_WORKSPACE, role=WorkspaceRole.OWNER):
    return Principal(
        auth_type=AuthType.JWT,
        user_id=ALICE,
        workspace_id=workspace_id,
        roles=frozenset({role}),
    )


def test_workspace_key_store_never_falls_back_to_another_workspace(key_environment):
    store = WorkspaceProviderCredentialsStore(data_dir=key_environment)
    store.upsert(ALICE_WORKSPACE, "openai", api_key="alice-private-key")

    assert store.get_plaintext(ALICE_WORKSPACE, "openai") == "alice-private-key"
    assert store.get_plaintext(BOB_WORKSPACE, "openai") is None
    assert store.list_entries(BOB_WORKSPACE) == []
    assert "alice-private-key" not in "".join(
        path.read_text() for path in key_environment.rglob("*.json")
    )
    with pytest.raises(TypeError):
        store.get_plaintext("../another-workspace", "openai")


def test_workspace_key_api_keeps_secret_out_of_response_and_enforces_role(
    key_environment, monkeypatch
):
    principal = {"value": _principal()}
    monkeypatch.setattr(workspace_api, "current_principal", lambda: principal["value"])
    app = Flask(__name__)
    app.register_blueprint(workspace_api.workspaces_bp, url_prefix="/api/workspaces")
    client = app.test_client()

    response = client.put(
        "/api/workspaces/current/provider-credentials/openai",
        json={"api_key": "alice-private-key"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["configured"] is True
    assert "alice-private-key" not in response.get_data(as_text=True)

    principal["value"] = _principal(BOB_WORKSPACE)
    response = client.get("/api/workspaces/current/provider-credentials")
    assert response.get_json()["data"] == {"items": [], "total": 0}

    principal["value"] = _principal(role=WorkspaceRole.VIEWER)
    response = client.put(
        "/api/workspaces/current/provider-credentials/openai",
        json={"api_key": "viewer-key"},
    )
    assert (response.status_code, response.get_json()["code"]) == (403, "role_required")

    principal["value"] = Principal(
        auth_type=AuthType.MASTER_TOKEN,
        workspace_id=ALICE_WORKSPACE,
        roles=frozenset({WorkspaceRole.OWNER}),
    )
    response = client.get("/api/workspaces/current/provider-credentials")
    assert (response.status_code, response.get_json()["code"]) == (403, "jwt_required")
