"""Tests für GitHub-Copilot-Provider (Token-Resolver + Modellliste)."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from app.services.llm_provider_registry import LlmProviderRegistry
from app.services.llm_providers.github_copilot import (
    GITHUB_COPILOT_MODELS,
    clear_token_cache,
    resolve_copilot_token,
)
from app.services.model_catalog_service import ModelCatalogService


@pytest.fixture(autouse=True)
def reset_caches():
    """Vor jedem Test Token-Cache und Catalog-Cache leeren."""
    clear_token_cache()
    ModelCatalogService._cache.clear()
    yield
    clear_token_cache()
    ModelCatalogService._cache.clear()


def test_resolve_copilot_token_returns_stdout():
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="gho_secrettoken\n", stderr="")
    with patch("app.services.llm_providers.github_copilot.shutil.which", return_value="/usr/local/bin/gh"):
        with patch("app.services.llm_providers.github_copilot.subprocess.run", return_value=completed):
            assert resolve_copilot_token() == "gho_secrettoken"


def test_resolve_copilot_token_missing_gh_returns_none():
    with patch("app.services.llm_providers.github_copilot.shutil.which", return_value=None):
        assert resolve_copilot_token() is None


def test_resolve_copilot_token_nonzero_exit_returns_none():
    completed = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="not logged in"
    )
    with patch("app.services.llm_providers.github_copilot.shutil.which", return_value="/usr/local/bin/gh"):
        with patch("app.services.llm_providers.github_copilot.subprocess.run", return_value=completed):
            assert resolve_copilot_token() is None


def test_resolve_copilot_token_timeout_returns_none():
    with patch("app.services.llm_providers.github_copilot.shutil.which", return_value="/usr/local/bin/gh"):
        with patch(
            "app.services.llm_providers.github_copilot.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=3.0),
        ):
            assert resolve_copilot_token() is None


def test_registry_contains_copilot():
    providers = {p.id: p for p in LlmProviderRegistry().get_providers()}
    assert "github_copilot" in providers
    copilot = providers["github_copilot"]
    assert copilot.type == "github_copilot"
    assert copilot.supports_models_endpoint is False
    assert set(copilot.fallback_models) == set(GITHUB_COPILOT_MODELS)


def test_catalog_returns_static_copilot_models():
    catalog = ModelCatalogService()
    models = catalog.get_models(
        "github_copilot",
        "github_copilot",
        "https://api.githubcopilot.com",
        api_key="gho_xxx",
    )
    ids = [m.id for m in models]
    assert ids == list(GITHUB_COPILOT_MODELS)
    assert all(m.source == "fallback" for m in models)
