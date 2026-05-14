from unittest.mock import MagicMock, patch
from app.storage.neo4j_storage import Neo4jStorage

def test_neo4j_storage_reconnect_after_fork():
    # Mock Neo4j driver and session
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch("app.storage.neo4j_storage.GraphDatabase.driver", return_value=mock_driver):
        with patch("app.storage.neo4j_storage.Neo4jStorage._verify_connectivity"):
            with patch("app.storage.neo4j_storage.Neo4jStorage._ensure_schema"):
                storage = Neo4jStorage(uri="bolt://localhost:7687", user="neo4j", password="password")

                # Initially driver should be set
                assert storage._driver is not None

                # Simulate fork reset
                storage._reset_driver_after_fork()
                assert storage._driver is None

                # Accessing a session should re-initialize driver
                session = storage._get_session()
                assert storage._driver is not None
                assert session == mock_session
                mock_driver.session.assert_called_once()
