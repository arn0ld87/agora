"""Tests for detect_oasis_platform() and create_model() dispatch routing.

Verifies that the three-way GEMINI / OLLAMA / OPENAI detection heuristic
maps model-name + base-url to the correct CAMEL ModelPlatformType, and that
create_model() sets the right environment variables (GOOGLE_API_KEY vs
OPENAI_BASE_URL) depending on the detected platform.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap — scripts/ is not on the default pytest sys.path.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Use the real camel.types — camel-ai is always installed in this venv.
from camel.types import ModelPlatformType  # type: ignore[import]  # noqa: E402

from _sim_common import detect_oasis_platform  # noqa: E402


# ---------------------------------------------------------------------------
# detect_oasis_platform — unit tests
# ---------------------------------------------------------------------------


class TestDetectOasisPlatform:
    def test_detect_gemini_url(self) -> None:
        result = detect_oasis_platform(
            "gemini-3-flash-preview",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        assert result == ModelPlatformType.GEMINI

    def test_detect_gemini_by_model_prefix(self) -> None:
        result = detect_oasis_platform("gemini-2.5-flash", "")
        assert result == ModelPlatformType.GEMINI

    def test_detect_gemini_by_model_prefix_non_google_url(self) -> None:
        result = detect_oasis_platform(
            "gemini-2.0-flash-lite", "https://api.example.com/v1"
        )
        assert result == ModelPlatformType.GEMINI

    def test_detect_ollama_cloud_by_url(self) -> None:
        result = detect_oasis_platform(
            "llama3.2:latest", "https://ollama.com/api"
        )
        assert result == ModelPlatformType.OLLAMA

    def test_detect_ollama_cloud_by_model_suffix(self) -> None:
        result = detect_oasis_platform(
            "qwen3-coder-next:cloud", "https://ollama.com"
        )
        assert result == ModelPlatformType.OLLAMA

    def test_detect_ollama_local(self) -> None:
        result = detect_oasis_platform(
            "qwen3:8b", "http://localhost:11434"
        )
        assert result == ModelPlatformType.OLLAMA

    def test_detect_ollama_local_ip(self) -> None:
        result = detect_oasis_platform(
            "qwen3:8b", "http://127.0.0.1:11434/v1"
        )
        assert result == ModelPlatformType.OLLAMA

    def test_detect_ollama_latest_suffix(self) -> None:
        result = detect_oasis_platform("llama3:latest", "")
        assert result == ModelPlatformType.OLLAMA

    def test_detect_openai(self) -> None:
        result = detect_oasis_platform(
            "gpt-5-nano", "https://api.openai.com/v1"
        )
        assert result == ModelPlatformType.OPENAI

    def test_detect_fallback_openai_empty(self) -> None:
        result = detect_oasis_platform("gpt-4o-mini", "")
        assert result == ModelPlatformType.OPENAI

    def test_detect_fallback_cloud_suffix_triggers_ollama(self) -> None:
        result = detect_oasis_platform(
            "qwen3-coder-next:cloud", "https://any-compat-gateway.example.com"
        )
        assert result == ModelPlatformType.OLLAMA

    def test_gemini_prefix_beats_ollama_url(self) -> None:
        result = detect_oasis_platform(
            "gemini-2.5-pro", "http://localhost:11434"
        )
        assert result == ModelPlatformType.GEMINI


# ---------------------------------------------------------------------------
# create_model() environment-variable routing — integration-level mocks
# ---------------------------------------------------------------------------


def _make_model_factory_mock() -> tuple[MagicMock, list[dict[str, Any]]]:
    """Return (mock_factory_module, calls_list).

    The calls_list is appended to on each ModelFactory.create() invocation,
    capturing keyword arguments for assertions.
    """
    calls: list[dict[str, Any]] = []

    mock_factory = MagicMock()
    mock_factory.create = MagicMock(
        side_effect=lambda *a, **kw: calls.append({"args": a, "kwargs": kw}) or MagicMock()
    )
    return mock_factory, calls


class TestCreateModelGeminiBranch:
    """create_model() with a Gemini model must not touch OPENAI_BASE_URL."""

    def test_gemini_sets_google_api_key_not_openai_base_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_NAME", "gemini-3-flash-preview")
        monkeypatch.setenv("LLM_API_KEY", "my-google-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        mock_factory, calls = _make_model_factory_mock()

        import run_parallel_simulation as rps  # type: ignore[import]
        monkeypatch.setattr(rps, "ModelFactory", mock_factory)

        config: dict[str, Any] = {}
        rps.create_model(config, use_boost=False)

        assert os.environ.get("OPENAI_BASE_URL", "") == "", \
            "OPENAI_BASE_URL must not be set for Gemini branch"
        assert os.environ.get("GOOGLE_API_KEY") == "my-google-key"
        assert len(calls) == 1
        platform_arg = calls[0]["args"][0] if calls[0]["args"] else calls[0]["kwargs"].get("model_platform")
        assert platform_arg == ModelPlatformType.GEMINI


class TestCreateModelOpenAIBranch:
    """create_model() with an OpenAI model must set OPENAI_BASE_URL (unchanged behaviour)."""

    def test_openai_sets_base_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_NAME", "gpt-5-nano")
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        mock_factory, calls = _make_model_factory_mock()

        import run_parallel_simulation as rps  # type: ignore[import]
        monkeypatch.setattr(rps, "ModelFactory", mock_factory)

        config: dict[str, Any] = {}
        rps.create_model(config, use_boost=False)

        assert os.environ.get("OPENAI_BASE_URL") == "https://api.openai.com/v1"
        assert len(calls) == 1
        platform_arg = calls[0]["args"][0] if calls[0]["args"] else calls[0]["kwargs"].get("model_platform")
        assert platform_arg == ModelPlatformType.OPENAI
