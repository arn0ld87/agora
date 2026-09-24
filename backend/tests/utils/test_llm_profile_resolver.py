"""Regressionsschutz Issue #1284: kein stilles Anthropic->custom_openai-Rerouting.

Vor dem Fix mappte ``_PROFILE_PROVIDER_TO_RUNTIME`` ein Anthropic-Profil auf
``custom_openai`` und übernahm die Profil-Base-URL (``https://api.anthropic.com``,
ohne ``/v1``) unverändert in ``data["llm_provider"]`` — der nachgelagerte
OpenAI-kompatible Client hätte damit gegen eine Route gesprochen, die es dort
nicht gibt (403/404 zur Laufzeit statt eines klaren Fehlers hier).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.contracts.llm_profile_contract import LlmProfile
from app.utils.llm_profile_resolver import expand_profile_in_data


def _profile(*, provider: str, model: str = "claude-sonnet-5") -> LlmProfile:
    now = datetime.now(UTC)
    return LlmProfile(
        id="profile-under-test",
        name="Test profile",
        provider=provider,
        base_url="https://api.anthropic.com",
        model_name=model,
        api_key="must-not-enter-route",
        created_at=now,
        updated_at=now,
    )


def test_anthropic_profile_fails_loud_instead_of_rerouting(monkeypatch):
    profile_store = MagicMock()
    profile_store.get.return_value = _profile(provider="anthropic")
    monkeypatch.setattr(
        "app.utils.llm_profile_resolver.get_llm_profile_repository",
        lambda: profile_store,
    )

    data = {"llm_model": "profile:profile-under-test"}
    with pytest.raises(ValueError, match="Anthropic"):
        expand_profile_in_data(data)

    # Kein stilles Umrouten: data bleibt unveraendert (kein custom_openai-Block).
    assert data == {"llm_model": "profile:profile-under-test"}


def test_anthropic_profile_error_mentions_issue_and_bedrock(monkeypatch):
    profile_store = MagicMock()
    profile_store.get.return_value = _profile(provider="anthropic")
    monkeypatch.setattr(
        "app.utils.llm_profile_resolver.get_llm_profile_repository",
        lambda: profile_store,
    )

    with pytest.raises(ValueError, match="#1284") as exc_info:
        expand_profile_in_data({"llm_model": "profile:profile-under-test"})
    assert "Bedrock" in str(exc_info.value)


def test_openai_profile_still_expands_normally(monkeypatch):
    """Regressionsschutz: der Fix darf nicht-anthropic Profile nicht anfassen."""
    profile_store = MagicMock()
    profile_store.get.return_value = _profile(provider="openai", model="gpt-4.1-mini")
    monkeypatch.setattr(
        "app.utils.llm_profile_resolver.get_llm_profile_repository",
        lambda: profile_store,
    )

    data = {"llm_model": "profile:profile-under-test"}
    expand_profile_in_data(data)

    assert data["llm_model"] == "gpt-4.1-mini"
    assert data["llm_provider"]["provider"] == "openai"
