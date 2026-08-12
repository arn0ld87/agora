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
_TESTS_DIR = Path(__file__).resolve().parent
for _p in (_SCRIPTS_DIR, _TESTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Use the real camel.types — camel-ai is always installed in this venv.
from camel.types import ModelPlatformType  # type: ignore[import]  # noqa: E402

from _sim_common import detect_oasis_platform  # noqa: E402
from _crash_skip import skipif_py314_aarch64  # noqa: E402


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


@skipif_py314_aarch64
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

        import run_parallel_simulation as rps  # type: ignore[import]
        create_gemini = MagicMock(return_value=MagicMock())
        monkeypatch.setattr(rps, "_create_gemini_model", create_gemini)

        config: dict[str, Any] = {}
        result = rps.create_model(config, use_boost=False)

        assert os.environ.get("OPENAI_BASE_URL", "") == "", \
            "OPENAI_BASE_URL must not be set for Gemini branch"
        assert os.environ.get("GOOGLE_API_KEY") == "my-google-key"
        assert result is create_gemini.return_value
        create_gemini.assert_called_once_with(
            model_type="gemini-3-flash-preview",
            model_config_dict=rps.build_camel_completion_params(
                model="gemini-3-flash-preview",
                completion_max_tokens=rps.resolve_model_runtime_settings(
                    "gemini-3-flash-preview"
                )["completion_max_tokens"],
            ),
            api_key="my-google-key",
        )


@skipif_py314_aarch64
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
        # Regression: OPENAI branch must not leak Ollama-only fields into the
        # request body — think/num_ctx would 400 on real OpenAI.
        model_cfg = calls[0]["kwargs"].get("model_config_dict", {})
        assert "extra_body" not in model_cfg, \
            "OPENAI branch must not emit extra_body (think/num_ctx are Ollama-only)"


@skipif_py314_aarch64
class TestCreateModelMiniMaxBranch:
    """create_model() mit einem MiniMax-Modell (api.minimax.io) routet ueber den
    OpenAI-Compat-Pfad und muss den MiniMax-`thinking`-Block in
    model_config_dict.extra_body setzen (Spec: thinking.type ∈ disabled/adaptive).
    """

    def test_minimax_think_off_sets_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_NAME", "MiniMax-M3")
        monkeypatch.setenv("LLM_API_KEY", "mm-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.minimax.io/v1")
        monkeypatch.delenv("OLLAMA_THINKING", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        mock_factory, calls = _make_model_factory_mock()

        import run_parallel_simulation as rps  # type: ignore[import]
        monkeypatch.setattr(rps, "ModelFactory", mock_factory)

        rps.create_model({}, use_boost=False)

        assert len(calls) == 1
        platform_arg = calls[0]["args"][0] if calls[0]["args"] else calls[0]["kwargs"].get("model_platform")
        assert platform_arg == ModelPlatformType.OPENAI
        model_cfg = calls[0]["kwargs"].get("model_config_dict", {})
        assert model_cfg.get("extra_body") == {"thinking": {"type": "disabled"}}

    def test_minimax_think_on_sets_adaptive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_NAME", "MiniMax-M3")
        monkeypatch.setenv("LLM_API_KEY", "mm-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.minimax.io/v1")
        monkeypatch.setenv("OLLAMA_THINKING", "true")
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        mock_factory, calls = _make_model_factory_mock()

        import run_parallel_simulation as rps  # type: ignore[import]
        monkeypatch.setattr(rps, "ModelFactory", mock_factory)

        rps.create_model({}, use_boost=False)

        model_cfg = calls[0]["kwargs"].get("model_config_dict", {})
        assert model_cfg.get("extra_body") == {"thinking": {"type": "adaptive"}}

    def test_minimax_openai_branch_passes_resolved_url_and_api_key_explicitly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Root Cause 404 ``model MiniMax-M3 not found``: Der OPENAI-Branch von
        ``create_model`` relied ausschließlich auf ``os.environ["OPENAI_BASE_URL"]``
        und ``OPENAI_API_KEY``. Ein Stale-Parent-Env (z. B. OpenAI-Default aus
        ``.env``) konnte die aufgelöste MiniMax-Route überschatten. CAMELs
        ``OpenAIModel.__init__`` gibt expliziten ``url``/``api_key``-Parametern
        Vorrang vor dem Env — deshalb muss der Branch sie explizit übergeben.

        Vor dem Fix wurden ``url``/``api_key`` im OPENAI-Branch NICHT an
        ``ModelFactory.create`` übergeben → dieser Test schlägt fehl (RED)."""
        monkeypatch.setenv("LLM_MODEL_NAME", "MiniMax-M3")
        monkeypatch.setenv("LLM_API_KEY", "mm-bound-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.minimax.io/v1")
        monkeypatch.delenv("OLLAMA_THINKING", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        # Stale-Parent-Env, das die Route überschatten dürfte, wenn sie nicht
        # explizit übergeben wird:
        monkeypatch.setenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "stale-openai-key")

        mock_factory, calls = _make_model_factory_mock()

        import run_parallel_simulation as rps  # type: ignore[import]
        monkeypatch.setattr(rps, "ModelFactory", mock_factory)

        rps.create_model({}, use_boost=False)

        assert len(calls) == 1
        kwargs = calls[0]["kwargs"]
        assert kwargs.get("model_platform") == ModelPlatformType.OPENAI
        assert kwargs.get("url") == "https://api.minimax.io/v1", (
            "OPENAI-Branch muss die aufgelöste MiniMax-URL explizit an "
            "ModelFactory.create übergeben, sonst gewinnt ein Stale-Env."
        )
        assert kwargs.get("api_key") == "mm-bound-key", (
            "OPENAI-Branch muss den gebundenen MiniMax-Key explizit übergeben, "
            "sonst gewinnt ein Stale-OPENAI_API_KEY aus dem Parent-Env."
        )


@skipif_py314_aarch64
class TestCreateModelOllamaBranch:
    """create_model() with an Ollama model must route via OllamaModel with url/api_key
    and emit think/num_ctx in extra_body — even for ``:latest`` suffixes and
    ``ollama.com`` URLs where the legacy ``_is_ollama_route`` heuristic would
    fail.
    """

    def test_ollama_sets_url_and_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_NAME", "llama3:latest")
        monkeypatch.setenv("LLM_API_KEY", "my-ollama-key")
        monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        mock_factory, calls = _make_model_factory_mock()

        import run_parallel_simulation as rps  # type: ignore[import]
        monkeypatch.setattr(rps, "ModelFactory", mock_factory)

        config: dict[str, Any] = {}
        rps.create_model(config, use_boost=False)

        assert os.environ.get("OPENAI_BASE_URL", "") == "", \
            "OPENAI_BASE_URL must not be set for Ollama branch"
        assert os.environ.get("GOOGLE_API_KEY", "") == "", \
            "GOOGLE_API_KEY must not be set for Ollama branch"
        assert len(calls) == 1
        kwargs = calls[0]["kwargs"]
        assert kwargs.get("model_platform") == ModelPlatformType.OLLAMA
        # ``/v1`` ist Pflicht, nicht Kosmetik: CAMELs OllamaModel ist ein
        # OpenAICompatibleModel und ruft ``POST {url}/chat/completions``. Die
        # frühere Fassung dieses Tests hat ``http://localhost:11434`` roh
        # durchgereicht erwartet und damit den Defekt festgeschrieben.
        assert kwargs.get("url") == "http://localhost:11434/v1"
        assert kwargs.get("api_key") == "my-ollama-key"

    def test_ollama_cloud_url_gets_v1_suffix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: ``https://ollama.com`` ohne ``/v1`` → OASIS-Preflight-404.

        Der Registry-Default für ``ollama_cloud`` ist ``https://ollama.com``.
        CAMELs ``OllamaModel`` erbt von ``OpenAICompatibleModel`` und ruft
        ``POST {url}/chat/completions`` — ohne ``/v1`` landet der Preflight auf
        ``https://ollama.com/chat/completions``, einer Route, die es nicht gibt.
        Ollama antwortet mit seiner HTML-404-Seite, das OpenAI-SDK macht daraus
        einen ``NotFoundError`` mit HTML-Body, und ``preflight_model_probe``
        lehnt den Lauf ab, bevor auch nur ein Agent startet.
        """
        monkeypatch.setenv("LLM_MODEL_NAME", "deepseek-v4-flash:0731-cloud")
        monkeypatch.setenv("LLM_API_KEY", "cloud-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://ollama.com")

        mock_factory, calls = _make_model_factory_mock()

        import run_parallel_simulation as rps  # type: ignore[import]
        monkeypatch.setattr(rps, "ModelFactory", mock_factory)

        rps.create_model({}, use_boost=False)

        kwargs = calls[0]["kwargs"]
        assert kwargs.get("model_platform") == ModelPlatformType.OLLAMA
        assert kwargs.get("url") == "https://ollama.com/v1"

    def test_ollama_url_with_v1_is_not_doubled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Eine bereits korrekte URL bleibt unverändert — kein ``/v1/v1``."""
        monkeypatch.setenv("LLM_MODEL_NAME", "deepseek-v4-flash:0731-cloud")
        monkeypatch.setenv("LLM_API_KEY", "cloud-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://ollama.com/v1/")

        mock_factory, calls = _make_model_factory_mock()

        import run_parallel_simulation as rps  # type: ignore[import]
        monkeypatch.setattr(rps, "ModelFactory", mock_factory)

        rps.create_model({}, use_boost=False)

        assert calls[0]["kwargs"].get("url") == "https://ollama.com/v1"

    def test_ollama_latest_suffix_emits_extra_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression for Gemini-Finding: ``:latest`` is detected as Ollama by
        ``detect_oasis_platform`` but was dropped by the legacy
        ``_is_ollama_route`` gate, silently losing ``think`` and ``num_ctx``.
        """
        monkeypatch.setenv("LLM_MODEL_NAME", "llama3:latest")
        monkeypatch.setenv("LLM_API_KEY", "my-ollama-key")
        monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434")
        monkeypatch.setenv("OLLAMA_THINKING", "true")

        mock_factory, calls = _make_model_factory_mock()

        import run_parallel_simulation as rps  # type: ignore[import]
        monkeypatch.setattr(rps, "ModelFactory", mock_factory)

        rps.create_model({}, use_boost=False)

        kwargs = calls[0]["kwargs"]
        model_cfg = kwargs.get("model_config_dict", {})
        assert "extra_body" in model_cfg, \
            ":latest model must emit extra_body with think/num_ctx"
        assert model_cfg["extra_body"].get("think") is True

    def test_ollama_cloud_host_emits_extra_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression for Gemini-Finding: ``ollama.com`` URL → OLLAMA route,
        must still produce ``extra_body`` even though the legacy heuristic
        only matched ``:11434``.
        """
        monkeypatch.setenv("LLM_MODEL_NAME", "qwen3-coder-next:cloud")
        monkeypatch.setenv("LLM_API_KEY", "cloud-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://ollama.com")
        monkeypatch.setenv("OLLAMA_THINKING", "false")

        mock_factory, calls = _make_model_factory_mock()

        import run_parallel_simulation as rps  # type: ignore[import]
        monkeypatch.setattr(rps, "ModelFactory", mock_factory)

        rps.create_model({}, use_boost=False)

        kwargs = calls[0]["kwargs"]
        assert kwargs.get("model_platform") == ModelPlatformType.OLLAMA
        model_cfg = kwargs.get("model_config_dict", {})
        assert "extra_body" in model_cfg
        assert model_cfg["extra_body"].get("think") is False
