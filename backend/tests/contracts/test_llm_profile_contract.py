"""Minimal-Contract-Tests für LlmProfile (P5.1)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.llm_profile_contract import (
    LlmProfile,
    LlmProfileCreateRequest,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _valid_profile(**overrides) -> dict:
    base = dict(
        id="uuid-1",
        name="Ollama lokal",
        provider="ollama",
        base_url="http://localhost:11434/v1",
        model_name="qwen2.5:32b",
        api_key="",
        is_default=True,
        created_at=NOW,
        updated_at=NOW,
    )
    return {**base, **overrides}


def test_valid_profile():
    p = LlmProfile(**_valid_profile())
    assert p.provider == "ollama"
    assert p.is_default is True


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        LlmProfile(**_valid_profile(unknown_field="x"))


def test_invalid_provider_rejected():
    with pytest.raises(ValidationError):
        LlmProfileCreateRequest(
            name="Test",
            provider="invalid_provider",  # type: ignore
            base_url="http://x",
            model_name="m",
        )
