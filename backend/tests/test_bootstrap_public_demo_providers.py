"""Public demo bootstrap must never inherit operator provider credentials."""

import pytest

from app.contracts.ai_provider_contract import ProviderConnectionUpsertRequest
from app.services.provider_connection_store import ProviderConnectionStore
from app.services.workspace_routing_store import WorkspaceRoutingStore
from scripts.bootstrap_public_demo_providers import bootstrap_public_demo_providers


def test_bootstrap_seeds_secret_free_connections_and_default(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    bootstrap_public_demo_providers()
    bootstrap_public_demo_providers()

    connections = ProviderConnectionStore().list_connections()
    assert {connection.id for connection in connections} == {"openai", "google", "minimax"}
    assert all(connection.secret_ref is None for connection in connections)
    assert WorkspaceRoutingStore().load().global_default.provider_id == "openai"


def test_bootstrap_refuses_existing_operator_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    ProviderConnectionStore().upsert_connection(ProviderConnectionUpsertRequest(
        display_name="Operator", provider_kind="openai", base_url="https://operator.example/v1"
    ))
    with pytest.raises(RuntimeError, match="not secret-free and canonical"):
        bootstrap_public_demo_providers()
