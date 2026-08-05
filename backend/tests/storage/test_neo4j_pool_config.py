"""Tests für explizite Pool-Kwargs beim GraphDatabase.driver()-Aufruf.

RED-Phase: schlägt fehl, weil Neo4jStorage.__init__ und _get_session noch
keine Pool-Kwargs übergeben (Fix 1 noch nicht implementiert).
"""
import importlib
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def restore_reloaded_modules():
    """Stellt nach Reload-Tests die ursprünglichen Modul-Namespaces wieder her.

    ``importlib.reload`` führt den Modul-Code im SELBEN Modul-Dict erneut aus
    und erzeugt dabei NEUE Klassenobjekte (``Config``, ``Neo4jStorage``).
    Andere Module und Test-Dateien halten aber weiterhin die ALTEN Objekte:
    ``patch.object(Config, ...)`` / ``monkeypatch.setattr(Config, ...)`` auf
    der alten Klasse wirkt dann nicht mehr auf Code, der über das Modul-Dict
    die neue Klasse sieht — ordnungsabhängige Failures in der Gesamt-Suite
    (z.B. test_vector_index_dim_drift, test_simulation_api_routes).

    Der Snapshot der Modul-Dicts VOR dem Reload und das Zurückschreiben
    DANACH stellt die ursprünglichen Objekt-Identitäten wieder her.
    """
    import app.config as config_module
    from app.storage import neo4j_storage as storage_module

    saved = [
        (config_module, dict(config_module.__dict__)),
        (storage_module, dict(storage_module.__dict__)),
    ]
    yield
    for module, snapshot in saved:
        module.__dict__.clear()
        module.__dict__.update(snapshot)


# Die Env-Variablen, aus denen Config die Pool-Kwargs liest (app/config.py).
_POOL_ENV_VARS = (
    'NEO4J_MAX_POOL_SIZE',
    'NEO4J_ACQ_TIMEOUT',
    'NEO4J_CONN_TIMEOUT',
    'NEO4J_MAX_LIFETIME',
    'NEO4J_LIVENESS_TIMEOUT',
)


@pytest.fixture
def pool_defaults_from_code(monkeypatch, restore_reloaded_modules):
    """Laedt ``Config`` ohne Pool-Env neu, damit die Code-Defaults gelten (#1074).

    ``Config`` liest die Pool-Kwargs beim Klassen-Import einmalig aus
    ``os.environ`` und friert sie ein. Auf Maschinen mit einer ``.env``, die
    z.B. ``NEO4J_MAX_POOL_SIZE=80`` setzt, pruefen die Durchreichungs-Tests
    daher die lokale Betriebskonfiguration statt die Defaults — und
    ``monkeypatch.delenv`` allein kommt zu spaet, weil der Wert bereits im
    Klassenattribut steht. In CI ohne ``.env`` bleibt der Defekt unsichtbar.

    Bewusst NICHT die Config-Attribute auf die erwarteten Werte setzen: dann
    pruefte der Test seine eigene Fixture statt der Defaults aus
    ``app/config.py``, und eine versehentliche Aenderung eines
    Produktions-Defaults bliebe unentdeckt (Codex-Review zu PR #1076). Env
    entfernen und neu laden laesst die Assertions scharf.

    Liefert das neu geladene ``neo4j_storage``-Modul: nach ``importlib.reload``
    sind ``Neo4jStorage`` und ``GraphDatabase`` neue Objekte, ein vorher
    importierter Name zeigt auf die alte Klasse.
    """
    for name in _POOL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    # ``config.py`` ruft beim Import ``load_dotenv(override=False)`` auf und
    # schreibt die Werte aus der ``.env`` zurueck nach ``os.environ`` — genau
    # die, die gerade entfernt wurden. Ohne diesen Patch macht der Reload das
    # ``delenv`` wieder rueckgaengig. ``from dotenv import load_dotenv`` in
    # ``config.py`` wird beim Reload neu ausgefuehrt und holt sich dabei die
    # gepatchte Funktion aus dem ``dotenv``-Modul.
    import dotenv
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *args, **kwargs: False)

    import app.config as config_module
    importlib.reload(config_module)

    from app.storage import neo4j_storage as storage_module
    importlib.reload(storage_module)
    return storage_module


