"""Tests für MAI-12: Fork-safe pool management."""
import os
from unittest.mock import MagicMock, patch


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

    # Soll nicht werfen
    storage._reset_driver_after_fork()

    assert storage._driver is None


def test_reset_driver_after_fork_handles_none_driver():
    """_reset_driver_after_fork() ist safe bei bereits None-Driver."""
    from app.storage.neo4j_storage import Neo4jStorage

    storage = Neo4jStorage.__new__(Neo4jStorage)
    storage._driver = None
    storage._is_connected = False

    storage._reset_driver_after_fork()  # darf nicht werfen

    assert storage._driver is None


def test_register_fork_handlers_no_neo4j():
    """register_fork_handlers() ohne neo4j_storage läuft durch."""
    from app.extensions import register_fork_handlers

    # Soll nicht werfen, auch ohne neo4j_storage
    register_fork_handlers(neo4j_storage=None)


def test_register_fork_handlers_with_mock_storage():
    """register_fork_handlers() registriert after_in_child Handler."""
    if not hasattr(os, "register_at_fork"):
        import pytest
        pytest.skip("register_at_fork nicht verfügbar")

    from app.extensions import register_fork_handlers

    mock_storage = MagicMock()
    registered = []

    with patch("os.register_at_fork", side_effect=lambda **kw: registered.append(kw)):
        register_fork_handlers(neo4j_storage=mock_storage)

    # Mindestens 1 Handler (Neo4j) + 1 (Redis signed_ticket)
    assert len(registered) >= 1
    # Der erste Handler sollte der Neo4j-Reset sein
    assert "after_in_child" in registered[0]
