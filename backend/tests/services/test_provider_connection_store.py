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


def test_upsert_persists_a_loopback_url_for_local_ollama(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, _ = _store(tmp_path, monkeypatch)

    connection = store.upsert_connection(
        _request(
            display_name="Ollama lokal",
            provider_kind="ollama",
            base_url="http://localhost:11434",
            api_key=None,
        )
    )

    assert connection.base_url == "http://localhost:11434"
    assert connection.transport == "local"
    assert store.list_connections() == [connection]


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


@pytest.mark.parametrize("operation", ["upsert", "probe", "delete"])
def test_process_lock_covers_read_modify_write_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """Der Prozess-Lock muss bereits vor dem Read und bis replace gehalten werden."""
    store, provider_connection_store = _store(tmp_path, monkeypatch)
    if operation != "upsert":
        store.upsert_connection(_request())

    lock_depth = 0
    original_read = store._read_raw
    original_replace = provider_connection_store.os.replace

    def track_flock(_fh: object, flag: int) -> None:
        nonlocal lock_depth
        if flag == provider_connection_store.fcntl.LOCK_EX:
            lock_depth += 1
        elif flag == provider_connection_store.fcntl.LOCK_UN:
            lock_depth -= 1

    def read_while_locked() -> dict:
        assert lock_depth == 1
        return original_read()

    def replace_while_locked(source: object, destination: object) -> None:
        assert lock_depth == 1
        original_replace(source, destination)

    monkeypatch.setattr(provider_connection_store.fcntl, "flock", track_flock)
    monkeypatch.setattr(store, "_read_raw", read_while_locked)
    monkeypatch.setattr(provider_connection_store.os, "replace", replace_while_locked)

    if operation == "upsert":
        store.upsert_connection(_request(display_name="OpenAI aktualisiert", api_key=None))
    elif operation == "probe":
        store.update_probe(
            "openai",
            status="connected",
            status_message="Verbindung hergestellt",
            tested_at=datetime(2026, 7, 12, 12, tzinfo=timezone.utc),
        )
    else:
        assert store.delete_connection("openai") is True

    assert lock_depth == 0


def test_rejects_json_document_whose_root_is_not_an_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _ = _store(tmp_path, monkeypatch)
    (tmp_path / "provider_connections.json").write_text("[]", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Konnte Provider-Connection-Store nicht lesen"):
        store.list_connections()


def test_partial_os_write_aborts_before_replacing_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, provider_connection_store = _store(tmp_path, monkeypatch)
    original = store.upsert_connection(_request())
    original_write = provider_connection_store.os.write
    original_replace = provider_connection_store.os.replace
    writes = 0

    def partial_write(fd: int, payload: bytes) -> int:
        nonlocal writes
        writes += 1
        if writes == 1:
            return original_write(fd, payload[:1])
        return 0

    def replace_must_not_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("os.replace darf nach unvollständigem Write nicht laufen")

    monkeypatch.setattr(provider_connection_store.os, "write", partial_write)
    monkeypatch.setattr(provider_connection_store.os, "replace", replace_must_not_run)

    with pytest.raises(RuntimeError, match="Konnte Provider-Connection-Store nicht schreiben"):
        store.upsert_connection(_request(display_name="Unvollständig", api_key=None))

    monkeypatch.setattr(provider_connection_store.os, "replace", original_replace)
    assert store.list_connections() == [original]
