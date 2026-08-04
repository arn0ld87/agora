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


# Die im Code hinterlegten Pool-Defaults (app/config.py). Bewusst als
# Literale gespiegelt statt aus Config gelesen: eine Assertion gegen
# ``Config.NEO4J_MAX_POOL_SIZE`` waere tautologisch und wuerde eine
# Aenderung des Defaults nicht mehr anzeigen.
_POOL_DEFAULTS = {
    'NEO4J_MAX_POOL_SIZE': 50,
    'NEO4J_ACQ_TIMEOUT': 60.0,
    'NEO4J_CONN_TIMEOUT': 15.0,
    'NEO4J_MAX_LIFETIME': 3600,
    'NEO4J_LIVENESS_TIMEOUT': 30.0,
}


@pytest.fixture
def pinned_pool_defaults(monkeypatch):
    """Pinnt die Pool-Werte auf die Code-Defaults (Issue #1074).

    ``Config`` liest die Pool-Kwargs beim Klassen-Import einmalig aus
    ``os.environ`` und friert sie ein. Auf Maschinen mit einer ``.env``, die
    z.B. ``NEO4J_MAX_POOL_SIZE=80`` setzt, pruefen die Durchreichungs-Tests
    daher die lokale Betriebskonfiguration statt die Defaults — und
    ``monkeypatch.delenv`` kommt zu spaet, weil der Wert bereits im
    Klassenattribut steht. In CI ohne ``.env`` bleibt der Defekt unsichtbar.

    Die Assertions in den Tests bleiben harte Literale; diese Fixture stellt
    nur sicher, dass sie gegen den Default und nicht gegen den Betriebswert
    laufen. Die Env-Override-Pfade deckt ``test_env_overrides_*`` ab.
    """
    from app.config import Config

    for name, value in _POOL_DEFAULTS.items():
        monkeypatch.setattr(Config, name, value)


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


def test_init_passes_pool_kwargs(pinned_pool_defaults):
    """Neo4jStorage.__init__ muss GraphDatabase.driver mit allen Pool-Kwargs aufrufen."""
    from app.storage.neo4j_storage import Neo4jStorage

    mock_driver = MagicMock()

    with (
        patch("app.storage.neo4j_storage.GraphDatabase.driver", return_value=mock_driver) as mock_factory,
        patch("app.storage.neo4j_storage.Neo4jStorage._verify_connectivity"),
        patch("app.storage.neo4j_storage.Neo4jStorage._ensure_schema"),
        patch("app.storage.neo4j_storage.NERExtractor", return_value=MagicMock()),
        patch("app.storage.neo4j_storage.EmbeddingService", return_value=MagicMock()),
    ):
        Neo4jStorage(uri="bolt://localhost:7687", user="neo4j", password="secret")

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


def test_lazy_reconnect_passes_pool_kwargs(pinned_pool_defaults):
    """Nach _reset_driver_after_fork ruft _get_session() driver erneut mit Pool-Kwargs auf."""
    from app.storage.neo4j_storage import Neo4jStorage

    mock_driver = MagicMock()
    mock_driver.session.return_value = MagicMock()

    with (
        patch("app.storage.neo4j_storage.GraphDatabase.driver", return_value=mock_driver) as mock_factory,
        patch("app.storage.neo4j_storage.Neo4jStorage._verify_connectivity"),
        patch("app.storage.neo4j_storage.Neo4jStorage._ensure_schema"),
        patch("app.storage.neo4j_storage.NERExtractor", return_value=MagicMock()),
        patch("app.storage.neo4j_storage.EmbeddingService", return_value=MagicMock()),
    ):
        storage = Neo4jStorage(uri="bolt://localhost:7687", user="neo4j", password="secret")
        # Simuliert den Fork-Reset (Fix 4)
        storage._driver = None
        storage._get_session()

    # Erster Call: __init__; zweiter Call: lazy reconnect
    assert mock_factory.call_count == 2
    _, kwargs = mock_factory.call_args  # letzter Call
    assert kwargs["max_connection_pool_size"] == 50
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
