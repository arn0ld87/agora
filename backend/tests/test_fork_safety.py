"""Tests für Fork-safe pool management.

History:
- MAI-12 (2026-05-14) führte ``register_fork_handlers`` mit
  ``os.register_at_fork`` ein.
- 2026-05-18 (dieser Fix): Unter ``gunicorn -k gevent --preload`` greift
  ``os.register_at_fork`` nicht zuverlässig — gevent monkey-patcht
  ``os.fork``. Der kanonische Pfad ist jetzt ``reset_pools_after_fork``,
  aufgerufen aus dem ``post_fork``-Hook in ``backend/gunicorn.conf.py``.
  ``os.register_at_fork`` bleibt als Defence-in-Depth-Fallback.
"""
import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_registered_storages():
    """Module-level Storage-Liste zwischen Tests isolieren."""
    from app import extensions

    extensions._REGISTERED_NEO4J_STORAGES.clear()
    yield
    extensions._REGISTERED_NEO4J_STORAGES.clear()


def test_reset_driver_after_fork_closes_and_nones_driver():
    """_reset_driver_after_fork() setzt _driver auf None."""
    from app.storage.neo4j_storage import Neo4jStorage

    storage = Neo4jStorage.__new__(Neo4jStorage)
    mock_driver = MagicMock()
    storage._driver = mock_driver
    storage._is_connected = True

    storage._reset_driver_after_fork()

    mock_driver.close.assert_called_once()
    assert storage._driver is None
    assert storage._is_connected is False


def test_reset_driver_after_fork_handles_close_error():
    """_reset_driver_after_fork() fängt Fehler beim close() ab."""
    from app.storage.neo4j_storage import Neo4jStorage

    storage = Neo4jStorage.__new__(Neo4jStorage)
    mock_driver = MagicMock()
    mock_driver.close.side_effect = RuntimeError("connection lost")
    storage._driver = mock_driver
    storage._is_connected = True

    storage._reset_driver_after_fork()

    assert storage._driver is None


def test_reset_driver_after_fork_handles_none_driver():
    """_reset_driver_after_fork() ist safe bei bereits None-Driver."""
    from app.storage.neo4j_storage import Neo4jStorage

    storage = Neo4jStorage.__new__(Neo4jStorage)
    storage._driver = None
    storage._is_connected = False

    storage._reset_driver_after_fork()

    assert storage._driver is None


def test_register_fork_handlers_no_neo4j():
    """register_fork_handlers() ohne neo4j_storage läuft durch."""
    from app.extensions import register_fork_handlers, _REGISTERED_NEO4J_STORAGES

    register_fork_handlers(neo4j_storage=None)

    assert _REGISTERED_NEO4J_STORAGES == []


def test_register_fork_handlers_captures_storage_reference():
    """register_fork_handlers() merkt sich die Storage-Referenz für post_fork."""
    from app.extensions import register_fork_handlers, _REGISTERED_NEO4J_STORAGES

    mock_storage = MagicMock()

    with patch("os.register_at_fork"):
        register_fork_handlers(neo4j_storage=mock_storage)

    assert _REGISTERED_NEO4J_STORAGES == [mock_storage]


def test_register_fork_handlers_is_idempotent():
    """Doppel-Registrierung derselben Storage erzeugt keinen Duplikat-Reset."""
    from app.extensions import register_fork_handlers, _REGISTERED_NEO4J_STORAGES

    mock_storage = MagicMock()

    with patch("os.register_at_fork"):
        register_fork_handlers(neo4j_storage=mock_storage)
        register_fork_handlers(neo4j_storage=mock_storage)

    assert _REGISTERED_NEO4J_STORAGES == [mock_storage]


def test_register_fork_handlers_registers_atfork_fallback():
    """register_fork_handlers() verdrahtet os.register_at_fork als Fallback."""
    if not hasattr(os, "register_at_fork"):
        pytest.skip("register_at_fork nicht verfügbar")

    from app.extensions import register_fork_handlers, reset_pools_after_fork

    registered = []
    with patch("os.register_at_fork", side_effect=lambda **kw: registered.append(kw)):
        register_fork_handlers(neo4j_storage=MagicMock())

    assert len(registered) == 1
    assert registered[0]["after_in_child"] is reset_pools_after_fork


def test_reset_pools_after_fork_resets_all_registered_neo4j_storages():
    """reset_pools_after_fork() ruft _reset_driver_after_fork auf jeder Storage."""
    from app.extensions import register_fork_handlers, reset_pools_after_fork

    storage_a = MagicMock()
    storage_b = MagicMock()

    with patch("os.register_at_fork"):
        register_fork_handlers(neo4j_storage=storage_a)
        register_fork_handlers(neo4j_storage=storage_b)

    reset_pools_after_fork()

    storage_a._reset_driver_after_fork.assert_called_once()
    storage_b._reset_driver_after_fork.assert_called_once()


def test_reset_pools_after_fork_resets_signed_ticket_redis():
    """reset_pools_after_fork() ruft signed_ticket.reset_after_fork auf."""
    from app.extensions import reset_pools_after_fork

    with patch("app.utils.signed_ticket.reset_after_fork") as mock_reset:
        reset_pools_after_fork()

    mock_reset.assert_called_once()


def test_reset_pools_after_fork_isolates_failures():
    """Eine fehlschlagende Pool-Reset darf nachfolgende Resets nicht blockieren."""
    from app.extensions import register_fork_handlers, reset_pools_after_fork

    failing = MagicMock()
    failing._reset_driver_after_fork.side_effect = RuntimeError("driver borked")
    healthy = MagicMock()

    with patch("os.register_at_fork"):
        register_fork_handlers(neo4j_storage=failing)
        register_fork_handlers(neo4j_storage=healthy)

    with patch("app.utils.signed_ticket.reset_after_fork") as mock_redis:
        reset_pools_after_fork()

    failing._reset_driver_after_fork.assert_called_once()
    healthy._reset_driver_after_fork.assert_called_once()
    mock_redis.assert_called_once()


def test_gunicorn_post_fork_hook_invokes_reset_pools():
    """gunicorn.conf.py::post_fork ruft reset_pools_after_fork auf."""
    import importlib.util
    from pathlib import Path

    conf_path = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location("agora_gunicorn_conf", conf_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    fake_worker = MagicMock(pid=4242)
    fake_server = MagicMock()

    with patch("app.extensions.reset_pools_after_fork") as mock_reset:
        module.post_fork(fake_server, fake_worker)

    mock_reset.assert_called_once()


def test_gunicorn_post_fork_hook_swallows_reset_errors():
    """post_fork crasht den Worker nicht, auch wenn der Reset wirft."""
    import importlib.util
    from pathlib import Path

    conf_path = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location("agora_gunicorn_conf", conf_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    with patch("app.extensions.reset_pools_after_fork", side_effect=RuntimeError("boom")):
        module.post_fork(MagicMock(), MagicMock(pid=99))  # must not raise
