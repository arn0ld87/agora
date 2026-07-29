"""
Tests fuer Issue #778 — Key-Routing-Divergenz in Sim-Prep-Generatoren.

Invariante: API-Key und Base-URL muessen aus derselben Quelle stammen. Der
`.env`-Fallback `Config.LLM_API_KEY` darf ausschliesslich dann greifen, wenn
auch die effektive Base-URL aus `Config.LLM_BASE_URL` stammt. Andernfalls
bleibt `api_key` `None` und der harte `ValueError("LLM_API_KEY not
configured")` greift — statt eines stillen Fremd-Provider/.env-Key-Mismatch
(404/401).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.config import Config
from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.simulation_config_generator import SimulationConfigGenerator

FOREIGN_BASE_URL = "https://foreign-provider.example.com/v1"
STORE_KEY = "store-key-fixture"
ENV_KEY = "env-key-fixture"


GENERATOR_CLASSES = (SimulationConfigGenerator, OasisProfileGenerator)


def _patch_openai_target(generator_cls: type) -> str:
    if generator_cls is SimulationConfigGenerator:
        return "app.llm.client.OpenAI"
    return "app.services.oasis_profile_generator.OpenAI"


@pytest.mark.parametrize("generator_cls", GENERATOR_CLASSES)
def test_store_key_and_foreign_base_url_take_precedence(
    monkeypatch: pytest.MonkeyPatch, generator_cls: type
) -> None:
    """Aufgeloester Store-Key + fremde Base-URL -> Store-Werte gewinnen, kein .env-Mix."""
    monkeypatch.setattr(Config, "LLM_API_KEY", ENV_KEY)
    monkeypatch.setattr(Config, "LLM_BASE_URL", "http://localhost:11434/v1")

    with patch(_patch_openai_target(generator_cls)):
        gen = generator_cls(api_key=STORE_KEY, base_url=FOREIGN_BASE_URL)

    assert gen.api_key == STORE_KEY
    assert gen.api_key != ENV_KEY
    assert gen.base_url == FOREIGN_BASE_URL


@pytest.mark.parametrize("generator_cls", GENERATOR_CLASSES)
def test_no_key_with_foreign_base_url_raises(
    monkeypatch: pytest.MonkeyPatch, generator_cls: type
) -> None:
    """Der Bug: kein Key + fremde Base-URL darf NICHT still auf .env-Key zurueckfallen."""
    monkeypatch.setattr(Config, "LLM_API_KEY", ENV_KEY)
    monkeypatch.setattr(Config, "LLM_BASE_URL", "http://localhost:11434/v1")

    with patch(_patch_openai_target(generator_cls)):
        with pytest.raises(ValueError, match="LLM_API_KEY not configured"):
            generator_cls(api_key=None, base_url=FOREIGN_BASE_URL)


@pytest.mark.parametrize("generator_cls", GENERATOR_CLASSES)
def test_no_key_no_base_url_uses_env_pair(
    monkeypatch: pytest.MonkeyPatch, generator_cls: type
) -> None:
    """Legacy-/Lokalpfad: kein Key, keine Base-URL -> .env-Paar greift wie bisher."""
    monkeypatch.setattr(Config, "LLM_API_KEY", ENV_KEY)
    monkeypatch.setattr(Config, "LLM_BASE_URL", "http://localhost:11434/v1")

    with patch(_patch_openai_target(generator_cls)):
        gen = generator_cls(api_key=None, base_url=None)

    assert gen.api_key == ENV_KEY
    assert gen.base_url == Config.LLM_BASE_URL


@pytest.mark.parametrize("generator_cls", GENERATOR_CLASSES)
def test_no_key_explicit_env_base_url_uses_env_key(
    monkeypatch: pytest.MonkeyPatch, generator_cls: type
) -> None:
    """Kein Key, Base-URL explizit gleich Config.LLM_BASE_URL -> .env-Key greift (gleiche Quelle)."""
    monkeypatch.setattr(Config, "LLM_API_KEY", ENV_KEY)
    monkeypatch.setattr(Config, "LLM_BASE_URL", "http://localhost:11434/v1")

    with patch(_patch_openai_target(generator_cls)):
        gen = generator_cls(api_key=None, base_url=Config.LLM_BASE_URL)

    assert gen.api_key == ENV_KEY
    assert gen.base_url == Config.LLM_BASE_URL
