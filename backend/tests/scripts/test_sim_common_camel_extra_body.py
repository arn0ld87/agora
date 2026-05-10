"""Provider-aware extra_body-Builder für CAMEL ModelFactory.create().

Regression-Cover für den `Unknown parameter: 'think'` 400 von OpenAI:
`think` ist ein Ollama-Reasoning-Toggle (gpt-oss / qwen3-thinking /
deepseek-r1). OpenAI/Anthropic/Mistral kennen den Parameter nicht und
antworten 400. Der Helper darf den Parameter ausschließlich für Ollama-
Routen einsetzen.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ liegt nicht auf dem Default-Pythonpath des Test-Runners.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _sim_common import build_camel_extra_body  # noqa: E402


class TestBuildCamelExtraBodyOllamaLocal:
    """Lokales Ollama (base_url enthält Port 11434)."""

    def test_local_ollama_sets_think_false_by_default(self) -> None:
        body = build_camel_extra_body(
            model="qwen3-coder",
            base_url="http://localhost:11434/v1",
            num_ctx=8192,
            think=False,
        )
        assert body == {"think": False, "options": {"num_ctx": 8192}}

    def test_local_ollama_sets_think_true_when_explicit(self) -> None:
        body = build_camel_extra_body(
            model="qwen3-coder",
            base_url="http://127.0.0.1:11434/v1",
            num_ctx=16384,
            think=True,
        )
        assert body == {"think": True, "options": {"num_ctx": 16384}}

    def test_local_ollama_omits_options_when_num_ctx_none(self) -> None:
        body = build_camel_extra_body(
            model="qwen3-coder",
            base_url="http://localhost:11434/v1",
            num_ctx=None,
            think=False,
        )
        assert body == {"think": False}


class TestBuildCamelExtraBodyOllamaCloud:
    """Ollama Cloud — Modell-Suffix `:cloud`, base_url egal."""

    def test_cloud_model_sets_think_regardless_of_base_url(self) -> None:
        body = build_camel_extra_body(
            model="qwen3-coder-next:cloud",
            base_url="https://ollama.com/v1",
            num_ctx=262144,
            think=False,
        )
        assert body == {"think": False, "options": {"num_ctx": 262144}}


class TestBuildCamelExtraBodyOpenAI:
    """OpenAI-Direct — `think` darf NICHT gesetzt werden (400 sonst)."""

    def test_openai_returns_empty_dict(self) -> None:
        body = build_camel_extra_body(
            model="gpt-5.4-mini",
            base_url="https://api.openai.com/v1",
            num_ctx=128000,
            think=False,
        )
        assert body == {}

    def test_openai_drops_think_even_when_true(self) -> None:
        body = build_camel_extra_body(
            model="gpt-5.4-mini",
            base_url="https://api.openai.com/v1",
            num_ctx=None,
            think=True,
        )
        assert "think" not in body
        assert "options" not in body

    def test_unknown_provider_returns_empty_dict(self) -> None:
        # Default-Path: wenn weder Ollama-URL noch :cloud-Suffix erkennbar
        # sind, conservatively keine Ollama-Parameter senden.
        body = build_camel_extra_body(
            model="claude-opus-4-7",
            base_url="https://api.anthropic.com/v1",
            num_ctx=200000,
            think=False,
        )
        assert body == {}

    def test_empty_base_url_with_plain_model_treated_as_openai(self) -> None:
        # Bei leerer base_url nutzt CAMEL OpenAI als Default — kein Ollama.
        body = build_camel_extra_body(
            model="gpt-5.4-mini",
            base_url="",
            num_ctx=None,
            think=False,
        )
        assert body == {}
