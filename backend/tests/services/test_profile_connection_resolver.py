"""Tests für die secret-freie Bindung von Legacy-Profilen an ProviderConnections.

Fokus: mehrdeutige Endpunkte dürfen nicht still den ersten Store-Eintrag ziehen
(Secret-Roulette), sondern müssen mit einer eindeutigen Fehlermeldung abbrechen.
"""

from datetime import datetime, timezone

import pytest

from app.contracts.ai_provider_contract import ProviderConnection
from app.contracts.llm_profile_contract import LlmProfile
from app.services.profile_connection_resolver import resolve_profile_connection


def _profile(provider: str, base_url: str) -> LlmProfile:
    now = datetime.now(timezone.utc)
    return LlmProfile(
        id="prof_ambig",
        name="p",
        provider=provider,
        base_url=base_url,
        model_name="m",
        api_key=None,
        created_at=now,
        updated_at=now,
    )


def _conn(connection_id: str, base_url: str, *, kind: str = "openai_compatible") -> ProviderConnection:
    return ProviderConnection(
        id=connection_id,
        provider_kind=kind,
        display_name=connection_id,
        transport="http",
        auth_mode="none",
        base_url=base_url,
        secret_ref=None,
    )


def test_ambiguous_endpoint_is_rejected():
    """Zwei aktivierte Connections mit demselben normalisierten Endpunkt → Abbruch."""
    profile = _profile("custom", "https://api.example.com/v1")
    connections = [
        _conn("conn-a", "https://api.example.com/v1"),
        _conn("conn-b", "https://api.example.com/v1"),
    ]
    with pytest.raises(ValueError, match="mehrdeutig"):
        resolve_profile_connection(profile, connections)


def test_single_endpoint_match_resolves_deterministically():
    """Genau ein Treffer wird eindeutig aufgelöst."""
    profile = _profile("custom", "https://api.example.com/v1")
    connections = [
        _conn("conn-a", "https://api.example.com/v1"),
        _conn("conn-b", "https://other.example.com/v1"),
    ]
    resolved = resolve_profile_connection(profile, connections)
    assert resolved is not None
    assert resolved.connection.id == "conn-a"


def test_no_match_returns_none_for_custom_profile():
    """Kein passender Endpunkt bei custom-Profil → None (kein Fehler)."""
    profile = _profile("custom", "https://unmatched.example.com/v1")
    connections = [_conn("conn-a", "https://api.example.com/v1")]
    assert resolve_profile_connection(profile, connections) is None
