"""Tests für den Fernet-verschlüsselten API-Keys-Persistence-Layer (PR 4 Hardening)."""
from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

from app.services.api_keys_store import ApiKeysStore


@pytest.fixture(autouse=True)
def _reset_singleton_env(monkeypatch, tmp_path):
    """Setzt den Store-Singleton und den Fernet-Cache für jeden Test zurück."""
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("AGORA_FERNET_KEY", key)
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))

    # Fernet-Modul-Cache invalidieren, damit Env-Änderungen greifen
    import app.services.api_keys_persistence as _pm
    _pm._fernet_instance = None
    _pm._fernet_key_raw = None

    from app.services import api_keys_store as _mod
    _mod._store_singleton = ApiKeysStore()
    yield
    _pm._fernet_instance = None
    _pm._fernet_key_raw = None
    _mod._store_singleton = ApiKeysStore()


def test_create_persists_to_disk(tmp_path, monkeypatch):
    """create() persistiert den Key; eine neue Store-Instanz sieht ihn."""

    store1 = ApiKeysStore()
    resp = store1.create("PersistTest", ["read"])
    key_id = resp.key.id

    # Frische Instanz liest vom Disk
    store2 = ApiKeysStore()
    found = [k for k in store2.list() if k.id == key_id]
    assert len(found) == 1
    assert found[0].label == "PersistTest"


def test_revoke_persists_to_disk(tmp_path, monkeypatch):
    """revoke() persistiert den revoked-Status; eine neue Store-Instanz sieht ihn."""
    store1 = ApiKeysStore()
    resp = store1.create("RevokeTest", ["write"])
    key_id = resp.key.id

    store1.revoke(key_id)

    store2 = ApiKeysStore()
    key = store2.get(key_id)
    assert key is not None
    assert key.status == "revoked"


def test_load_with_missing_file_returns_empty(tmp_path, monkeypatch):
    """Fehlende Datei → load() gibt leeres Dict zurück, kein Crash."""
    from app.services.api_keys_persistence import load

    data_file = tmp_path / "api_keys.json"
    assert not data_file.exists()

    result = load(data_dir=tmp_path)
    assert result == {}


def test_save_uses_chmod_0600(tmp_path, monkeypatch):
    """Gespeicherte Datei hat exakte Permissions 0o600."""
    store = ApiKeysStore()
    store.create("PermTest", ["admin"])

    data_file = tmp_path / "api_keys.json"
    assert data_file.exists()
    mode = os.stat(data_file).st_mode & 0o777
    assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


def test_save_uses_fernet_encryption(tmp_path, monkeypatch):
    """Gespeicherte Datei ist KEIN Plain-JSON — kein lesbares 'label'/'scopes' im Bytestream."""
    store = ApiKeysStore()
    store.create("SecretLabel", ["admin"])

    data_file = tmp_path / "api_keys.json"
    raw_bytes = data_file.read_bytes()

    # Weder Label noch Scope darf im Klartext stehen
    assert b"SecretLabel" not in raw_bytes
    assert b'"scopes"' not in raw_bytes
    assert b'"label"' not in raw_bytes


def test_missing_fernet_key_raises_in_non_debug(tmp_path, monkeypatch):
    """Fehlendes AGORA_FERNET_KEY ohne Debug-Modus → RuntimeError beim Speichern."""
    monkeypatch.delenv("AGORA_FERNET_KEY", raising=False)
    monkeypatch.setenv("FLASK_DEBUG", "false")

    import app.services.api_keys_persistence as _pm
    _pm._fernet_instance = None
    _pm._fernet_key_raw = None

    store = ApiKeysStore()
    with pytest.raises(RuntimeError, match="AGORA_FERNET_KEY"):
        store.create("ShouldFail", ["read"])


def test_missing_fernet_key_autogenerates_in_debug(tmp_path, monkeypatch):
    """Fehlendes AGORA_FERNET_KEY im Debug-Modus → kein Crash, Key wird angelegt."""
    monkeypatch.delenv("AGORA_FERNET_KEY", raising=False)
    monkeypatch.setenv("FLASK_DEBUG", "true")

    import app.services.api_keys_persistence as _pm
    _pm._fernet_instance = None
    _pm._fernet_key_raw = None

    store = ApiKeysStore()
    resp = store.create("DebugAutoKey", ["read"])

    assert resp.key.label == "DebugAutoKey"
    assert resp.token.startswith("ago_")


def test_validate_token_throttles_disk_flush_by_ttl(tmp_path, monkeypatch):
    """Gemini-Review #524: `validate_token` darf nicht bei jedem API-Request
    den kompletten Store auf Disk schreiben — `last_used_at` wird per TTL
    gedrosselt persistiert."""
    from datetime import datetime, timedelta, timezone

    import app.services.api_keys_store as _store_mod

    store = ApiKeysStore()
    resp = store.create("ThrottleTest", ["read"])
    token = resp.token

    flush_calls: list[int] = []
    real_save = store._save

    def _counting_save() -> None:
        flush_calls.append(1)
        real_save()

    monkeypatch.setattr(store, "_save", _counting_save)

    base = datetime(2026, 5, 17, 18, 0, tzinfo=timezone.utc)
    times = iter(
        [
            base,
            base + timedelta(seconds=5),
            base + timedelta(seconds=10),
            base + timedelta(seconds=30),
            base + timedelta(seconds=61),  # > TTL
        ]
    )
    monkeypatch.setattr(_store_mod, "_now", lambda: next(times))

    for _ in range(5):
        store.validate_token(token)

    # 5 Aufrufe, aber maximal 2 Disk-Flushes:
    # erster (previous=None → flush) + nach 61 s (TTL überschritten).
    assert len(flush_calls) == 2, (
        f"Erwartete 2 Disk-Flushes (initial + nach TTL), bekam {len(flush_calls)}"
    )
