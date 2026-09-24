"""Regressionsschutz Issue #1284: kein stilles Anthropic->custom_openai-Rerouting.

Vor dem Fix mappte ``_PROFILE_PROVIDER_TO_RUNTIME`` ein Anthropic-Profil auf
``custom_openai`` und übernahm die Profil-Base-URL (``https://api.anthropic.com``,
ohne ``/v1``) unverändert in ``data["llm_provider"]`` — der nachgelagerte
OpenAI-kompatible Client hätte damit gegen eine Route gesprochen, die es dort
nicht gibt (403/404 zur Laufzeit statt eines klaren Fehlers hier).

Codex-Review-Finding (Runde 2): das Gate darf nicht auf dem blossen
Profil-Provider allein feuern — es muss die *effektive*, nach der
dokumentierten "Request gewinnt gegen Profil"-Regel gemergte Route pruefen,
sonst blockiert es einen gueltigen expliziten Override (z. B. auf Bedrock).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.contracts.llm_profile_contract import LlmProfile
from app.utils.llm_profile_resolver import expand_profile_in_data


def _profile(
    *, provider: str, model: str = "claude-sonnet-5", base_url: str = "https://api.anthropic.com"
) -> LlmProfile:
    now = datetime.now(UTC)
    return LlmProfile(
        id="profile-under-test",
        name="Test profile",
        provider=provider,
        base_url=base_url,
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
    profile_store.get.return_value = _profile(
        provider="openai", model="gpt-4.1-mini", base_url="https://api.openai.com/v1"
    )
    monkeypatch.setattr(
        "app.utils.llm_profile_resolver.get_llm_profile_repository",
        lambda: profile_store,
    )

    data = {"llm_model": "profile:profile-under-test"}
    expand_profile_in_data(data)

    assert data["llm_model"] == "gpt-4.1-mini"
    assert data["llm_provider"]["provider"] == "openai"


def test_anthropic_profile_with_explicit_bedrock_override_is_not_rejected(monkeypatch):
    """Codex-Finding: Request gewinnt gegen Profil (dokumentierte Vorrangregel).

    Ein Anthropic-Profil-Token kombiniert mit einem expliziten
    ``llm_provider``-Override (z. B. auf Bedrock, #1282) darf nicht schon am
    Profil selbst scheitern — die effektive, gemergte Route zeigt gar nicht
    mehr auf Anthropic."""
    profile_store = MagicMock()
    profile_store.get.return_value = _profile(provider="anthropic")
    monkeypatch.setattr(
        "app.utils.llm_profile_resolver.get_llm_profile_repository",
        lambda: profile_store,
    )

    data = {
        "llm_model": "profile:profile-under-test",
        "llm_provider": {
            "provider": "bedrock",
            "base_url": "https://bedrock-mantle.eu-central-1.api.aws/v1",
            "api_key": "bedrock-key",
        },
    }
    expand_profile_in_data(data)

    assert data["llm_provider"]["base_url"] == "https://bedrock-mantle.eu-central-1.api.aws/v1"
    assert data["llm_provider"]["provider"] == "bedrock"
    assert data["llm_provider"]["api_key"] == "bedrock-key"


def test_anthropic_profile_with_partial_override_missing_base_url_still_rejected(monkeypatch):
    """Ein Override, der nur den Provider-Namen aendert, aber die
    Anthropic-Base-URL des Profils nicht ueberschreibt, muss weiterhin
    scheitern — die effektive Route zeigt noch immer auf api.anthropic.com."""
    profile_store = MagicMock()
    profile_store.get.return_value = _profile(provider="anthropic")
    monkeypatch.setattr(
        "app.utils.llm_profile_resolver.get_llm_profile_repository",
        lambda: profile_store,
    )

    data = {
        "llm_model": "profile:profile-under-test",
        "llm_provider": {"provider": "custom_openai"},
    }
    with pytest.raises(ValueError, match="Anthropic"):
        expand_profile_in_data(data)
