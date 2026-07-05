"""Root-Conftest: Setzt globale Test-Umgebung für alle Test-Suites.

Stellt sicher dass:
1. AGORA_FERNET_KEY immer gesetzt ist (benötigt für ApiKeysStore-Persistenz).
2. AGORA_DATA_DIR auf tmp_path zeigt (verhindert Disk-Verschmutzung).
3. Fernet-Cache zwischen Tests invalidiert wird.
4. ApiKeysStore-Singleton für jeden Test zurückgesetzt wird.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _clean_llm_json_mode_env(monkeypatch):
    """Hermetik: Verhindert Env-Leaks aus der Shell (z.B. LLM_DISABLE_JSON_MODE=true).

    Tests, die die Flags explizit brauchen, setzen sie selbst via monkeypatch
    (siehe tests/utils/test_llm_client_json_mode_env.py, Issue #593).
    """
    monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
    monkeypatch.delenv("LLM_DISABLE_JSON_OBJECT_MODE", raising=False)


@pytest.fixture(autouse=True)
def _global_fernet_env(monkeypatch, tmp_path):
    """Setzt AGORA_FERNET_KEY + AGORA_DATA_DIR für jeden Test und räumt auf."""
    fernet_key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("AGORA_FERNET_KEY", fernet_key)
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))

    # Fernet-Cache im Persistence-Modul invalidieren
    try:
        import app.services.api_keys_persistence as _pm
        _pm._fernet_instance = None
        _pm._fernet_key_raw = None
    except ImportError:
        pass

    # Store-Singleton neu initialisieren
    try:
        from app.services.api_keys_store import ApiKeysStore
        import app.services.api_keys_store as _sm
        _sm._store_singleton = ApiKeysStore()
    except ImportError:
        pass

    yield

    # Cleanup: Cache nach Test invalidieren
    try:
        import app.services.api_keys_persistence as _pm
        _pm._fernet_instance = None
        _pm._fernet_key_raw = None
    except ImportError:
        pass
