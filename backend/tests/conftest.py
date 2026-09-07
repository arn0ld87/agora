"""Root-Conftest: Setzt globale Test-Umgebung für alle Test-Suites.

Stellt sicher dass:
1. AGORA_FERNET_KEY immer gesetzt ist (benötigt für ApiKeysStore-Persistenz).
2. AGORA_DATA_DIR auf tmp_path zeigt (verhindert Disk-Verschmutzung).
3. Fernet-Cache zwischen Tests invalidiert wird.
4. ApiKeysStore-Singleton für jeden Test zurückgesetzt wird.
5. AGORA_AUTH_TOKEN nicht aus der lokalen .env in die Suite leakt.
6. ``torch`` vorab geladen ist (verhindert einen Interpreter-Segfault, s.u.).
"""
from __future__ import annotations

import os

# ``nltk`` >= 3.10 installiert beim Import einen Meta-Path-Finder
# (``nltk/inisec.py``), der jeden von nltk ausgelösten Import blockiert, dessen
# Modul unterhalb des aktuellen Arbeitsverzeichnisses liegt. Läuft pytest aus
# ``backend/`` heraus, liegt ``backend/.venv`` unter dem CWD — damit gilt *jedes*
# venv-Paket als "aus dem CWD" und ``regex``/``defusedxml`` fliegen mit einem
# ``ImportError`` raus, sobald ``unstructured`` beim Parsen nltk lädt.
# Das Setzen MUSS vor dem ersten nltk-Import passieren; der Hook wird auf
# Modulebene installiert. Dasselbe setzt das Dockerfile für den Container und
# ``app/__init__.py`` für jeden Einstieg, der ``app`` importiert.
#
# Hier bewusst eine unbedingte Zuweisung statt ``setdefault``: nltk deaktiviert
# den Hook nur beim exakten Wert ``"1"``. Ein aus der Shell geerbtes
# ``NLTK_DISABLE_IMPORT_SECURITY=0`` ließe ``setdefault`` unverändert und die
# Suite liefe in genau den ImportError, den sie verhindern soll — dieselbe
# Hermetik-Erwägung wie bei ``_clean_llm_json_mode_env`` und
# ``_clean_auth_token_env`` weiter unten. In ``app/__init__.py`` bleibt es
# dagegen ``setdefault``, damit der Betreiber die Entscheidung überschreiben kann.
os.environ["NLTK_DISABLE_IMPORT_SECURITY"] = "1"

# Hermetik: ``LLM_API_KEY`` darf nicht aus der lokalen ``.env`` kommen.
#
# ``Config.validate()`` erzwingt einen nicht-leeren Wert, und ``create_app()``
# ruft sie auf. Ohne Vorgabe scheitern deshalb alle Tests, die eine App bauen
# (``tests/test_embedding_service.py``, ``tests/services/
# test_initial_post_agent_assignment.py``) mit ``Critical configuration
# missing`` — und zwar nur dort, wo keine ``.env`` liegt. Lokal lief die Suite
# gruen, weil ``app/config.py`` beim Import ``load_dotenv()`` aufruft und den
# echten Key prozessweit in ``os.environ`` zieht; in CI lief sie gruen, weil
# ``ci.yml`` ``LLM_API_KEY: dummy-ci-key`` als Job-Env setzt. Ein frischer
# Checkout ohne beides — etwa ein neuer Worktree — war rot. Der schlimmere
# Fall ist der stille: ``test_create_app_still_fails_on_embedding_
# misconfiguration`` erwartet ``Embedding configuration invalid``, bekam aber
# den LLM-Key-Fehler und haette damit auch gegen eine reparierte
# Embedding-Pruefung nichts mehr ausgesagt.
#
# ``setdefault`` statt unbedingter Zuweisung, anders als beim nltk-Hook
# darueber: ein aus der Shell exportierter Key soll weiterhin gewinnen, damit
# Laeufe gegen ein echtes Provider-Backend (Marker ``llm``) moeglich bleiben.
# Vorweggenommen wird nur der ``.env``-Pfad, denn ``load_dotenv(override=
# False)`` ueberspringt Keys, die bereits in ``os.environ`` stehen.
os.environ.setdefault("LLM_API_KEY", "test-dummy-key")

# ``torch`` MUSS vor der ersten ``mock.patch.dict(sys.modules, ...)`` geladen
# sein — sonst stirbt der Interpreter mit SIGSEGV.
#
# ``patch.dict`` nimmt beim Betreten einen Snapshot von ``sys.modules`` und
# stellt ihn beim Verlassen über ``clear()`` + ``update(snapshot)`` wieder her.
# War ``torch`` zum Snapshot-Zeitpunkt noch nicht importiert, wird es *innerhalb*
# des Blocks aber geladen (``oasis.social_platform.recsys`` zieht es), dann ist
# der komplette ``torch``-Namensraum danach aus ``sys.modules`` verschwunden —
# im CPython-Extension-Cache jedoch weiterhin registriert.
#
# Der nächste ``import torch`` führt ``torch/__init__.py`` erneut aus und trifft
# bei ``from torch._C import *`` auf ``reload_singlephase_extension``: CPython
# ruft ``initModule()`` der single-phase-init-Extension ein zweites Mal auf,
# torch registriert seine Methodentabelle auf ein Modulobjekt in inkonsistentem
# Zustand -> ``PyObject_SetAttrString`` auf ungültigem Pointer -> SIGSEGV.
#
# Rein reihenfolgeabhängig: ``tests/scripts/test_bert_memory_profile.py`` läuft
# isoliert sauber durch, im Verbund crasht ``pytest tests/scripts/``.
# Der Vorab-Import setzt ``torch`` in jeden Snapshot und macht das ``clear()``
# damit unschädlich.
try:
    import torch  # noqa: F401
except ImportError:  # torch ist optional — Suiten ohne Recsys laufen ohne
    pass

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


@pytest.fixture
def hermetic_settings(monkeypatch, tmp_path):
    """Schneidet den persistierten Settings-Layer ab (Issue #1074).

    ``app.services.oasis_profile_generator`` liest Settings ueber
    ``settings_layer.get_default_service()``, dessen File-Layer
    (``backend/instance/settings.json``) Vorrang vor ``os.environ`` hat.
    Auf Entwicklermaschinen sind dort Betriebswerte hinterlegt — Tests
    pruefen dann die lokale Konfiguration statt das Resolutionsverhalten,
    und zwar auch dort, wo sie die Variable per ``setenv`` explizit setzen.
    In CI existiert die Datei nicht, weshalb solche Defekte dort unsichtbar
    bleiben und nur das lokale Gate blockieren.

    ``SettingsService`` nimmt genau dafuer einen ``instance_path`` entgegen
    (siehe dessen Docstring); hier zeigt er auf ein leeres tmp-Verzeichnis.

    Gibt das Generator-Modul zurueck, damit Tests die zu pruefende Funktion
    ueber denselben Namespace aufrufen koennen, in dem gepatcht wurde.
    """
    from app.services import oasis_profile_generator
    from app.services.settings_layer import SettingsService

    # Eine Instanz, nicht eine pro Aufruf: der produktive
    # ``get_default_service()`` haelt ein Modul-Singleton, dessen in-memory
    # ``_override`` ueber mehrere Zugriffe hinweg lebt. Eine Fabrik wuerde das
    # Override bei jedem ``_get_settings()`` verlieren und damit ein anderes
    # Verhalten pruefen als die Anwendung zeigt.
    service = SettingsService(instance_path=tmp_path / 'settings.json')
    monkeypatch.setattr(oasis_profile_generator, '_get_settings', lambda: service)
    return oasis_profile_generator
