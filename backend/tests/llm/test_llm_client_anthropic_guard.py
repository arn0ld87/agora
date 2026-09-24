"""LLMClient transport guard for Anthropic base URLs (Issue #1284).

Second line of defense behind the routing validation in
``llm_profile_resolver.py``/``llm_routing_seed.py``: any construction path
that still ends up here with a base URL pointing at Anthropic's API (e.g. a
stage route persisted before this fix, replayed on resume without going
through the routing seed again) must fail loud instead of silently building
an OpenAI-compatible client against a host it can't actually talk to.
"""
from __future__ import annotations

import pytest

from app.llm.client import LLMClient


def _client(**overrides):
    defaults = dict(
        api_key="sk-ant-test",
        base_url="https://api.anthropic.com",
        model="claude-sonnet-5",
        use_active_config=False,
    )
    defaults.update(overrides)
    return LLMClient(**defaults)


def test_anthropic_base_url_raises_instead_of_building_openai_client():
    with pytest.raises(ValueError, match="Anthropic"):
        _client()


def test_anthropic_base_url_error_mentions_issue_and_bedrock():
    with pytest.raises(ValueError, match="#1284") as exc_info:
        _client()
    assert "Bedrock" in str(exc_info.value)


def test_anthropic_subdomain_base_url_also_rejected():
    with pytest.raises(ValueError, match="Anthropic"):
        _client(base_url="https://eu.api.anthropic.com")


def test_non_anthropic_base_url_is_unaffected():
    """Regressionsschutz: der Guard darf nur auf echte Anthropic-Hosts feuern."""
    client = _client(base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    assert client.base_url == "https://api.openai.com/v1"
