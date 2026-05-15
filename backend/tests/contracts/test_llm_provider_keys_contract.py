"""Contract-Tests für llm_provider_keys_contract.py."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.llm_provider_keys_contract import (
    LlmProviderKeyCreateRequest,
    LlmProviderKeyEntry,
    LlmProviderKeysListResponse,
)


def test_entry_accepts_masked_value():
    entry = LlmProviderKeyEntry(
        provider_id="openai",
        masked_value="sk-...abcd",
        base_url=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert entry.provider_id == "openai"


def test_entry_rejects_plain_key_as_masked_value():
    with pytest.raises(ValidationError):
        LlmProviderKeyEntry(
            provider_id="openai",
            masked_value="sk-1234567890abcdef",  # echtes Format ohne "..."
            base_url=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )


def test_create_request_rejects_short_key():
    with pytest.raises(ValidationError):
        LlmProviderKeyCreateRequest(api_key="abc")


def test_create_request_accepts_optional_base_url():
    body = LlmProviderKeyCreateRequest(api_key="sk-abcdefgh12345", base_url="https://x.test/v1")
    assert body.base_url == "https://x.test/v1"


def test_create_request_extra_forbid():
    with pytest.raises(ValidationError):
        LlmProviderKeyCreateRequest.model_validate(
            {"api_key": "sk-abcdefgh12345", "garbage": "no"}
        )


def test_list_response_roundtrip():
    payload = LlmProviderKeysListResponse(items=[], total=0)
    assert payload.model_dump(mode="json") == {"items": [], "total": 0}
