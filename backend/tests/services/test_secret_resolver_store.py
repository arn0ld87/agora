"""Tests für SecretResolver-Integration mit dem persistenten Store."""
from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.services import llm_provider_secrets_store as store_module
from app.services.llm_provider_secrets_store import (
    LlmProviderSecretsStore,
    reset_singleton_for_tests,
)
from app.services.secret_resolver import SecretResolver


@pytest.fixture
def configured_store(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGORA_SECRET_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    reset_singleton_for_tests()
    yield store_module.get_llm_provider_secrets_store()
    reset_singleton_for_tests()


def test_store_overrides_env(monkeypatch, configured_store):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key-should-lose")
    configured_store.upsert("openai", api_key="sk-store-wins-aaaa")

    resolver = SecretResolver()
    assert resolver.get_api_key("openai", "openai") == "sk-store-wins-aaaa"


def test_env_used_when_store_empty(monkeypatch, configured_store):
    monkeypatch.setenv("OPENAI_API_KEY", "env-fallback")
    resolver = SecretResolver()
    assert resolver.get_api_key("openai", "openai") == "env-fallback"


def test_session_overrides_store(configured_store):
    configured_store.upsert("openai", api_key="sk-store-aaaa1111")
    resolver = SecretResolver(session_api_keys={"openai": "session-wins"})
    assert resolver.get_api_key("openai", "openai") == "session-wins"


def test_google_key_from_env(monkeypatch, configured_store):
    monkeypatch.setenv("GOOGLE_API_KEY", "google-env-key")
    resolver = SecretResolver()
    assert resolver.get_api_key("google", "google") == "google-env-key"


def test_google_key_from_store_overrides_env(monkeypatch, configured_store):
    monkeypatch.setenv("GOOGLE_API_KEY", "google-env-key")
    configured_store.upsert("google", api_key="AIzaSyStoreWinsxx99")
    resolver = SecretResolver()
    assert resolver.get_api_key("google", "google") == "AIzaSyStoreWinsxx99"


def test_missing_secret_key_falls_back_to_env(monkeypatch, tmp_path):
    monkeypatch.delenv("AGORA_SECRET_KEY", raising=False)
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "env-only-key")
    reset_singleton_for_tests()
    resolver = SecretResolver()
    # Store wirft RuntimeError ohne Master-Key — Resolver soll auf env fallen
    assert resolver.get_api_key("openai", "openai") == "env-only-key"
    reset_singleton_for_tests()
