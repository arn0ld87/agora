"""Token-Key-Mapper für CAMEL ``model_config_dict``.

Regression-Cover für ``openai.BadRequestError 400 — 'max_tokens' is not
supported with this model. Use 'max_completion_tokens' instead.``: Die
GPT-5-Familie und die Reasoning-Modelle ``o1``/``o3``/``o4`` haben
``max_tokens`` deprecated und akzeptieren ausschließlich
``max_completion_tokens``. Ältere OpenAI-Modelle (``gpt-4o``,
``gpt-4-turbo``) sowie alle nicht-OpenAI-Backends (Qwen, Llama, Claude,
Ollama-Modelle) erwarten weiterhin ``max_tokens``.

Der Helper muss den richtigen Schlüssel pro Modell-Familie liefern,
damit die OASIS-Subprocess-Skripte
(``run_parallel_simulation.py`` / ``run_reddit_simulation.py`` /
``run_twitter_simulation.py``) ihren ``model_config_dict``-Aufbau
provider-aware halten können.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _sim_common import (  # noqa: E402
    build_camel_completion_params,
    uses_max_completion_tokens,
)


class TestUsesMaxCompletionTokensGpt5Family:
    """GPT-5-Familie verlangt ``max_completion_tokens``."""

    @pytest.mark.parametrize(
        "model",
        [
            "gpt-5",
            "gpt-5-mini",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.4-thinking",
            "gpt-5-turbo",
            "GPT-5.4-MINI",
        ],
    )
    def test_gpt5_models_use_max_completion_tokens(self, model: str) -> None:
        assert uses_max_completion_tokens(model) is True


class TestUsesMaxCompletionTokensReasoningModels:
    """o1/o3/o4-Reasoning-Modelle verlangen ``max_completion_tokens``."""

    @pytest.mark.parametrize(
        "model",
        [
            "o1",
            "o1-mini",
            "o1-preview",
            "o3",
            "o3-mini",
            "o4-mini",
            "O1-MINI",
        ],
    )
    def test_reasoning_models_use_max_completion_tokens(self, model: str) -> None:
        assert uses_max_completion_tokens(model) is True


class TestUsesMaxCompletionTokensLegacyOpenAI:
    """Ältere OpenAI-Modelle akzeptieren weiterhin ``max_tokens``."""

    @pytest.mark.parametrize(
        "model",
        [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
        ],
    )
    def test_legacy_openai_uses_max_tokens(self, model: str) -> None:
        assert uses_max_completion_tokens(model) is False


class TestUsesMaxCompletionTokensNonOpenAI:
    """Nicht-OpenAI-Backends nutzen weiterhin ``max_tokens``."""

    @pytest.mark.parametrize(
        "model",
        [
            "qwen3-coder",
            "qwen3-coder-next:cloud",
            "llama3.1:70b",
            "claude-opus-4-7",
            "deepseek-r1:cloud",
            "gpt-oss:cloud",
            "mistral-large",
            "",
        ],
    )
    def test_non_openai_uses_max_tokens(self, model: str) -> None:
        assert uses_max_completion_tokens(model) is False


class TestBuildCamelCompletionParams:
    """Builder produziert das richtige Dict für ``model_config_dict``."""

    def test_gpt5_returns_max_completion_tokens(self) -> None:
        params = build_camel_completion_params(
            model="gpt-5.4-mini",
            completion_max_tokens=4096,
        )
        assert params == {"max_completion_tokens": 4096}

    def test_o1_returns_max_completion_tokens(self) -> None:
        params = build_camel_completion_params(
            model="o1-mini",
            completion_max_tokens=2048,
        )
        assert params == {"max_completion_tokens": 2048}

    def test_legacy_openai_returns_max_tokens(self) -> None:
        params = build_camel_completion_params(
            model="gpt-4o",
            completion_max_tokens=8192,
        )
        assert params == {"max_tokens": 8192}

    def test_qwen_cloud_returns_max_tokens(self) -> None:
        params = build_camel_completion_params(
            model="qwen3-coder-next:cloud",
            completion_max_tokens=16384,
        )
        assert params == {"max_tokens": 16384}

    def test_only_one_key_returned(self) -> None:
        # Wichtig: NICHT beide Keys gleichzeitig — OpenAI rejected unknown
        # parameters strict bei GPT-5.
        params = build_camel_completion_params(
            model="gpt-5.4-mini",
            completion_max_tokens=4096,
        )
        assert "max_tokens" not in params
        assert set(params.keys()) == {"max_completion_tokens"}
