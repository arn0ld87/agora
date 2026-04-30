"""Tests for app.utils.api_errors — ApiErrorCode catalogue + json_error integration."""

from __future__ import annotations

from flask import Flask

from app.utils.api_errors import DEFAULT_MESSAGES, ApiErrorCode
from app.utils.api_responses import json_error


REQUIRED_CODES = {
    "invalid_id",
    "not_found",
    "validation_failed",
    "auth_required",
    "auth_invalid",
    "auth_forbidden",
    "rate_limited",
    "service_unavailable",
    "neo4j_unavailable",
    "llm_unavailable",
    "ontology_missing",
    "ontology_generation_failed",
    "simulation_not_prepared",
    "simulation_already_running",
    "persona_review_required",
    "upload_too_large",
    "unsupported_format",
    "timeout",
    "internal_error",
    "not_implemented",
    "bad_request",
    "method_not_allowed",
}


def _ctx():
    return Flask(__name__).test_request_context()


def test_catalogue_covers_required_codes():
    have = {c.value for c in ApiErrorCode}
    missing = REQUIRED_CODES - have
    assert not missing, f"missing codes: {sorted(missing)}"
    assert len(have) >= 20


def test_each_code_has_non_empty_default_message():
    for code in ApiErrorCode:
        msg = DEFAULT_MESSAGES.get(code)
        assert msg, f"missing default message for {code}"
        assert isinstance(msg, str)
        assert msg.strip() == msg, f"message for {code} has leading/trailing whitespace"
        assert not msg.endswith("."), f"message for {code} ends with period: {msg!r}"


def test_str_enum_compares_equal_to_literal_string():
    # Backwards-compat: existing call sites pass code="not_found" as str literal.
    assert ApiErrorCode.NOT_FOUND == "not_found"
    assert "invalid_id" == ApiErrorCode.INVALID_ID
    # Membership against a set of strings still works.
    assert ApiErrorCode.TIMEOUT in {"timeout", "other"}


def test_str_enum_value_matches_member_name_lowercased():
    for code in ApiErrorCode:
        assert code.value == code.name.lower(), (
            f"{code.name} value {code.value!r} should be lowercase of name"
        )


def test_json_error_with_api_error_code_uses_default_message_and_sets_code():
    with _ctx():
        response, status = json_error(ApiErrorCode.INVALID_ID)
        payload = response.get_json()
    assert status == 400
    assert payload == {
        "success": False,
        "error": DEFAULT_MESSAGES[ApiErrorCode.INVALID_ID],
        "code": "invalid_id",
    }


def test_json_error_with_api_error_code_respects_explicit_status():
    with _ctx():
        response, status = json_error(ApiErrorCode.NOT_FOUND, status=404)
        payload = response.get_json()
    assert status == 404
    assert payload["code"] == "not_found"
    assert payload["error"] == DEFAULT_MESSAGES[ApiErrorCode.NOT_FOUND]


def test_json_error_with_api_error_code_allows_explicit_message_override():
    with _ctx():
        response, status = json_error(
            ApiErrorCode.SIMULATION_NOT_PREPARED,
            status=409,
            message="Bitte erst Personas reviewen",
        )
        payload = response.get_json()
    assert status == 409
    assert payload["code"] == "simulation_not_prepared"
    assert payload["error"] == "Bitte erst Personas reviewen"


def test_json_error_with_string_message_is_unchanged():
    # Backwards-compat: bestehende string-basierte Aufrufe bleiben gültig.
    with _ctx():
        response, status = json_error("specific legacy message", status=400)
        payload = response.get_json()
    assert status == 400
    assert payload == {"success": False, "error": "specific legacy message"}


def test_json_error_string_with_explicit_code_is_unchanged():
    with _ctx():
        response, status = json_error("legacy", status=500, code="legacy_code")
        payload = response.get_json()
    assert status == 500
    assert payload["code"] == "legacy_code"
    assert payload["error"] == "legacy"
