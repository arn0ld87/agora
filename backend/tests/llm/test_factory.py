"""Tests für die profil-basierte LLMClient-Factory (Bug #3).

Der Legacy-Profil-Pfad muss den API-Key aus dem kanonischen
Provider-Connection-Store beziehen und den (potenziell veralteten) im Profil
gespeicherten Key nur als Fallback nutzen.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.contracts.llm_profile_contract import LlmProfile


def _profile(provider: str, base_url: str, *, api_key: str | None, model: str = "m") -> LlmProfile:
    now = datetime.now(timezone.utc)
    return LlmProfile(
        id="prof_1",
        name="p",
        provider=provider,
        base_url=base_url,
        model_name=model,
        api_key=api_key,
        created_at=now,
        updated_at=now,
    )


def _conn(connection_id: str, provider_kind: str, base_url: str, *, enabled: bool = True):
    return SimpleNamespace(
        id=connection_id,
        provider_kind=provider_kind,
        base_url=base_url,
        enabled=enabled,
        secret_ref=connection_id,
    )


def _build(profile, *, connections, secrets):
    """Ruft build_client_from_profile mit gemockten Stores + LLMClient auf.

    Gibt die kwargs zurück, mit denen ``LLMClient`` konstruiert worden wäre.
    """
    store = MagicMock()
    store.list_connections.return_value = connections
    secrets_store = MagicMock()
    secrets_store.get_plaintext.side_effect = lambda ref: secrets.get(ref)

    with patch(
        "app.services.provider_connection_store.ProviderConnectionStore",
        return_value=store,
    ), patch(
        "app.services.llm_provider_secrets_store.get_llm_provider_secrets_store",
        return_value=secrets_store,
    ), patch("app.llm.factory.LLMClient") as client_cls:
        from app.llm.factory import build_client_from_profile

        build_client_from_profile(profile)
        assert client_cls.call_count == 1
        return client_cls.call_args.kwargs


def test_prefers_connection_secret_over_stale_profile_key():
    """provider_kind-Match: veralteter Profil-Key wird durch Connection-Key ersetzt."""
    profile = _profile("openai", "https://api.openai.com/v1", api_key="agora-local-ollama-dummy")
    kwargs = _build(
        profile,
        connections=[_conn("openai", "openai", "https://api.openai.com/v1")],
        secrets={"openai": "sk-proj-echt"},
    )
    assert kwargs["api_key"] == "sk-proj-echt"
    assert kwargs["api_key_source"] == "connection_store"
    assert kwargs["route_provider_id"] == "openai"


def test_matches_connection_by_base_url_when_provider_generic():
    """provider='custom' matcht die minimax-Connection über die base_url."""
    profile = _profile("custom", "https://api.minimax.io/v1", api_key="stale")
    kwargs = _build(
        profile,
        connections=[
            _conn("openai", "openai", "https://api.openai.com/v1"),
            _conn("minimax", "minimax", "https://api.minimax.io/v1"),
        ],
        secrets={"minimax": "mm-real-key"},
    )
    assert kwargs["api_key"] == "mm-real-key"
    assert kwargs["api_key_source"] == "connection_store"
    assert kwargs["route_provider_id"] == "minimax"


def test_falls_back_to_profile_key_without_matching_connection():
    """Keine passende Connection → Profil-Key bleibt maßgeblich."""
    profile = _profile("openai", "https://api.openai.com/v1", api_key="sk-own")
    kwargs = _build(
        profile,
        connections=[_conn("google", "google", "https://generativelanguage.googleapis.com/v1beta/openai")],
        secrets={"google": "g-key"},
    )
    assert kwargs["api_key"] == "sk-own"
    assert kwargs["api_key_source"] == "profile"


def test_disabled_connection_is_ignored():
    """Deaktivierte Connections dürfen ihren Secret nicht beisteuern."""
    profile = _profile("openai", "https://api.openai.com/v1", api_key="sk-own")
    kwargs = _build(
        profile,
        connections=[_conn("openai", "openai", "https://api.openai.com/v1", enabled=False)],
        secrets={"openai": "sk-proj-echt"},
    )
    assert kwargs["api_key"] == "sk-own"
    assert kwargs["api_key_source"] == "profile"


def test_cloud_profile_without_any_key_raises():
    """Cloud-Provider ohne Connection- UND Profil-Key scheitert vor dem HTTP-Call."""
    profile = _profile("openai", "https://api.openai.com/v1", api_key=None)
    with pytest.raises(ValueError, match="api_key fehlt"):
        _build(profile, connections=[], secrets={})
