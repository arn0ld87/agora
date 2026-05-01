"""
Tests for GPU readiness detection
"""

import pytest
from unittest.mock import patch, MagicMock
from app.utils.gpu_probe import detect_gpu


class TestDetectGPU:
    """Test GPU detection probe"""

    def test_nvidia_smi_available(self):
        """Test detection when nvidia-smi is in PATH"""
        with patch("shutil.which") as mock_which, \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_which.return_value = "/usr/bin/nvidia-smi"
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'{"models":[]}'
            mock_urlopen.return_value = mock_resp
            result = detect_gpu()
            assert result["nvidia_smi_available"] is True

    def test_nvidia_smi_not_available(self):
        """Test detection when nvidia-smi is not in PATH"""
        with patch("shutil.which") as mock_which, \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_which.return_value = None
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'{"models":[]}'
            mock_urlopen.return_value = mock_resp
            result = detect_gpu()
            assert result["nvidia_smi_available"] is False
            # No "nvidia-smi not found" spam anymore — we rely on Ollama API

    def test_ollama_gpu_active(self):
        """Test when Ollama reports VRAM usage (GPU active)"""
        with patch("shutil.which") as mock_which, \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_which.return_value = None
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = (
                b'{"models":[{"name":"qwen3-embedding:4b","size_vram":4095045632}]}'
            )
            mock_urlopen.return_value = mock_resp
            result = detect_gpu()
            assert result["ollama_uses_gpu"] is True
            assert any("GPU aktiv" in h for h in result["hints"])

    def test_ollama_cpu_only_no_vram(self):
        """Test when Ollama has models loaded but zero VRAM"""
        with patch("shutil.which") as mock_which, \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_which.return_value = None
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = (
                b'{"models":[{"name":"llama3.2:3b","size_vram":0}]}'
            )
            mock_urlopen.return_value = mock_resp
            result = detect_gpu()
            assert result["ollama_uses_gpu"] is False
            assert any("keine Modelle mit GPU" in h for h in result["hints"])

    def test_ollama_reachable_no_models(self):
        """Test when Ollama is reachable but no models loaded"""
        with patch("shutil.which") as mock_which, \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_which.return_value = None
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'{"models":[]}'
            mock_urlopen.return_value = mock_resp
            result = detect_gpu()
            assert result["ollama_uses_gpu"] is False
            assert any("keine Modelle geladen" in h for h in result["hints"])

    def test_ollama_not_reachable(self):
        """Test when Ollama API is not reachable"""
        import urllib.error
        with patch("shutil.which") as mock_which, \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_which.return_value = None
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
            result = detect_gpu()
            assert result["ollama_uses_gpu"] is None
            assert any("nicht erreichbar" in h for h in result["hints"])

    def test_ollama_unreachable_fallback_hint(self):
        """Test fallback hint when Ollama is completely unreachable"""
        import urllib.error
        with patch("shutil.which") as mock_which, \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_which.return_value = None
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
            result = detect_gpu()
            assert result["nvidia_smi_available"] is False
            assert result["ollama_uses_gpu"] is None
            assert any("GPU-Status unbekannt" in h for h in result["hints"])

    def test_never_throws(self):
        """Ensure detect_gpu never raises exceptions"""
        with patch("shutil.which") as mock_which, \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_which.side_effect = Exception("Catastrophic failure")
            mock_urlopen.side_effect = Exception("Another failure")
            try:
                result = detect_gpu()
                assert "nvidia_smi_available" in result
                assert "ollama_uses_gpu" in result
                assert "hints" in result
            except Exception as e:
                pytest.fail(f"detect_gpu should never throw, but raised {e}")
