"""Contract-Tests für api_keys_contract (Slice G2)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.api_keys_contract import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyModel,
    ApiKeysListResponse,
)


def _valid_model_kwargs() -> dict:
    return {
        "id": "abc123",
        "label": "CI bot",
        "prefix": "ago_deadbeef",
        "scopes": ["read"],
        "status": "active",
        "hashed_token": "a" * 64,
        "created_at": datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc),
    }


class TestApiKeyModel:
    def test_minimal_valid_model(self) -> None:
        model = ApiKeyModel(**_valid_model_kwargs())
        assert model.label == "CI bot"
        assert model.scopes == ["read"]
        assert model.status == "active"
        assert model.last_used_at is None
        assert model.revoked_at is None

    def test_prefix_pattern_rejects_bad_prefix(self) -> None:
        kwargs = _valid_model_kwargs()
        kwargs["prefix"] = "key_deadbee"
        with pytest.raises(ValidationError):
            ApiKeyModel(**kwargs)

    def test_prefix_rejects_uppercase_hex(self) -> None:
        kwargs = _valid_model_kwargs()
        kwargs["prefix"] = "ago_DEADBEEF"
        with pytest.raises(ValidationError):
            ApiKeyModel(**kwargs)

    def test_scopes_must_not_be_empty(self) -> None:
        kwargs = _valid_model_kwargs()
        kwargs["scopes"] = []
        with pytest.raises(ValidationError):
            ApiKeyModel(**kwargs)

    def test_invalid_scope_rejected(self) -> None:
        kwargs = _valid_model_kwargs()
        kwargs["scopes"] = ["root"]
        with pytest.raises(ValidationError):
            ApiKeyModel(**kwargs)

    def test_invalid_status_rejected(self) -> None:
        kwargs = _valid_model_kwargs()
        kwargs["status"] = "expired"
        with pytest.raises(ValidationError):
            ApiKeyModel(**kwargs)

    def test_extra_field_forbidden(self) -> None:
        kwargs = _valid_model_kwargs()
        kwargs["secret"] = "leak"
        with pytest.raises(ValidationError):
            ApiKeyModel(**kwargs)

    def test_label_max_length_enforced(self) -> None:
        kwargs = _valid_model_kwargs()
        kwargs["label"] = "x" * 121
        with pytest.raises(ValidationError):
            ApiKeyModel(**kwargs)


class TestApiKeyCreateRequest:
    def test_minimal_request_valid(self) -> None:
        req = ApiKeyCreateRequest(label="CI", scopes=["read"])
        assert req.label == "CI"

    def test_empty_label_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApiKeyCreateRequest(label="", scopes=["read"])

    def test_empty_scopes_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApiKeyCreateRequest(label="CI", scopes=[])

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApiKeyCreateRequest.model_validate(
                {"label": "CI", "scopes": ["read"], "tenant": "x"}
            )

    def test_multi_scope_allowed(self) -> None:
        req = ApiKeyCreateRequest(label="CI", scopes=["read", "write", "admin"])
        assert set(req.scopes) == {"read", "write", "admin"}


class TestApiKeyCreateResponse:
    def test_token_pattern_validates_48_hex(self) -> None:
        token = "ago_" + ("a" * 48)
        resp = ApiKeyCreateResponse(
            key=ApiKeyModel(**_valid_model_kwargs()),
            token=token,
        )
        assert resp.token == token

    def test_token_with_wrong_prefix_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApiKeyCreateResponse(
                key=ApiKeyModel(**_valid_model_kwargs()),
                token="key_" + ("a" * 48),
            )

    def test_token_with_uppercase_hex_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApiKeyCreateResponse(
                key=ApiKeyModel(**_valid_model_kwargs()),
                token="ago_" + ("A" * 48),
            )

    def test_token_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApiKeyCreateResponse(
                key=ApiKeyModel(**_valid_model_kwargs()),
                token="ago_" + ("a" * 16),
            )


class TestApiKeysListResponse:
    def test_empty_list_valid(self) -> None:
        resp = ApiKeysListResponse(items=[], total=0)
        assert resp.total == 0

    def test_negative_total_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApiKeysListResponse(items=[], total=-1)

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApiKeysListResponse.model_validate(
                {"items": [], "total": 0, "cursor": "x"}
            )