def _make_storage(monkeypatch=None, *, extra_patches=None):
    """Erzeugt eine Neo4jStorage-Instanz mit allen externen Deps gemockt.

    GraphDatabase.driver, NERExtractor, EmbeddingService, _verify_connectivity
    und _ensure_schema werden gepatcht, damit __init__ ohne echte DB durchläuft.
    Gibt (storage, mock_driver_factory) zurück, wobei mock_driver_factory das
    gepatchte ``GraphDatabase.driver``-Callable ist.
    """
    mock_driver = MagicMock()
    mock_driver.session.return_value = MagicMock()

    patches = [
        patch("app.storage.neo4j_storage.GraphDatabase.driver", return_value=mock_driver),
        patch("app.storage.neo4j_storage.Neo4jStorage._verify_connectivity"),
        patch("app.storage.neo4j_storage.Neo4jStorage._ensure_schema"),
        patch("app.storage.neo4j_storage.NERExtractor", return_value=MagicMock()),
        patch("app.storage.neo4j_storage.EmbeddingService", return_value=MagicMock()),
    ]
    if extra_patches:
        patches.extend(extra_patches)

    return patches, mock_driver


# ---------------------------------------------------------------------------
# Test 1: __init__ übergibt Pool-Kwargs
# ---------------------------------------------------------------------------


def test_init_passes_pool_kwargs(pool_defaults_from_code):
    """Neo4jStorage.__init__ muss GraphDatabase.driver mit allen Pool-Kwargs aufrufen."""
    storage_module = pool_defaults_from_code

    mock_driver = MagicMock()

    with (
        patch.object(storage_module, "GraphDatabase") as mock_gdb,
        patch.object(storage_module.Neo4jStorage, "_verify_connectivity"),
        patch.object(storage_module.Neo4jStorage, "_ensure_schema"),
        patch.object(storage_module, "NERExtractor", return_value=MagicMock()),
        patch.object(storage_module, "EmbeddingService", return_value=MagicMock()),
    ):
        mock_gdb.driver.return_value = mock_driver
        storage_module.Neo4jStorage(uri="bolt://localhost:7687", user="neo4j", password="secret")

    mock_factory = mock_gdb.driver
    mock_factory.assert_called_once()
    _, kwargs = mock_factory.call_args
    assert kwargs["auth"] == ("neo4j", "secret")
    assert kwargs["max_connection_pool_size"] == 50
    assert kwargs["connection_acquisition_timeout"] == 60.0
    assert kwargs["connection_timeout"] == 15.0
    assert kwargs["max_connection_lifetime"] == 3600
    assert kwargs["liveness_check_timeout"] == 30.0
    assert kwargs["keep_alive"] is True


# ---------------------------------------------------------------------------
# Test 2: Lazy-Reconnect nach Fork übergibt dieselben Pool-Kwargs
# ---------------------------------------------------------------------------


