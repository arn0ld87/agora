"""
Tests for the unified /api/status endpoint.
Simpler approach: test the functions directly rather than via Flask test client.
"""

import os
from unittest.mock import Mock, patch

import pytest
import requests

from app import __version__
from app.config import Config
from app.api.status import (
    _get_backend_status,
    _get_e2e_status,
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
        # allow_small_sim ist entfallen: es gibt keine harte Untergrenze
        # von 30 Personas mehr, die ein Schalter aufheben muesste (B4).
        assert 'allow_small_sim' not in result

    def test_get_e2e_status_defaults_to_inactive(self, monkeypatch):
        """Ohne AGORA_E2E_LLM_MODE ist der Stub aus — Normalfall in Produktion."""
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        result = _get_e2e_status()
        assert result == {"llm_mode": None, "stub_active": False}

    def test_get_e2e_status_reports_active_stub(self, monkeypatch):
        """AGORA_E2E_LLM_MODE=stub wird als stub_active=True gemeldet.

        Die E2E-Suite assertiert hart auf dieses Feld
        (frontend/tests/e2e/helpers/diagnostics.ts::assertStubModeActive).
        Bliebe es aus, liefe die Suite unbemerkt gegen einen echten Provider.
        """
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "stub")
        result = _get_e2e_status()
        assert result["llm_mode"] == "stub"
        assert result["stub_active"] is True

    def test_get_e2e_status_other_modes_are_not_stub(self, monkeypatch):
        """Nur exakt "stub" zaehlt — jeder andere Wert bedeutet echter Provider."""
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "live")
        result = _get_e2e_status()
        assert result["llm_mode"] == "live"
        assert result["stub_active"] is False

        # Leerstring ist "nicht gesetzt", nicht "unbekannter Modus".
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", "")
        assert _get_e2e_status() == {"llm_mode": None, "stub_active": False}

    @pytest.mark.parametrize("padded", [" stub", "stub ", " stub ", "\tstub\n", "   "])
    def test_get_e2e_status_does_not_strip_before_comparing(self, monkeypatch, padded):
        """Gepolsterte Werte sind KEIN Stub — exakt wie im LLM-Pfad.

        ``llm/client.py:596``/``:994``, ``llm/tool_calls.py:165`` und
        ``storage/embedding_service.py:157`` vergleichen den Rohwert ohne
        ``strip()`` gegen ``"stub"``. Ein ``strip()`` an dieser Stelle wuerde
        bei ``" stub "`` ``stub_active=True`` melden, waehrend der LLM-Pfad
        denselben Wert als Nicht-Stub liest und den echten Provider ruft —
        ``assertStubModeActive`` gaebe dann genau den ungueltigen Lauf frei,
        den es verhindern soll.
        """
        monkeypatch.setenv("AGORA_E2E_LLM_MODE", padded)
        result = _get_e2e_status()
        assert result["stub_active"] is False
        # Rohwert bleibt sichtbar, damit der Tippfehler in der
        # Playwright-Fehlermeldung auftaucht statt weggeputzt zu werden.
        assert result["llm_mode"] == padded

        # Gegenprobe: derselbe Vergleich, den der LLM-Pfad zieht.
        assert os.environ.get("AGORA_E2E_LLM_MODE") != "stub"

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


