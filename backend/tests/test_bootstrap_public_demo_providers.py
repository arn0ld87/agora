"""Public demo bootstrap must never inherit operator provider credentials."""

import pytest
from cryptography.fernet import Fernet

from app.config import DEMO_MODE_FORBIDDEN_ENV_VARS
from app.contracts.ai_provider_contract import ProviderConnectionUpsertRequest
from app.contracts.llm_routing_contract import StageLLMRoute
from app.services.llm_provider_secrets_store import LlmProviderSecretsStore
from app.services.provider_connection_store import ProviderConnectionStore
from app.services import settings_layer
from app.services.workspace_routing_store import WorkspaceRoutingStore
from scripts.bootstrap_public_demo_providers import bootstrap_public_demo_providers


@pytest.fixture(autouse=True)
def settings_file(tmp_path, monkeypatch):
    """The bootstrap reads file settings as well as env; isolate both layers."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(
        settings_layer, "_default_service", settings_layer.SettingsService(instance_path=path)
    )
    return path


def _clear_all_forbidden_vars(monkeypatch):
    for name in DEMO_MODE_FORBIDDEN_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_bootstrap_refuses_when_operator_env_var_set(tmp_path, monkeypatch):
    """Item 4: bootstrap muss vor jedem Write abbrechen, sobald eine
    verbotene Betreiber-Env-Var gesetzt ist. Die Meldung nennt nur den Namen.
    """
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    _clear_all_forbidden_vars(monkeypatch)
    secret_value = "unit-test-anthropic-operator-value"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret_value)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY") as excinfo:
        bootstrap_public_demo_providers()

    assert secret_value not in str(excinfo.value)
    assert ProviderConnectionStore().list_connections() == []


def test_bootstrap_seeds_secret_free_connections_and_default(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    _clear_all_forbidden_vars(monkeypatch)
    bootstrap_public_demo_providers()
    bootstrap_public_demo_providers()

    connections = ProviderConnectionStore().list_connections()
    assert {connection.id for connection in connections} == {
        "openai", "google", "minimax", "ollama_cloud", "bedrock",
    }
    assert all(connection.secret_ref is None for connection in connections)
    assert WorkspaceRoutingStore().load().global_default.provider_id == "openai"


def test_bootstrap_refuses_operator_key_in_settings_file(tmp_path, monkeypatch, settings_file):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    _clear_all_forbidden_vars(monkeypatch)
    settings_file.write_text('{"OPENAI_API_KEY": "unit-test-operator-key"}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="instance/settings.json:OPENAI_API_KEY") as excinfo:
        bootstrap_public_demo_providers()

    assert "unit-test-operator-key" not in str(excinfo.value)
    assert ProviderConnectionStore().list_connections() == []


def test_bootstrap_refuses_existing_operator_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    _clear_all_forbidden_vars(monkeypatch)
    ProviderConnectionStore().upsert_connection(ProviderConnectionUpsertRequest(
        display_name="Operator", provider_kind="openai", base_url="https://operator.example/v1"
    ))
    with pytest.raises(RuntimeError, match="not secret-free and canonical"):
        bootstrap_public_demo_providers()


def test_bootstrap_refuses_operator_secret_in_secrets_store(tmp_path, monkeypatch):
    """An operator secret in the Fernet store must block bootstrap even without
    a matching ``ProviderConnection.secret_ref`` (e.g. orphaned/legacy entry)."""
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    _clear_all_forbidden_vars(monkeypatch)
    monkeypatch.setenv("AGORA_SECRET_KEY", Fernet.generate_key().decode("utf-8"))
    LlmProviderSecretsStore(data_dir=tmp_path).upsert("openai", api_key="sk-operator-secret-key")

    with pytest.raises(RuntimeError, match="operator secret present"):
        bootstrap_public_demo_providers()

    assert ProviderConnectionStore().list_connections() == []


def test_bootstrap_refuses_routing_default_to_non_demo_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    _clear_all_forbidden_vars(monkeypatch)
    WorkspaceRoutingStore().set_global_default(
        StageLLMRoute(provider_id="ollama", model="llama3")
    )

    with pytest.raises(RuntimeError, match="non-demo connection"):
        bootstrap_public_demo_providers()

    assert ProviderConnectionStore().list_connections() == []


def test_bootstrap_refuses_stage_override_to_non_demo_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    _clear_all_forbidden_vars(monkeypatch)
    WorkspaceRoutingStore().set_stage_override(
        "report_generation", StageLLMRoute(provider_id="ollama", model="llama3")
    )

    with pytest.raises(RuntimeError, match="non-demo connection"):
        bootstrap_public_demo_providers()

    assert ProviderConnectionStore().list_connections() == []
