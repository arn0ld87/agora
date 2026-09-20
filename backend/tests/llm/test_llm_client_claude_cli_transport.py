"""LLMClient._resolve_transport wiring for the claude_cli provider.

Mirrors the (untested) codex_cli wiring in the same method — this file only
covers the claude_cli branch, which is the part this change adds.
"""
from __future__ import annotations

import pytest

from app.contracts.provider_types import PROVIDER_CLAUDE_CLI
from app.llm.client import LLMClient
from app.llm.providers.claude_cli import ClaudeCliClient


def _client(**overrides):
    defaults = dict(
        api_key="tok_abc",
        model="sonnet",
        use_active_config=False,
        provider_type=PROVIDER_CLAUDE_CLI,
    )
    defaults.update(overrides)
    return LLMClient(**defaults)


def test_claude_cli_active_flag_set_from_provider_type():
    client = _client()
    assert client._claude_cli_active is True
    assert client._codex_cli_active is False


def test_claude_cli_has_no_base_url():
    client = _client()
    assert client.base_url is None


def test_claude_cli_client_is_claude_cli_client_with_resolved_token():
    client = _client(api_key="tok_secret")
    assert isinstance(client.client, ClaudeCliClient)
    assert client.client._oauth_token == "tok_secret"


def test_claude_cli_missing_api_key_raises():
    with pytest.raises(ValueError, match="LLM_API_KEY not configured"):
        _client(api_key=None, allow_api_key_fallback=False)


def test_claude_cli_is_ollama_short_circuits_false():
    assert _client()._is_ollama() is False


def test_claude_cli_is_minimax_short_circuits_false():
    assert _client()._is_minimax() is False


def test_claude_cli_detect_provider_returns_unknown():
    assert _client()._detect_provider() == "unknown"
