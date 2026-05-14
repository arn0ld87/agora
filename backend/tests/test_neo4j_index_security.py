
import pytest
from unittest.mock import MagicMock, patch
from app.storage.neo4j_storage import Neo4jStorage

def test_ensure_vector_index_dim_sanitization():
    # Mocking dependencies for Neo4jStorage init
    mock_embedding = MagicMock()
    mock_ner = MagicMock()

    # We use patch to avoid real connection attempts during init
    with patch.object(Neo4jStorage, '_verify_connectivity', return_value=None):
        # Initialize storage with mocks
        storage = Neo4jStorage(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password",
            embedding_service=mock_embedding,
            ner_extractor=mock_ner
        )
        storage._driver = MagicMock()

    mock_session = MagicMock()

    # Case 1: Valid index name should pass
    # Mock session.run to return a row with different dimension
    mock_result = MagicMock()
    mock_result.single.return_value = {"dim": 128}
    mock_session.run.return_value = mock_result

    storage._ensure_vector_index_dim(mock_session, "valid_index", 256)

    # Verify DROP INDEX was called with valid name
    mock_session.run.assert_any_call("DROP INDEX valid_index")

    # Case 2: Invalid index name (Cypher injection attempt) should raise ValueError
    hostile_name = "idx`; DROP DATABASE neo4j; //"
    with pytest.raises(ValueError, match="Invalid index name for DROP INDEX"):
        storage._ensure_vector_index_dim(mock_session, hostile_name, 256)

    # Case 3: Another invalid name
    with pytest.raises(ValueError, match="Invalid index name for DROP INDEX"):
        storage._ensure_vector_index_dim(mock_session, "invalid-name-with-dashes", 256)
