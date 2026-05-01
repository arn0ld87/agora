"""Slice 1 (PR1) — Placeholder-Reject-Coverage für Config.validate().

`backend/tests/test_config_validate.py` deckt die Auth-Token-Pflicht aus
P0.1a ab. Slice 1 erweitert `validate()` um harte Rejects für die
Platzhalter-Strings aus `.env.example` (SECRET_KEY: `change-me*`,
`agora`, `password`; NEO4J_PASSWORD: `change-me`, `agora`, `neo4j`,
`password`). Diese Tests sichern den neuen Pfad gegen Regression.
"""

from __future__ import annotations

import logging

import pytest

from app.config import (
    Config,
    NEO4J_PASSWORD_PLACEHOLDERS,
    SECRET_KEY_PLACEHOLDERS,
)


@pytest.fixture
def agora_config_log():
    """Hängt einen ListHandler an `agora.config` an (Logger hat propagate=False)."""
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger('agora.config')
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)


@pytest.fixture
def base_env(monkeypatch):
    """Defaults so validate() only fails on the security policy, nothing else."""
    monkeypatch.setattr(Config, "SECRET_KEY", "real-secret-from-env", raising=False)
    monkeypatch.setattr(Config, "LLM_API_KEY", "ollama", raising=False)
    monkeypatch.setattr(Config, "NEO4J_URI", "bolt://localhost:7687", raising=False)
    monkeypatch.setattr(Config, "NEO4J_PASSWORD", "real-neo4j-password", raising=False)
    monkeypatch.setattr(Config, "EMBEDDING_MODEL", "nomic-embed-text", raising=False)
    monkeypatch.setattr(Config, "VECTOR_DIM", 768, raising=False)
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("AGORA_ALLOW_ANONYMOUS", raising=False)


def test_validate_non_debug_rejects_missing_token(monkeypatch, base_env):
    """Empty AGORA_AUTH_TOKEN outside debug → fail-fast (already covered, sanity)."""
    monkeypatch.setattr(Config, "DEBUG", False, raising=False)

    errors = Config.validate()

    assert any("AGORA_AUTH_TOKEN missing in non-debug mode" in e for e in errors)


@pytest.mark.parametrize("placeholder", sorted(SECRET_KEY_PLACEHOLDERS))
def test_validate_non_debug_rejects_placeholder_secret_key(
    monkeypatch, base_env, placeholder
):
    """SECRET_KEY = jeder bekannte Platzhalter im Nicht-Debug → ConfigError."""
    monkeypatch.setattr(Config, "DEBUG", False, raising=False)
    monkeypatch.setattr(Config, "SECRET_KEY", placeholder, raising=False)
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "deploy-token")

    errors = Config.validate()

    assert any("SECRET_KEY uses a known placeholder" in e for e in errors), (
        f"Placeholder '{placeholder}' wurde nicht abgewiesen: {errors}"
    )


@pytest.mark.parametrize("placeholder", sorted(NEO4J_PASSWORD_PLACEHOLDERS))
def test_validate_non_debug_rejects_placeholder_neo4j_password(
    monkeypatch, base_env, placeholder
):
    """NEO4J_PASSWORD = jeder bekannte Platzhalter im Nicht-Debug → ConfigError."""
    monkeypatch.setattr(Config, "DEBUG", False, raising=False)
    monkeypatch.setattr(Config, "NEO4J_PASSWORD", placeholder, raising=False)
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "deploy-token")

    errors = Config.validate()

    assert any("NEO4J_PASSWORD uses a known placeholder" in e for e in errors), (
        f"Placeholder '{placeholder}' wurde nicht abgewiesen: {errors}"
    )


def test_validate_debug_allows_placeholder_secret_with_warning(
    monkeypatch, base_env, agora_config_log
):
    """Debug-Modus darf Platzhalter behalten, soll aber laut warnen."""
    monkeypatch.setattr(Config, "DEBUG", True, raising=False)
    monkeypatch.setattr(Config, "SECRET_KEY", "change-me", raising=False)

    errors = Config.validate()

    assert not any("SECRET_KEY" in e for e in errors)
    messages = [record.getMessage() for record in agora_config_log]
    assert any(
        "SECRET_KEY uses a placeholder value" in msg for msg in messages
    ), messages


def test_validate_non_debug_with_real_values_passes(monkeypatch, base_env):
    """Echte Werte + Token → validate() liefert keine Security-Errors."""
    monkeypatch.setattr(Config, "DEBUG", False, raising=False)
    monkeypatch.setattr(Config, "SECRET_KEY", "real-deploy-secret", raising=False)
    monkeypatch.setattr(Config, "NEO4J_PASSWORD", "real-neo4j-pass", raising=False)
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "deploy-token")

    errors = Config.validate()

    assert not any("SECRET_KEY" in e for e in errors)
    assert not any("NEO4J_PASSWORD" in e for e in errors)
    assert not any("AGORA_AUTH_TOKEN" in e for e in errors)


def test_validate_case_insensitive_placeholder_match(monkeypatch, base_env):
    """Großbuchstaben-Variante eines Platzhalters wird ebenfalls abgewiesen."""
    monkeypatch.setattr(Config, "DEBUG", False, raising=False)
    monkeypatch.setattr(Config, "SECRET_KEY", "CHANGE-ME", raising=False)
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "deploy-token")

    errors = Config.validate()

    assert any("SECRET_KEY uses a known placeholder" in e for e in errors)
