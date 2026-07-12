"""Tests für den Fernet-encrypted LLM-Provider-Secrets-Store."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.services.llm_provider_secrets_store import (
    LlmProviderSecretsStore,
    _mask_key,
    get_llm_provider_secrets_store,
    reset_singleton_for_tests,
)


@pytest.fixture
def secret_env(monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("AGORA_SECRET_KEY", key)
    yield key


@pytest.fixture
def temp_store(tmp_path: Path, secret_env):
    store = LlmProviderSecretsStore(data_dir=tmp_path)
    yield store
    if (tmp_path / "llm_provider_secrets.json").exists():
        (tmp_path / "llm_provider_secrets.json").unlink()


def test_upsert_roundtrip_encrypts_and_returns_masked_entry(temp_store):
    entry = temp_store.upsert("openai", api_key="sk-test1234567890abcdef")
    assert entry.provider_id == "openai"
    assert entry.masked_value.endswith("cdef")
    assert "test" not in entry.masked_value
    assert temp_store.get_plaintext("openai") == "sk-test1234567890abcdef"


def test_upsert_keeps_created_at_on_replace(temp_store):
    first = temp_store.upsert("openai", api_key="sk-aaaaaaaaaaaaaa01")
    second = temp_store.upsert("openai", api_key="sk-bbbbbbbbbbbbbb02")
    assert first.created_at == second.created_at
    assert second.updated_at >= first.updated_at
    assert temp_store.get_plaintext("openai") == "sk-bbbbbbbbbbbbbb02"


def test_delete_removes_entry(temp_store):
    temp_store.upsert("openai", api_key="sk-xxxxxxxxxxxx9999")
    assert temp_store.delete("openai") is True
    assert temp_store.get_entry("openai") is None
    assert temp_store.delete("openai") is False


def test_mark_validated_updates_timestamp(temp_store):
    temp_store.upsert("openai", api_key="sk-yyyyyyyyyyyy7777")
    updated = temp_store.mark_validated("openai", ok=True)
    assert updated is not None
    assert updated.last_validation_ok is True
    assert updated.last_validated_at is not None


def test_list_entries_returns_all_providers(temp_store):
    temp_store.upsert("openai", api_key="sk-aaa00000aaaa0001")
    temp_store.upsert("google", api_key="AIza000000000bbbb")
    entries = temp_store.list_entries()
    assert {e.provider_id for e in entries} == {"openai", "google"}


def test_missing_secret_key_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("AGORA_SECRET_KEY", raising=False)
    store = LlmProviderSecretsStore(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match="AGORA_SECRET_KEY"):
        store.upsert("openai", api_key="sk-ccc00000cccc0002")


def test_invalid_secret_key_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("AGORA_SECRET_KEY", "not-a-valid-fernet-key")
    store = LlmProviderSecretsStore(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match="kein gültiger Fernet-Key"):
        store.upsert("openai", api_key="sk-ddd00000dddd0003")


def test_decrypt_with_wrong_key_raises(monkeypatch, tmp_path):
    key_a = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("AGORA_SECRET_KEY", key_a)
    store = LlmProviderSecretsStore(data_dir=tmp_path)
    store.upsert("openai", api_key="sk-eee00000eeee0004")

    # Schlüssel rotieren ohne Re-Encrypt → Lookup muss klar fehlschlagen
    key_b = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("AGORA_SECRET_KEY", key_b)
    with pytest.raises(RuntimeError, match="entschlüsselt"):
        store.get_plaintext("openai")


def test_mask_key_format():
    assert _mask_key("sk-1234567890abcd") == "sk-...abcd"
    assert _mask_key("AIzaSyABCDEFGHIJKL") == "AI-...IJKL"
    assert _mask_key("ghp_xxxxxxxxxxxxYY99") == "gh-...YY99"
    # Sehr kurzer Key fällt auf Sentinel zurück
    short = _mask_key("abc")
    assert "..." in short


def test_singleton_persists_across_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGORA_SECRET_KEY", Fernet.generate_key().decode("utf-8"))
    reset_singleton_for_tests()
    a = get_llm_provider_secrets_store()
    b = get_llm_provider_secrets_store()
    assert a is b
    a.upsert("openai", api_key="sk-fff00000ffff0005")
    assert b.get_plaintext("openai") == "sk-fff00000ffff0005"
    reset_singleton_for_tests()


def test_upsert_holds_file_lock_from_read_through_replace(temp_store, monkeypatch):
    """Der Prozess-Lock umschließt die gesamte Read-modify-write-Sequenz."""
    events: list[str] = []
    real_read = temp_store._read_raw
    real_replace = os.replace

    @contextmanager
    def tracked_file_lock():
        events.append("lock")
        try:
            yield
        finally:
            events.append("unlock")

    def tracked_read() -> dict:
        assert events == ["lock"]
        events.append("read")
        return real_read()

    def tracked_replace(source: str | Path, target: str | Path) -> None:
        assert events == ["lock", "read"]
        events.append("replace")
        real_replace(source, target)

    monkeypatch.setattr(temp_store, "_file_lock", tracked_file_lock)
    monkeypatch.setattr(temp_store, "_read_raw", tracked_read)
    monkeypatch.setattr(
        "app.services.llm_provider_secrets_store.os.replace", tracked_replace
    )

    temp_store.upsert("openai", api_key="sk-lock-order-0123456789")

    assert events == ["lock", "read", "replace", "unlock"]


def test_write_retries_partial_os_write_until_payload_is_complete(temp_store, monkeypatch):
    """Ein Short-Write darf nicht zu einer atomar ersetzten Trunkierung führen."""
    real_write = os.write

    def partial_write(fd: int, payload: bytes) -> int:
        chunk_length = max(1, len(payload) // 3)
        return real_write(fd, payload[:chunk_length])

    monkeypatch.setattr(
        "app.services.llm_provider_secrets_store.os.write", partial_write
    )

    temp_store.upsert("openai", api_key="sk-partial-write-0123456789")

    assert temp_store.get_plaintext("openai") == "sk-partial-write-0123456789"


def test_json_root_that_is_not_an_object_raises_controlled_runtime_error(
    temp_store,
):
    """Korrupte JSON-Roots dürfen nie als internes AttributeError austreten."""
    temp_store._path.write_text("[]", encoding="utf-8")

    with pytest.raises(RuntimeError, match="JSON-Root"):
        temp_store.list_entries()
