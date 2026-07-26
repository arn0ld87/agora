"""Root-Conftest: Setzt globale Test-Umgebung für alle Test-Suites.

Stellt sicher dass:
1. AGORA_FERNET_KEY immer gesetzt ist (benötigt für ApiKeysStore-Persistenz).
2. AGORA_DATA_DIR auf tmp_path zeigt (verhindert Disk-Verschmutzung).
3. Fernet-Cache zwischen Tests invalidiert wird.
4. ApiKeysStore-Singleton für jeden Test zurückgesetzt wird.
5. AGORA_AUTH_TOKEN nicht aus der lokalen .env in die Suite leakt.
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
def _clean_auth_token_env(monkeypatch):
    """Hermetik: ``AGORA_AUTH_TOKEN`` darf nicht aus der lokalen ``.env`` kommen.

    ``app/config.py`` ruft beim Import ``load_dotenv()`` auf und zieht damit den
    echten ``AGORA_AUTH_TOKEN`` aus ``.env`` bzw. ``backend/.env`` prozessweit in
    ``os.environ``. Der Wert ist danach in *jedem* Test gesetzt.

    Für sich genommen wäre das harmlos — kritisch wird es zusammen mit den
    Blueprint-Singletons: ``install_blueprint_guard`` hängt seinen
    ``before_request``-Hook an das Blueprint-*Objekt* und markiert es dauerhaft
    über ``_agora_guard_installed``. Ruft irgendein Test ``create_app()``
    (``tests/api/test_cors.py``, ``tests/test_fork_safety.py``,
    ``tests/observability/test_logging_wiring.py``), ist der Guard danach
    permanent auf ``simulation_bp``, ``graph_bp``, ``report_bp`` & Co. installiert
    — auch für jede spätere nackte ``Flask()``-App, die dasselbe Blueprint
    registriert. Mit gesetztem Token ist der Guard scharf und antwortet
    ``401 auth_required``.

    Ergebnis war eine Reihenfolgen-Abhängigkeit: Suiten liefen isoliert grün und
    im Gesamtlauf rot, je nachdem ob vorher ein ``create_app()``-Test lief. In CI
    fiel das nie auf, weil dort keine ``.env`` existiert — es traf nur lokale
    Läufe.

    Tests für den Auth-Layer selbst setzen den Token weiterhin explizit per
    ``monkeypatch.setenv`` (``tests/test_auth.py``, ``tests/test_auth_ticket.py``);
    dieses autouse-Fixture läuft davor und steht ihnen nicht im Weg.

    **Leerer String statt ``delenv``** — das ist der entscheidende Teil. Wird der
    Key *entfernt*, setzt ihn der nächste ``load_dotenv(override=False)`` sofort
    wieder: ``override=False`` überspringt nur Keys, die bereits in ``os.environ``
    stehen. Genau das passiert in Suiten, die ``app.config`` erst *während* eines
    Tests importieren (z. B. über ``_global_fernet_env`` → ``api_keys_store`` →
    ``app.config``) — dort war der Token nach dem ``delenv`` prompt wieder da.
    Ein leerer Wert belegt den Key, ohne den Guard scharf zu machen:
    ``_expected_token()`` und der Open-Mode-Check in ``scopes.require_scope``
    prüfen beide auf Truthiness.
    """
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "")


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
