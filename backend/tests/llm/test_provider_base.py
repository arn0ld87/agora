"""Tests fuer den Backward-Compat-Wrapper ``app.llm.providers.base.detect_provider``
(Issue #591 / MiniMax-Erweiterung).

``detect_provider`` in ``base.py`` ist eine reine Delegations-Duennschicht auf
``app.llm.providers.registry.detect_provider(mode="http")`` (Single Source of
Truth). Diese Tests fixieren, dass der Wrapper das erweiterte Vokabular
(inkl. ``"minimax"``) unveraendert durchreicht und mit der Registry
uebereinstimmt.
"""
from __future__ import annotations

import pytest

from app.llm.providers.base import detect_provider
from app.llm.providers.registry import detect_provider as registry_detect_provider


WRAPPER_CASES = [
    # (base_url, model, expected)
    ("http://localhost:11434/v1", "qwen2.5:32b", "ollama"),
    ("https://ollama.com/v1", "qwen3-coder-next:cloud", "cloud"),
    ("https://api.minimax.io/v1", "MiniMax-M3", "minimax"),
    ("https://api.minimax.io/anthropic", "MiniMax-M3", "minimax"),
    ("https://api.openai.com/v1", "gpt-4", "openai"),
    (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-3-flash-preview",
        "google",
    ),
    ("http://some-other-host:8080/v1", "some-model", "unknown"),
    (None, None, "unknown"),
]


@pytest.mark.parametrize(("base_url", "model", "expected"), WRAPPER_CASES)
def test_detect_provider_wrapper_matches_expected(base_url, model, expected):
    assert detect_provider(base_url, model) == expected


@pytest.mark.parametrize(("base_url", "model", "expected"), WRAPPER_CASES)
def test_detect_provider_wrapper_delegates_to_registry_http_mode(base_url, model, expected):
    """The wrapper must be a pure pass-through — no divergence from the SSoT."""
    assert detect_provider(base_url, model) == registry_detect_provider(
        base_url, model, mode="http"
    )


def test_detect_provider_wrapper_returns_minimax_literal():
    """Regression: the wrapper's Literal return type was widened to include
    ``"minimax"`` alongside the pre-existing ollama/cloud/openai/google/unknown
    vocabulary; the runtime value must actually surface it (not just the type
    annotation)."""
    result = detect_provider("https://api.minimax.io/v1", "MiniMax-M3")
    assert result == "minimax"
    assert isinstance(result, str)