class TestOllamaStatusProviderGating:
    """Regression für den Bug 'MiniMax wird gegen /api/tags geprüft'.

    Die alte Logik hat ``LLM_BASE_URL`` gestrippt und pauschal ``/api/tags``
    angefragt — bei MiniMax-URLs führt das zu 404 und Log-Spam. Der Status-
    Endpoint muss den Probe anhand der Provider-Heuristik überspringen.
    """

    def _set_provider(self, monkeypatch, base_url, model=""):
        monkeypatch.setattr(Config, "LLM_BASE_URL", base_url)
        monkeypatch.setattr(Config, "LLM_MODEL_NAME", model)
        # Kein OLLAMA_BASE_URL-Override — wir wollen nur LLM_BASE_URL testen.
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    def test_minimax_url_skips_api_tags_probe(self, monkeypatch):
        self._set_provider(monkeypatch, "https://api.minimax.io/v1", "MiniMax-M3")
        with patch('app.api.status.requests.get') as mock_get:
            result = _get_ollama_status()
        assert result['reachable'] is None
        assert result['skipped'] is True
        assert 'minimax' in result['reason'].lower()
        assert result['models_available'] == []
        assert result['base_url'] is None
        # KEIN HTTP-Call gegen /api/tags.
        mock_get.assert_not_called()

    def test_openai_url_skips_api_tags_probe(self, monkeypatch):
        self._set_provider(monkeypatch, "https://api.openai.com/v1", "gpt-4")
        with patch('app.api.status.requests.get') as mock_get:
            result = _get_ollama_status()
        assert result['reachable'] is None
        assert result['skipped'] is True
        assert 'openai' in result['reason'].lower()
        mock_get.assert_not_called()

    def test_google_url_skips_api_tags_probe(self, monkeypatch):
        self._set_provider(
            monkeypatch,
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "gemini-3",
        )
        with patch('app.api.status.requests.get') as mock_get:
            result = _get_ollama_status()
        assert result['skipped'] is True
        mock_get.assert_not_called()

    def test_ollama_url_calls_api_tags(self, monkeypatch):
        """Echter Ollama-Provider → /api/tags MUSS weiterhin aufgerufen werden."""
        self._set_provider(monkeypatch, "http://localhost:11434/v1", "qwen2.5:32b")
        with patch('app.api.status.requests.get') as mock_get:
            mock_resp = Mock()
            mock_resp.json.return_value = {"models": [{"name": "qwen2.5:32b"}]}
            mock_resp.raise_for_status = Mock()
            mock_get.return_value = mock_resp
            result = _get_ollama_status()
        assert result['skipped'] is False
        assert result['reachable'] is True
        assert "qwen2.5:32b" in result['models_available']
        assert result['base_url'] == "http://localhost:11434"
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        assert called_url.endswith("/api/tags")
        assert "/v1/api/tags" not in called_url

    def test_ollama_url_connectivity_error_is_defensive(self, monkeypatch):
        """Ollama-Verbindungsfehler dürfen KEINEN HTTP-500 verursachen."""
        self._set_provider(monkeypatch, "http://localhost:11434/v1", "qwen2.5:32b")
        with patch('app.api.status.requests.get', side_effect=Exception("boom")):
            result = _get_ollama_status()
        assert result['reachable'] is False
        assert result['skipped'] is False
        assert 'boom' in result['error']
        assert result['models_available'] == []

    def test_ollama_env_url_preferred_over_llm_base_url(self, monkeypatch):
        """``OLLAMA_BASE_URL`` schlägt ``LLM_BASE_URL``, wenn beide gesetzt sind."""
        self._set_provider(monkeypatch, "http://localhost:11434/v1", "qwen2.5:32b")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.internal.lan:9999")
        with patch('app.api.status.requests.get') as mock_get:
            mock_resp = Mock()
            mock_resp.json.return_value = {"models": []}
            mock_resp.raise_for_status = Mock()
            mock_get.return_value = mock_resp
            result = _get_ollama_status()
        assert result['base_url'] == "http://ollama.internal.lan:9999"
        called_url = mock_get.call_args[0][0]
        assert called_url.startswith("http://ollama.internal.lan:9999/api/tags")


class TestOllamaStatusExplicitEnvOverride:
    """Alex' Setup: MiniMax-M3 als Chat-Provider, Ollama nur für Embeddings.

    Regression: ein Provider-Gate, das vor ``OLLAMA_BASE_URL`` greift, blendet
    einen real erreichbaren Ollama-Server aus dem Status aus, sobald der
    Chat-Provider kein Ollama ist. Wer die Env-Variable setzt, benennt den
    Server ausdrücklich — das muss gewinnen.
    """

    def _set_provider(self, monkeypatch, base_url, model=""):
        monkeypatch.setattr(Config, "LLM_BASE_URL", base_url)
        monkeypatch.setattr(Config, "LLM_MODEL_NAME", model)

    def test_minimax_chat_with_explicit_ollama_env_still_probes(self, monkeypatch):
        self._set_provider(monkeypatch, "https://api.minimax.io/v1", "MiniMax-M3")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

        with patch('app.api.status.requests.get') as mock_get:
            mock_resp = Mock()
            mock_resp.json.return_value = {
                "models": [{"name": "qwen3-embedding:4b"}]
            }
            mock_resp.raise_for_status = Mock()
            mock_get.return_value = mock_resp
            result = _get_ollama_status()

        assert result['skipped'] is False
        assert result['reachable'] is True
        assert result['base_url'] == "http://localhost:11434"
        assert mock_get.call_args[0][0].startswith("http://localhost:11434/api/tags")
        assert "qwen3-embedding:4b" in result['models_available']

    def test_minimax_chat_without_ollama_env_skips(self, monkeypatch):
        """Ohne explizite Env bleibt der Skip — kein 404 gegen api.minimax.io."""
        self._set_provider(monkeypatch, "https://api.minimax.io/v1", "MiniMax-M3")
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

        with patch('app.api.status.requests.get') as mock_get:
            result = _get_ollama_status()

        mock_get.assert_not_called()
        assert result['skipped'] is True
        assert result['reachable'] is None
        assert "minimax" in result['reason'].lower()

    def test_explicit_ollama_env_unreachable_stays_defensive(self, monkeypatch):
        """Ollama down bei MiniMax-Chat: reachable=False, kein HTTP-500."""
        self._set_provider(monkeypatch, "https://api.minimax.io/v1", "MiniMax-M3")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

        with patch('app.api.status.requests.get') as mock_get:
            mock_get.side_effect = requests.ConnectionError("connection refused")
            result = _get_ollama_status()

        assert result['skipped'] is False
        assert result['reachable'] is False
        assert result['error'] is not None


