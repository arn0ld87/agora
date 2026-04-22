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
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/nvidia-smi"
            result = detect_gpu()
            assert result["nvidia_smi_available"] is True

    def test_nvidia_smi_not_available(self):
        """Test detection when nvidia-smi is not in PATH"""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            result = detect_gpu()
            assert result["nvidia_smi_available"] is False
            assert any("nvidia-smi not found" in h for h in result["hints"])

    def test_ollama_running_with_models(self):
        """Test when Ollama is running with loaded models"""
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            mock_which.return_value = None
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="NAME\nqwen2.5:32b  4.2 GB\n"
            )
            result = detect_gpu()
            assert result["ollama_uses_gpu"] is True
            assert any("Ollama process" in h for h in result["hints"])

    def test_ollama_running_no_models(self):
        """Test when Ollama is running but no models loaded"""
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            mock_which.return_value = None
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=""
            )
            result = detect_gpu()
            assert result["ollama_uses_gpu"] is False
            assert any("not running" in h.lower() or "no models" in h.lower() for h in result["hints"])

    def test_ollama_not_available(self):
        """Test when ollama command is not available"""
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            mock_which.return_value = None
            mock_run.side_effect = FileNotFoundError("ollama not found")
            result = detect_gpu()
            assert result["ollama_uses_gpu"] is None
            assert any("Cannot determine Ollama" in h for h in result["hints"])

    def test_ollama_timeout(self):
        """Test when ollama ps times out"""
        import subprocess
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            mock_which.return_value = None
            mock_run.side_effect = subprocess.TimeoutExpired("ollama", 5)
            result = detect_gpu()
            assert result["ollama_uses_gpu"] is None
            assert any("Cannot determine Ollama" in h for h in result["hints"])

    def test_cpu_only_fallback_hint(self):
        """Test that CPU-only fallback hint is added when appropriate"""
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            mock_which.return_value = None
            mock_run.side_effect = FileNotFoundError()
            result = detect_gpu()
            assert any("CPU-only mode" in h for h in result["hints"])

    def test_never_throws(self):
        """Ensure detect_gpu never raises exceptions"""
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            # Simulate catastrophic failure
            mock_which.side_effect = Exception("Catastrophic failure")
            mock_run.side_effect = Exception("Another failure")

            # Should not raise
            try:
                result = detect_gpu()
                # At least the structure should be present
                assert "nvidia_smi_available" in result
                assert "ollama_uses_gpu" in result
                assert "hints" in result
            except Exception as e:
                pytest.fail(f"detect_gpu should never throw, but raised {e}")
