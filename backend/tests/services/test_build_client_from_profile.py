"""Tests für build_client_from_profile() — P5.3 Factory-Funktion.

Drei Fälle gemäß Briefing:
1. Ollama-Profil ohne api_key → LLMClient baut erfolgreich.
2. OpenAI-Profil mit api_key → LLMClient baut, api_key und model korrekt.
3. Cloud-Profil ohne api_key → ValueError sofort, kein HTTP-Request.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.contracts.llm_profile_contract import LlmProfile
from app.utils.llm_client import build_client_from_profile


def _make_profile(**overrides) -> LlmProfile:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id="test-profile-01",
        name="Test",
        provider="ollama",
        base_url="http://localhost:11434/v1",
        model_name="qwen2.5:32b",
        api_key="",
        is_default=False,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return LlmProfile(**defaults)


def test_build_client_from_ollama_profile():
    """Ollama-Profil ohne api_key baut LLMClient erfolgreich."""
    profile = _make_profile(provider="ollama", base_url="http://localhost:11434/v1", api_key="")

    with patch("app.llm.client.OpenAI"):
        client = build_client_from_profile(profile)

    assert client.model == "qwen2.5:32b"
    assert client.api_key == "ollama"  # Dummy für Ollama
    assert "localhost" in client.base_url


def test_build_client_from_openai_profile():
    """OpenAI-Profil mit api_key baut LLMClient mit korrekten Werten."""
    profile = _make_profile(
        provider="openai",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4o",
        api_key="sk-xyz",
    )

    with patch("app.llm.client.OpenAI"):
        client = build_client_from_profile(profile, run_id="run-42")

    assert client.api_key == "sk-xyz"
    assert client.model == "gpt-4o"
    assert client.run_id == "run-42"


def test_build_client_rejects_cloud_without_key():
    """Cloud-Provider ohne api_key löst ValueError aus — kein HTTP-Request."""
    profile = _make_profile(
        provider="openai",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4o",
        api_key="",
    )

    with pytest.raises(ValueError, match="api_key fehlt"):
        build_client_from_profile(profile)
