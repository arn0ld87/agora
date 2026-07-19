"""Tests für die profil-basierte LLMClient-Factory (Bug #3).

Der Legacy-Profil-Pfad muss den API-Key aus dem kanonischen
Provider-Connection-Store beziehen. Profil-Secrets dürfen nie als Fallback
verwendet werden. Die Connection-Auswahl bindet Provider-Kind und Endpunkt;
ein kindübergreifender Endpoint-Match gilt ausschließlich für ``custom``.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.contracts.llm_profile_contract import LlmProfile
from app.llm.factory import _is_local_base_url


@pytest.mark.parametrize("base_url", [None, ""])
def test_is_local_base_url_rejects_missing_values(base_url):
    assert _is_local_base_url(base_url) is False


def _profile(provider: str, base_url: str, *, api_key: str | None, model: str = "m") -> LlmProfile:
    """
    Construct a test LLM profile with the specified provider, endpoint, API key, and model.
    
    Parameters:
        provider (str): The provider identifier.
        base_url (str): The provider endpoint.
        api_key (str | None): The profile API key, if available.
        model (str): The model name.
    
    Returns:
        LlmProfile: A test profile with fixed identity fields and current UTC timestamps.
    """
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


_UNSET = object()


def _conn(
    connection_id: str,
    provider_kind: str,
    base_url: str,
    *,
    enabled: bool = True,
    auth_mode: str = "api_key",
    secret_ref=_UNSET,
):
    """Baut ein connection-artiges Objekt (nur die von der Factory gelesenen Felder)."""
    return SimpleNamespace(
        id=connection_id,
        provider_kind=provider_kind,
        base_url=base_url,
        enabled=enabled,
        auth_mode=auth_mode,
        secret_ref=connection_id if secret_ref is _UNSET else secret_ref,
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


def test_provider_kind_match_wins_over_base_url_and_ignores_store_order():
    """provider_kind- und Endpunkt-Match bleiben order-unabhängig."""
    profile = _profile(
        "google",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="stale",
    )
    kwargs = _build(
        profile,
        connections=[
            _conn("minimax", "minimax", "https://api.minimax.io/v1"),
            _conn("google", "google", "https://generativelanguage.googleapis.com/v1beta/openai"),
        ],
        secrets={"minimax": "mm-key", "google": "g-real"},
    )
    assert kwargs["api_key"] == "g-real"
    assert kwargs["route_provider_id"] == "google"


def test_non_custom_profile_never_matches_by_base_url():
    """Ein spezifischer (non-custom) Provider darf keinen fremden Secret per base_url ziehen."""
    profile = _profile("openai", "https://api.minimax.io/v1", api_key="sk-own")
    with pytest.raises(ValueError, match="ProviderConnection"):
        _build(
            profile,
            connections=[_conn("minimax", "minimax", "https://api.minimax.io/v1")],
            secrets={"minimax": "mm-key"},
        )


def test_cloud_profile_key_is_rejected_without_matching_connection():
    """Legacy-Profil-Keys dürfen den kanonischen Connection-Store nicht umgehen."""
    profile = _profile("openai", "https://api.openai.com/v1", api_key="sk-own")
    with pytest.raises(ValueError, match="ProviderConnection"):
        _build(
            profile,
            connections=[_conn("google", "google", "https://generativelanguage.googleapis.com/v1beta/openai")],
            secrets={"google": "g-key"},
        )


def test_disabled_connection_is_ignored():
    """Deaktivierte Connections dürfen ihren Secret nicht beisteuern."""
    profile = _profile("openai", "https://api.openai.com/v1", api_key="sk-own")
    with pytest.raises(ValueError, match="ProviderConnection"):
        _build(
            profile,
            connections=[_conn("openai", "openai", "https://api.openai.com/v1", enabled=False)],
            secrets={"openai": "sk-proj-echt"},
        )


def test_cloud_profile_without_any_key_raises():
    """Ensure a cloud provider profile without a connection or profile API key raises a validation error."""
    profile = _profile("openai", "https://api.openai.com/v1", api_key=None)
    with pytest.raises(ValueError, match="api_key fehlt"):
        _build(profile, connections=[], secrets={})


def test_hostname_containing_ollama_is_not_treated_as_local():
    """Nur lokale Hostnamen dürfen ohne ProviderConnection-Secret arbeiten."""
    profile = _profile("custom", "https://ollama.attacker.example/v1", api_key=None)
    with pytest.raises(ValueError, match="ProviderConnection"):
        _build(profile, connections=[], secrets={})


def test_matching_provider_kind_rejects_mismatched_profile_endpoint():
    """Ein Connection-Secret darf nie an eine abweichende Profil-URL gehen."""
    profile = _profile("openai", "https://attacker.example/v1", api_key=None)

    with pytest.raises(ValueError, match="Profil-Endpunkt.*ProviderConnection"):
        _build(
            profile,
            connections=[_conn("openai", "openai", "https://api.openai.com/v1")],
            secrets={"openai": "sk-proj-echt"},
        )


def test_local_no_auth_connection_keeps_route_without_secret():
    """Eine aufgelöste No-Auth-Connection (auth_mode='none') liefert die autoritative
    Route (connection_id + base_url) ohne Secret — kein ValueError, kein Dummy-Key-Zwang,
    und die connection_id geht NICHT verloren."""
    profile = _profile("custom", "http://localhost:11434", api_key=None)
    kwargs = _build(
        profile,
        connections=[
            _conn(
                "ollama-local",
                "ollama",
                "http://localhost:11434",
                auth_mode="none",
                secret_ref=None,
            )
        ],
        secrets={},
    )
    assert kwargs["route_provider_id"] == "ollama-local"
    assert kwargs["api_key_source"] == "local_no_auth"
    assert kwargs["base_url"] == "http://localhost:11434"


def test_api_key_connection_without_secret_raises_instead_of_dummy_key():
    """Eine api_key-Connection ohne hinterlegtes Secret darf NICHT auf den Dummy-Key
    'ollama' zurückfallen — auch nicht bei lokalem Endpunkt. Der Hostname ist kein
    Authentifizierungsmodell; maßgeblich ist der explizite auth_mode."""
    profile = _profile("custom", "http://localhost:11434", api_key=None)
    with pytest.raises(ValueError, match="api_key fehlt"):
        _build(
            profile,
            connections=[
                _conn(
                    "local-secured",
                    "ollama",
                    "http://localhost:11434",
                    auth_mode="api_key",
                    secret_ref="local-secured",
                )
            ],
            secrets={},  # secret_ref zeigt ins Leere
        )
