"""
Tests for the unified /api/status endpoint.
Simpler approach: test the functions directly rather than via Flask test client.
"""

from unittest.mock import Mock, patch

from app import __version__
from app.config import Config
from app.api.status import (
    _get_backend_status,
    _get_neo4j_status,
    _get_ollama_status,
    _get_disk_status,
)


class TestStatusFunctions:
    """Test suite for status helper functions"""

    def test_get_backend_status(self):
        """Test backend status returns correct version and ok=true."""
        result = _get_backend_status()
        assert result['ok'] is True
        assert result['version'] == __version__

    def test_get_disk_status(self):
        """Test disk status returns expected fields."""
        result = _get_disk_status()
        assert 'uploads' in result
        assert 'path' in result['uploads']
        assert 'total_bytes' in result['uploads']
        assert 'free_bytes' in result['uploads']
        assert 'used_pct' in result['uploads']

    def test_get_ollama_status_reachable(self):
        """Test Ollama status when service is reachable."""
        with patch('app.api.status.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                'models': [
                    {'name': 'qwen2.5:32b'},
                    {'name': 'nomic-embed-text'},
                ]
            }
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            result = _get_ollama_status()

            assert result['reachable'] is True
            assert result['error'] is None
            assert len(result['models_available']) == 2
            assert 'qwen2.5:32b' in result['models_available']
            assert result['default_model'] == Config.LLM_MODEL_NAME
            assert result['base_url'] is not None

    def test_get_ollama_status_unreachable(self):
        """Test Ollama status when service is unreachable."""
        with patch('app.api.status.requests.get') as mock_get:
            mock_get.side_effect = Exception("Connection refused")

            result = _get_ollama_status()

            assert result['reachable'] is False
            assert result['error'] is not None
            assert result['models_available'] == []
            assert result['default_model'] == Config.LLM_MODEL_NAME

    def test_get_neo4j_status_no_storage(self):
        """Test Neo4j status when storage is not initialized."""
        from flask import Flask
        app = Flask(__name__)

        with app.app_context():
            # No storage initialized
            app.extensions = {}

            result = _get_neo4j_status()

            assert result['reachable'] is False
            assert result['error'] is not None
            assert 'uri' in result

    def test_get_neo4j_status_uses_startup_error_when_available(self):
        """Surface the original startup error instead of a generic placeholder."""
        from flask import Flask
        app = Flask(__name__)

        with app.app_context():
            app.extensions = {
                'neo4j_storage_error': 'AuthError: unauthorized',
            }

            result = _get_neo4j_status()

            assert result['reachable'] is False
            assert result['error'] == 'AuthError: unauthorized'

    def test_get_neo4j_status_reachable(self):
        """Test Neo4j status when service is reachable."""
        from flask import Flask
        app = Flask(__name__)
        app.extensions = {}

        # Mock a storage object with a working driver
        mock_storage = Mock()
        mock_driver = Mock()
        mock_driver.verify_connectivity = Mock()
        mock_storage._driver = mock_driver
        app.extensions['neo4j_storage'] = mock_storage

        with app.app_context():
            result = _get_neo4j_status()

            assert result['reachable'] is True
            assert result['error'] is None
            assert 'uri' in result

    def test_get_neo4j_status_unreachable(self):
        """Test Neo4j status when service is unreachable."""
        from flask import Flask
        app = Flask(__name__)
        app.extensions = {}

        # Mock a storage object with a failing driver
        mock_storage = Mock()
        mock_driver = Mock()
        mock_driver.verify_connectivity = Mock(
            side_effect=Exception("Connection refused")
        )
        mock_storage._driver = mock_driver
        mock_storage.verify_connectivity = Mock(
            side_effect=Exception("Connection refused")
        )
        app.extensions['neo4j_storage'] = mock_storage

        with app.app_context():
            result = _get_neo4j_status()

            assert result['reachable'] is False
            assert result['error'] is not None
            assert 'uri' in result

    def test_get_neo4j_status_after_fork_reset_driver_is_none(self):
        """Regression: nach gunicorn-Fork-Reset ist storage._driver=None.

        Direkter Zugriff auf ``storage._driver.verify_connectivity()`` würde
        ``'NoneType' object has no attribute 'verify_connectivity'`` werfen
        und im UI als Service-Ausfall sichtbar machen, obwohl Neo4j selbst
        erreichbar ist. Der Status-Endpoint muss die Lazy-Reconnect-Logik
        des Storage nutzen.
        """
        import threading
        from flask import Flask
        from app.storage.neo4j_storage import Neo4jStorage

        app = Flask(__name__)
        app.extensions = {}

        # Bare Neo4jStorage instance — kein __init__-Call, damit kein echter
        # Driver oder Server-Roundtrip nötig ist.
        storage = Neo4jStorage.__new__(Neo4jStorage)
        storage._driver = None
        storage._lock = threading.Lock()
        storage._uri = 'bolt://127.0.0.1:0'
        storage._user = 'neo4j'
        storage._password = 'invalid'
        storage._is_connected = False
        storage._last_error = None
        storage._last_success_ts = None
        app.extensions['neo4j_storage'] = storage

        with app.app_context():
            result = _get_neo4j_status()

        assert result['reachable'] is False
        assert result['error'] is not None
        # Der konkrete NoneType-AttributeError darf nicht durchschlagen —
        # er ist ein internes Symptom, nicht der echte Connectivity-Fehler.
        assert "'NoneType'" not in result['error'], (
            f"NoneType-AttributeError leakt durch: {result['error']!r}"
        )
        assert "verify_connectivity'" not in result['error'], (
            f"NoneType-AttributeError leakt durch: {result['error']!r}"
        )
