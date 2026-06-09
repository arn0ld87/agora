import os
from unittest.mock import MagicMock, patch
import app.extensions as _ext
from app.extensions import register_fork_handlers


def test_register_fork_handlers(monkeypatch):
    if not hasattr(os, "register_at_fork"):
        return

    mock_neo4j = MagicMock()

    # Reset module-level globals so this test is isolated regardless of
    # import order or previous calls from other test modules.
    # monkeypatch.setattr auto-restores original values after the test,
    # preventing order-dependency leaks into subsequent tests.
    monkeypatch.setattr(_ext, "_FORK_HANDLER_REGISTERED", False)
    monkeypatch.setattr(_ext, "_REGISTERED_NEO4J_STORAGES", [])
    monkeypatch.setattr(_ext, "_REGISTERED_EVENT_BUSES", [])

    with patch("os.register_at_fork") as mock_reg:
        register_fork_handlers(neo4j_storage=mock_neo4j)

        # Since #551 (gunicorn post_fork refactor) register_fork_handlers
        # registers a single combined handler (reset_pools_after_fork) instead
        # of separate handlers per pool type.
        assert mock_reg.call_count == 1

        # Retrieve the combined handler
        _args, kwargs = mock_reg.call_args_list[0]
        after_in_child = kwargs.get("after_in_child")
        assert after_in_child is not None

        # Invoke the handler and verify it resets the Neo4j driver
        after_in_child()
        mock_neo4j._reset_driver_after_fork.assert_called_once()
