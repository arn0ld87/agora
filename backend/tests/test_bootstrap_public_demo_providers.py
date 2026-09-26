"""Public demo bootstrap must never inherit operator provider credentials."""

import pytest
from cryptography.fernet import Fernet

from app.contracts.ai_provider_contract import ProviderConnectionUpsertRequest
from app.contracts.llm_routing_contract import StageLLMRoute
from app.services.llm_provider_secrets_store import LlmProviderSecretsStore
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


def test_bootstrap_refuses_operator_secret_in_secrets_store(tmp_path, monkeypatch):
    """An operator secret in the Fernet store must block bootstrap even without
    a matching ``ProviderConnection.secret_ref`` (e.g. orphaned/legacy entry)."""
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGORA_SECRET_KEY", Fernet.generate_key().decode("utf-8"))
    LlmProviderSecretsStore(data_dir=tmp_path).upsert("openai", api_key="sk-operator-secret-key")

    with pytest.raises(RuntimeError, match="operator secret present"):
        bootstrap_public_demo_providers()

    assert ProviderConnectionStore().list_connections() == []


def test_bootstrap_refuses_routing_default_to_non_demo_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    WorkspaceRoutingStore().set_global_default(
        StageLLMRoute(provider_id="ollama", model="llama3")
    )

    with pytest.raises(RuntimeError, match="non-demo connection"):
        bootstrap_public_demo_providers()

    assert ProviderConnectionStore().list_connections() == []


def test_bootstrap_refuses_stage_override_to_non_demo_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    WorkspaceRoutingStore().set_stage_override(
        "report_generation", StageLLMRoute(provider_id="ollama", model="llama3")
    )

    with pytest.raises(RuntimeError, match="non-demo connection"):
        bootstrap_public_demo_providers()

    assert ProviderConnectionStore().list_connections() == []
