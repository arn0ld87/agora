"""Tests for Config.validate() — focus on the auth-policy fail-fast (P0.1a)."""

from __future__ import annotations

import pytest

from app.config import Config


@pytest.fixture
def base_env(monkeypatch):
    """Provide the non-auth required values so validate() only fails on auth."""
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret", raising=False)
    monkeypatch.setattr(Config, "LLM_API_KEY", "ollama", raising=False)
    monkeypatch.setattr(Config, "NEO4J_URI", "bolt://localhost:7687", raising=False)
    monkeypatch.setattr(Config, "NEO4J_PASSWORD", "test-pass", raising=False)
    # Ensure embedding dim does not trip the unrelated check.
    monkeypatch.setattr(Config, "EMBEDDING_MODEL", "nomic-embed-text", raising=False)
    monkeypatch.setattr(Config, "VECTOR_DIM", 768, raising=False)
    # Strip leftover env that other tests may have set.
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("AGORA_ALLOW_ANONYMOUS", raising=False)


def test_validate_debug_mode_allows_missing_auth_token(monkeypatch, base_env):
    monkeypatch.setattr(Config, "DEBUG", True, raising=False)

    errors = Config.validate()

    assert not any("AGORA_AUTH_TOKEN" in e for e in errors)


def test_validate_non_debug_without_token_fails(monkeypatch, base_env):
    monkeypatch.setattr(Config, "DEBUG", False, raising=False)

    errors = Config.validate()

    assert any("AGORA_AUTH_TOKEN missing in non-debug mode" in e for e in errors)


def test_validate_non_debug_with_token_passes(monkeypatch, base_env):
    monkeypatch.setattr(Config, "DEBUG", False, raising=False)
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "deploy-secret")

    errors = Config.validate()

    assert not any("AGORA_AUTH_TOKEN" in e for e in errors)


def test_validate_non_debug_with_allow_anonymous_passes(monkeypatch, base_env):
    monkeypatch.setattr(Config, "DEBUG", False, raising=False)
    monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", "true")

    errors = Config.validate()

    assert not any("AGORA_AUTH_TOKEN" in e for e in errors)


def test_validate_non_debug_allow_anonymous_other_truthy_values(monkeypatch, base_env):
    monkeypatch.setattr(Config, "DEBUG", False, raising=False)
    for value in ("1", "yes", "TRUE", "Yes"):
        monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", value)
        errors = Config.validate()
        assert not any("AGORA_AUTH_TOKEN" in e for e in errors), value
