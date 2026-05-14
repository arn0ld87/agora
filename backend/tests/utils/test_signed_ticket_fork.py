import os
from unittest.mock import MagicMock, patch
from app.extensions import register_fork_handlers

def test_register_fork_handlers():
    if not hasattr(os, "register_at_fork"):
        return

    mock_neo4j = MagicMock()

    with patch("os.register_at_fork") as mock_reg:
        register_fork_handlers(neo4j_storage=mock_neo4j)

        # Should be called twice: once for Neo4j, once for Redis
        assert mock_reg.call_count == 2

        # Check Neo4j handler
        args, kwargs = mock_reg.call_args_list[0]
        after_in_child = kwargs.get("after_in_child")
        assert after_in_child is not None

        # Execute Neo4j handler and verify it calls _reset_driver_after_fork
        after_in_child()
        mock_neo4j._reset_driver_after_fork.assert_called_once()