def test_lazy_reconnect_passes_pool_kwargs(pool_defaults_from_code):
    """Nach _reset_driver_after_fork ruft _get_session() driver erneut mit Pool-Kwargs auf."""
    storage_module = pool_defaults_from_code

    mock_driver = MagicMock()
    mock_driver.session.return_value = MagicMock()

    with (
        patch.object(storage_module, "GraphDatabase") as mock_gdb,
        patch.object(storage_module.Neo4jStorage, "_verify_connectivity"),
        patch.object(storage_module.Neo4jStorage, "_ensure_schema"),
        patch.object(storage_module, "NERExtractor", return_value=MagicMock()),
        patch.object(storage_module, "EmbeddingService", return_value=MagicMock()),
    ):
        mock_gdb.driver.return_value = mock_driver
        mock_factory = mock_gdb.driver
        storage = storage_module.Neo4jStorage(uri="bolt://localhost:7687", user="neo4j", password="secret")
        # Simuliert den Fork-Reset (Fix 4)
        storage._driver = None
        storage._get_session()

    # Erster Call: __init__; zweiter Call: lazy reconnect
    assert mock_factory.call_count == 2
    _, kwargs = mock_factory.call_args  # letzter Call
    # Alle fuenf Pool-Werte, nicht nur drei: ein Fehler beim Durchreichen von
    # connection_acquisition_timeout, connection_timeout oder
    # max_connection_lifetime im Reconnect-Pfad blieb sonst unentdeckt
    # (CodeRabbit-Review zu PR #1076).
    assert kwargs["max_connection_pool_size"] == 50
    assert kwargs["connection_acquisition_timeout"] == 60.0
    assert kwargs["connection_timeout"] == 15.0
    assert kwargs["max_connection_lifetime"] == 3600
    assert kwargs["liveness_check_timeout"] == 30.0
    assert kwargs["keep_alive"] is True


# ---------------------------------------------------------------------------
# Test 3: NEO4J_LIVENESS_TIMEOUT überschreibt liveness_check_timeout
# ---------------------------------------------------------------------------


def test_env_overrides_liveness(monkeypatch, restore_reloaded_modules):
    """NEO4J_LIVENESS_TIMEOUT=5.5 muss als liveness_check_timeout=5.5 ankommen."""
    monkeypatch.setenv("NEO4J_LIVENESS_TIMEOUT", "5.5")

    # Config wird zur Import-Zeit ausgewertet — Modul neu laden damit der Wert greift.
    import app.config as config_module
    importlib.reload(config_module)

    from app.storage import neo4j_storage as storage_module
    importlib.reload(storage_module)

    mock_driver = MagicMock()
    mock_driver.session.return_value = MagicMock()

    with (
        patch.object(storage_module, "GraphDatabase") as mock_gdb,
        patch.object(storage_module.Neo4jStorage, "_verify_connectivity"),
        patch.object(storage_module.Neo4jStorage, "_ensure_schema"),
        patch.object(storage_module, "NERExtractor", return_value=MagicMock()),
        patch.object(storage_module, "EmbeddingService", return_value=MagicMock()),
    ):
        mock_gdb.driver.return_value = mock_driver
        storage_module.Neo4jStorage(uri="bolt://localhost:7687", user="neo4j", password="pw")

    _, kwargs = mock_gdb.driver.call_args
    assert kwargs["liveness_check_timeout"] == 5.5


# ---------------------------------------------------------------------------
# Test 4: NEO4J_MAX_POOL_SIZE überschreibt max_connection_pool_size
# ---------------------------------------------------------------------------


def test_env_overrides_pool_size(monkeypatch, restore_reloaded_modules):
    """NEO4J_MAX_POOL_SIZE=120 muss als max_connection_pool_size=120 ankommen."""
    monkeypatch.setenv("NEO4J_MAX_POOL_SIZE", "120")

    import app.config as config_module
    importlib.reload(config_module)

    from app.storage import neo4j_storage as storage_module
    importlib.reload(storage_module)

    mock_driver = MagicMock()
    mock_driver.session.return_value = MagicMock()

    with (
        patch.object(storage_module, "GraphDatabase") as mock_gdb,
        patch.object(storage_module.Neo4jStorage, "_verify_connectivity"),
        patch.object(storage_module.Neo4jStorage, "_ensure_schema"),
        patch.object(storage_module, "NERExtractor", return_value=MagicMock()),
        patch.object(storage_module, "EmbeddingService", return_value=MagicMock()),
    ):
        mock_gdb.driver.return_value = mock_driver
        storage_module.Neo4jStorage(uri="bolt://localhost:7687", user="neo4j", password="pw")

    _, kwargs = mock_gdb.driver.call_args
    assert kwargs["max_connection_pool_size"] == 120
