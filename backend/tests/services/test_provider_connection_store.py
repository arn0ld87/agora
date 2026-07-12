from __future__ import annotations

import json
import importlib
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.contracts.ai_provider_contract import ProviderConnectionUpsertRequest
from app.services.llm_provider_secrets_store import LlmProviderSecretsStore


def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGORA_SECRET_KEY", Fernet.generate_key().decode("utf-8"))
    module = importlib.import_module("app.services.provider_connection_store")
    return module.ProviderConnectionStore(
        data_dir=tmp_path,
        secrets_store=LlmProviderSecretsStore(data_dir=tmp_path),
    ), module


def _request(**overrides: object) -> ProviderConnectionUpsertRequest:
    values = {
        "display_name": "OpenAI",
        "provider_kind": "openai",
        "base_url": "https://api.openai.example/v1",
        "api_key": "test-only-api-key",
    }
    values.update(overrides)
    return ProviderConnectionUpsertRequest(**values)


def test_list_connections_is_empty_without_store_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, _ = _store(tmp_path, monkeypatch)
    assert store.list_connections() == []


def test_upsert_persists_metadata_and_secret_reference_without_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _ = _store(tmp_path, monkeypatch)
    connection = store.upsert_connection(_request())

    assert connection.id == "openai"
    assert connection.secret_ref == "openai"
    assert connection.auth_mode == "api_key"
    assert connection.transport == "http"
    assert connection.status == "unknown"
    assert connection.created_at == connection.updated_at
    assert store._secrets_store.get_plaintext("openai") == "test-only-api-key"

    stored = (tmp_path / "provider_connections.json").read_text(encoding="utf-8")
    assert "test-only-api-key" not in stored
    assert json.loads(stored)["connections"]["openai"]["secret_ref"] == "openai"
    assert stat.S_IMODE((tmp_path / "provider_connections.json").stat().st_mode) == 0o600


def test_update_probe_persists_status_message_and_timestamps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, provider_connection_store = _store(tmp_path, monkeypatch)
    created_at = datetime(2026, 7, 12, 10, tzinfo=timezone.utc)
    updated_at = datetime(2026, 7, 12, 11, tzinfo=timezone.utc)
    tested_at = datetime(2026, 7, 12, 10, 30, tzinfo=timezone.utc)
    timestamps = iter((created_at, updated_at))
    monkeypatch.setattr(provider_connection_store, "_now", lambda: next(timestamps))
    connection = store.upsert_connection(_request())

    probed = store.update_probe(
        connection.id,
        status="connected",
        status_message="Verbindung hergestellt",
        tested_at=tested_at,
    )

    assert probed.status == "connected"
    assert probed.status_message == "Verbindung hergestellt"
    assert probed.created_at == created_at
    assert probed.updated_at == updated_at
    assert probed.last_tested_at == tested_at
    assert store.list_connections() == [probed]


def test_delete_connection_removes_metadata_and_referenced_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _ = _store(tmp_path, monkeypatch)
    connection = store.upsert_connection(_request())

    assert store.delete_connection(connection.id) is True
    assert store.delete_connection(connection.id) is False
    assert store.list_connections() == []
    assert store._secrets_store.get_entry("openai") is None


def test_failed_atomic_write_keeps_previous_connection_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, provider_connection_store = _store(tmp_path, monkeypatch)
    original = store.upsert_connection(_request())

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(provider_connection_store.os, "replace", fail_replace)

    with pytest.raises(RuntimeError, match="Konnte Provider-Connection-Store nicht schreiben"):
        store.upsert_connection(_request(display_name="Geändert", api_key=None))

    assert store.list_connections() == [original]