class TestOllamaStatusContractShape:
    """Review-Findings PR #955: Contract-SSoT + maschinenlesbarer Skip-Grund."""

    def _set_provider(self, monkeypatch, base_url, model=""):
        monkeypatch.setattr(Config, "LLM_BASE_URL", base_url)
        monkeypatch.setattr(Config, "LLM_MODEL_NAME", model)

    def test_skip_payload_validates_against_pydantic_contract(self, monkeypatch):
        """Die Antwort muss gegen den Backend-Contract validieren.

        Ohne diese Kopplung könnte der Schema-Drift-Gate eine Divergenz
        zwischen ``/api/status`` und dem Zod-Spiegel nicht erkennen.
        """
        from app.contracts.system_status_contract import SystemStatusOllama

        self._set_provider(monkeypatch, "https://api.minimax.io/v1", "MiniMax-M3")
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

        result = _get_ollama_status()

        validated = SystemStatusOllama.model_validate(result)
        assert validated.reachable is None
        assert validated.skipped is True
        # Maschinenlesbar für den i18n-Lookup — nicht die englische Prosa.
        assert validated.skipped_provider == "minimax"

    def test_reachable_payload_validates_against_pydantic_contract(self, monkeypatch):
        from app.contracts.system_status_contract import SystemStatusOllama

        self._set_provider(monkeypatch, "http://localhost:11434/v1", "qwen3:8b")
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

        with patch('app.api.status.requests.get') as mock_get:
            mock_resp = Mock()
            mock_resp.json.return_value = {"models": [{"name": "qwen3:8b"}]}
            mock_resp.raise_for_status = Mock()
            mock_get.return_value = mock_resp
            result = _get_ollama_status()

        validated = SystemStatusOllama.model_validate(result)
        assert validated.reachable is True
        assert validated.skipped is False
        assert validated.skipped_provider is None
        assert validated.models_available == ["qwen3:8b"]

    def test_custom_port_ollama_on_local_host_is_probed(self, monkeypatch):
        """Selbstgehostetes Ollama auf Nicht-Standard-Port auf localhost bleibt sichtbar."""
        self._set_provider(monkeypatch, "http://localhost:11435/v1", "llama3")
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

        with patch('app.api.status.requests.get') as mock_get:
            mock_resp = Mock()
            mock_resp.json.return_value = {"models": [{"name": "llama3"}]}
            mock_resp.raise_for_status = Mock()
            mock_get.return_value = mock_resp
            result = _get_ollama_status()

        assert result['skipped'] is False
        assert result['reachable'] is True
        assert mock_get.call_args[0][0] == "http://localhost:11435/api/tags"

    def test_unknown_gateway_on_remote_host_is_not_probed(self, monkeypatch):
        """Codex-Finding: ein Dritt-Gateway auf fremdem Host nicht pauschal proben.

        ``http://gateway.example:11435/v1`` fällt in ``detect_provider`` auf
        ``"unknown"`` zurück, bedient ``/api/tags`` aber nicht. Es zu proben
        würde genau die 404-Klasse reproduzieren, die der Fix beseitigt.
        Wer solch ein Gateway als Ollama betreibt, setzt ``OLLAMA_BASE_URL``.
        """
        self._set_provider(monkeypatch, "http://gateway.example:11435/v1", "llama3")
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

        with patch('app.api.status.requests.get') as mock_get:
            result = _get_ollama_status()

        mock_get.assert_not_called()
        assert result['skipped'] is True
        assert result['reachable'] is None

    def test_explicit_env_with_v1_suffix_does_not_hit_v1_api_tags(self, monkeypatch):
        """CodeRabbit-Finding: ``/v1/api/tags`` wäre wieder ein 404."""
        self._set_provider(monkeypatch, "https://api.minimax.io/v1", "MiniMax-M3")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

        with patch('app.api.status.requests.get') as mock_get:
            mock_resp = Mock()
            mock_resp.json.return_value = {"models": []}
            mock_resp.raise_for_status = Mock()
            mock_get.return_value = mock_resp
            result = _get_ollama_status()

        called = mock_get.call_args[0][0]
        assert called == "http://localhost:11434/api/tags"
        assert "/v1/api/tags" not in called
        assert result['base_url'] == "http://localhost:11434"
