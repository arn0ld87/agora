"""Durchstich: aufgeloester ``claude_cli``-Token erreicht den Persona-Generator.

Der Abbruch der Persona-Phase entstand nicht im Generator, sondern eine Ebene
darueber: die Stage-Route wurde fuer jeden ``transport="cli"``-Provider ohne
Key-Aufloesung zurueckgegeben. Der Generator sah ``api_key=None`` und brach ab,
und weil derselbe Wert in ``effective_llm_runtime`` gegossen und durch alle
Prepare-Phasen gereicht wird, zog sich der Fehler ueber die Folgeschritte.

Dieser Test geht die Strecke Route → ``_resolve_llm_connection`` →
``OasisProfileGenerator`` in einem Stueck, statt sie nur an jedem Ende einzeln
zu pruefen.
"""
from __future__ import annotations

import pytest

from app.contracts.llm_routing_contract import ResolvedRoute
from app.services import prepare_llm
from app.services.oasis_profile_generator import OasisProfileGenerator


def _claude_cli_route() -> ResolvedRoute:
    return ResolvedRoute(
        stage="persona_generation",
        provider_id="claude_cli",
        model="sonnet",
        base_url_sanitized=None,
        routing_version=3,
    )


def test_resolved_claude_cli_token_reaches_generator(monkeypatch):
    monkeypatch.setattr(
        prepare_llm, "resolve_route_api_key", lambda _route: "claude-oauth-token"
    )

    api_key, base_url, provider_type = prepare_llm._resolve_llm_connection(
        _claude_cli_route()
    )

    assert api_key == "claude-oauth-token"
    assert base_url is None
    assert provider_type == "claude_cli"

    generator = OasisProfileGenerator(
        api_key=api_key,
        base_url=base_url,
        provider_type=provider_type,
        model_name="sonnet",
    )

    assert generator.api_key == "claude-oauth-token"
    assert generator.base_url is None
    assert generator.provider_type == "claude_cli"


def test_missing_claude_cli_token_fails_at_generator_with_provider_message(monkeypatch):
    """Ohne Token darf der Lauf nicht stillschweigend weiterlaufen — und die
    Meldung muss auf die Route zeigen, nicht auf ``LLM_API_KEY``."""
    monkeypatch.setattr(prepare_llm, "resolve_route_api_key", lambda _route: None)

    api_key, base_url, provider_type = prepare_llm._resolve_llm_connection(
        _claude_cli_route()
    )
    assert api_key is None

    with pytest.raises(ValueError) as excinfo:
        OasisProfileGenerator(
            api_key=api_key,
            base_url=base_url,
            provider_type=provider_type,
            model_name="sonnet",
        )

    assert "claude_cli" in str(excinfo.value)
